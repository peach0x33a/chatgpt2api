from __future__ import annotations

import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.accounts as accounts_module
from services.config import config


def _auth_headers() -> dict[str, str]:
    # 其他测试可能通过环境变量覆盖 auth-key，这里跟随当前配置。
    return {"Authorization": f"Bearer {config.auth_key}"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(accounts_module.create_router())
    return TestClient(app)


class AccountResponseShapeTests(unittest.TestCase):
    def test_create_accounts_returns_only_summary(self) -> None:
        client = _client()
        summary = {"email": "a@b.com", "type": "Plus", "status": "正常", "quota": 25}
        raw_account = {"access_token": "at", "refresh_token": "rt", "id_token": "it", "password": "pw"}
        with (
            mock.patch.object(
                accounts_module.account_service,
                "add_accounts",
                return_value={"added": 1, "skipped": 0, "items": [raw_account]},
            ),
            mock.patch.object(
                accounts_module.account_service,
                "refresh_accounts",
                return_value={"refreshed": 1, "errors": [], "items": [raw_account]},
            ),
            mock.patch.object(
                accounts_module.account_service,
                "summarize_tokens",
                return_value=[summary],
            ),
        ):
            response = client.post("/api/accounts", json={"tokens": ["at"]}, headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body.keys()), {"added", "skipped", "refreshed", "errors", "accounts"})
        self.assertEqual(body["accounts"], [summary])
        for secret in ("access_token", "refresh_token", "id_token", "password"):
            self.assertNotIn(secret, response.text)

    def test_delete_accounts_returns_only_removed(self) -> None:
        client = _client()
        with mock.patch.object(
            accounts_module.account_service,
            "delete_accounts",
            return_value={"removed": 2, "items": [{"access_token": "at"}]},
        ):
            response = client.request(
                "DELETE", "/api/accounts", json={"tokens": ["at"]}, headers=_auth_headers()
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"removed": 2})

    def test_update_account_returns_only_summary(self) -> None:
        client = _client()
        summary = {"email": "a@b.com", "type": "Plus", "status": "正常", "quota": 10}
        stored = {"access_token": "at", "refresh_token": "rt", **summary}
        with (
            mock.patch.object(accounts_module.account_service, "update_account", return_value=stored),
            mock.patch.object(accounts_module.account_service, "account_summary", return_value=summary),
        ):
            response = client.post(
                "/api/accounts/update",
                json={"access_token": "at", "quota": 10},
                headers=_auth_headers(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"account": summary})
        self.assertNotIn("refresh_token", response.text)

    def test_refresh_progress_drops_pool_items(self) -> None:
        client = _client()
        progress = {
            "total": 1,
            "processed": 1,
            "done": True,
            "error": None,
            "result": {
                "refreshed": 1,
                "errors": [],
                "relogined": 0,
                "items": [{"access_token": "at", "refresh_token": "rt"}],
            },
        }
        with mock.patch.object(
            accounts_module.account_service,
            "get_refresh_progress",
            return_value=progress,
        ):
            response = client.get("/api/accounts/refresh/progress/abc", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("items", response.json()["result"])
        self.assertNotIn("access_token", response.text)


if __name__ == "__main__":
    unittest.main()
