"""内部接口：仅供 Go 对外服务调用的语义化入口。

设计约定：

- 这一层不认识 OpenAI / Anthropic 协议，只接受「生图」「编辑」「文本」「搜索」
  这样的语义参数，返回统一的内部结果或内部事件流。
- 所有协议翻译都在 Go 侧完成。因此这里的响应形状一旦确定，就应当稳定。
- 鉴权用共享密钥 ``CHATGPT2API_UPSTREAM_TOKEN``，与对外密钥体系隔离。
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from typing import Any, Iterator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from services.config import config
from services.log_service import LoggedCall
from services.protocol import (
    openai_v1_chat_complete,
    openai_v1_image_edit,
    openai_v1_image_generations,
    openai_v1_models,
    openai_search,
)
from services.protocol.conversation import (
    ConversationRequest,
    ImageOutput,
    encode_images,
    stream_image_outputs_with_pool,
)
from utils.helper import extract_chat_prompt

INTERNAL_TOKEN_ENV = "CHATGPT2API_UPSTREAM_TOKEN"

# 内部身份：所有内部调用共享一个逻辑身份，便于日志聚合。
INTERNAL_IDENTITY = {"id": "internal", "name": "Go 对外服务", "role": "admin"}


def _expected_token() -> str:
    import os

    return str(os.getenv(INTERNAL_TOKEN_ENV) or "").strip()


def _require_internal(token: str | None) -> None:
    expected = _expected_token()
    if not expected:
        # 未配置时不允许调用，避免默认裸奔。
        raise HTTPException(status_code=503, detail={"error": "internal token is not configured"})
    if not hmac.compare_digest(str(token or ""), expected):
        raise HTTPException(status_code=401, detail={"error": "invalid internal token"})


def _image_payload(body: dict[str, Any]) -> dict[str, Any]:
    """把内部请求整理成协议层可直接消费的 payload。"""
    payload = {
        "prompt": str(body.get("prompt") or ""),
        "model": str(body.get("model") or "gpt-image-2"),
        "n": int(body.get("n") or 1),
        "size": body.get("size") or None,
        "quality": str(body.get("quality") or "auto"),
        "response_format": str(body.get("response_format") or "b64_json"),
        "base_url": str(body.get("base_url") or "") or None,
    }
    images = body.get("images") or []
    if isinstance(images, list) and images:
        payload["images"] = images
    masks = body.get("mask") or []
    if isinstance(masks, list) and masks:
        payload["mask"] = masks
    return payload


def _usage_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    usage = result.get("usage")
    return usage if isinstance(usage, dict) else None


def _error_payload(exc: Exception) -> tuple[int, dict[str, Any]]:
    """把异常映射成 (状态码, 错误体)，保留上游语义。

    对外服务的错误形状由 Go 侧决定，这里只需要给出正确的状态码和
    机器可读的 code，避免把 429 抹成 502 误导客户端重试策略。
    """
    message = str(exc) or "upstream request failed"
    status_code = int(getattr(exc, "status_code", 0) or 0)
    code = str(getattr(exc, "code", "") or "")
    error_type = str(getattr(exc, "error_type", "") or "")

    # 号池耗尽是最常见且必须保真的语义。
    if "no available image quota" in message.lower():
        return 429, {"message": "no available image quota", "code": "insufficient_quota",
                     "type": "insufficient_quota"}
    # 超时是「可恢复」语义：图片可能仍在上游异步生成，前端据此提供继续等待。
    # 注意：SSE 硬上限错误用的是「硬上限」而非「超时」，两者都要映射到这里，
    # 否则前端识别不到可恢复场景。
    lowered = message.lower()
    if (
            "超时" in message
            or "硬上限" in message
            or "timed out" in lowered
            or "timeout" in lowered
            or "hard timeout" in lowered
    ):
        return 504, {"message": message, "code": "image_poll_timeout", "type": "timeout_error"}
    if status_code >= 400:
        return status_code, {"message": message, "code": code or "upstream_error",
                             "type": error_type or "server_error"}
    return 502, {"message": message, "code": "upstream_error", "type": "server_error"}


def _error_response(exc: Exception) -> JSONResponse:
    status_code, body = _error_payload(exc)
    return JSONResponse(status_code=status_code, content={"error": body})


def _decode_image_entry(value: Any) -> tuple[bytes, str, str] | None:
    """把内部契约里的图片字符串还原成 (bytes, filename, mime) 三元组。

    Go 侧统一用「data URL 或裸 base64」传递图片，因为这样内部契约最简单；
    但协议层的编辑处理器期望三元组，转换放在这里做，避免契约泄漏实现细节。
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()

    # data URL: data:image/png;base64,xxxx
    if text.startswith("data:"):
        header, _, payload = text.partition(",")
        if not payload:
            return None
        mime_type = header.split(";", 1)[0].removeprefix("data:") or "image/png"
        try:
            data = base64.b64decode(payload, validate=False)
        except Exception:
            return None
        if not data:
            return None
        extension = mime_type.split("/", 1)[1] if "/" in mime_type else "png"
        return data, f"image_1.{extension}", mime_type

    # 裸 base64：无法判断类型，按 PNG 处理（上游只看内容）
    try:
        data = base64.b64decode(text, validate=False)
    except Exception:
        return None
    if not data:
        return None
    return data, "image_1.png", "image/png"


def _decode_images(values: Any) -> list[tuple[bytes, str, str]]:
    """批量还原图片列表。"""
    if not isinstance(values, list):
        return []
    decoded: list[tuple[bytes, str, str]] = []
    for index, value in enumerate(values, start=1):
        item = _decode_image_entry(value)
        if item is None:
            continue
        data, _, mime_type = item
        extension = mime_type.split("/", 1)[1] if "/" in mime_type else "png"
        decoded.append((data, f"image_{index}.{extension}", mime_type))
    return decoded


def _image_result(body: dict[str, Any]) -> dict[str, Any]:
    """执行一次非流式生图/编辑，返回内部结果。"""
    payload = _image_payload(body)
    is_edit = bool(body.get("images"))
    if is_edit:
        # 协议层的编辑处理器要求 (bytes, filename, mime) 三元组。
        payload["images"] = _decode_images(body.get("images"))
        if body.get("mask"):
            payload["mask"] = _decode_images(body.get("mask"))
    handler = openai_v1_image_edit.handle if is_edit else openai_v1_image_generations.handle
    result = handler(payload)
    if not isinstance(result, dict):
        raise RuntimeError("image handler returned a stream unexpectedly")
    # base_url 由 Go 侧提供，避免内部再把 URL 指向 sidecar。
    return {
        "created": int(result.get("created") or time.time()),
        "data": result.get("data") or [],
        "usage": _usage_from_result(result),
        "message": str(result.get("message") or ""),
    }


def _internal_event(output: ImageOutput) -> dict[str, Any]:
    """把内部图片事件规整成 Go 侧能直接消费的形状。"""
    if output.kind == "progress":
        return {
            "type": "progress",
            "index": output.index,
            "total": output.total,
            "text": output.text,
            "step": output.upstream_event_type or "",
            "conversation_id": output.conversation_id,
            "account_email": output.account_email,
        }
    if output.kind == "result":
        return {
            "type": "result",
            "index": output.index,
            "total": output.total,
            "data": output.data,
            "conversation_id": output.conversation_id,
            "account_email": output.account_email,
        }
    return {
        "type": "message",
        "index": output.index,
        "total": output.total,
        "text": output.text,
        "conversation_id": output.conversation_id,
        "account_email": output.account_email,
    }


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def create_internal_router() -> APIRouter:
    router = APIRouter()

    @router.get("/internal/health")
    async def health(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")):
        _require_internal(x_internal_token)
        return {"status": "ok"}

    @router.post("/internal/v1/models")
    async def list_models(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")):
        _require_internal(x_internal_token)
        return await run_in_threadpool(openai_v1_models.list_models)

    @router.post("/internal/v1/images/generations")
    async def generate(
            request: Request,
            x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ):
        _require_internal(x_internal_token)
        body = await request.json()
        payload = _image_payload(body)
        if not payload["prompt"].strip():
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})

        if body.get("stream"):
            return _stream_image_response(payload, edit=False)

        call = LoggedCall(INTERNAL_IDENTITY, "/internal/images/generations", payload["model"], "文生图",
                          request_text=payload["prompt"])
        try:
            result = await run_in_threadpool(_image_result, {"prompt": payload["prompt"], "model": payload["model"],
                                                            "n": payload["n"], "size": payload["size"],
                                                            "quality": payload["quality"],
                                                            "response_format": payload["response_format"],
                                                            "base_url": payload["base_url"]})
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一转成内部错误体
            call.log("调用失败", status="failed", error=str(exc))
            return _error_response(exc)
        call.log("调用完成", result)
        return result

    @router.post("/internal/v1/images/edits")
    async def edit(
            request: Request,
            x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ):
        _require_internal(x_internal_token)
        body = await request.json()
        payload = _image_payload(body)
        if not payload["prompt"].strip():
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})
        images = payload.get("images") or []
        if not images:
            raise HTTPException(status_code=400, detail={"error": "image is required"})

        if body.get("stream"):
            return _stream_image_response(payload, edit=True)

        call = LoggedCall(INTERNAL_IDENTITY, "/internal/images/edits", payload["model"], "图生图",
                          request_text=payload["prompt"])
        try:
            result = await run_in_threadpool(_image_result, {"prompt": payload["prompt"], "model": payload["model"],
                                                            "n": payload["n"], "size": payload["size"],
                                                            "quality": payload["quality"],
                                                            "response_format": payload["response_format"],
                                                            "base_url": payload["base_url"],
                                                            "images": images})
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            call.log("调用失败", status="failed", error=str(exc))
            return _error_response(exc)
        call.log("调用完成", result)
        return result

    @router.post("/internal/v1/text/completions")
    async def text_completion(
            request: Request,
            x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ):
        _require_internal(x_internal_token)
        body = await request.json()
        model = str(body.get("model") or "auto")
        messages = body.get("messages") or []
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail={"error": "messages is required"})
        thinking_effort = str(body.get("thinking_effort") or "")

        if body.get("stream"):
            return _stream_text_response(model, messages, thinking_effort)

        payload = {"model": model, "messages": messages, "thinking_effort": thinking_effort}
        call = LoggedCall(INTERNAL_IDENTITY, "/internal/text/completions", model, "文本生成",
                          request_text="")
        try:
            response = await run_in_threadpool(openai_v1_chat_complete.handle, payload)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            call.log("调用失败", status="failed", error=str(exc))
            return _error_response(exc)
        text = _extract_text(response)
        usage = _extract_usage(response)
        call.log("调用完成", {"usage": usage})
        return {"text": text, "usage": usage}

    @router.post("/internal/v1/images/resume")
    async def resume(
            request: Request,
            x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ):
        """在已有会话上继续轮询图片结果。

        这是「超时后继续等待」的实现：图片可能已在上游异步生成完成，
        只是首轮轮询的时间窗不够。复用同一 conversation_id 可以避免重新
        消耗一次生图额度。
        """
        _require_internal(x_internal_token)
        body = await request.json()
        conversation_id = str(body.get("conversation_id") or "").strip()
        if not conversation_id:
            raise HTTPException(status_code=400, detail={"error": "conversation_id is required"})
        extra_timeout = float(body.get("extra_timeout_secs") or 30)

        call = LoggedCall(INTERNAL_IDENTITY, "/internal/images/resume", "gpt-image-2", "续轮询",
                          request_text="")
        try:
            result = await run_in_threadpool(_resume_poll, conversation_id, extra_timeout)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            call.log("调用失败", status="failed", error=str(exc))
            return _error_response(exc)
        call.log("调用完成", {"conversation_id": conversation_id})
        return result

    @router.post("/internal/v1/search")
    async def search(
            request: Request,
            x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    ):
        _require_internal(x_internal_token)
        body = await request.json()
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail={"error": "prompt is required"})
        call = LoggedCall(INTERNAL_IDENTITY, "/internal/search", openai_search.MODEL, "搜索", request_text=prompt)
        try:
            result = await run_in_threadpool(openai_search.handle, {"prompt": prompt})
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            call.log("调用失败", status="failed", error=str(exc))
            return _error_response(exc)
        call.log("调用完成", result)
        # openai_search.handle 返回的正文在 answer 字段（不是 text），
        # 这里做一次归一，避免上层拿到空字符串。
        return {
            "text": str(result.get("answer") or result.get("text") or ""),
            "annotations": result.get("annotations") or [],
            "sources": result.get("sources") or [],
        }

    return router


def _resume_poll(conversation_id: str, extra_timeout_secs: float) -> dict[str, Any]:
    """在已存在的会话上继续轮询并下载图片。

    注意：这里不复用 image_task_service 的实现，因为它内部构造
    OpenAIBackendAPI(proxy_url=...) 而该参数并不存在，会直接抛 TypeError。
    """
    from services.account_service import account_service
    from services.openai_backend_api import OpenAIBackendAPI
    from services.protocol.conversation import format_image_result

    token = account_service.get_text_access_token()
    backend = OpenAIBackendAPI(token or "")
    try:
        file_ids, sediment_ids = backend._poll_image_results(conversation_id, extra_timeout_secs)
        if not file_ids and not sediment_ids:
            raise RuntimeError(f"继续等待 {int(extra_timeout_secs)} 秒后仍未找到图片结果")

        image_urls = backend.resolve_conversation_image_urls(
            conversation_id, file_ids, sediment_ids, poll=False,
        )
        if not image_urls:
            raise RuntimeError("图片 URL 解析失败")

        image_items = [
            {"b64_json": base64.b64encode(image_data).decode("ascii")}
            for image_data in backend.download_image_bytes(image_urls)
        ]
        data = format_image_result(image_items, "", "b64_json", "", int(time.time()))["data"]
        return {
            "created": int(time.time()),
            "data": data,
            "usage": None,
            "conversation_id": conversation_id,
        }
    finally:
        backend.close()


def _stream_image_response(payload: dict[str, Any], *, edit: bool) -> StreamingResponse:
    """把内部图片事件流以 SSE 形式输出。"""
    encoded_images = encode_images(_decode_images(payload.get("images"))) if payload.get("images") else None
    request = ConversationRequest(
        prompt=payload["prompt"],
        model=payload["model"],
        n=payload["n"],
        size=payload["size"],
        quality=payload["quality"],
        response_format=payload["response_format"],
        base_url=payload["base_url"],
        images=encoded_images,
        message_as_error=True,
    )

    def generate() -> Iterator[str]:
        try:
            for output in stream_image_outputs_with_pool(request):
                yield _sse(_internal_event(output))
        except Exception as exc:  # noqa: BLE001 - 流已开始，只能以事件形式报错
            status_code, body = _error_payload(exc)
            conversation_id = str(getattr(exc, "conversation_id", "") or "")
            yield _sse({
                "type": "error",
                "conversation_id": conversation_id,
                "error": {
                    "status": status_code,
                    "code": body["code"],
                    "message": body["message"],
                },
            })
            return
        yield _sse({"type": "done"})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _stream_text_response(model: str, messages: list[dict[str, Any]], thinking_effort: str) -> StreamingResponse:
    """把文本增量以内部 SSE 输出。"""
    payload = {"model": model, "messages": messages, "thinking_effort": thinking_effort, "stream": True}

    def generate() -> Iterator[str]:
        try:
            events = openai_v1_chat_complete.handle(payload)
            for event in events:
                for text in _iter_chunk_text(event):
                    yield _sse({"type": "delta", "text": text})
        except Exception as exc:  # noqa: BLE001
            status_code, body = _error_payload(exc)
            conversation_id = str(getattr(exc, "conversation_id", "") or "")
            yield _sse({
                "type": "error",
                "conversation_id": conversation_id,
                "error": {
                    "status": status_code,
                    "code": body["code"],
                    "message": body["message"],
                },
            })
            return
        yield _sse({"type": "done"})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _iter_chunk_text(chunk: Any) -> Iterator[str]:
    """从 chat.completion.chunk 中提取文本增量。"""
    if not isinstance(chunk, dict):
        return
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return
    first = choices[0]
    if not isinstance(first, dict):
        return
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return
    content = delta.get("content")
    if isinstance(content, str) and content:
        yield content


def _extract_text(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


def _extract_usage(response: Any) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    usage = response.get("usage")
    return usage if isinstance(usage, dict) else None
