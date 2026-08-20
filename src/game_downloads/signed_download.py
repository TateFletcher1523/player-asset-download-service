from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol


class DownloadStorage(Protocol):
    async def presign_download(
        self,
        bucket: str,
        key: str,
        *,
        expires_seconds: int,
        idempotency_key: str,
        response_disposition: str,
    ) -> str: ...


class AssetKind(StrEnum):
    REPLAY = "replay"
    MAP = "map"
    SCREENSHOT = "screenshot"


class ModerationState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DownloadRequest:
    player_id: str
    asset_id: str
    asset_kind: AssetKind


@dataclass(frozen=True)
class DownloadResult:
    asset_id: str
    status: str
    download_url: str | None = None
    expires_seconds: int | None = None


@dataclass(frozen=True)
class PlayerAsset:
    asset_id: str
    owner_id: str
    asset_kind: AssetKind
    object_key: str
    moderation_state: ModerationState


class AssetCatalog:
    def __init__(self, assets: list[PlayerAsset]) -> None:
        self._assets = {asset.asset_id: asset for asset in assets}

    def get(self, asset_id: str) -> PlayerAsset | None:
        return self._assets.get(asset_id)


class SignedDownloadService:
    def __init__(self, storage: DownloadStorage, catalog: AssetCatalog, bucket: str) -> None:
        self.storage = storage
        self.catalog = catalog
        self.bucket = bucket

    async def issue(self, request: DownloadRequest) -> DownloadResult:
        asset = self.catalog.get(request.asset_id)
        if asset is None or asset.owner_id != request.player_id:
            return DownloadResult(asset_id=request.asset_id, status="not_found")
        if asset.asset_kind != request.asset_kind:
            return DownloadResult(asset_id=request.asset_id, status="not_found")
        if asset.moderation_state != ModerationState.APPROVED:
            return DownloadResult(
                asset_id=asset.asset_id,
                status=f"moderation_{asset.moderation_state.value}",
            )

        expires_seconds = 300
        token = sha256(
            f"{request.player_id}:{asset.asset_id}:{asset.object_key}".encode()
        ).hexdigest()
        url = await self.storage.presign_download(
            self.bucket,
            asset.object_key,
            expires_seconds=expires_seconds,
            idempotency_key=f"download-{token}",
            response_disposition=f'attachment; filename="{asset.asset_id}.bin"',
        )
        return DownloadResult(
            asset_id=asset.asset_id,
            status="ready",
            download_url=url,
            expires_seconds=expires_seconds,
        )
