"""Offline regressions: synthetic cookies only; no user config or requests."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from curl_cffi import requests as creq
from siscli import cli, config
from siscli.transport import Transport


class StatusTests(unittest.TestCase):
    def run_status(self, jar=None, cfg=None, env=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            if jar is not None:
                path.write_text(json.dumps(jar), encoding="utf-8")
            with patch.dict(os.environ, env or {}, clear=True), \
                    patch.object(config, "session_path", return_value=path):
                transport = Transport()
                sis = SimpleNamespace(transport=transport, cfg=cfg or {})
                before = path.read_bytes() if path.exists() else None
                with patch.object(transport._sess, "request", side_effect=AssertionError("network forbidden")), \
                        patch.object(cli, "Sis", return_value=sis), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    result = cli.main(["status"])
                self.assertEqual(result, 0)
                self.assertEqual(before, path.read_bytes() if path.exists() else None)
                text = output.getvalue()
                for secret in ("test-secret", "test-token", "test-user"):
                    self.assertNotIn(secret, text)
                data = json.loads(text)
                self.assertIsNone(data["authenticated"])
                self.assertFalse(data["authentication_checked"])
                self.assertIsNone(data["reachable"])
                self.assertFalse(data["network_checked"])
                return data

    def test_missing_session_and_credentials_does_not_exit_or_login(self):
        data = self.run_status()
        self.assertEqual(data["session"], "absent_or_unusable")
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_cached_token_never_implies_authenticated(self):
        data = self.run_status([{"name": "PS_TOKEN", "value": "test-token"}])
        self.assertEqual(data["session"], "cached_unverified")
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_stored_credentials_are_not_used_to_login(self):
        data = self.run_status(cfg={"username": "test-user", "password": "test-secret"})
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_environment_credentials_follow_resolver(self):
        data = self.run_status(env={config.ENV_USERNAME: "test-user", config.ENV_PASSWORD: "test-secret"})
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_partial_credentials_block_relogin(self):
        data = self.run_status(cfg={"username": "test-user"})
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_non_token_jar_is_not_authenticated(self):
        data = self.run_status([{"name": "PS_DEVICEFEATURES", "value": "test-token"}])
        self.assertEqual(data["session"], "absent_or_unusable")

    def test_malformed_cookie_entries_are_reported_without_details(self):
        data = self.run_status([{"value": "test-secret"}])
        self.assertEqual(data["session"], "unreadable")

    def test_unreadable_session_does_not_hide_credential_availability(self):
        with patch.object(Transport, "load_session", side_effect=OSError("test-secret")):
            data = self.run_status(cfg={"username": "test-user", "password": "test-secret"})
        self.assertEqual(data["session"], "unreadable")
        self.assertEqual(data["relogin"], "credentials_available_unverified")


class StatusIntegrationTests(unittest.TestCase):
    """Exercise real Sis construction and config loading in a synthetic home."""

    def run_status(self, config_bytes=None, session_bytes=None, absent_home=False):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "synthetic-home"
            if not absent_home:
                home.mkdir()
            for name, content in (("config.json", config_bytes), ("session.json", session_bytes)):
                if content is not None:
                    (home / name).write_bytes(content)

            def snapshot():
                return {str(p.relative_to(home)): p.read_bytes() for p in home.rglob("*") if p.is_file()}

            before = snapshot()
            with patch.dict(os.environ, {"SIS_CLI_HOME": str(home)}, clear=True), \
                    patch.object(creq.Session, "request", side_effect=AssertionError("network forbidden")) as request, \
                    patch("socket.socket.connect", side_effect=AssertionError("network forbidden")) as connect, \
                    patch.object(cli.Sis, "_relogin", side_effect=AssertionError("login forbidden")) as login, \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                result = cli.main(["status"])
            self.assertEqual(result, 0)
            request.assert_not_called()
            connect.assert_not_called()
            login.assert_not_called()
            self.assertEqual(before, snapshot())
            text = output.getvalue() + errors.getvalue()
            for secret in ("test-user", "test-secret", "test-token"):
                self.assertNotIn(secret, text)
            self.assertEqual(errors.getvalue(), "")
            data = json.loads(output.getvalue())
            self.assertIsNone(data["authenticated"])
            self.assertIsNone(data["reachable"])
            self.assertFalse(data["authentication_checked"])
            self.assertFalse(data["network_checked"])
            return data

    def test_non_object_configs_do_not_crash(self):
        for value in (None, [1], "test-secret", 1, True, []):
            with self.subTest(value=value):
                data = self.run_status(config_bytes=json.dumps(value).encode("utf-8"))
                self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_invalid_config_json_is_unavailable_without_rewrite(self):
        data = self.run_status(config_bytes=b'{"password": "test-secret"')
        self.assertEqual(data["relogin"], "blocked_missing_credentials")

    def test_session_errors_handled_by_loader_are_absent_or_unusable(self):
        for content in (b"invalid-json", b"\xff", b"[]", b"{}"):
            with self.subTest(content=content):
                data = self.run_status(session_bytes=content)
                self.assertEqual(data["session"], "absent_or_unusable")

    def test_malformed_cookie_entry_is_unreadable(self):
        data = self.run_status(session_bytes=b'[{"value": "test-token"}]')
        self.assertEqual(data["session"], "unreadable")

    def test_cached_session_and_stored_credentials_remain_unchanged(self):
        data = self.run_status(
            config_bytes=b'{"username": "test-user", "password": "test-secret"}',
            session_bytes=b'[{"name": "PS_TOKEN", "value": "test-token"}]')
        self.assertEqual(data["session"], "cached_unverified")
        self.assertEqual(data["relogin"], "credentials_available_unverified")

    def test_missing_home_creates_no_authentication_files(self):
        data = self.run_status(absent_home=True)
        self.assertEqual(data["session"], "absent_or_unusable")
        self.assertEqual(data["relogin"], "blocked_missing_credentials")


if __name__ == "__main__":
    unittest.main()
