from __future__ import annotations

import unittest
from unittest import mock

from services.config import config
from services.openai_backend_api import ChatRequirements, OpenAIBackendAPI
from services.protocol import anthropic_v1_messages, openai_v1_chat_complete, openai_v1_response
from services.protocol.chat_completion_cache import normalize_text_messages


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}
    text = ""

    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """只记录请求体，不真的出网。"""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs.get("json") or {}))
        if url.endswith("/prepare"):
            return FakeResponse({"conduit_token": "conduit-1"})
        return FakeResponse({})


class TextAccountTraceTests(unittest.TestCase):
    """文字链路要把实际使用的账号带出来，日志才有得溯源。"""

    def test_stream_text_completion_reports_account_email(self) -> None:
        def fake_stream(_backend, request):
            request.account_email = "text@example.com"
            yield "hello"

        with (
            mock.patch.object(openai_v1_chat_complete, "text_backend", return_value=object()),
            mock.patch.object(openai_v1_chat_complete, "stream_text_deltas", side_effect=fake_stream),
        ):
            chunks = list(openai_v1_chat_complete.handle({
                "model": "auto",
                "stream": True,
                "messages": [{"role": "user", "content": "who am i"}],
            }))

        self.assertEqual(chunks[-1]["_account_email"], "text@example.com")
        # 中间帧不该带，避免客户端看到内部字段。
        for chunk in chunks[:-1]:
            self.assertNotIn("_account_email", chunk)

    def test_non_stream_text_completion_reports_account_email(self) -> None:
        def fake_collect(_backend, request):
            request.account_email = "text@example.com"
            return "ok"

        with (
            mock.patch.object(openai_v1_chat_complete, "text_backend", return_value=object()),
            mock.patch.object(openai_v1_chat_complete, "collect_text", side_effect=fake_collect),
        ):
            response = openai_v1_chat_complete.handle({
                "model": "auto",
                "messages": [{"role": "user", "content": "who am i"}],
            })

        self.assertEqual(response["_account_email"], "text@example.com")

    def test_responses_text_reports_account_email(self) -> None:
        def fake_stream(_backend, request):
            request.account_email = "text@example.com"
            yield "ok"

        with (
            mock.patch.object(openai_v1_response, "text_backend", return_value=object()),
            mock.patch.object(openai_v1_response, "stream_text_deltas", side_effect=fake_stream),
        ):
            events = list(openai_v1_response.handle({"model": "auto", "input": "hi", "stream": True}))

        completed = [event for event in events if event.get("type") == "response.completed"]
        self.assertEqual(completed[-1]["_account_email"], "text@example.com")

    def test_responses_non_stream_reports_account_email(self) -> None:
        def fake_stream(_backend, request):
            request.account_email = "text@example.com"
            yield "ok"

        with (
            mock.patch.object(openai_v1_response, "text_backend", return_value=object()),
            mock.patch.object(openai_v1_response, "stream_text_deltas", side_effect=fake_stream),
        ):
            response = openai_v1_response.handle({"model": "auto", "input": "hi"})

        self.assertEqual(response["_account_email"], "text@example.com")

    def test_anthropic_stream_carries_account_on_message_stop(self) -> None:
        chunks = [
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "hi"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "_account_email": "text@example.com"},
        ]
        events = list(anthropic_v1_messages.stream_events(
            iter(chunks), "auto", 1, lambda text: len(text),
        ))
        stop = [event for event in events if event.get("type") == "message_stop"][-1]
        self.assertEqual(stop["_account_email"], "text@example.com")

    def test_anthropic_non_stream_reports_account_email(self) -> None:
        with mock.patch.object(anthropic_v1_messages.OpenAIBackendAPI, "close"):
            backend = anthropic_v1_messages.OpenAIBackendAPI(access_token="")
            request = anthropic_v1_messages.MessageRequest(
                backend=backend,
                messages=[{"role": "user", "content": "hi"}],
                model="auto",
            )
            with (
                mock.patch.object(anthropic_v1_messages, "message_request", return_value=request),
                mock.patch.object(
                    anthropic_v1_messages,
                    "stream_text_chat_completion",
                    return_value=iter([
                        {"choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]},
                        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "_account_email": "a@b.c"},
                    ]),
                ),
            ):
                response = anthropic_v1_messages.handle({"model": "auto", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(response["_account_email"], "a@b.c")


class CacheDisabledTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old = config.data.get("chat_completion_cache")

    def tearDown(self) -> None:
        if self.old is None:
            config.data.pop("chat_completion_cache", None)
        else:
            config.data["chat_completion_cache"] = self.old

    def test_default_is_disabled(self) -> None:
        from services.config import DEFAULT_CHAT_COMPLETION_CACHE

        self.assertFalse(DEFAULT_CHAT_COMPLETION_CACHE["enabled"])

    def test_messages_untouched_when_cache_disabled(self) -> None:
        config.data["chat_completion_cache"] = {
            "enabled": False,
            "normalize_messages": True,
            "drop_adjacent_duplicates": True,
            "drop_assistant_history": True,
        }
        messages = [
            {"role": "user", "content": "same"},
            {"role": "user", "content": "same"},
            {"role": "assistant", "content": "old"},
        ]
        self.assertEqual(normalize_text_messages(messages), messages)


class ImagePayloadRegressionTests(unittest.TestCase):
    """生图请求体不能带 history_and_training_disabled。

    实测（2026-11，免费号）：临时聊天调用生图工具会被上游直接拒绝，返回
    「目前你正在使用临时聊天，暂时无法调用图片生成工具」，且不扣配额。
    这条用例钉住这个约束，避免以后又被当成「隔离记忆」的开关加回来。
    """

    def _backend(self) -> tuple[OpenAIBackendAPI, FakeSession]:
        backend = OpenAIBackendAPI(access_token="")
        session = FakeSession()
        backend.session = session  # type: ignore[assignment]
        return backend, session

    def test_image_payload_is_not_temporary_chat(self) -> None:
        backend, session = self._backend()
        requirements = ChatRequirements(token="sentinel")

        backend._prepare_image_conversation("a cat", requirements, "gpt-image-2")
        backend._start_image_generation("a cat", requirements, "conduit-1", "gpt-image-2")

        self.assertEqual(len(session.calls), 2)
        for _, payload in session.calls:
            self.assertNotIn("history_and_training_disabled", payload)
            # 生图请求仍要带 picture_v2，别把原有字段改掉。
            self.assertEqual(payload["system_hints"], ["picture_v2"])


if __name__ == "__main__":
    unittest.main()
