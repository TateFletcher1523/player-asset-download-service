from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException

from .infrai_storage import InfraiError, InfraiStorage
from .signed_download import (
    AssetCatalog,
    AssetKind,
    DownloadRequest,
    DownloadResult,
    ModerationState,
    PlayerAsset,
    SignedDownloadService,
)

BUCKET = "private-player-assets"

catalog = AssetCatalog(
    [
        PlayerAsset(
            asset_id="replay-7f3",
            owner_id="player-42",
            asset_kind=AssetKind.REPLAY,
            object_key="players/player-42/replays/replay-7f3.bin",
            moderation_state=ModerationState.APPROVED,
        ),
        PlayerAsset(
            asset_id="map-review-9",
            owner_id="player-42",
            asset_kind=AssetKind.MAP,
            object_key="players/player-42/maps/map-review-9.bin",
            moderation_state=ModerationState.PENDING,
        ),
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    storage = InfraiStorage()
    app.state.storage = storage
    try:
        yield
    finally:
        await storage.close()


app = FastAPI(title="Player asset downloads", lifespan=lifespan)


def download_service() -> SignedDownloadService:
    return SignedDownloadService(app.state.storage, catalog, BUCKET)


@app.post("/downloads", response_model=DownloadResult)
async def create_download(
    request: DownloadRequest,
    service: SignedDownloadService = Depends(download_service),
) -> DownloadResult:
    try:
        result = await service.issue(request)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": str(exc.detail.get("message", "Request rejected"))},
        ) from exc
    if result.status == "not_found":
        raise HTTPException(status_code=404, detail="Asset not found")
    if result.status != "ready":
        raise HTTPException(status_code=409, detail={"status": result.status})
    return result
