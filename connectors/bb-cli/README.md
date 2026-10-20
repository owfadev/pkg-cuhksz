# bb-cli — CUHK-SZ Blackboard Read-Only CLI Connector

A command-line connector for `bb.cuhk.edu.cn` (Blackboard Learn Classic 3900.39): **a purely read-only data plane — no agent logic, no MCP, no monitoring** — serving as a fact interface for upper layers (wiki domain plugins / humans / scripts). The technical route follows bbwatch's empirical findings (curl_cffi fingerprint + ADFS OAuth2 + the official REST API); login details were rewritten from live reverse engineering on 2026-09-29.

## Installation

Use the instance's declared Python environment when one exists. Otherwise, from `connectors/bb-cli`, choose one of these isolated environments; activation and global PATH changes are unnecessary.

Windows (PowerShell or Git Bash):

```text
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m bbcli --help
```

macOS / Linux:

```text
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m bbcli --help
```

On hosts using uv, `uv venv .venv` and `uv pip install --python .venv -e .` are an alternative; use the corresponding environment's Python path above to run the module. No `--break-system-packages` is needed for a virtual environment.

If an earlier `pip --user` installation succeeded but `bb-cli` is not found, run `python -m bbcli --help` using the **same Python that installed it**. This bypasses the missing console-script PATH entry. `No module named bbcli` means that interpreter cannot see the installed package; check `python -m pip show bbcli` and use the intended environment instead of reinstalling globally. For the default user-install script directory, use:

```text
python -c "import sysconfig; print(sysconfig.get_path('scripts', scheme=sysconfig.get_preferred_scheme('user')))"
```

The user scheme matters: an unqualified `get_path('scripts')` may report the base interpreter's script directory. Custom install prefixes can differ. Prefer the module invocation over changing persistent PATH settings. `--help` checks the launcher without logging in; run authentication only when needed for the user's task.

Dependencies are only `curl_cffi` (Chrome TLS fingerprint — the site rejects plain OpenSSL handshakes) and `beautifulsoup4`.

## Authentication

- `bb-cli login`: interactively enter your student id and password (the password is not echoed). The student id automatically gets the `cuhksz\` domain prefix appended (matching the login page's custom JS); input already containing `@` or `\` is left unchanged.
- Credentials and sessions live only in the local user directory `~/.bb-cli/` (`BB_CLI_HOME` can override): `config.json` (credentials, permission 0600) + `session.json` (cookie jar). **Never written into any repository.**
- Off-disk option: `--password-env VAR` (or the `BB_CLI_PASSWORD` environment variable) + `--no-store`.
- An expired session automatically re-logs in once and replays the request (triggered by 401).

**Multiple accounts & the default account** (0.2.0): credentials are stored per account (`login --account <name>`, default name = the username) as `{"accounts": {name: {username, password}}, "default_account": name}`; the legacy flat config is still read as an implicit default account and normalized on the next save. **Automatic re-login only ever uses the default account** — the first stored login becomes it automatically; `bb-cli default` shows it, `bb-cli default <name>` switches (clearing the session so the next command deterministically logs in as it); `bb-cli accounts` lists accounts (passwords never shown). When several accounts are stored and no default is set, auto-login refuses to pick one and says so. Recommended init: run `bb-cli login` manually once to leave credentials, and confirm the default (`bb-cli default`). The environment variables only apply to explicit `login` (plus a last-resort auto-login fallback when no default account has stored credentials).

- `bb-cli logout` logs out and clears the local session (stored accounts are kept — manage them with `bb-cli accounts`).

## Commands (all read-only, JSON by default, `--format text` for humans)

| Command | Purpose |
|---|---|
| `whoami` / `status` / `terms` | Identity, session status, term list |
| `accounts` / `default [<name>]` | List stored accounts (passwords never shown) / show or set the default account — the only one auto-login ever uses |
| `courses [--term substring]` | My courses (`--format text` prints one line per course) |
| `tree <course> [--depth N] [--no-attachments]` | Content tree (folder/lesson/assignment, leaves carry attachment names) |
| `files <course> [--match regex]` | Course file inventory (full paths + attachment id/file name/mime; `--match` applies to paths and file names) |
| `fetch <course> [--match regex] [--since YYYY-MM-DD] [-o DIR] [--dest DIR] [--dry-run]` | Download course files preserving the `course/directory-tree` structure; `--match` applies to paths and file names; existing files are skipped; same-name attachments get the attachment id as a suffix; `--dest` lands directly in the given directory (no course-name prefix appended) |
| `announcements [--course substring\|all] [--limit N] [--html]` | Announcements (scans all courses by default, bodies converted to plain text; a course that fails to pull is skipped and reported in the `skipped` list) |
| `dues [--from D] [--to D] [--course C]` | Cross-course deadlines: calendar endpoint + per-course gradebook columns **dual-source merged and deduplicated** (the calendar misses items, the gradebook is the fallback; entries carry `source`; for the same course and title the calendar entry is kept; request volume ≈ number of courses) |
| `assignments <course>` | Assignment list: due × points possible × my submission status (NeedsGrading/Graded/None) |
| `submission <course> [--match regex] [--download] [-o DIR] [--dest DIR]` | My submission details: status × submission time × file list; `--download` saves to `course/submissions/assignment/file` (Classic route); `--dest` lands directly in the given directory (no course-name/submissions prefix appended) |
| `grades [course] [--due-only]` | Gradebook columns × my status (all courses by default) |
| `roster <course>` | Course members (includes lastAccessed — mind privacy) |
| `raw GET <path> [--q k=v]...` | Pass-through for arbitrary REST GET — route new needs here first, wrap a dedicated command after validation |

The course argument accepts: a course id (`_18030_1`), a course code, or a name substring (`AIE3005`); on ambiguity a candidate list is printed.

**Timestamp handling** (0.1.1): Learn REST raw values are UTC ISO (`…Z`); `--format text` time display and `--from` / `--to` / `--since` date filtering are converted to the local timezone, while JSON output keeps the raw API value.

**dues JSON fields** (0.1.2): entries are normalized to `course / title / source (calendar|gradebook) / due / end / type` (the old `start` field was folded into `due`); `skipped` is the list of courses whose gradebook pull failed.

**fetch filtering and refresh** (0.1.4): `--exclude-mime substring,…` (skip when mimeType contains any of the substrings, e.g. `video/,audio/`) and `--exclude-ext mp4,mov` (skip by extension) are pre-skipped while building the plan, reported in the `skipped` list (also visible with `--dry-run`); `--max-size MB` is a download-time circuit breaker (attachment metadata carries no size, so it can only trip mid-download); `--refresh` re-pulls existing files and compares — identical content is reported `same` and skipped, changed content lands as a new file suffixed with the first 8 hex chars of its content hash (the old file is kept = revision history), reported in the `updated` list.

**fetch default media filtering and placement** (0.1.5): `fetch` skips common media extensions by default (`mts/mpg/mpeg/avi/mkv/wav/mp4/mov/mp3/m4a/webm`); `--no-media-filter` restores full download, `--exclude-ext` appends to the default list. `--dest DIR` lets `fetch` / `submission` target an exact destination directory directly (no automatic course-name prefix). File names are HTML-entity-decoded and truncated preserving the extension before landing on disk (long names no longer lose suffixes like `.pdf`).

**Git Bash note**: raw paths starting with `/` get rewritten by MSYS; prefix the command with `MSYS_NO_PATHCONV=1` or drop the leading slash (relative path).

## Known limits (live-tested 2026-09-29)

- 404 under student sessions: `gradebook/attempts` (flat list), `discussion/forums`, `users/me/memberships`, `tasks`, `gradebook/grades`.
- Exceptions verified (2026-09-30): `gradebook/columns/{col}/attempts` returns your own attempt (with submission time); `attempts/{id}/files` lists file names; REST `/download` is still 404, but the `/webapps/assignment/download?course_id=…&attempt_id=…&file_id=…&fileName=…` link inside the Classic view page (`/webapps/assignment/uploadAssignment?…&mode=view`) works for downloads — wrapped as the `submission` command (v0.1.3).
- Discussion boards, if ever needed, would require the DOM route (see bb-mcp); not in v1.
- Classic (JSP) courses only; Ultra courses unverified.
- Write operations (submitting assignments / posting announcements) are deliberately not provided — upper layers needing them require explicit user instruction and separate design.
- The login-failure page's error text lives permanently in HTML templates, so detection can only rely on state progression; if the school redesigns the login page, re-run with `BB_CLI_DEBUG=<dir>` to capture evidence.

## Acknowledgments

- [jsyzlbw/bbwatch](https://github.com/jsyzlbw/bbwatch): the curl_cffi fingerprint route and REST endpoint verification.
- [changshenhan/bb-mcp](https://github.com/changshenhan/bb-mcp): endpoint and site-behavior reference.
