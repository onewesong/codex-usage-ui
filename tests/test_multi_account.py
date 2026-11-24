import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from codex_usage import account_snapshots, fetch_usage_from_script, human_summary
from collect_history import collect_once
from history_store import load_history_samples, save_history_snapshot_if_changed

ROOT = Path(__file__).resolve().parents[1]


def snapshot(account_id, percent=10):
    return {
        "account_id": account_id, "email": account_id + "@example.com", "plan_type": "plus",
        "rate_limit": {
            "allowed": True, "limit_reached": False,
            "primary_window": {"used_percent": percent, "limit_window_seconds": 18000, "reset_at": 2000000000},
        },
    }


class PayloadTest(unittest.TestCase):
    def test_legacy_and_empty_payloads(self):
        legacy = {"plan_type": "plus", "rate_limit": {}}
        self.assertEqual(account_snapshots(legacy), [legacy])
        self.assertEqual(account_snapshots({"accounts": []}), [])

    def test_invalid_account_envelopes_are_rejected(self):
        for data in (
            [], {"accounts": {}}, {"accounts": [None]}, {"accounts": [{}]},
            {"accounts": [{"account_id": " "}]},
            {"accounts": [snapshot("a"), snapshot("a")]},
            {"accounts": [{"account_id": "a", "accounts": []}]},
            {"accounts": [{"account_id": "a", "error": 123}]},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                account_snapshots(data)

    def test_custom_fetcher_validates_without_changing_raw_output(self):
        body = json.dumps({"accounts": [snapshot("a"), snapshot("b")]})
        result = subprocess.CompletedProcess(["fetch-example"], 0, stdout=body, stderr="")
        with mock.patch("codex_usage.subprocess.run", return_value=result):
            raw, data = fetch_usage_from_script("fetch-example")
        self.assertEqual(raw, body)
        self.assertEqual(len(account_snapshots(data)), 2)
        result.stdout = '{"accounts":[{}]}'
        with mock.patch("codex_usage.subprocess.run", return_value=result), self.assertRaises(ValueError):
            fetch_usage_from_script("fetch-example")

    def test_human_output_includes_successful_and_failed_accounts(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            human_summary({"accounts": [snapshot("a"), {"account_id": "b", "error": "temporarily unavailable"}]})
        self.assertIn("a@example.com", output.getvalue())
        self.assertIn("10%", output.getvalue())
        self.assertIn("b", output.getvalue())
        self.assertIn("temporarily unavailable", output.getvalue())

    def test_cli_accepts_generic_example(self):
        env = {**os.environ, "CODEX_USAGE_FETCH_SCRIPT": "cat examples/multi-account-snapshot.json"}
        result = subprocess.run([sys.executable, "get-codex-usage.py", "--human"], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        self.assertIn("alice@example.com", result.stdout)
        self.assertIn("bob@example.com", result.stdout)


class HistoryTest(unittest.TestCase):
    def test_change_detection_and_queries_are_scoped_to_account(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "history.sqlite3"
            data = {"accounts": [snapshot("a", 10), snapshot("b", 20)]}
            def save(time):
                return save_history_snapshot_if_changed(data, db_path=db, sampled_at=time)["inserted_series_count"]
            self.assertEqual(save(1900000000), 2)
            self.assertEqual(save(1900000300), 0)
            data["accounts"][0]["rate_limit"]["primary_window"]["used_percent"] = 30
            self.assertEqual(save(1900000600), 1)
            self.assertEqual(len(load_history_samples("全部", db_path=db, account_id="a")), 2)
            self.assertEqual(len(load_history_samples("全部", db_path=db, account_id="b")), 1)
            self.assertTrue(load_history_samples("全部", db_path=db, account_id="a' OR 1=1 --").empty)

    def test_legacy_history_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "history.sqlite3"
            legacy = snapshot("legacy")
            del legacy["account_id"]
            save_history_snapshot_if_changed(legacy, db_path=db)
            save_history_snapshot_if_changed({"accounts": [snapshot("a")]}, db_path=db)
            self.assertEqual(len(load_history_samples("全部", db_path=db)), 2)
            self.assertEqual(len(load_history_samples("全部", db_path=db, account_id="")), 1)
            self.assertEqual(len(load_history_samples("全部", db_path=db, account_id="a")), 1)

    def test_partial_and_total_collection_failures(self):
        failed = {"account_id": "b", "error": "temporarily unavailable"}
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"CODEX_USAGE_DB_PATH": str(Path(directory) / "history.sqlite3")}):
            data = {"accounts": [snapshot("a"), failed]}
            with mock.patch("collect_history.fetch_usage_snapshot", return_value=("example", "{}", data)):
                self.assertEqual(collect_once()["result"], "saved")
            data = {"accounts": [failed]}
            with mock.patch("collect_history.fetch_usage_snapshot", return_value=("example", "{}", data)):
                self.assertEqual(collect_once()["result"], "error")
            self.assertEqual(set(load_history_samples("全部")["account_id"]), {"a"})


class UITest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict(os.environ, {
            "CODEX_USAGE_DB_PATH": str(Path(self.directory.name) / "history.sqlite3"),
            "CODEX_USAGE_AUTO_COLLECTOR": "0",
        })
        patch.start()
        self.addCleanup(patch.stop)
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)

    def app(self):
        return AppTest.from_file(str(ROOT / "codex_usage_app.py")).run(timeout=20)

    def test_selection_survives_reordering_and_handles_removed_account(self):
        data = {"accounts": [snapshot("a"), snapshot("b")]}
        with mock.patch("codex_usage.fetch_usage_snapshot", side_effect=lambda: ("example", json.dumps(data), copy.deepcopy(data))):
            app = self.app()
            app.selectbox[0].select("b").run()
            self.assertFalse(app.exception)
            self.assertEqual(json.loads(app.code[0].value)["account_id"], "b")
            data["accounts"].reverse()
            st.cache_data.clear()
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(json.loads(app.code[0].value)["account_id"], "b")
            data["accounts"] = [snapshot("a")]
            st.cache_data.clear()
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(json.loads(app.code[0].value)["account_id"], "a")

    def test_failed_account_keeps_history_and_does_not_block_switching(self):
        save_history_snapshot_if_changed(snapshot("b"))
        data = {"accounts": [snapshot("a"), {"account_id": "b", "error": "temporarily unavailable"}]}
        with mock.patch("codex_usage.fetch_usage_snapshot", return_value=("example", json.dumps(data), data)):
            app = self.app()
            app.selectbox[0].select("b").run()
            self.assertFalse(app.exception)
            self.assertIn("temporarily unavailable", app.error[0].value)
            self.assertTrue(app.radio)
            app.selectbox[0].select("a").run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)

    def test_empty_and_legacy_single_account(self):
        for data in ({"accounts": []}, snapshot("single")):
            with self.subTest(data=data), mock.patch("codex_usage.fetch_usage_snapshot", return_value=("example", json.dumps(data), data)):
                st.cache_data.clear()
                app = self.app()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertFalse(app.selectbox)

    def test_history_chart_only_contains_selected_account(self):
        data = {"accounts": [snapshot("a", 10), snapshot("b", 70)]}
        save_history_snapshot_if_changed(data, sampled_at=1900000000)
        updated = {"accounts": [snapshot("a", 20), snapshot("b", 80)]}
        save_history_snapshot_if_changed(updated, sampled_at=1900000300)
        with mock.patch("codex_usage.fetch_usage_snapshot", return_value=("example", json.dumps(updated), updated)), mock.patch(
            "history_store.pd.read_sql_query", wraps=pd.read_sql_query
        ) as read_sql:
            app = self.app()
            app.radio[0].set_value("全部").run()
            self.assertFalse(app.exception)
            self.assertEqual(read_sql.call_args.kwargs["params"], ["a"])
            app.selectbox[0].select("b").run()
            self.assertFalse(app.exception)
            self.assertEqual(read_sql.call_args.kwargs["params"], ["b"])


if __name__ == "__main__":
    unittest.main()
