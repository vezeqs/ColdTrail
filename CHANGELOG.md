# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Webhook credentials passed as `--alert-target` are no longer written to the
  audit log.
- `watch` rejects a blank target with a usage error instead of a traceback.
- `posts` and `harvest` reject a non-ISO `--since` instead of silently dropping
  the filter.
- `posts --no-deleted` now actually hides tombstones.
- `Store.attachments(limit=None)` returns every row instead of raising
  `sqlite3.IntegrityError`.
- `evidence export` reports a corrupt digest as a one-line error with exit 2.

## [0.1.0] - 2026-11-01

Initial release.

### Added

- **Pivot** across 482 sources (50 curated + 432 declarative sites), with
  handle/email variants, multi-hop expansion, and per-source failure isolation.
- **Harvest** of profiles, paginated posts, follow graphs, incremental cursors,
  and profile-change history into SQLite (schema v7, FTS5 search).
- **Correlation** with additive evidence scoring, calibrated confidence,
  Jaro-Winkler handle similarity, and identity clusters.
- **Investigation** helpers: domain, IP, phone, RDAP, DNS, crt.sh, TLS, BGP/ASN,
  Wayback, search dorks, and breach metadata (HIBP, HudsonRock, LeakCheck,
  Pwned Passwords).
- **Evidence** stored content-addressed (SHA-256), with case dossiers, tags,
  notes, attachments, and an audit log.
- **Exports**: JSON, JSONL, CSV, GraphML, GEXF, DOT, HTML, Markdown, STIX 2.1,
  SARIF 2.1.0, and Maltego, with redaction and encryption.
- **Interfaces**: Typer CLI, Textual TUI, and a local FastAPI web UI with SSE
  job streaming.
- **Automation**: `batch --jobs`, `watch` monitoring with alerts, `recluster`,
  and `diff` between runs.

### Security

- Untrusted text is escaped per output context (HTML, XML attributes, Markdown
  tables, DOT, URLs, CSV cells).
- Exports are created `0600` by `os.open`; evidence blobs are validated as
  64 lowercase hex characters before any path join.
- Privacy defaults: no telemetry, opt-in raw capture, owner-only files
  (`0600`/`0700`), Tor via `socks5h`, hashed email targets, and a Host/Origin
  gated web UI.
