from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("CHATGPT2API_AUTH_KEY", "test-auth")

from services.account_service import AccountService
from services.config import config
from services.storage.json_storage import JSONStorageBackend


class AccountScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_mode = config.data.get("image_account_schedule_mode")
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.addCleanup(self._restore_mode)

    def _restore_mode(self) -> None:
        if self._original_mode is None:
            config.data.pop("image_account_schedule_mode", None)
        else:
            config.data["image_account_schedule_mode"] = self._original_mode

    def _make_service(self) -> AccountService:
        service = AccountService(JSONStorageBackend(Path(self._tmp_dir.name) / "accounts.json"))
        service.add_account_items(
            [
                {"access_token": "token-1", "status": "正常", "quota": 3},
                {"access_token": "token-2", "status": "正常", "quota": 3},
            ]
        )
        service.fetch_remote_info = lambda access_token, event="fetch_remote_info": service.get_account(access_token)
        return service

    def test_round_robin_alternates_accounts(self) -> None:
        config.data["image_account_schedule_mode"] = "round_robin"
        service = self._make_service()

        first = service.get_available_access_token()
        service.release_image_slot(first)
        second = service.get_available_access_token()
        service.release_image_slot(second)

        self.assertEqual([first, second], ["token-1", "token-2"])

    def test_sequential_reuses_first_account_until_quota_exhausted(self) -> None:
        config.data["image_account_schedule_mode"] = "sequential"
        service = self._make_service()

        first = service.get_available_access_token()
        service.release_image_slot(first)
        second = service.get_available_access_token()
        service.release_image_slot(second)

        self.assertEqual([first, second], ["token-1", "token-1"])

        service.update_account("token-1", {"status": "限流", "quota": 0})
        service.release_image_slot("token-1")
        next_token = service.get_available_access_token()
        service.release_image_slot(next_token)

        self.assertEqual(next_token, "token-2")

    def test_schedule_mode_normalizes_unknown_values(self) -> None:
        config.data["image_account_schedule_mode"] = "unknown"
        self.assertEqual(config.image_account_schedule_mode, "round_robin")

        config.data["image_account_schedule_mode"] = "SEQUENTIAL"
        self.assertEqual(config.image_account_schedule_mode, "sequential")


if __name__ == "__main__":
    unittest.main()
