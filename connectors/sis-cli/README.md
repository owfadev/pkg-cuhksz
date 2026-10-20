# sis-cli — CUHK-SZ SIS Read-Only CLI Connector

A command-line connector for `sis.cuhk.edu.cn` (Oracle PeopleSoft Campus Solutions): **a purely read-only data plane — no agent logic, no MCP, no monitoring** — serving as a fact interface for upper layers (wiki domain plugins / humans / scripts). The technical route and login findings carry over from bb-cli (the same ADFS `sts.cuhk.edu.cn`, the same `cuhksz\` domain-prefix rule); the PeopleSoft-side login and component access were written from live reverse engineering on 2026-10-05.

## Installation

Use the instance's declared Python environment when one exists. Otherwise, from `connectors/sis-cli`, choose one of these isolated environments; activation and global PATH changes are unnecessary.

Windows (PowerShell or Git Bash):

```text
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
./.venv/Scripts/python.exe -m siscli --help
```

macOS / Linux:

```text
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m siscli --help
```

On hosts using uv, `uv venv .venv` and `uv pip install --python .venv -e .` are an alternative; use the corresponding environment's Python path above to run the module. No `--break-system-packages` is needed for a virtual environment.

If an earlier `pip --user` installation succeeded but `sis-cli` is not found, run `python -m siscli --help` using the **same Python that installed it**. This bypasses the missing console-script PATH entry. `No module named siscli` means that interpreter cannot see the installed package; check `python -m pip show siscli` and use the intended environment instead of reinstalling globally. For the default user-install script directory, use:

```text
python -c "import sysconfig; print(sysconfig.get_path('scripts', scheme=sysconfig.get_preferred_scheme('user')))"
```

The user scheme matters: an unqualified `get_path('scripts')` may report the base interpreter's script directory. Custom install prefixes can differ. Prefer the module invocation over changing persistent PATH settings. `--help` checks the launcher without logging in; run authentication only when needed for the user's task.

Dependencies are only `curl_cffi` (Chrome TLS fingerprint) and `beautifulsoup4`.

## Authentication (ADFS OAuth2 → PeopleSoft session)

Flow (fully HTTP-reproducible, no browser):

1. `sts.cuhk.edu.cn/adfs/oauth2/authorize` (client_id registered to SIS) → ADFS form login (same source as bb-cli: a single POST, the student id automatically gets the `cuhksz\` prefix);
2. the callback `sis.cuhk.edu.cn/sso/dologin.html?code=…` is a static page — replicate its JS form and POST `/psp/csprd/?cmd=login&languageCd=…&code=…` (fixed service account `CUSZ_SSO_LOGIN` + a random password; GET that URL first to warm up `PSJSESSIONID` before POSTing);
3. the PeopleSoft backend exchanges the code for a session; once `PS_TOKEN` lands, the login has succeeded.

Credentials and sessions live only in the local `~/.sis-cli/` (`SIS_CLI_HOME` can override): `config.json` (credentials, permission 0600) + `session.json` (cookie jar). **Never written into any repository.** Off-disk option: the environment variables `SIS_CLI_USERNAME` / `SIS_CLI_PASSWORD`, or `sis-cli login --no-store`.

**Multiple accounts & the default account** (0.4.0): credentials are stored per account (`login --account <name>`, default name = the username) as `{"accounts": {name: {username, password}}, "default_account": name}`; the legacy flat config is still read as an implicit default account and normalized on the next save. **Automatic re-login (per command — see below) only ever uses the default account**: the first stored login becomes it automatically; `sis-cli default` shows it, `sis-cli default <name>` switches (clearing the session so the next command deterministically logs in as it); `sis-cli accounts` lists accounts (passwords never shown). When several accounts are stored and no default is set, auto-login refuses to pick one and says so. Recommended init: run `sis-cli login` manually once to leave credentials, and confirm the default (`sis-cli default`). The environment variables only apply to explicit `login` (plus a last-resort auto-login fallback when no default account has stored credentials).

**Short-lived sessions**: in live testing `PS_TOKEN` expires in about 5 minutes, and `PORTAL-PSJSESSIONID` is re-issued on a rolling basis with each response. CLI strategy: write through session.json after every request; when component access hits the login shell, automatically re-login once and replay — using the **default account's** stored credentials (the ADFS session persists, so a re-login costs ≈ two requests).

## PeopleSoft access essentials (verified 2026-10-05)

- **PS_DEVICEFEATURES cookie**: the shell-page JS uses it to detect the browser environment; without it, direct psc hits only ever return the bootstrap shell. Format = JSON stripped of `{}`/quotes, commas replaced by spaces (see `/csprd/signin.js`). The CLI always seeds a typical desktop Chrome value on the session.
- **psc/psp ping-pong**: hitting `/psc/…/c/<component>` directly first returns a shell (`self.location` points to the psp-version URL); following it reaches the real content or a portal framework page (the `ptifrmtgtframe` TargetContent iframe — take its src and GET it).
- **PORTALPARAM_PTCNAV**: the student-role permission check carries the navigation context — direct psc hits must include `?PORTALPARAM_PTCNAV=<HC_…>`; without it you get "not authorized" (verified: SSR_STUDENT_SCHEDULE without PTCNAV was rejected; SSR_SSENRL_SCHD_W with it passed). The long FolderPath/EOPP parameters can be omitted entirely.
- Components expose no public REST: the data lives inside PIA HTML; write a parser per component.

## Commands (all read-only, `--format text|json`)

| Command | Purpose |
|---|---|
| `status` | Session status and the list of available components |
| `login` / `logout` | Interactive login (`--account <name>` stores under an account name; first login becomes the default; `--no-store` keeps credentials off disk) / logout and clear local state (stored passwords wiped, account names kept) |
| `accounts` / `default [<name>]` | List stored accounts (passwords never shown) / show or set the default account — the only one auto-login ever uses |

| `schedule [--days]` | My weekly class schedule: this week's events + the term course table; `--days` adds the **day-of-week timetable** from the student center page (Mo/Tu/We…) |
| `grades [--term substring]` | View my grades: per-term course rows (course/units/grading basis/grade/grade points); defaults to the newest term |
| `history` | Full course history: course/description/term/grade/units (page-direct, no interaction needed) |
| `appt [--term substring]` | Enrollment dates: registration windows (start/end times) + unit limits |
| `exam [--term substring]` | Exam schedule (empty when the current term has not published it yet) |
| `transcript [--lang eng\|chi\|ge-edu] [-o F]` | Download the unofficial transcript PDF (View Report → FILEDB_XMLP PDF, AES with empty password) |
| `identity` | Structured student identity: name/id/email/holds (prsnldata page) + college/major/admitted/mode of study (transcript PDF, needs pypdf) |
| `dpr` | Degree progress report (currently requires Request Audit to generate; outputs the page's current state as-is) |
| `center` / `assignments` | Student center page / per-assignment grades (text summaries; assignments often has no data) |
| `raw <url> [--post --action IC-name --set k=v] [--file F]` | GET/POST pass-through — the POST navigation primitive (issue #6 ①): dropdown jumps and View Report style pages are reachable via ICAction POST; probes no longer stop at GET |

**term interaction mechanism** (grades/appt/exam): GET the search page → parse the term radios (`SSR_DUMMY_RECV1$sels$0`, the page is reverse-ordered, newest first) → POST the `win0` form (ICAction=Continue button `DERIVED_SSS_SCT_SSR_PB_GO`) → result page. This POST is a query action (equivalent to clicking "Continue" on the web page) and changes no data.

## Known limits (live-tested 2026-10-05)

- `exam` exam schedule: same mechanism as grades (the term POST); empty until the current term publishes it — data will appear naturally once published.
- `assignments` (per-assignment grades) directly shows "There is no information"; keep under observation; use `grades` for per-term grades.
- Tuition bills (Finances-type) and the shopping-cart read views are not registered (visible in the menu; `raw --post` can scout ahead).
- The `dpr` report currently shows "not available" — viewable only after Request Audit (submitting the report task) generates it; that button is a submit-type action, not auto-executed in v0.3, pending a ruling.
- The PDF-side fields of `identity` depend on pypdf (optional dependency; when missing, that group of fields is marked unavailable).
- Page bodies contain the student's real name and other private data — CLI output goes to the terminal/local machine only, **never into any repository**.
- A school PIA upgrade or a login-page redesign will break the chain: re-run with `SIS_CLI_DEBUG=<dir>` to capture evidence.
- **Write operations (enroll/drop/swap/submit) are deliberately not provided** — misuse has real academic-record consequences; if genuinely needed, explicit user instruction and separate design are required.

## Git Bash note

Raw paths starting with `/` get rewritten by MSYS; prefix the command with `MSYS_NO_PATHCONV=1` or drop the leading slash (relative path).

## Status contract (0.3.1)

`status` is an offline diagnostic. It does not attempt silent login or contact the school. Its JSON separates local evidence from facts that require a server check:

- `authenticated: null`, `authentication_checked: false`: authentication is unknown, including when cached cookies exist. This changes the old boolean field; consumers must not treat null as an authenticated state.
- `session`: `cached_unverified` when a local token loads; `absent_or_unusable` when it does not; `unreadable` when a local error escapes the loader (for example, malformed cookie entries). The loader itself handles invalid JSON, unreadable bytes/files and empty/non-list jars by returning no usable session, so those cases report `absent_or_unusable`; `unreadable` is not a complete inventory of damaged files. An absent token does not say whether credentials could establish a new session.
- `reachable: null`, `network_checked: false`: network reachability is unknown, never inferred from cached state or missing credentials.
- `relogin`: `credentials_available_unverified` or `blocked_missing_credentials`, using the same resolver as normal re-login (including its environment-variable policy). No credentials or raw exception messages are emitted.
- `components` lists supported commands, not verified server permissions. Exit 0 means the diagnostic completed.
- A non-object JSON configuration is treated as empty, just like missing or invalid JSON; the original file is not rewritten. Constructing the client may create an empty local home directory, but status does not write configuration or session files.

A subsequent user-requested read may report a network failure (check campus network/VPN), or an expired session that cannot re-login (authenticate interactively, especially after `login --no-store`). Status does not claim to probe session validity, network health, or password validity.

### Changelog

- 0.3.1: replace optimistic status/silent-login behavior with explicit offline evidence, unknown authentication/reachability, and credential availability. Normal login and query behavior is unchanged.
