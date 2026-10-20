"""sis-cli command surface: all read-only. Write operations (enroll/drop/submit-type actions) are deliberately not provided.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from . import config, parser
from .api import Sis


def _fmt(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def cmd_status(sis: Sis, args) -> int:
    # Loading a cookie jar is local evidence only, not a server validation.
    session = "absent_or_unusable"
    try:
        if sis.transport.load_session():
            session = "cached_unverified"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        session = "unreadable"
    try:
        # Use the same resolver as re-login; never echo values or exception text.
        config.resolve_auto_credentials(sis.cfg)
        relogin = "credentials_available_unverified"
    except SystemExit:
        relogin = "blocked_missing_credentials"
    accounts = config.accounts_view(sis.cfg)
    default = config.default_account(sis.cfg)
    print(_fmt({"authenticated": None,
                "authentication_checked": False,
                "session": session,
                "reachable": None,
                "network_checked": False,
                "relogin": relogin,
                "default_account": default,
                "accounts": len(accounts),
                "host": "sis.cuhk.edu.cn",
                "components": sorted(config.COMPONENTS)}))
    return 0


def cmd_login(sis: Sis, args) -> int:
    accounts = config.accounts_view(sis.cfg)
    name = args.account or ""
    username = args.username or os.environ.get(config.ENV_USERNAME)
    if not username and name and name in accounts:
        username = accounts[name].get("username")
    if not username:  # convenience: prefill from the default account's stored username
        d = config.default_account(sis.cfg)
        if d is not None:
            username = accounts.get(d, {}).get("username")
    if not username:
        username = input("Student id: ").strip()
    password = os.environ.get(args.password_env) if args.password_env else None
    if not password:
        password = getpass.getpass("Password: ")
    make_default = args.default or config.default_account(sis.cfg) is None
    info = sis.login(username, password, store=not args.no_store,
                     account=args.account, make_default=make_default)
    if not args.no_store:
        print(f"credentials for account '{info['account']}' saved to {config.config_path()} (local user directory only)",
              file=sys.stderr)
    print(_fmt(info))
    return 0


def cmd_accounts(sis: Sis, args) -> int:
    rows = config.list_accounts(sis.cfg)
    d = config.default_account(sis.cfg)
    out = {"accounts": rows, "default_account": d}
    if len(rows) > 1 and not d:
        out["hint"] = "multiple accounts and no default set: automatic re-login refuses to pick — run `sis-cli default <name>`"
    print(_fmt(out))
    for r in rows:
        print(f"{'*' if r['default'] else ' '} {r['name']}  {r['username']}  "
              f"{'password stored' if r['has_password'] else 'no password stored'}")
    if not rows:
        print("(no accounts — run `sis-cli login`)")
    if out.get("hint"):
        print(f"!! {out['hint']}", file=sys.stderr)
    return 0


def cmd_default(sis: Sis, args) -> int:
    if not args.name:
        d = config.default_account(sis.cfg)
        print(_fmt({"default_account": d, "accounts": config.list_accounts(sis.cfg)}))
        print(f"default account: {d or '(none — the first stored account becomes the default)'}")
        return 0
    accounts = config.accounts_view(sis.cfg)
    if args.name not in accounts:
        print(f"Unknown account '{args.name}'; known: {', '.join(sorted(accounts)) or '(none)'} "
              f"— create one with `sis-cli login --account {args.name}`", file=sys.stderr)
        return 1
    config.store_account(sis.cfg, args.name, accounts[args.name]["username"],
                         accounts[args.name].get("password"), make_default=True)
    config.save_config(sis.cfg)
    p = config.session_path()
    if p.exists():
        p.unlink()  # deterministic switch: the next command re-logs-in as the new default
    print(_fmt({"default_account": args.name,
                "note": "local session cleared; the next command will auto-login as this account "
                        "(auto-login only ever uses the default account)"}))
    return 0


def cmd_logout(sis: Sis, args) -> int:
    sis.logout()
    n = len(config.accounts_view(sis.cfg))
    extra = f", {n} account name(s) kept for quick re-login (passwords wiped)" if n else ""
    print(f"logged out (local session and stored passwords cleared{extra})")
    return 0


def cmd_schedule(sis: Sis, args) -> int:
    data = sis.schedule_with_days() if args.days else sis.schedule()
    if args.format == "json":
        print(_fmt(data))
        return 0
    print(f"[{data['week'] or 'current week'}] {len(data['events'])} event(s) / {len(data['courses'])} course(s)")
    for e in data["events"]:
        print(f"  {e['class']:<18} {e['type']:<12} {e['time']:<20} {e['location']}")
    if data.get("timetable"):
        print("Timetable (with weekdays, student center page):")
        for t in data["timetable"]:
            print(f"  {t['class']:<16} {t['type']:<5} {t['days']:<6} {t['time']:<22} {t['location']}")
    if data["courses"]:
        print("Term courses:")
        for c in data["courses"]:
            print(f"  {c['class']:<28} {c['title'][:36]:<38} {c['start']}~{c['end']}")
    return 0


def cmd_grades(sis: Sis, args) -> int:
    data = sis.grades(args.term)
    if args.format == "json":
        print(_fmt(data))
        return 0
    print(f"[{data['term']}] {len(data['rows'])} grade row(s)")
    for r in data["rows"]:
        print(f"  {r['course']:<10} {r['description'][:34]:<36} {r['units']:>5} {r['grading'][:22]:<24} {r['grade']:>4} {r['points']:>7}")
    if data["gpa"]:
        print("GPA:", "  ".join(f"{k}={v}" for k, v in data["gpa"].items()))
    if not data["rows"]:
        print(f"(No grades yet for this term; available terms: {', '.join(data['terms_available'])})")
    return 0


def cmd_history(sis: Sis, args) -> int:
    rows = sis.history()
    if args.format == "json":
        print(_fmt(rows))
        return 0
    print(f"Course history: {len(rows)} course(s)")
    for r in rows:
        print(f"  {r['course']:<10} {r['description'][:34]:<36} {r['term']:<18} {r['grade'] or '-':>4} {r['units']:>5}")
    return 0


def cmd_appt(sis: Sis, args) -> int:
    data = sis.appt(args.term)
    if args.format == "json":
        print(_fmt(data))
        return 0
    print(f"[{data['term']}] enrollment windows")
    for a in data["appointments"]:
        print(f"  {a['session']}: {a['begins']} {a['begin_time']} ~ {a['ends']} {a['end_time']}")
    for k, v in data["limits"].items():
        print(f"  {k}: {v}")
    if not data["appointments"]:
        print(f"(No enrollment-window info for this term; available terms: {', '.join(data['terms_available'])})")
    return 0


def cmd_exam(sis: Sis, args) -> int:
    data = sis.exam(args.term)
    if args.format == "json":
        print(_fmt(data))
        return 0
    print(f"[{data['term']}] exam schedule: {len(data['rows'])} row(s)")
    for r in data["rows"]:
        print("  " + "  ".join(f"{k}={v}" for k, v in r.items() if v))
    return 0


def cmd_text_component(sis: Sis, args) -> int:
    html = sis.component_html(args.cmd)
    if args.format == "json":
        print(_fmt({"component": args.cmd, "text": parser.textify(html)}))
    else:
        print(parser.textify(html))
    return 0


def cmd_transcript(sis: Sis, args) -> int:
    data, url = sis.transcript_pdf(args.lang)
    import pathlib
    dest = pathlib.Path(args.out) if args.out else pathlib.Path(f"unofficial_transcript_{args.lang}.pdf")
    dest.write_bytes(data)
    print(f"saved {dest} ({len(data)}B) | source: {url[:110]}")
    return 0


def cmd_identity(sis: Sis, args) -> int:
    data = sis.identity()
    if args.format == "json":
        print(_fmt(data))
        return 0
    for k, v in data.items():
        print(f"  {k}: {v}")
    return 0


def cmd_dpr(sis: Sis, args) -> int:
    html = sis.dpr_html()
    if args.format == "json":
        print(_fmt({"text": parser.textify(html)}))
    else:
        print(parser.textify(html))
    return 0


def cmd_raw(sis: Sis, args) -> int:
    if args.post:
        # POST navigation: --action names the ICAction + --set k=v overrides fields (issue #6 ①)
        comp, nav = None, None
        from . import config as cfg
        for name, (c, n) in cfg.COMPONENTS.items():
            if c in args.url:
                comp, nav = c, n
                break
        if comp is None:
            print("raw --post needs the URL of a registered component (containing the component name is enough to match)", file=sys.stderr)
            return 1
        extra = {}
        for kv in args.set or []:
            k, _, v = kv.partition("=")
            extra[k] = v
        out = sis.transport.submit_icaction(comp, nav, args.action, extra or None)
    else:
        out = sis.raw(args.url)
    if args.file:
        import pathlib
        pathlib.Path(args.file).write_text(out, encoding="utf-8", errors="replace")
        print(f"saved {args.file} ({len(out)}B)")
    else:
        print(out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sis-cli",
                                 description="sis.cuhk.edu.cn read-only CLI connector (PeopleSoft CS)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="local session/credential evidence (no network or login)")
    sub.add_parser("logout", help="log out and clear local credentials/session")
    sub.add_parser("accounts", help="list stored accounts (passwords never shown)")

    p = sub.add_parser("default", help="show or set the default account (the only one auto-login ever uses)")
    p.add_argument("name", nargs="?", help="account name to make the default; omit to show the current one")

    p = sub.add_parser("login", help="interactive login (first login becomes the default account)")
    p.add_argument("--username", "-u")
    p.add_argument("--account", help="store the credentials under this account name (default: the username)")
    p.add_argument("--default", action="store_true",
                   help="also make this account the default (automatic re-login only ever uses the default)")
    p.add_argument("--no-store", action="store_true", help="keep credentials off disk (default: stored in ~/.sis-cli)")
    p.add_argument("--password-env")

    p = sub.add_parser("schedule", help="my weekly class schedule (--days adds day-of-week attribution from the student center page)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--days", action="store_true", help="include the timetable with weekday/session attribution")

    for comp, label in [
            ("grades", "view my grades (per term; --term substring optional)"),
            ("appt", "enrollment dates (--term substring optional)"),
            ("exam", "my exam schedule (--term substring optional)"),
            ("history", "my course history (full, direct output)")]:
        p = sub.add_parser(comp, help=label)
        p.add_argument("--format", choices=["text", "json"], default="text")
        if comp != "history":
            p.add_argument("--term", help="term substring (defaults to the newest; e.g. 'Term 2')")

    p = sub.add_parser("center", help="student center page (text summary)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p = sub.add_parser("assignments", help="per-assignment grades (often no data; under observation)")
    p.add_argument("--format", choices=["text", "json"], default="text")

    p = sub.add_parser("transcript", help="download the unofficial transcript PDF (--lang eng|chi|ge-edu)")
    p.add_argument("--lang", choices=["eng", "chi", "ge-edu"], default="eng")
    p.add_argument("-o", "--out", help="output path (defaults to the current directory)")

    p = sub.add_parser("identity", help="structured student identity (name/id/email/college/major/admitted)")
    p.add_argument("--format", choices=["text", "json"], default="json")

    p = sub.add_parser("dpr", help="degree progress report (currently needs Request Audit; text output as-is)")
    p.add_argument("--format", choices=["text", "json"], default="text")

    p = sub.add_parser("raw", help="arbitrary GET/POST pass-through (validate new needs here first, then wrap a command)")
    p.add_argument("url")
    p.add_argument("--file", help="save to the given file instead of printing")
    p.add_argument("--post", action="store_true", help="POST navigation (requires a registered component URL)")
    p.add_argument("--action", help="ICAction name (e.g. a button id)")
    p.add_argument("--set", action="append", metavar="k=v", help="form field overrides (repeatable)")

    args = ap.parse_args(argv)
    sis = Sis()

    handlers = {"status": cmd_status, "login": cmd_login, "logout": cmd_logout,
                "accounts": cmd_accounts, "default": cmd_default,
                "schedule": cmd_schedule, "grades": cmd_grades, "history": cmd_history,
                "appt": cmd_appt, "exam": cmd_exam, "raw": cmd_raw,
                "center": cmd_text_component, "assignments": cmd_text_component,
                "transcript": cmd_transcript, "identity": cmd_identity, "dpr": cmd_dpr}

    if args.cmd not in ("login", "logout", "status", "accounts", "default"):
        sis.ensure_session()
    if args.cmd == "raw" and args.file:
        import pathlib
        out = sis.raw(args.url)
        pathlib.Path(args.file).write_text(out, encoding="utf-8", errors="replace")
        print(f"saved {args.file} ({len(out)}B)")
        return 0
    return handlers[args.cmd](sis, args)


if __name__ == "__main__":
    sys.exit(main())
