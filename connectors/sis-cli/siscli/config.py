"""Configuration and paths: every tunable lives here.

Credentials/sessions live only in the user directory (default ~/.sis-cli,
SIS_CLI_HOME overrides); never written into the working directory or any
repository. Environment variables take precedence over the config file.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

SIS_HOST = "https://sis.cuhk.edu.cn"
ADFS_CLIENT_ID = "3f09a73c-33cf-49b8-8f0c-b79ea2f3e83b"
ADFS_REDIRECT_URI = SIS_HOST + "/sso/dologin.html"
ADFS_AUTHORIZE_URL = (
    "https://sts.cuhk.edu.cn/adfs/oauth2/authorize"
    "?response_type=code"
    f"&client_id={ADFS_CLIENT_ID}"
    f"&redirect_uri={ADFS_REDIRECT_URI}"
)
# PeopleSoft sessions last only minutes (PS_TOKENEXPIRE measured at ~5 minutes):
# reusing a jar across processes is unreliable — a light in-command login is
# primary, jar reuse secondary.
SESSION_SOFT_TTL = 240  # seconds; beyond this, treat as expired and re-login directly
IMPERSONATE = "chrome124"
REQUEST_TIMEOUT = 40

# The PeopleSoft shell-page JS detects the browser environment via the
# PS_DEVICEFEATURES cookie; without it, direct psc hits only ever return the
# bootstrap shell. Format = JSON stripped of {}/quotes, commas replaced by
# spaces (see ptDeviceFeatures in /csprd/signin.js); the value is a typical
# desktop Chrome fingerprint.
PS_DEVICEFEATURES = (
    "width:1920 height:1080 pixelratio:1 touch:0 geolocation:1 websockets:1 "
    "webworkers:1 datepicker:1 dtpicker:1 timepicker:1 dnd:1 sessionstorage:1 "
    "localstorage:1 history:1 canvas:1 svg:1 postmessage:1 hc:0"
)

# Components available to the student role (2026-10-05, verified both ways:
# browser menu navigation + direct HTTP psc+PTCNAV hits).
# PTCNAV is the navigation context for the permission check — without it you
# get "not authorized".
COMPONENTS = {
    # Direct-output components (GET returns content)
    "schedule": ("SA_LEARNER_SERVICES.SSR_SSENRL_SCHD_W.GBL", "HC_SSR_SSENRL_SCHD_W_GBL"),
    "center": ("SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL", "HC_SSS_STUDENT_CENTER"),
    "history": ("SA_LEARNER_SERVICES_2.SSS_MY_CRSEHIST.GBL", "HC_SSS_MY_CRSEHIST_GBL2"),
    # term-interaction components (GET the search page → POST the term radio + Continue)
    "grades": ("SA_LEARNER_SERVICES.SSR_SSENRL_GRADE.GBL", "HC_SSR_SSENRL_GRADE_GBL"),
    "appt": ("SA_LEARNER_SERVICES.SSR_SSENRL_APPT.GBL", "HC_SSR_SSENRL_APPT"),
    "exam": ("SA_LEARNER_SERVICES.SSR_SSENRL_EXAM_L.GBL", "HC_SSR_SSENRL_EXAM_L_GBL"),
    "list_schedule": ("SA_LEARNER_SERVICES.SSR_SSENRL_LIST.GBL", "HC_SSR_SSENRL_LIST_GBL"),
    # Per-assignment grades (View My Assignments) — live tests usually show "no information"; under observation
    "assignments": ("SA_LEARNER_SERVICES.SS_LAM_STD_GR_LST.GBL", "HC_SS_LAM_STD_GR_LST_GBL1"),
    # Unofficial transcript (View Report produces the PDF; report types: UE01 English / UC01 Chinese / UFCEC national-condition education)
    "transcript": ("SA_LEARNER_SERVICES.SSS_TSRQST_UNOFF.GBL", "HC_SSS_TSRQST_UNOFF_GBL"),
    # Personal data summary (name/email/holds/todo; main source for the identity command)
    "prsnldata": ("CC_PORTFOLIO.SSS_PRSNLDATA_SUMM.GBL", "HC_SSS_PRSNLDATA_SUMM_GBL"),
    # Degree progress report (My Academic Requirements) — currently shows "page not available" (needs Request Audit; under observation)
    "dpr": ("SA_LEARNER_SERVICES.SAA_SS_DPR_ADB.GBL", "HC_SAA_SS_DPR_ADB_GBL"),
}
# ICAction constants (verified 2026-10-05)
IC_VIEW_REPORT = "CUSZ_TSRQST_WRK_VIEW_PB"  # transcript View Report button
TRANSCRIPT_TYPES = {"eng": "UE01", "chi": "UC01", "ge-edu": "UFCEC"}
TRANSCRIPT_TYPE_FIELD = "DERIVED_SSTSRPT_TSCRPT_TYPE3"
# Components that require term selection + Continue (uniform interaction: radio SSR_DUMMY_RECV1$sels$0 + DERIVED_SSS_SCT_SSR_PB_GO)
TERM_COMPONENTS = {"grades", "appt", "exam", "list_schedule"}

ENV_HOME = "SIS_CLI_HOME"
ENV_USERNAME = "SIS_CLI_USERNAME"
ENV_PASSWORD = "SIS_CLI_PASSWORD"
ENV_PROXY = "SIS_CLI_PROXY"
ENV_DEBUG = "SIS_CLI_DEBUG"  # set to a directory path to dump debug HTML


def sis_home() -> Path:
    root = os.environ.get(ENV_HOME)
    home = Path(root).expanduser() if root else Path.home() / ".sis-cli"
    home.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    return sis_home() / "config.json"


def session_path() -> Path:
    return sis_home() / "session.json"


def _restrict(path: Path) -> None:
    """Best-effort permission tightening (POSIX 0600; Windows merely inherits the user-directory ACL)."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    p = config_path()
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _restrict(p)


def resolve_credentials(cfg: dict, cli_user: str | None, password_env: str | None) -> tuple[str, str]:
    """Credential resolution priority: CLI/env vars > config file. The password is never echoed into logs."""
    username = cli_user or os.environ.get(ENV_USERNAME) or cfg.get("username")
    password = None
    if password_env:
        password = os.environ.get(password_env)
    elif os.environ.get(ENV_PASSWORD):
        password = os.environ.get(ENV_PASSWORD)
    else:
        password = cfg.get("password")
    if not username or not password:
        raise SystemExit(
            "Missing credentials: use `sis-cli login` to enter them interactively, or set "
            f"{ENV_USERNAME}/{ENV_PASSWORD}, or pass --password-env to name a variable"
        )
    return username, password


def proxy() -> str | None:
    return os.environ.get(ENV_PROXY) or None


def debug_dir() -> Path | None:
    d = os.environ.get(ENV_DEBUG)
    if not d:
        return None
    p = Path(d).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
