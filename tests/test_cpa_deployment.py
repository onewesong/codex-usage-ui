import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from history_store import load_history_samples, save_history_snapshot_if_changed

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fetch_cpa_usage", ROOT / "deploy/outer/fetch_cpa_usage.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def snapshot(account_id, percent):
    return {"account_id": account_id, "email": account_id + "@example.test", "plan_type": "plus",
            "rate_limit": {"allowed": True, "limit_reached": False,
                           "primary_window": {"used_percent": percent, "limit_window_seconds": 18000, "reset_at": 2000000000}}}


class CPADeploymentTest(unittest.TestCase):
    def test_accounts_are_fetched_via_cpa_without_exporting_credentials(self):
        client = adapter.CPAClient("management-secret")
        files = [{"provider": "codex", "auth_index": account, "email": account + "@example.test",
                  "id_token": {"chatgpt_account_id": account}, "access_token": "never-export-this"}
                 for account in ("a", "b")]
        files.append({"provider": "other", "auth_index": "skip"})
        files.append(dict(files[0], auth_index="duplicate"))

        def request(path, payload=None):
            if path.endswith("auth-files"):
                return {"files": files}
            self.assertEqual(path, "/v0/management/api-call")
            self.assertEqual(payload["url"], "https://chatgpt.com/backend-api/wham/usage")
            self.assertEqual(payload["header"]["Authorization"], "Bearer $TOKEN$")
            self.assertEqual(payload["header"]["ChatGPT-Account-Id"], payload["auth_index"])
            return {"status_code": 200, "body": json.dumps(snapshot(payload["auth_index"], 20))}

        with mock.patch.object(client, "request", side_effect=request):
            result = client.snapshot()
        self.assertEqual({a["account_id"] for a in result["accounts"]}, {"a", "b"})
        self.assertNotIn("never-export-this", json.dumps(result))
        self.assertNotIn("management-secret", json.dumps(result))

    def test_failed_account_does_not_hide_successful_accounts_or_leak_error_body(self):
        client = adapter.CPAClient("key")
        files = [{"provider": "codex", "auth_index": index} for index in ("good", "bad")]

        def request(path, payload=None):
            if path.endswith("auth-files"):
                return {"files": files}
            if payload["auth_index"] == "bad":
                return {"status_code": 401, "body": "sensitive diagnostic"}
            return {"status_code": 200, "body": json.dumps(snapshot("good", 20))}

        with mock.patch.object(client, "request", side_effect=request):
            accounts = client.snapshot()["accounts"]
        self.assertIn("rate_limit", accounts[0])
        self.assertIn("401", accounts[1]["error"])
        self.assertNotIn("sensitive diagnostic", json.dumps(accounts))

    def test_history_changes_are_isolated_by_account(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "history.sqlite3"
            data = {"accounts": [snapshot("a", 10), snapshot("b", 20)]}
            self.assertEqual(save_history_snapshot_if_changed(data, db_path=db, sampled_at=1900000000)["inserted_series_count"], 2)
            self.assertEqual(save_history_snapshot_if_changed(data, db_path=db, sampled_at=1900000300)["inserted_series_count"], 0)
            data["accounts"][0]["rate_limit"]["primary_window"]["used_percent"] = 30
            self.assertEqual(save_history_snapshot_if_changed(data, db_path=db, sampled_at=1900000600)["inserted_series_count"], 1)
            rows = load_history_samples("全部", db_path=db)
            self.assertEqual(rows.groupby("account_id").size().to_dict(), {"a": 2, "b": 1})

    def test_ui_can_switch_between_accounts(self):
        from streamlit.testing.v1 import AppTest
        data = {"accounts": [snapshot("a", 10), snapshot("b", 20)]}
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {
            "CODEX_USAGE_DB_PATH": str(Path(directory) / "ui.sqlite3"), "CODEX_USAGE_AUTO_COLLECTOR": "0",
        }), mock.patch("codex_usage.fetch_usage_snapshot", return_value=("test CPA", json.dumps(data), data)):
            app = AppTest.from_file(str(ROOT / "codex_usage_app.py")).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            self.assertEqual(json.loads(app.code[0].value)["account_id"], "a")
            app.selectbox[0].select_index(1).run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(json.loads(app.code[0].value)["account_id"], "b")


if __name__ == "__main__":
    unittest.main()
