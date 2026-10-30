"""统一的账号导入接口。

背景：原项目把 CPA（CLIProxyAPI）与 sub2api 拆成两套几乎相同的流程——
各自维护「连接配置 → 列出远端条目 → 选择 → 拉取凭证 → 导入 → 轮询进度」。
两者真正的差异只有「怎么列出条目」和「怎么拉凭证」，其余完全一致。

这里把它们抽象成一个来源模型：

- ``kind="cpa"``：远端是 CLIProxyAPI，条目是 auth 文件，凭证是文件里的
  access_token（可能带 refresh_token）。
- ``kind="sub2api"``：远端是 sub2api 面板，条目是 OAuth 账号，凭证是
  账号的 access_token / refresh_token。

对调用方（前端）而言只有一套 API：注册来源、列出候选、批量导入、查进度。
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.support import require_admin
from services.account_service import account_service
from services.cpa_service import (
    CPAConfig,
    cpa_config,
    fetch_remote_access_token,
    list_remote_files,
)
from services.sub2api_service import (
    list_remote_accounts,
    sub2api_config,
)
from services.log_service import LOG_TYPE_ACCOUNT, log_service

SourceKind = Literal["cpa", "sub2api"]


# ── 来源注册表 ────────────────────────────────────────────────────
#
# CPA 和 sub2api 的配置格式不同，但对外都投影成同一个 ImportSource 形状。
# 这里不复制底层存储，只读取它们。

def _source_from_cpa(pool: dict) -> dict[str, Any]:
    return {
        "id": str(pool.get("id") or ""),
        "kind": "cpa",
        "name": str(pool.get("name") or ""),
        "base_url": str(pool.get("base_url") or ""),
        "has_secret": bool(str(pool.get("secret_key") or "").strip()),
        "email": "",
        "group_id": "",
        "job": pool.get("import_job"),
    }


def _source_from_sub2api(server: dict) -> dict[str, Any]:
    return {
        "id": str(server.get("id") or ""),
        "kind": "sub2api",
        "name": str(server.get("name") or ""),
        "base_url": str(server.get("base_url") or ""),
        "has_secret": bool(
            str(server.get("api_key") or "").strip()
            or (str(server.get("email") or "").strip() and str(server.get("password") or "").strip())
        ),
        "email": str(server.get("email") or ""),
        "group_id": str(server.get("group_id") or ""),
        "job": server.get("import_job"),
    }


def _list_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    sources.extend(_source_from_cpa(pool) for pool in cpa_config.list_pools())
    sources.extend(_source_from_sub2api(server) for server in sub2api_config.list_servers())
    return sources


def _get_source(kind: str, source_id: str) -> dict[str, Any] | None:
    if kind == "cpa":
        pool = cpa_config.get_pool(source_id)
        return pool
    server = sub2api_config.get_server(source_id)
    return server


# ── 候选条目 ──────────────────────────────────────────────────────

def _list_candidates(kind: str, source_id: str) -> list[dict[str, Any]]:
    source = _get_source(kind, source_id)
    if source is None:
        raise ValueError("source not found")

    if kind == "cpa":
        files = list_remote_files(source)
        return [
            {
                "id": item["name"],
                "name": item["name"],
                "email": item.get("email") or "",
                "has_refresh_token": None,  # 文件里可能带，但列表接口不返回
            }
            for item in files
        ]

    accounts = list_remote_accounts(source)
    return [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "email": str(item.get("email") or ""),
            "plan_type": str(item.get("plan_type") or ""),
            "status": str(item.get("status") or ""),
            "expires_at": str(item.get("expires_at") or ""),
            "has_refresh_token": bool(item.get("has_refresh_token")),
        }
        for item in accounts
    ]


# ── 凭证拉取 ──────────────────────────────────────────────────────

def _fetch_cpa_credentials(pool: dict, names: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """从 CPA 拉取 auth 文件，返回标准凭证列表。"""
    credentials: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    def fetch_one(name: str) -> dict[str, Any] | None:
        # 复用原有实现，但它只返回 access_token。CPA 的文件里通常也带
        # refresh_token，为了让「优先用 RT」能生效，这里直接读完整文件。
        from services.cpa_service import _management_headers
        from curl_cffi.requests import Session
        from services.proxy_service import proxy_settings

        base_url = str(pool.get("base_url") or "").strip()
        secret_key = str(pool.get("secret_key") or "").strip()
        if not base_url or not secret_key:
            raise RuntimeError("invalid pool config")

        session = Session(**proxy_settings.build_session_kwargs(verify=True))
        try:
            response = session.get(
                f"{base_url.rstrip('/')}/v0/management/auth-files/download",
                headers=_management_headers(secret_key),
                params={"name": name},
                timeout=30,
            )
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status_code}")
            payload = response.json()
        finally:
            session.close()

        if not isinstance(payload, dict):
            raise RuntimeError("invalid payload")
        return {
            "name": name,
            "access_token": str(payload.get("access_token") or "").strip(),
            "refresh_token": str(payload.get("refresh_token") or "").strip(),
            "email": str(payload.get("email") or "").strip(),
            "expires_at": str(payload.get("expired") or payload.get("expires_at") or "").strip(),
            "source_type": "codex",
        }

    with ThreadPoolExecutor(max_workers=min(16, max(1, len(names)))) as executor:
        futures = {executor.submit(fetch_one, name): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                item = future.result()
            except Exception as exc:  # noqa: BLE001
                errors.append({"name": name, "error": str(exc) or "unknown error"})
                continue
            if not item.get("access_token") and not item.get("refresh_token"):
                errors.append({"name": name, "error": "no access_token or refresh_token in file"})
                continue
            credentials.append(item)
    return credentials, errors


def _fetch_sub2api_credentials(
    server: dict,
    account_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """从 sub2api 导出账号凭证。"""
    from services.sub2api_service import _auth_headers, _unwrap_envelope
    from curl_cffi.requests import Session

    base_url = str(server.get("base_url") or "").strip()
    headers = _auth_headers(server)
    credentials: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    session = Session(verify=True)
    try:
        response = session.get(
            f"{base_url.rstrip('/')}/api/v1/admin/accounts/data",
            headers=headers,
            params={"ids": ",".join(account_ids), "timezone": "Asia/Shanghai"},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}")
        payload = response.json()
    finally:
        session.close()

    data = _unwrap_envelope(payload)
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        raise RuntimeError("invalid export payload")

    for account in accounts:
        if not isinstance(account, dict):
            continue
        creds = account.get("credentials") if isinstance(account.get("credentials"), dict) else {}
        access_token = str(creds.get("access_token") or creds.get("accessToken") or "").strip()
        refresh_token = str(creds.get("refresh_token") or "").strip()
        label = str(account.get("id") or creds.get("chatgpt_account_id") or account.get("name") or "unknown")
        if not access_token and not refresh_token:
            errors.append({"name": label, "error": "no access_token or refresh_token"})
            continue
        credentials.append({
            "name": label,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email": str(creds.get("email") or account.get("name") or "").strip(),
            "expires_at": str(creds.get("expires_at") or "").strip(),
            "source_type": "codex",
        })

    if len(accounts) < len(account_ids):
        missing = len(account_ids) - len(accounts)
        errors.append({"name": ",".join(account_ids), "error": f"{missing} accounts not exported"})
    return credentials, errors


# ── 导入进度 ──────────────────────────────────────────────────────

_import_jobs: dict[str, dict[str, Any]] = {}
_import_jobs_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job(total: int) -> dict[str, Any]:
    return {
        "job_id": uuid.uuid4().hex,
        "status": "pending",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "total": total,
        "completed": 0,
        "added": 0,
        "skipped": 0,
        "refreshed": 0,
        "failed": 0,
        "errors": [],
    }


def _update_job(job_id: str, **updates: Any) -> dict[str, Any] | None:
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
        if job is None:
            return None
        job.update(updates)
        job["updated_at"] = _now_iso()
        return dict(job)


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
        return dict(job) if job else None


def _run_import(
    job_id: str,
    kind: str,
    source_id: str,
    candidate_ids: list[str],
    prefer_refresh_token: bool,
) -> None:
    """后台执行导入。"""
    _update_job(job_id, status="running")
    try:
        source = _get_source(kind, source_id)
        if source is None:
            raise RuntimeError("source not found")

        if kind == "cpa":
            credentials, fetch_errors = _fetch_cpa_credentials(source, candidate_ids)
        else:
            credentials, fetch_errors = _fetch_sub2api_credentials(source, candidate_ids)

        for error in fetch_errors:
            with _import_jobs_lock:
                job = _import_jobs.get(job_id)
                if job is not None:
                    job["errors"].append(error)

        if not credentials:
            _update_job(
                job_id,
                status="failed",
                completed=len(candidate_ids),
                failed=len(fetch_errors),
            )
            return

        # 按用户偏好裁剪凭证：只要 RT 时丢弃 AT，让账号服务用 RT 现换。
        payloads: list[dict[str, Any]] = []
        for item in credentials:
            payload: dict[str, Any] = {
                "email": item.get("email") or "",
                "source_type": item.get("source_type") or "codex",
            }
            if item.get("refresh_token"):
                payload["refresh_token"] = item["refresh_token"]
            # 未要求「只用 RT」或没有 RT 时，带上 AT 作为回退。
            if item.get("access_token") and not (prefer_refresh_token and item.get("refresh_token")):
                payload["access_token"] = item["access_token"]
            payloads.append(payload)

        add_result = account_service.add_account_items(payloads)
        added_tokens = [
            str(item.get("access_token") or "")
            for item in add_result.get("items") or []
            if str(item.get("access_token") or "")
        ]
        refresh_result = account_service.refresh_accounts(added_tokens) if added_tokens else {}

        errors = list(fetch_errors) + list(add_result.get("errors") or [])
        _update_job(
            job_id,
            status="completed",
            completed=len(candidate_ids),
            added=int(add_result.get("added") or 0),
            skipped=int(add_result.get("skipped") or 0),
            refreshed=int(refresh_result.get("refreshed") or 0),
            failed=len(errors),
            errors=errors,
        )
        log_service.add(
            LOG_TYPE_ACCOUNT,
            f"统一导入完成（{kind}）",
            {"added": add_result.get("added"), "skipped": add_result.get("skipped")},
        )
    except Exception as exc:  # noqa: BLE001
        _update_job(
            job_id,
            status="failed",
            completed=len(candidate_ids),
            failed=len(candidate_ids),
            errors=[{"name": "import", "error": str(exc) or "import failed"}],
        )


# ── 请求模型 ──────────────────────────────────────────────────────

class ImportSourceCreate(BaseModel):
    kind: SourceKind
    name: str = ""
    base_url: str = ""
    # CPA
    secret_key: str = ""
    # sub2api
    email: str = ""
    password: str = ""
    api_key: str = ""
    group_id: str = ""


class ImportSourceUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    secret_key: str | None = None
    email: str | None = None
    password: str | None = None
    api_key: str | None = None
    group_id: str | None = None


class ImportStartRequest(BaseModel):
    """开始导入。

    - ``candidate_ids``：CPA 的文件名，或 sub2api 的账号 ID。
    - ``credential_mode``：``auto`` 优先用 RT，没有则用 AT；
      ``refresh_token`` 强制只用 RT（由后端现换 AT）；
      ``access_token`` 只用 AT。
    """

    candidate_ids: list[str] = Field(default_factory=list)
    credential_mode: Literal["auto", "refresh_token", "access_token"] = "auto"


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/import/sources")
    async def list_sources(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        return {"sources": _list_sources()}

    @router.post("/api/import/sources")
    async def create_source(body: ImportSourceCreate, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        if body.kind == "cpa":
            if not body.base_url.strip() or not body.secret_key.strip():
                raise HTTPException(status_code=400, detail={"error": "base_url and secret_key are required"})
            pool = cpa_config.add_pool(body.name or body.base_url, body.base_url, body.secret_key)
            return {"source": _source_from_cpa(pool), "sources": _list_sources()}

        if not body.base_url.strip():
            raise HTTPException(status_code=400, detail={"error": "base_url is required"})
        if not body.api_key.strip() and not (body.email.strip() and body.password.strip()):
            raise HTTPException(status_code=400, detail={"error": "api_key or email+password is required"})
        server = sub2api_config.add_server(
            name=body.name or body.base_url,
            base_url=body.base_url,
            email=body.email,
            password=body.password,
            api_key=body.api_key,
            group_id=body.group_id,
        )
        return {"source": _source_from_sub2api(server), "sources": _list_sources()}

    @router.post("/api/import/sources/{kind}/{source_id}")
    async def update_source(
            kind: SourceKind,
            source_id: str,
            body: ImportSourceUpdate,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        updates = {key: value for key, value in body.model_dump().items() if value is not None}
        if kind == "cpa":
            pool = cpa_config.update_pool(source_id, updates)
            if pool is None:
                raise HTTPException(status_code=404, detail={"error": "source not found"})
            return {"source": _source_from_cpa(pool), "sources": _list_sources()}

        server = sub2api_config.update_server(source_id, updates)
        if server is None:
            raise HTTPException(status_code=404, detail={"error": "source not found"})
        return {"source": _source_from_sub2api(server), "sources": _list_sources()}

    @router.delete("/api/import/sources/{kind}/{source_id}")
    async def delete_source(
            kind: SourceKind,
            source_id: str,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        removed = (
            cpa_config.delete_pool(source_id)
            if kind == "cpa"
            else sub2api_config.delete_server(source_id)
        )
        if not removed:
            raise HTTPException(status_code=404, detail={"error": "source not found"})
        return {"sources": _list_sources()}

    @router.get("/api/import/sources/{kind}/{source_id}/candidates")
    async def list_candidates(
            kind: SourceKind,
            source_id: str,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        try:
            items = await run_in_threadpool(_list_candidates, kind, source_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail={"error": str(exc)}) from exc
        return {"source_id": source_id, "kind": kind, "candidates": items}

    @router.post("/api/import/sources/{kind}/{source_id}/run")
    async def run_import(
            kind: SourceKind,
            source_id: str,
            body: ImportStartRequest,
            authorization: str | None = Header(default=None),
    ):
        require_admin(authorization)
        candidate_ids = [str(item).strip() for item in body.candidate_ids if str(item).strip()]
        if not candidate_ids:
            raise HTTPException(status_code=400, detail={"error": "candidate_ids is required"})
        if _get_source(kind, source_id) is None:
            raise HTTPException(status_code=404, detail={"error": "source not found"})

        job = _new_job(len(candidate_ids))
        with _import_jobs_lock:
            _import_jobs[job["job_id"]] = job

        thread = threading.Thread(
            target=_run_import,
            args=(
                job["job_id"],
                kind,
                source_id,
                candidate_ids,
                body.credential_mode == "refresh_token",
            ),
            name=f"import-{kind}-{source_id}",
            daemon=True,
        )
        thread.start()
        return {"job": job}

    @router.get("/api/import/jobs/{job_id}")
    async def get_job(job_id: str, authorization: str | None = Header(default=None)):
        require_admin(authorization)
        job = _get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail={"error": "job not found"})
        return {"job": job}

    return router
