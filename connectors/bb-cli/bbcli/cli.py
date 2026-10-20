"""Command surface: all read-only. JSON output by default; raw accepts GET only (write operations are out of scope for v1)."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, auth, config
from .api import BBClient
from .transport import ApiError, TooLarge, Transport, TransportError


# ---- Output ----
def emit(obj, fmt: str, text_fn=None):
    if fmt == "text" and text_fn:
        lines = list(text_fn(obj)) or ["(no results)"]
        for line in lines:
            print(line)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def strip_html(html: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)


_MAX_NAME = 80
_DEFAULT_MEDIA_EXTS = {"mts", "mpg", "mpeg", "avi", "mkv", "wav",
                       "mp4", "mov", "mp3", "m4a", "webm"}


def _sanitize(name: str) -> str:
    s = html.unescape(name or "")
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", s).strip(" .")
    if not s:
        return "_"
    if len(s) <= _MAX_NAME:
        return s
    stem, dot, ext = s.rpartition(".")
    if dot and ext and len(ext) <= 10 and " " not in ext:
        return stem[: _MAX_NAME - 1 - len(ext)] + "." + ext
    return s[:_MAX_NAME]


def _local_dt(iso: str | None) -> datetime | None:
    """API raw values are UTC ISO (…Z); values without a timezone mark are treated as UTC too. Returns None on parse failure."""
    if not iso:
        return None
    s = iso.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()  # local timezone


def _date_part(iso: str | None) -> str:
    dt = _local_dt(iso)
    return dt.strftime("%Y-%m-%d") if dt else (iso or "")[:10]


def _dt_part(iso: str | None) -> str:
    dt = _local_dt(iso)
    return dt.strftime("%Y-%m-%dT%H:%M") if dt else (iso or "")[:16]


# ---- Session assembly ----
def build_client() -> tuple[BBClient, Transport, dict]:
    cfg = config.load_config()
    t = Transport()
    t.load_session()

    def relogin():
        username, password = config.resolve_auto_credentials(cfg)
        auth.login(t, username, password)
        t.save_session()

    t._relogin = relogin
    return BBClient(t), t, cfg


def need_auth(client: BBClient):
    try:
        client.me()
    except auth.CredentialError as e:
        print(f"Stored credentials rejected ({e}); run `bb-cli login` again", file=sys.stderr)
        sys.exit(2)
    except ApiError as e:
        if e.status == 401:
            print("Not logged in or session expired: run `bb-cli login` first", file=sys.stderr)
        else:
            print(f"Auth check failed: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        # Surface the real failure instead of masking it as a session problem
        # (e.g. PermissionError writing session.json, TransportError on network).
        print(f"Auth check failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)


# ---- Command implementations ----
def cmd_login(args):
    import getpass
    import os

    cfg = config.load_config()
    accounts = config.accounts_view(cfg)
    name = args.account or ""
    username = args.username or os.environ.get(config.ENV_USERNAME)
    if not username and name and name in accounts:
        username = accounts[name].get("username")
    if not username:  # convenience: prefill from the default account's stored username
        d = config.default_account(cfg)
        if d is not None:
            username = accounts.get(d, {}).get("username")
    if not username:
        username = input("Student id / email prefix: ").strip()
    if args.password_env:
        password = os.environ.get(args.password_env)
        if not password:
            sys.exit(f"Environment variable {args.password_env} is not set")
    elif os.environ.get(config.ENV_PASSWORD):
        password = os.environ[config.ENV_PASSWORD]
    else:
        password = getpass.getpass("Password: ")
    t = Transport()
    me = auth.login(t, username, password)
    t.save_session()
    name = name or username
    make_default = args.default or config.default_account(cfg) is None
    config.store_account(cfg, name, username, None if args.no_store else password,
                         make_default=make_default)
    config.save_config(cfg)
    if not args.no_store:
        print(f"Credentials for account '{name}' saved to {config.config_path()} (local user directory only)", file=sys.stderr)
    d = config.default_account(cfg)
    note = (f"account '{name}' is now the default — automatic re-login will use this account only"
            if d == name else
            f"note: default account is '{d}' — automatic re-login uses that one; switch with `bb-cli default {name}`")
    emit({"login": "ok", "user": me.get("name"), "id": me.get("id"),
          "account": name, "default_account": d, "note": note}, args.format,
          lambda o: [f"login ok  user={((o.get('user') or {}).get('given')) or o.get('user')}  "
                     f"account={o['account']}  default={o['default_account']}", o["note"]])


def cmd_accounts(args):
    cfg = config.load_config()
    rows = config.list_accounts(cfg)
    d = config.default_account(cfg)
    hint = None if len(rows) <= 1 or d else \
        "multiple accounts and no default set: automatic re-login refuses to pick — run `bb-cli default <name>`"
    emit({"accounts": rows, "default_account": d, "hint": hint}, args.format,
          lambda o: [f"{'*' if r['default'] else ' '} {r['name']}  {r['username']}  "
                     f"{'password stored' if r['has_password'] else 'no password stored'}"
                     for r in o["accounts"]] + (["!! " + o["hint"]] if o.get("hint") else [])
          or ["(no accounts — run `bb-cli login`)"])


def cmd_default(args):
    cfg = config.load_config()
    if not args.name:
        d = config.default_account(cfg)
        rows = config.list_accounts(cfg)
        emit({"default_account": d, "accounts": rows}, args.format,
              lambda o: [f"default account: {o['default_account'] or '(none — first stored account becomes the default)'}"]
              + [f"{'*' if r['default'] else ' '} {r['name']}  {r['username']}" for r in o["accounts"]])
        return
    accounts = config.accounts_view(cfg)
    if args.name not in accounts:
        sys.exit(f"Unknown account '{args.name}'; known: {', '.join(sorted(accounts)) or '(none)'}"
                 f" — create one with `bb-cli login --account {args.name}`")
    config.store_account(cfg, args.name, accounts[args.name]["username"],
                         accounts[args.name].get("password"), make_default=True)
    config.save_config(cfg)
    p = config.session_path()
    if p.exists():
        p.unlink()  # deterministic switch: the next command re-logs-in as the new default
    emit({"default_account": args.name,
          "note": "local session cleared; the next command will auto-login as this account "
                  "(auto-login only ever uses the default account)"}, args.format,
          lambda o: [f"default account set to '{o['default_account']}'", o["note"]])


def cmd_logout(args):
    t = Transport()
    t.load_session()
    auth.logout(t)
    n = len(config.accounts_view(config.load_config()))
    extra = f" ({n} stored account(s) kept — manage with `bb-cli accounts`)" if n else ""
    print(f"Logged out; local session cleared{extra}")


def cmd_whoami(args):
    c, _, _ = build_client()
    need_auth(c)
    emit(c.me(), args.format)


def cmd_status(args):
    c, t, cfg = build_client()
    t._relogin = None  # status probing never triggers auto re-login; an unauthenticated state is reported as-is
    has_file = config.session_path().exists()
    try:
        me = c.me()
        ok = True
    except Exception:
        me, ok = None, False
    emit({"session_file": has_file, "authenticated": ok,
          "user": (me or {}).get("name"), "default_account": config.default_account(cfg),
          "accounts": len(config.accounts_view(cfg))}, args.format,
         lambda o: [f"session_file={'yes' if o['session_file'] else 'no'}  "
                    f"authenticated={'yes' if o['authenticated'] else 'no'}  "
                    f"user={((o.get('user') or {}).get('given')) or '-'}  "
                    f"default_account={o['default_account'] or '-'}  accounts={o['accounts']}"] +
         (["!! no stored credentials for auto re-login — run `bb-cli login` (first login becomes the default account)"]
          if o["accounts"] == 0 else
          ["!! multiple accounts and no default set — auto-login refuses to pick; run `bb-cli default <name>`"]
          if not o["default_account"] else []))


def cmd_terms(args):
    c, _, _ = build_client()
    need_auth(c)
    emit(c.terms(), args.format,
         lambda ts: [f"{t['id']}  {t['name']}  {_date_part((t.get('availability') or {}).get('duration', {}).get('start'))}" for t in ts])


def cmd_courses(args):
    c, _, _ = build_client()
    need_auth(c)
    courses = c.my_courses()
    if args.term:
        terms = {t["id"]: t.get("name") or "" for t in c.terms()}
        low = args.term.lower()
        courses = [x for x in courses if low in terms.get(x.get("termId"), "").lower()]
    emit(courses, args.format,
         lambda cs: [f"{x['id']}  [{(x.get('termId') or '')}]  {x.get('name')}" for x in cs])


def cmd_tree(args):
    c, _, _ = build_client()
    need_auth(c)
    course = c.resolve_course(args.course)

    def node(n, depth):
        d = {"title": n.get("title"), "id": n.get("id"),
             "handler": (n.get("contentHandler") or {}).get("id"),
             "created": n.get("created"), "modified": n.get("modified")}
        kids = []
        if n.get("hasChildren") and depth < args.depth:
            kids = [node(k, depth + 1) for k in c.children(course["id"], n["id"])]
        if not kids and not args.no_attachments:
            atts = c.attachments(course["id"], n["id"])
            if atts:
                d["attachments"] = [a.get("fileName") for a in atts]
        if kids:
            d["children"] = kids
        return d

    top = c.contents(course["id"])
    emit({"course": course.get("name"), "id": course["id"],
          "children": [node(n, 1) for n in top]}, args.format)


def _walk_files(c: BBClient, cid: str, depth: int):
    for path, n in c.walk(cid, max_depth=depth):
        if n.get("hasChildren"):
            continue
        handler = (n.get("contentHandler") or {}).get("id") or ""
        if handler in ("resource/x-bb-folder", "resource/x-bb-lesson"):
            continue
        atts = c.attachments(cid, n["id"])
        if atts:
            yield {"path": " / ".join(path), "content_id": n["id"],
                   "modified": n.get("modified"),
                   "attachments": [{"id": a["id"], "fileName": a.get("fileName"),
                                    "mime": a.get("mimeType")} for a in atts]}


def _match_rows(rows: list[dict], pattern: str) -> list[dict]:
    """--match applies to both content paths and attachment file names (case-insensitive)."""
    rx = re.compile(pattern, re.I)

    def hay(r: dict) -> str:
        return r["path"] + " " + " ".join(a.get("fileName") or "" for a in r["attachments"])

    return [r for r in rows if rx.search(hay(r))]


def cmd_files(args):
    c, _, _ = build_client()
    need_auth(c)
    course = c.resolve_course(args.course)
    rows = list(_walk_files(c, course["id"], args.depth))
    if args.match:
        rows = _match_rows(rows, args.match)
    emit({"course": course.get("name"), "count": len(rows), "files": rows}, args.format,
          lambda o: [f"{r['path']}  [{', '.join(a['fileName'] or '' for a in r['attachments'])}]" for r in o["files"]])


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_fetch(args):
    c, _, _ = build_client()
    need_auth(c)
    course = c.resolve_course(args.course)
    rows = list(_walk_files(c, course["id"], 12))
    if args.match:
        rows = _match_rows(rows, args.match)
    if args.since:
        rows = [r for r in rows if _date_part(r.get("modified")) >= args.since]
    mime_subs = [m.strip().lower() for m in (args.exclude_mime or "").split(",") if m.strip()]
    exts = {e.strip().lstrip(".").lower() for e in (args.exclude_ext or "").split(",") if e.strip()}
    if not args.no_media_filter:
        exts |= _DEFAULT_MEDIA_EXTS
    max_bytes = int(args.max_size * 1024 * 1024) if args.max_size else None

    def _excluded(a) -> str | None:
        mime = (a.get("mimeType") or "").lower()
        if any(m in mime for m in mime_subs):
            return "mime"
        name = a.get("fileName") or ""
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext in exts:
            return "ext"
        return None

    plan, skipped = [], []
    used: set[str] = set()
    for r in rows:
        for a in r["attachments"]:
            why = _excluded(a)
            if why:
                skipped.append({"file": a.get("fileName") or a["id"], "reason": why})
                continue
            rel = "/".join([_sanitize(p) for p in r["path"].split(" / ")[:-1]]
                           + [_sanitize(a["fileName"] or a["id"])])
            if rel in used:  # same-name attachments in one directory: suffix the attachment id to prevent overwrites
                stem, _, ext = rel.rpartition(".")
                rel = f"{stem}_{a['id'][:8]}.{ext}" if stem else f"{rel}_{a['id'][:8]}"
            used.add(rel)
            plan.append({"rel": rel, "content_id": r["content_id"], "attachment": a})
    if args.dry_run:
        emit({"dry_run": True, "course": course.get("name"), "count": len(plan),
              "plan": plan, "skipped": skipped}, args.format)
        return
    outdir = Path(args.out or ".").expanduser()
    root = Path(args.dest).expanduser() if args.dest else outdir / _sanitize(course.get("name") or course["id"])
    base = root if args.dest else outdir
    done, updated, errors = [], [], []
    for p in plan:
        dest = root / Path(*p["rel"].split("/"))
        if dest.exists() and not args.refresh:
            done.append({"path": str(dest.relative_to(base)), "bytes": "exists"})
            continue
        try:
            if dest.exists() and args.refresh:
                # Re-pull and compare: drop if identical; changed content lands as a new file suffixed with the content hash, the old file is kept (revision history)
                tmp = dest.with_suffix(dest.suffix + ".new")
                c.t.download(c.download_url(course["id"], p["content_id"], p["attachment"]["id"]),
                             tmp, max_bytes=max_bytes)
                digest = _sha256_file(tmp)
                if digest == _sha256_file(dest):
                    tmp.unlink()
                    done.append({"path": str(dest.relative_to(base)), "bytes": "same"})
                    continue
                if "." in dest.name:
                    stem, ext = dest.name.rsplit(".", 1)
                    new = dest.with_name(f"{stem}_{digest[:8]}.{ext}")
                else:
                    new = dest.with_name(f"{dest.name}_{digest[:8]}")
                os.replace(tmp, new)
                updated.append({"path": str(new.relative_to(base)),
                                "old": str(dest.relative_to(base))})
                continue
            n = c.t.download(c.download_url(course["id"], p["content_id"], p["attachment"]["id"]),
                             dest, max_bytes=max_bytes)
            done.append({"path": str(dest.relative_to(base)), "bytes": n})
        except TooLarge as e:
            skipped.append({"file": p["attachment"].get("fileName") or p["attachment"]["id"],
                            "reason": "max-size", "detail": str(e)[:120]})
        except (ApiError, TransportError) as e:
            errors.append({"rel": p["rel"], "error": str(e)[:200]})
    emit({"course": course.get("name"), "out": str(outdir),
          "downloaded": done, "updated": updated, "skipped": skipped, "errors": errors}, args.format)


def cmd_announcements(args):
    c, _, _ = build_client()
    need_auth(c)
    if args.course and args.course != "all":
        course = c.resolve_course(args.course)
        rows = c.announcements(course["id"])
        for r in rows:
            r["courseName"] = course.get("name")
        skipped = []
    else:
        rows, skipped = c.course_announcements_all()
    rows.sort(key=lambda r: r.get("created") or "", reverse=True)
    if args.limit:
        rows = rows[: args.limit]
    if not args.html:
        for r in rows:
            r["bodyText"] = strip_html(r.get("body") or "")

    def _lines(o):
        out = [f"{_date_part(r.get('created'))}  {r.get('courseName', '(institution)')}  {r.get('title')}" for r in o["announcements"]]
        if o.get("skipped"):
            names = ", ".join(s.get("course") or s.get("id") or "?" for s in o["skipped"])
            out.append(f"!! skipped {len(o['skipped'])} course(s) (pull failed): {names}")
        return out

    emit({"count": len(rows), "announcements": rows, "skipped": skipped}, args.format, _lines)


def cmd_dues(args):
    c, _, _ = build_client()
    need_auth(c)
    # Dual-source merge: calendar endpoint + per-course gradebook columns (the calendar misses items, the gradebook is the fallback; for the same course and title keep the calendar entry)
    items = [{"course": r.get("calendarName"), "title": r.get("title"), "source": "calendar",
              "due": r.get("start"), "end": r.get("end"), "type": r.get("type")}
             for r in c.calendar_items()]
    skipped = []
    if args.course:
        course = c.resolve_course(args.course)
        courses = [course]
        low = (course.get("name") or "").lower()
        items = [x for x in items if low in (x["course"] or "").lower()]
    else:
        courses = c.my_courses()
    for course in courses:
        try:
            cols = c.grade_columns(course["id"])
        except (TransportError, ApiError) as e:
            skipped.append({"course": course.get("name"), "id": course.get("id"), "error": str(e)[:120]})
            continue
        for col in cols:
            due = (col.get("grading") or {}).get("due")
            if due:
                items.append({"course": course.get("name"), "title": col.get("name"),
                              "source": "gradebook", "due": due, "end": None, "type": None})
    dedup, seen = [], set()
    for x in sorted(items, key=lambda i: i["source"] != "calendar"):  # stable sort: calendar entries enter first
        k = (" ".join((x["course"] or "").split()), " ".join((x["title"] or "").split()))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(x)
    items = dedup
    if args.from_:
        items = [x for x in items if _date_part(x.get("due")) >= args.from_]
    if args.to:
        items = [x for x in items if _date_part(x.get("due")) <= args.to]
    items.sort(key=lambda x: x.get("due") or "")

    def _lines(o):
        out = [f"{_date_part(r['due'])}  {r['course']}  {r['title']}  [{r['source']}]" for r in o["dues"]]
        if o.get("skipped"):
            names = ", ".join(s.get("course") or s.get("id") or "?" for s in o["skipped"])
            out.append(f"!! skipped {len(o['skipped'])} course gradebook(s) (pull failed): {names}")
        return out

    emit({"count": len(items), "dues": items, "skipped": skipped}, args.format, _lines)


def cmd_assignments(args):
    c, _, _ = build_client()
    need_auth(c)
    course = c.resolve_course(args.course)
    rows = []
    for col in c.grade_columns(course["id"]):
        grading = col.get("grading") or {}
        if not grading.get("due"):
            continue
        st = c.column_status(course["id"], col["id"]) or {}
        rows.append({"name": col.get("name"), "due": grading.get("due"),
                     "possible": (col.get("score") or {}).get("possible"),
                     "status": st.get("status"), "score": st.get("score"),
                     "column_id": col.get("id"), "content_id": col.get("contentId")})
    rows.sort(key=lambda r: r.get("due") or "")
    emit({"course": course.get("name"), "assignments": rows}, args.format,
         lambda o: [f"{_dt_part(r['due'])}  {r['name']}  [{r['status'] or '-'}]" for r in o["assignments"]])


def cmd_submission(args):
    c, _, _ = build_client()
    need_auth(c)
    course = c.resolve_course(args.course)
    uid = c.me()["id"]
    rows = []
    for col in c.grade_columns(course["id"]):
        name = col.get("name") or ""
        if args.match and not re.search(args.match, name, re.I):
            continue
        att = next((a for a in c.column_attempts(course["id"], col["id"])
                    if a.get("userId") == uid), None)
        files = c.attempt_files(course["id"], att["id"]) if att else []
        rows.append({"name": name,
                     "due": (col.get("grading") or {}).get("due"),
                     "status": (att or {}).get("status") or "None",
                     "submitted_at": (att or {}).get("created"),
                     "column_id": col.get("id"), "attempt_id": (att or {}).get("id"),
                     "files": [{"id": f.get("id"), "name": f.get("name")} for f in files]})
    rows.sort(key=lambda r: r.get("due") or "")
    dl = []
    if args.download:
        outdir = Path(args.out or ".").expanduser()
        root = Path(args.dest).expanduser() if args.dest else outdir / _sanitize(course.get("name") or course["id"]) / "submissions"
        base = root if args.dest else outdir
        for r in rows:
            if not r["attempt_id"]:
                continue
            for f in r["files"]:
                dest = root / _sanitize(r["name"] or r["column_id"]) / _sanitize(f["name"] or f["id"])
                if dest.exists():
                    dl.append({"path": str(dest.relative_to(base)), "bytes": "exists"})
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    n = c.t.download(c.attempt_download_url(course["id"], r["attempt_id"], f["id"], f["name"]), dest)
                    dl.append({"path": str(dest.relative_to(base)), "bytes": n})
                except (ApiError, TransportError) as e:
                    dl.append({"file": f.get("name"), "error": str(e)[:200]})
    emit({"course": course.get("name"), "submissions": rows, "downloaded": dl}, args.format,
         lambda o: [f"{_dt_part(r['due']) or '-'}  {r['name']}  [{r['status']}]  "
                    f"submitted {_dt_part(r['submitted_at']) or '-'}  "
                    f"{', '.join(f['name'] or '' for f in r['files'])}" for r in o["submissions"]])


def cmd_grades(args):
    c, _, _ = build_client()
    need_auth(c)
    courses = [c.resolve_course(args.course)] if args.course else c.my_courses()
    out = []
    for course in courses:
        rows = []
        for col in c.grade_columns(course["id"]):
            if args.due_only and not (col.get("grading") or {}).get("due"):
                continue
            st = c.column_status(course["id"], col["id"]) or {}
            rows.append({"name": col.get("name"),
                         "due": (col.get("grading") or {}).get("due"),
                         "possible": (col.get("score") or {}).get("possible"),
                         "status": st.get("status"), "score": st.get("score"),
                         "column_id": col.get("id")})
        out.append({"course": course.get("name"), "columns": rows})
    emit(out if len(out) != 1 else out[0], args.format)


def cmd_roster(args):
    c, _, _ = build_client()
    need_auth(c)
    course = c.resolve_course(args.course)
    rows = c.roster(course["id"])
    slim = [{"userId": r.get("userId"), "role": r.get("courseRoleId"),
             "lastAccessed": r.get("lastAccessed")} for r in rows]
    emit({"course": course.get("name"), "count": len(slim), "members": slim}, args.format)


def cmd_raw(args):
    if args.method.upper() != "GET":
        sys.exit("v1 is read-only: raw accepts GET only")
    c, _, _ = build_client()
    need_auth(c)
    params = {}
    for kv in args.q or []:
        k, _, v = kv.partition("=")
        params[k] = v
    emit(c.get(args.path, params or None), args.format)


# ---- Argument parsing ----
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bb-cli", description="CUHK-SZ Blackboard read-only CLI connector")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--format", choices=["json", "text"], default="json")
    common = argparse.ArgumentParser(add_help=False)  # lets --format be accepted after the subcommand too
    common.add_argument("--format", choices=["json", "text"], default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    def cmd(name: str, help_: str):
        return sub.add_parser(name, help=help_, parents=[common])

    s = cmd("login", "log in and save the session (first login becomes the default account)")
    s.add_argument("--username")
    s.add_argument("--account", help="store the credentials under this account name (default: the username)")
    s.add_argument("--default", action="store_true",
                   help="also make this account the default (automatic re-login only ever uses the default)")
    s.add_argument("--password-env", help="read the password from this environment variable")
    s.add_argument("--no-store", action="store_true", help="do not write the password into the local config")
    s.set_defaults(fn=cmd_login)

    cmd("logout", "log out and clear the local session").set_defaults(fn=cmd_logout)
    cmd("whoami", "current user").set_defaults(fn=cmd_whoami)
    cmd("accounts", "list stored accounts (passwords never shown)").set_defaults(fn=cmd_accounts)

    s = cmd("default", "show or set the default account (the only one auto-login ever uses)")
    s.add_argument("name", nargs="?", help="account name to make the default; omit to show the current one")
    s.set_defaults(fn=cmd_default)

    cmd("status", "session status").set_defaults(fn=cmd_status)
    cmd("terms", "term list").set_defaults(fn=cmd_terms)

    s = cmd("courses", "my courses")
    s.add_argument("--term", help="filter by term name (substring)")
    s.set_defaults(fn=cmd_courses)

    s = cmd("tree", "course content tree")
    s.add_argument("course")
    s.add_argument("--depth", type=int, default=12)
    s.add_argument("--no-attachments", action="store_true")
    s.set_defaults(fn=cmd_tree)

    s = cmd("files", "course file inventory")
    s.add_argument("course")
    s.add_argument("--match", help="regex filter on paths (case-insensitive)")
    s.add_argument("--depth", type=int, default=12)
    s.set_defaults(fn=cmd_files)

    s = cmd("fetch", "download course files (preserving the directory structure)")
    s.add_argument("course")
    s.add_argument("--match")
    s.add_argument("--since", help="only items whose content was modified on or after YYYY-MM-DD")
    s.add_argument("-o", "--out", default=".")
    s.add_argument("--dest", help="exact target directory: land directly here, no course-name prefix appended")
    s.add_argument("--exclude-mime", help="skip attachments whose mimeType contains any substring (comma-separated, e.g. video/,audio/)")
    s.add_argument("--exclude-ext", help="skip attachments with these extensions (comma-separated, e.g. mp4,mov)")
    s.add_argument("--no-media-filter", action="store_true",
                   help="disable the default media-extension filter (only --exclude-mime/--exclude-ext apply)")
    s.add_argument("--max-size", type=float, help="per-file size cap in MB; trips mid-download and skips")
    s.add_argument("--refresh", action="store_true",
                   help="re-pull existing files and compare: identical ones are skipped; changed content lands as a new file suffixed with the content hash (old file kept)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_fetch)

    s = cmd("announcements", "announcements (all courses by default)")
    s.add_argument("--course", help="course substring/id, or all")
    s.add_argument("--limit", type=int)
    s.add_argument("--html", action="store_true", help="keep the raw HTML body")
    s.set_defaults(fn=cmd_announcements)

    s = cmd("dues", "cross-course deadlines (calendar endpoint)")
    s.add_argument("--course")
    s.add_argument("--from", dest="from_")
    s.add_argument("--to")
    s.set_defaults(fn=cmd_dues)

    s = cmd("assignments", "assignment list (columns x my status)")
    s.add_argument("course")
    s.set_defaults(fn=cmd_assignments)

    s = cmd("submission", "my submissions: status x time x files (--download saves them)")
    s.add_argument("course")
    s.add_argument("--match", help="regex filter on assignment names (case-insensitive)")
    s.add_argument("--download", action="store_true", help="download submitted files to course/submissions/assignment/")
    s.add_argument("-o", "--out", default=".")
    s.add_argument("--dest", help="exact target directory: land directly here (still grouped assignment/file underneath), no course-name/submissions prefix appended")
    s.set_defaults(fn=cmd_submission)

    s = cmd("grades", "gradebook (all courses by default)")
    s.add_argument("course", nargs="?")
    s.add_argument("--due-only", action="store_true")
    s.set_defaults(fn=cmd_grades)

    s = cmd("roster", "course member list")
    s.add_argument("course")
    s.set_defaults(fn=cmd_roster)

    s = cmd("raw", "arbitrary REST GET pass-through (/learn/api/public/v1/...)")
    s.add_argument("method")
    s.add_argument("path")
    s.add_argument("--q", action="append", help="query parameter k=v (repeatable)")
    s.set_defaults(fn=cmd_raw)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except (auth.CredentialError,) as e:
        print(f"Credential error: {e}", file=sys.stderr)
        sys.exit(2)
    except auth.AuthError as e:
        print(f"Login failed: {e}", file=sys.stderr)
        sys.exit(2)
    except (TransportError, ApiError) as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
