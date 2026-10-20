---
name: sis-cli
owner: framework
description: "Read-only access to sis.cuhk.edu.cn (CUHK-SZ SIS, PeopleSoft Campus Solutions) via the connectors/sis-cli CLI: pull weekly class schedule, grades (summary), course history, enrollment dates and relay them. Query-and-answer only; writes nothing to wiki. Triggers on: sis-cli, sis, sis.cuhk.edu.cn, check sis schedule, check my timetable, check enrollment dates, student information system, timetable query, 学生信息系统, 课表查询."
---

# sis-cli: SIS (PeopleSoft) Read-Only Connector

Pull information from sis.cuhk.edu.cn via `connectors/sis-cli/` (a purely read-only CLI data plane) and relay it to the user. Queries answer directly: nothing is written to wiki and no data area is modified.

## Scope

Read: SIS student self-service pages (weekly schedule with day-of-week / per-term grades / course history / enrollment dates / exam schedule / student center)
Write: none — read-only by design. **Enrollment actions (add/drop/swap classes) and any state-changing transaction are deliberately NOT provided**; the user risks academic penalties for misuse, so never attempt them via raw or any other route. The only POST the CLI ever makes is the term-selection "Continue" query on search pages — a pure query action equivalent to clicking Continue in the browser.

## Schedule query routing

For timetable or next-class questions in a wiki instance, first read `wiki/calendar.md` and the relevant `wiki/calendar/YYYY-MM.md` month projection (including the next month if the requested date crosses a month boundary). Answer locally when the projection identifies the matching SIS source, covers the requested dates, and has an unexpired `stale_after`. Cite that local source and preserve its time zone/date context. Other calendar sources or manual notes are not automatically SIS timetable evidence.

If the projection is absent, stale, lacks freshness/source evidence, or does not cover the requested dates, use SIS as the source under the user's authorization and the instance's connector rules. An explicit request to refresh or verify current server data overrides the local-cache preference. If network/authentication prevents refresh, disclose the limitation; historical local data must be labelled as such and must not be silently re-dated. Outside a wiki instance, this connector remains usable directly; do not create a wiki merely to run a query.

## Prerequisites (install / auth)

1. Install (if missing): `cd connectors/sis-cli && python -m venv .venv && .venv/Scripts/pip install -e .` (deps: curl_cffi + beautifulsoup4 only; may reuse the bb-cli venv via PYTHONPATH for smoke runs)
2. Init (strongly recommended): run `sis-cli login` manually once to leave stored credentials (`--username <student-id>`; password via the `SIS_CLI_PASSWORD` env var or interactive prompt; `--no-store` keeps it off disk; session cookie lives in `~/.sis-cli/session.json`). The first login automatically becomes the **default account** — confirm with `sis-cli default`, switch with `sis-cli default <name>`. Credentials only ever live under `~/.sis-cli/`
3. Self-check: `sis-cli status` lists components when authenticated; sessions expire in ~5 minutes — the CLI re-logs in automatically per command (default account only), so no manual re-login is normally needed.


## Steps

1. `sis-cli status` to inspect local session/credential evidence and registered components; it does not confirm authentication or network reachability
2. Pick a command per the need (see Command cheat sheet); `--format text` prints human-readable lines, JSON keeps structured values
3. Relay the results to the user (language: see Language below)

## Command cheat sheet

| Need | Command |
|---|---|
| Weekly schedule + day-of-week timetable | `sis-cli schedule --days --format text` |
| My grades for a term | `sis-cli grades [--term 'Term 2']` (default = newest term; term list is reverse-chronological) |
| Full course history | `sis-cli history` |
| Enrollment dates / registration window | `sis-cli appt [--term 'Summer']` |
| Exam schedule | `sis-cli exam` (empty when not yet published) |
| Download unofficial transcript PDF | `sis-cli transcript [--lang eng] [-o out.pdf]` |
| Structured student identity (name/id/email/college/major/admitted) | `sis-cli identity` |
| Degree progress report (currently needs Request Audit) | `sis-cli dpr` |
| Student center / per-assignment grades | `sis-cli center` / `sis-cli assignments` (text summaries) |
| Any page as HTML, GET or ICAction POST navigation | `sis-cli raw <url> [--post --action BTN --set k=v] --file out.html` |
| Accounts / default account | `sis-cli accounts` (list, passwords never shown) / `sis-cli default [<name>]` (show or switch; switching clears the session so the next command auto-logs-in as it) |

Component URLs take the form `/psc/csprd/EMPLOYEE/HRMS/c/<COMPONENT>?PORTALPARAM_PTCNAV=<NAV>` — both parts are registered in `siscli/config.py`; use `raw` for anything not yet wrapped.

## Status values

Schedule `--days` rows carry `days` (Mo/Tu/We/Th/Fr/Sa/Su combos), `time` (e.g. `10:30AM - 11:50AM`), `location`; supervision sections may have no fixed meeting (empty days/time). Grades rows carry course/units/grading basis (Graded, Pass/Fail, Distinction/Pass/Failure)/grade/grade points; Pass-type grades have empty points. `--term` accepts a substring (e.g. `Term 2`, `Summer`) matched against term labels like `2025-26 Term 2` / `2025-26 Summer Session`.

## Known limits

- `exam` returns empty until the school publishes the term's exam schedule (mechanism verified)
- `assignments` (per-assignment gradebook) usually shows "no information" — use `grades` for per-term grades
- Tuition / Finances and enrollment-cart read views are not registered — explore via `raw` first, then wrap
- PIA upgrades or sign-in page changes will break the chain: re-run with `SIS_CLI_DEBUG=<dir>` to capture evidence
- Page bodies contain the student's real name and personal data: relay in conversation only, never commit CLI output into any repo

## Prohibitions

- Never perform or emulate write transactions (enroll/drop/swap/edit classes, cart submits, personal-data edits); user faces academic penalties for these
- Student ids / passwords never enter the repo; never echo the password; credentials live only in `~/.sis-cli/`
- Do not paste raw component HTML (contains personal data) into the wiki or commit it

## Language

Follow the upper-layer requirements and the conversation context. Keep course names, course codes, component names, file names, and paths verbatim.
