from __future__ import annotations

import unittest
from unittest import mock

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
        self.calls: list[str] = []

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        return FakeResponse(self.payload)


class AccountMemoryParseTests(unittest.TestCase):
    """上游字段名不能直接漏给前端，解析层要挡一层。"""

    def _backend(self, payload: dict) -> OpenAIBackendAPI:
        backend = OpenAIBackendAPI(access_token="")
        backend.session = FakeSession(payload)  # type: ignore[assignment]
        return backend

    def test_memories_are_normalized(self) -> None:
        backend = self._backend({
            "memories": [
                {"id": "m1", "content": "喜欢扁平插画", "created_at": "2026-01-01", "updated_at": "2026-01-02"},
                {"id": "m2", "content": "常用中文"},          # 缺时间字段
                {"id": "m3"},                                # 没内容，保留空串
                "not-a-dict",                                 # 脏数据要跳过
            ],
            "memory_num_tokens": 12,
            "memory_max_tokens": 5000000,
        })

        result = backend.get_memories()

        self.assertEqual([item["id"] for item in result["memories"]], ["m1", "m2", "m3"])
        self.assertEqual(result["memories"][0]["content"], "喜欢扁平插画")
        self.assertEqual(result["memories"][1]["updated_at"], None)
        self.assertEqual(result["memories"][2]["content"], "")
        self.assertEqual(result["memory_num_tokens"], 12)
        self.assertEqual(result["memory_max_tokens"], 5000000)

    def test_missing_memories_becomes_empty_list(self) -> None:
        result = self._backend({}).get_memories()
        self.assertEqual(result["memories"], [])
        self.assertIsNone(result["memory_num_tokens"])

    def test_system_messages_keep_only_known_fields(self) -> None:
        backend = self._backend({
            "about_user_message": "我是后端工程师",
            "name_user_message": "老王",
            "enabled": True,
            "traits_enabled": False,
            "disabled_tools": ["image_gen"],
            "unexpected_internal_field": "should-not-leak",
        })

        result = backend.get_user_system_messages()

        self.assertEqual(result["about_user_message"], "我是后端工程师")
        self.assertEqual(result["name_user_message"], "老王")
        self.assertIs(result["enabled"], True)
        self.assertIs(result["traits_enabled"], False)
        self.assertEqual(result["disabled_tools"], ["image_gen"])
        self.assertNotIn("unexpected_internal_field", result)
        # 没返回的字段统一补空串，前端不必再判 undefined。
        self.assertEqual(result["about_model_message"], "")

    def test_system_messages_defaults(self) -> None:
        result = self._backend({}).get_user_system_messages()
        self.assertEqual(result["about_user_message"], "")
        self.assertIs(result["enabled"], False)
        self.assertEqual(result["disabled_tools"], [])


if __name__ == "__main__":
    unittest.main()
