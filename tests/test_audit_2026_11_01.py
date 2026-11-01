"""Regression tests for the 2026-11-01 audit findings.

Every test here failed before its fix; each one names the finding it guards in
``AUDIT.md``.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from coldtrail.cli import app
from coldtrail.cli._app import _redact_argv
from coldtrail.models import Post
from coldtrail.store import Store

runner = CliRunner()


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "t.db") as db:
        yield db


# -- F1: webhook credentials must not reach the audit log -------------------


def test_redact_argv_hides_alert_target():
    argv = [
        "watch",
        "alice",
        "--alert",
        "discord",
        "--alert-target",
        "https://discord.com/api/webhooks/123/SUPERSECRET",
    ]
    redacted = _redact_argv(argv)
    assert "SUPERSECRET" not in " ".join(redacted)
    assert "--alert-target" in redacted
    assert redacted[redacted.index("--alert-target") + 1] == "[redacted]"


def test_redact_argv_hides_alert_target_in_equals_form():
    redacted = _redact_argv(["--alert-target=https://hooks.slack.com/services/T/B/SECRET"])
    assert redacted == ["--alert-target=[redacted]"]


# -- F2: watch must reject a blank target like every other command ----------


def test_watch_rejects_blank_target(tmp_path):
    result = runner.invoke(app, ["--db", str(tmp_path / "w.db"), "watch", "   "])
    assert result.exit_code == 2, result.output
    assert "non-empty" in result.output
    assert "Traceback" not in result.output


# -- F3: an unparseable --since must be rejected, not silently dropped ------


def test_posts_rejects_invalid_since(tmp_path):
    result = runner.invoke(app, ["--db", str(tmp_path / "p.db"), "posts", "--since", "garbage"])
    assert result.exit_code == 2, result.output
    assert "ISO" in result.output


def test_harvest_rejects_invalid_since(tmp_path):
    result = runner.invoke(
        app,
        ["--db", str(tmp_path / "h.db"), "harvest", "alice", "-s", "github", "--since", "garbage"],
    )
    assert result.exit_code == 2, result.output
    assert "ISO" in result.output


# -- F4: --no-deleted must actually hide tombstones -------------------------


def test_posts_no_deleted_hides_tombstones(store):
    run_id = store.start_run("pivot", "alice")
    store.save_posts(
        run_id,
        [
            Post(source="github", username="alice", post_id="1", url="u", text="kept"),
            Post(source="github", username="alice", post_id="2", url="u", text="gone"),
        ],
    )
    with store.conn:
        store.conn.execute(
            "UPDATE posts SET deleted_at = '2026-01-01T00:00:00Z' WHERE post_id = '2'"
        )

    result = runner.invoke(app, ["--db", str(store.path), "posts", "--no-deleted", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert [row["post_id"] for row in rows] == ["1"]

    with_deleted = runner.invoke(app, ["--db", str(store.path), "posts", "--json"])
    assert with_deleted.exit_code == 0, with_deleted.output
    assert len(json.loads(with_deleted.output)) == 2


# -- F5: attachments(limit=None) must mean "all rows" -----------------------


def test_attachments_limit_none_returns_all(store):
    for index in range(3):
        store.add_attachment(
            run_id=None,
            target_type="run",
            target=str(index),
            sha256=f"{index:064x}",
            filename=f"{index}.txt",
            media_type="text/plain",
            size=1,
            note=None,
        )
    assert len(store.attachments(limit=None)) == 3


# -- F6: a corrupt digest is an error message, not a traceback --------------


def test_evidence_export_reports_bad_digest_cleanly(store, tmp_path):
    attachment_id = store.add_attachment(
        run_id=None,
        target_type="run",
        target="1",
        sha256="../../../../etc/passwd",
        filename="x",
        media_type="text/plain",
        size=1,
        note=None,
    )
    result = runner.invoke(
        app,
        [
            "--db",
            str(store.path),
            "evidence",
            "export",
            str(attachment_id),
            "--out",
            str(tmp_path / "out.bin"),
        ],
    )
    assert result.exit_code == 2, result.output
    assert "invalid evidence digest" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "out.bin").exists()
