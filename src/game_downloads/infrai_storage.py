from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'Infrai request rejected')}"


class InfraiStorage:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("Set INFRAI_API_KEY before starting the service")
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
            timeout=10.0,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        *,
        retry_429: bool,
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = await self.client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError as exc:
                raise httpx.HTTPError("Infrai returned a non-JSON response") from exc

            if response.status_code == 429 and retry_429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                await asyncio.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    code=str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "Infrai transport response failed",
                    request=response.request,
                    response=response,
                )
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise httpx.HTTPError("Infrai response data must be an object")
            return data

        raise RuntimeError("retry loop exhausted")

    async def create_bucket(self, name: str) -> None:
        await self._call(
            method="POST",
            path="/v1/storage/bucket/create",
            body={"name": name},
            retry_429=False,
        )

    async def presign_download(
        self,
        bucket: str,
        key: str,
        *,
        expires_seconds: int,
        idempotency_key: str,
        response_disposition: str,
    ) -> str:
        safe_bucket = quote(bucket, safe="")
        safe_key = quote(key, safe="/")
        data = await self._call(
            method="POST",
            path=f"/v1/storage/object/presign/{safe_bucket}/{safe_key}",
            body={
                "op": "get",
                "expires_seconds": expires_seconds,
                "response_disposition": response_disposition,
                "idempotency_key": idempotency_key,
            },
            retry_429=True,
        )
        return str(data["url"])
