---
name: bb-cli
owner: framework
description: "Read-only access to bb.cuhk.edu.cn (CUHK-SZ Blackboard) via the connectors/bb-cli CLI: pull courses, assignments, grades, announcements, course files, and my submissions on demand and relay them. Query-and-answer only; writes nothing to wiki. Triggers on: bb-cli, bb, blackboard, bb.cuhk.edu.cn, fetch from bb, check bb courses, check bb assignments, check bb grades, check bb announcements."
---

# bb-cli: Blackboard Read-Only Connector

Pull information from bb.cuhk.edu.cn via `connectors/bb-cli/` (a purely read-only CLI data plane) and relay it to the user. Queries answer directly: nothing is written to wiki and no data area is modified.

## Scope

Read: Blackboard (courses / assignments / grades / announcements / course files / my submissions / members)
Write: none (read-only by design; submitting assignments or posting announcements is deliberately not provided — would require explicit user instruction and separate design)

## Prerequisites (install / auth)

1. Install (if missing): `cd connectors/bb-cli` and install editable with the host's Python package manager (deps: curl_cffi + beautifulsoup4 only; e.g. a venv + its pip on dev desktops, `uv venv .venv && uv pip install -e .` on PEP 668 hosts — instance-level environment declarations in AGENTS.md take precedence)
   - If `bb-cli` is not on PATH, invoke the installed module with that environment's Python: `python -m bbcli --help` (replace `python` with the actual interpreter path). For a local venv use `./.venv/Scripts/python.exe` on Windows, `./.venv/bin/python` on macOS/Linux; no activation or global PATH edit is needed.
   - A successful install is not proof that the console script is discoverable. Check `--help` before authentication; if the module is missing, verify the interpreter with `python -m pip show bbcli`. See this connector's README Installation section for complete Windows/Git Bash, Unix, and `--user` recovery steps.
2. Login: `bb-cli login --username <student-id> --no-store` (password via the `BB_CLI_PASSWORD` env var or interactive prompt; `--no-store` keeps it off disk; session cookie lives in `~/.bb-cli/session.json`)
3. Self-check: `bb-cli status --format text` → `authenticated=yes` means ready; on 401 run `login` again

## Steps

1. `bb-cli status` to confirm the session
2. Pick a command per the need (see Command cheat sheet); `--format text` prints one human-readable line per row, JSON keeps raw API values
3. Relay the results to the user (language: see Language below)

## Command cheat sheet

| Need | Command |
|---|---|
| My courses | `bb-cli courses [--term <term-name-substring>] --format text` |
| Terms | `bb-cli terms --format text` (locate the current term name first, then filter with it, e.g. `--term 2610UG`) |
| Assignments + status | `bb-cli assignments <course> --format json` (due / possible / status / score) |
| Gradebook | `bb-cli grades [<course>] [--due-only]` |
| Upcoming deadlines (one course / all) | `bb-cli dues [--course C] [--from D] [--to D] --format text` |
| Announcements | `bb-cli announcements [--course <substring>] [--limit N]` |
| Course files / download | `bb-cli files <course>` / `bb-cli fetch <course> [-o DIR] [--dest DIR] [--exclude-mime video/,audio/] [--exclude-ext ext,…] [--no-media-filter] [--max-size MB] [--refresh]` |
| My submissions | `bb-cli submission <course> [--download] [--dest DIR]` |
| Identity | `bb-cli whoami` |

The course argument accepts a course id (`_18027_1`), a course code, or a name substring (`AIE3905`); on ambiguity the CLI lists the candidates.

## Status values

`status` from `assignments` / `grades`: `Graded` = graded (with score), `NeedsGrading` = submitted and awaiting grade, empty/`None` = not submitted or no data.

## Timestamps

`--format text` display and `--from` / `--to` / `--since` filtering use the local timezone; JSON output keeps the raw API value (UTC ISO `…Z`).

## Media & refresh

`fetch` skips common media extensions by default (`mts/mpg/mpeg/avi/mkv/wav/mp4/mov/mp3/m4a/webm`); `--no-media-filter` restores "download everything". `--exclude-mime` / `--exclude-ext` add to the filter (skipped items are reported in the `skipped` list — record them as pointer entries, do not download), `--max-size MB` is a download-time breaker, and `--refresh` re-pulls existing files: identical content is reported `same` and kept, changed content lands as a new file suffixed with the first 8 hex of its content hash (the old file is kept as revision history, reported in `updated`). `--dest DIR` points the download at an exact target directory (no course-name subfolder appended).

## Known limits

- 404 under student sessions: `gradebook/attempts` (flat list), `discussion/forums`, `users/me/memberships`, `tasks`, `gradebook/grades`
- Classic (JSP) courses only; Ultra unverified
- Write operations (submitting / posting) deliberately not provided
- `connectors/bb-cli/README.md` is the single source of truth for the full table

## Prohibitions

- Never perform write operations (submitting assignments / posting announcements); if ever needed, requires explicit user instruction and separate design
- Student ids / passwords never enter the repo; never echo the password; credentials live only in `~/.bb-cli/`

## Language

Follow the upper-layer requirements and the conversation context. Keep course names, course codes, file names, and paths verbatim.
