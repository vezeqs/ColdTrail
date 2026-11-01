# ColdTrail audit — 2026-11-01

Baseline: `master` @ `50e7ce6`, 620 tests, ruff/mypy/bandit clean.
Scope: logic and functionality — error paths, state, parsing, dead flags, and the
claims in README/AGENTS.
Method: baseline run, targeted repro scripts against temp databases, exhaustive
CLI surface sweep (61 leaf commands), hostile-input probes of every exporter, and
property checks on correlation (`score_pair` symmetry, cluster determinism).

Six findings. Every one below was reproduced; the command and the observed output
are recorded verbatim.

---

## F1 — Webhook credentials are written to the audit log (High)

**Claim:** AGENTS.md invariant 7: "Secrets never reach output. `doctor`/`config`
redact proxy userinfo and key values; `_redact_argv` covers `--token`,
`--passphrase`, `--api-key`, `--secret`, `--key`, and `--proxy`." README: "no
telemetry … owner-only files".

**Evidence:**

```console
$ coldtrail --db /tmp/f1/t.db watch "   " --alert discord \
    --alert-target "https://discord.com/api/webhooks/123456789/SUPERSECRETTOKEN"
$ sqlite3 /tmp/f1/t.db 'SELECT args_json FROM audit ORDER BY id DESC LIMIT 1'
{"argv": ["--db", "/tmp/f1/t.db", "watch", "   ", "--alert", "discord",
 "--alert-target", "https://discord.com/api/webhooks/123456789/SUPERSECRETTOKEN"]}
```

`secret present: True`

**Cause:** `SENSITIVE_FLAGS` in `cli/_app.py` does not include `--alert-target`.
Discord and Slack webhook URLs *are* credentials: anyone holding the URL can post
to the channel. The value is persisted in `audit.args_json` and printed by
`coldtrail audit`.

**Fix:** add `--alert-target` to `SENSITIVE_FLAGS`.

**Status:** fixed, tests `test_audit_log_redacts_alert_target` and
`test_redact_argv_hides_alert_target`.

---

## F2 — `watch` with a blank target prints a traceback (Medium)

**Claim:** AGENTS.md invariant: "Empty targets: `Form(min_length=1)` accepts
`" "`. Validate after `.strip()` in `pivot()`, `harvest()`, `collect_follows()`,
and web routes." The same rule is not applied to `watch`.

**Evidence:**

```console
$ coldtrail --db /tmp/audit/t.db watch "   "
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ .../src/coldtrail/cli/collect.py:544 in watch                                │
╰──────────────────────────────────────────────────────────────────────────────╯
ValueError: target must be a non-empty username or email
$ echo $?
1
```

`pivot`, `harvest`, and `graph` all reject the same input cleanly with exit 2:

```console
$ coldtrail pivot "   " ; echo $?
╭─ Error ──────────────────────────────────────╮
│ Invalid value: target must be a non-empty username or email │
╰──────────────────────────────────────────────╯
2
```

**Cause:** `watch` has no argument validator; the `ValueError` raised inside
`pivot()` escapes the `run_cli` wrapper, which only converts `ConfigError` and
`StoreError`.

**Fix:** validate the target in the `watch` command the same way `pivot` does.

**Status:** fixed, test `test_watch_rejects_blank_target`.

---

## F3 — An unparseable `--since` is silently ignored (Medium)

**Claim:** `--since` is documented as an ISO lower bound
(`coldtrail posts --since …`, `coldtrail harvest --since …`).

**Evidence:**

```console
$ coldtrail --db /tmp/ro/t.db posts --since garbage
┃ Run ┃ Source ┃ When ┃ Text ┃ URL ┃
└─────┴────────┴──────┴──────┴─────┘
$ echo $?
0

$ coldtrail --db /tmp/ro/t.db timeline --since garbage
╭─ Error ──────────────────────────────────────────────────────────────╮
│ Invalid value: --since must be an ISO timestamp, got 'garbage'       │
╰──────────────────────────────────────────────────────────────────────╯
$ echo $?
2
```

`harvest alice -s github --since garbage` likewise runs to completion and saves a
run: `utils.is_after()` returns `True` when either side fails to parse, so the
filter is dropped rather than reported.

**Cause:** `Store.posts()` falls back to a lexicographic `created_at >= ?`
comparison when `epoch_seconds()` returns `None`; the `posts` and `harvest`
commands never validate the option, unlike `timeline`.

**Fix:** reject non-ISO values in both commands, matching `timeline`.

**Status:** fixed, tests `test_posts_rejects_invalid_since` and
`test_harvest_rejects_invalid_since`.

---

## F4 — `posts --deleted` is a no-op flag (Low)

**Claim:** `coldtrail posts --help` advertises `--deleted  Include tombstones
[default: True]`.

**Evidence:**

```console
$ coldtrail --db /tmp/ro/t.db posts --json | head -c 60
[ { "id": 1, …              # identical output with and without --deleted
$ coldtrail posts --help | grep deleted
│ --deleted    Include tombstones [default: True] │
```

**Cause:** the option is declared as `typer.Option("--deleted", …) = True`, with
no `--no-deleted` counterpart, so it can only ever be `True` and tombstones can
never be excluded.

**Fix:** declare `--deleted/--no-deleted` with the existing default of `True`, so
the documented behaviour is preserved and the flag does something.

**Status:** fixed, test `test_posts_no_deleted_hides_tombstones`.

---

## F5 — `Store.attachments(limit=None)` raises instead of meaning "no limit" (Low)

**Claim:** every sibling query accepts `limit=None` to mean "no limit":
`profiles(run_id=…, limit=None)`, `posts(…, limit=None)`, `links(…, limit=None)`,
`entities(…, limit=None)`, `clusters(…, limit=None)`.

**Evidence:**

```console
$ python -c "from coldtrail.store import Store; Store('/tmp/prune/t.db').attachments(limit=None)"
Traceback (most recent call last):
  ...
sqlite3.IntegrityError: datatype mismatch
```

**Cause:** `attachments()` always binds `LIMIT ? OFFSET ?`; SQLite rejects a
`NULL` limit. The method is the only one in the query surface that cannot express
"all rows", so a caller following the established convention crashes.

**Fix:** accept `int | None` and omit the LIMIT clause when it is `None`.

**Status:** fixed, test `test_attachments_limit_none_returns_all`.

---

## F6 — `evidence export` on a non-hex digest raises a raw traceback (Medium)

**Claim:** the CLI wrapper turns configuration and storage failures into one
actionable line with exit 2 (`cli:main` docstring in AGENTS.md).

**Evidence:** with a hand-edited `attachments.sha256` of `../../../../etc/passwd`
(the traversal is correctly *rejected* — the error path is what fails):

```console
$ coldtrail --db /tmp/crit3/t.db evidence export 2 --out /tmp/crit3/leak.bin
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ .../src/coldtrail/cli/evidence.py:114 in evidence_export                     │
│ .../src/coldtrail/evidence.py:157 in evidence_path                           │
│ ❱ raise ValueError(f"invalid evidence digest: {sha256!r}")                   │
╰──────────────────────────────────────────────────────────────────────────────╯
ValueError: invalid evidence digest: '../../../../etc/passwd'
$ echo $?
1
```

**Cause:** `evidence_path()` raises `ValueError`, which `run_cli` does not
convert, so a corrupt database row produces a traceback.

**Fix:** report the bad digest as a one-line error and exit 2, like every other
storage failure.

**Status:** fixed, test `test_evidence_export_reports_bad_digest_cleanly`.

---

## Checked and found sound

Recorded so the next audit does not redo the work:

- **Source counts:** 482 = 50 curated + 432 declarative, matching README.
- **Correlation:** `score_pair(a, b) == score_pair(b, a)` over 780 random pairs;
  `build_clusters` is order-independent.
- **Timeline ordering:** mixed UTC offsets sort by instant in `store.timeline`,
  `report.to_html`, and `report.to_markdown`.
- **Exporters:** hostile input (`<script>`, `javascript:` URLs, `=HYPERLINK()`)
  is neutralised in HTML, CSV, Markdown, DOT; GraphML and GEXF stay valid XML.
- **Evidence:** tampering is detected (`hash mismatch`); path traversal is
  rejected (`invalid digest`).
- **Redaction:** `export --redact` covers run target, checks, profiles, posts,
  entities, links, clusters, and edges.
- **Web UI:** foreign `Host` and cross-site `Origin` are 403; blank form target is
  400; unknown job/run/attachment is 404.
- **FTS:** quotes, `*`, parentheses, `C++`, and emoji do not crash or over-match.
- **Tool runner:** option-like targets (`--help`, `-rf`) are rejected.
- **CLI surface:** all 61 leaf commands respond to `--help` with exit 0.
