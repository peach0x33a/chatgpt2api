from __future__ import annotations

import unittest

from services.openai_backend_api import OpenAIBackendAPI


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}
    text = ""

    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict) -> None:
        self.headers: dict[str, str] = {}
        self.payload = payload
        self.patch_calls: list[str] = []
        self.get_calls: list[str] = []

    def get(self, url: str, **kwargs):
        self.get_calls.append(url)
        return FakeResponse(self.payload)

    def patch(self, url: str, **kwargs):
        self.patch_calls.append(url)
        # 上游只会回显被改的那个 flag
        value = url.rsplit("value=", 1)[-1] == "true"
        return FakeResponse({"m3m": value})


class AccountFeatureToggleTests(unittest.TestCase):
    def _backend(self, payload: dict) -> tuple[OpenAIBackendAPI, FakeSession]:
        backend = OpenAIBackendAPI(access_token="")
        session = FakeSession(payload)
        backend.session = session  # type: ignore[assignment]
        return backend, session

    def test_settings_only_returns_settings_map(self) -> None:
        backend, _ = self._backend({"settings": {"m3m": True, "sunshine": True}, "flags": {}})
        self.assertEqual(backend.get_account_settings(), {"m3m": True, "sunshine": True})

    def test_settings_missing_map_becomes_empty(self) -> None:
        backend, _ = self._backend({"flags": {}})
        self.assertEqual(backend.get_account_settings(), {})

    def test_toggle_puts_parameters_in_query_string(self) -> None:
        backend, session = self._backend({"settings": {"m3m": False}})

        result = backend.set_account_feature("m3m", False)

        self.assertEqual(result, {"m3m": False})
        self.assertEqual(len(session.patch_calls), 1)
        url = session.patch_calls[0]
        self.assertIn("/backend-api/settings/account_user_setting", url)
        self.assertIn("feature=m3m", url)
        self.assertIn("value=false", url)

    def test_toggle_value_is_lowercase_literal(self) -> None:
        backend, session = self._backend({})
        backend.set_account_feature("m3m", True)
        # 上游只接受小写 true/false，Python 的 True 不能直接拼进去
        self.assertIn("value=true", session.patch_calls[0])
        self.assertNotIn("value=True", session.patch_calls[0])


if __name__ == "__main__":
    unittest.main()
