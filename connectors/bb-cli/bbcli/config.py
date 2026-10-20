"""Configuration and paths: every tunable lives here.

Credentials/sessions live only in the user directory (default ~/.bb-cli,
BB_CLI_HOME overrides); never written into the working directory or any
repository. Environment variables take precedence over the config file
(for the explicit `login` command; automatic re-login uses the default
account only — see resolve_auto_credentials).
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

BB_HOST = "https://bb.cuhk.edu.cn"
ADFS_CLIENT_ID = "4b71b947-7b0d-4611-b47e-0ec37aabfd5e"
ADFS_REDIRECT_URI = BB_HOST + "/webapps/bb-SSOIntegrationOAuth2-BBLEARN/authValidate/getCode"
ADFS_AUTHORIZE_URL = (
    "https://sts.cuhk.edu.cn/adfs/oauth2/authorize"
    "?response_type=code"
    f"&client_id={ADFS_CLIENT_ID}"
    f"&redirect_uri={ADFS_REDIRECT_URI}"
)
IMPERSONATE = "chrome124"  # the site does TLS client fingerprinting; plain OpenSSL handshakes get rejected
REQUEST_TIMEOUT = 30

ENV_HOME = "BB_CLI_HOME"
ENV_USERNAME = "BB_CLI_USERNAME"
ENV_PASSWORD = "BB_CLI_PASSWORD"
ENV_PROXY = "BB_CLI_PROXY"
ENV_DEBUG = "BB_CLI_DEBUG"  # set to a directory path to dump debug HTML


def bb_home() -> Path:
    root = os.environ.get(ENV_HOME)
    home = Path(root).expanduser() if root else Path.home() / ".bb-cli"
    home.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    return bb_home() / "config.json"


def session_path() -> Path:
    return bb_home() / "session.json"


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
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    p = config_path()
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _restrict(p)


# ---- Multi-account store ----
# config.json shape (0.2.0+): {"accounts": {name: {"username": ..., "password": ...}},
# "default_account": name}. The legacy flat {"username", "password"} shape is still
# read as an implicit default account and normalized away on the next save.
# Automatic re-login only ever uses the DEFAULT account; other stored accounts
# are never auto-logged-in.

def accounts_view(cfg: dict) -> dict:
    """Normalized in-memory view {name: {"username", "password"}}; legacy flat fields fold in."""
    accounts = {k: dict(v) for k, v in (cfg.get("accounts") or {}).items() if isinstance(v, dict)}
    legacy_user = cfg.get("username")
    if legacy_user and legacy_user not in [a.get("username") for a in accounts.values()]:
        accounts.setdefault(str(legacy_user), {"username": legacy_user, "password": cfg.get("password")})
    return accounts


def default_account(cfg: dict) -> str | None:
    """The single account automatic re-login may use; None when absent or ambiguous."""
    accounts = accounts_view(cfg)
    name = cfg.get("default_account")
    if name in accounts:
        return name
    if len(accounts) == 1:  # the only stored account is the implicit default
        return next(iter(accounts))
    return None  # nothing stored, or multiple accounts with no default set


def list_accounts(cfg: dict) -> list[dict]:
    d = default_account(cfg)
    return [{"name": n, "username": a.get("username"),
             "has_password": bool(a.get("password")), "default": n == d}
            for n, a in sorted(accounts_view(cfg).items())]


def store_account(cfg: dict, name: str, username: str, password: str | None, *, make_default: bool) -> dict:
    """Write an account under `name` (password None = recorded without stored credentials),
    normalizing legacy flat fields away. The default pointer moves only when explicit
    (make_default) or when it is currently unset/dangling; an existing different default wins."""
    accounts = accounts_view(cfg)
    accounts[name] = {"username": username, "password": password}
    cfg["accounts"] = accounts
    cfg.pop("username", None)
    cfg.pop("password", None)
    if make_default or cfg.get("default_account") not in accounts:
        cfg["default_account"] = name
    return cfg


def resolve_auto_credentials(cfg: dict) -> tuple[str, str]:
    """Credentials for AUTOMATIC re-login (401-triggered) only — the default account,
    exclusively. Chain: named default → implicit default (legacy flat / single stored
    account) → env vars as a last-resort off-disk fallback. A non-default account is
    never auto-logged-in."""
    accounts = accounts_view(cfg)
    name = default_account(cfg)
    if name is not None:
        acct = accounts[name]
        if acct.get("username") and acct.get("password"):
            return acct["username"], acct["password"]
    env_user = os.environ.get(ENV_USERNAME)
    env_pw = os.environ.get(ENV_PASSWORD)
    if env_user and env_pw:
        print(f"no default-account credentials stored; falling back to {ENV_USERNAME}/{ENV_PASSWORD} env vars", file=sys.stderr)
        return env_user, env_pw
    raise SystemExit(
        "No credentials for automatic re-login (auto-login only ever uses the DEFAULT account): "
        "run `bb-cli login --account <name>` interactively to store credentials, then "
        "`bb-cli default <name>` — the first stored account becomes the default automatically")


def proxy() -> str | None:
    return os.environ.get(ENV_PROXY) or None


def debug_dir() -> Path | None:
    d = os.environ.get(ENV_DEBUG)
    if not d:
        return None
    p = Path(d).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
