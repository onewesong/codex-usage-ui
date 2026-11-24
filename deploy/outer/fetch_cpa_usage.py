#!/usr/bin/env python3
"""Read every Codex account's quota through the local CPA management API."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CPAClient:
    def __init__(self, key: str, base_url: str = "http://127.0.0.1:8317"):
        self.key = key
        self.base_url = base_url
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path: str, payload=None):
        headers = {"Authorization": "Bearer " + self.key, "Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers)
        try:
            with self.opener.open(request, timeout=12) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"CPA management API returned HTTP {exc.code}") from None
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"CPA management API unavailable ({type(exc).__name__})") from None
        if not isinstance(result, dict):
            raise RuntimeError("CPA returned an invalid response object")
        return result

    def fetch_account(self, auth):
        claims = auth.get("id_token")
        claims = claims if isinstance(claims, dict) else {}
        index = str(auth.get("auth_index") or "")
        account_id = str(claims.get("chatgpt_account_id") or "cpa:" + index)
        identity = {
            "account_id": account_id,
            "email": str(auth.get("email") or auth.get("name") or index),
            "plan_type": str(claims.get("plan_type") or "unknown"),
        }
        try:
            if not index:
                raise RuntimeError("CPA account has no auth_index")
            if auth.get("disabled"):
                raise RuntimeError("CPA account is disabled")
            headers = {"Authorization": "Bearer $TOKEN$", "Accept": "application/json"}
            if claims.get("chatgpt_account_id"):
                headers["ChatGPT-Account-Id"] = str(claims["chatgpt_account_id"])
            result = self.request("/v0/management/api-call", {
                "auth_index": index,
                "method": "GET",
                "url": "https://chatgpt.com/backend-api/wham/usage",
                "header": headers,
            })
            if result.get("status_code") != 200:
                raise RuntimeError(f"Codex quota API returned HTTP {result.get('status_code', 'unknown')}")
            usage = json.loads(result.get("body", ""))
            if not isinstance(usage, dict) or not isinstance(usage.get("rate_limit"), dict):
                raise RuntimeError("Codex quota API returned no rate_limit object")
            usage["account_id"] = account_id
            usage["email"] = identity["email"]
            return usage
        except (RuntimeError, ValueError, TypeError) as exc:
            return {**identity, "error": str(exc)}

    def snapshot(self):
        files = self.request("/v0/management/auth-files").get("files")
        if not isinstance(files, list):
            raise RuntimeError("CPA returned no auth-files list")
        accounts, seen = [], set()
        for auth in sorted(files, key=lambda item: (bool(item.get("disabled")), str(item.get("name", "")))):
            if str(auth.get("provider") or auth.get("type")).lower() != "codex":
                continue
            claims = auth.get("id_token")
            claims = claims if isinstance(claims, dict) else {}
            identity = claims.get("chatgpt_account_id") or auth.get("auth_index") or auth.get("name")
            if identity in seen:
                continue
            seen.add(identity)
            accounts.append(auth)
        if not accounts:
            raise RuntimeError("CPA has no Codex accounts")
        with ThreadPoolExecutor(max_workers=4) as pool:
            snapshots = list(pool.map(self.fetch_account, accounts))
        return {"source": "local-cpa", "accounts": snapshots}


def main():
    try:
        key_path = Path(os.environ["CPA_MANAGEMENT_KEY_FILE"])
        key = key_path.read_text().strip()
        if not key or "\n" in key or "\r" in key:
            raise RuntimeError("CPA management key file must contain one nonempty key")
        print(json.dumps(CPAClient(key).snapshot(), ensure_ascii=False))
    except Exception as exc:
        # Never print a request, auth-file payload, key, token or upstream response body.
        print(f"CPA quota fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
