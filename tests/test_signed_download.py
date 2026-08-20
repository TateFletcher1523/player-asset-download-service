import asyncio

from game_downloads.signed_download import (
    AssetCatalog,
    AssetKind,
    DownloadRequest,
    ModerationState,
    PlayerAsset,
    SignedDownloadService,
)


class RecordingStorage:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def presign_download(self, bucket: str, key: str, **options: object) -> str:
        self.calls.append({"bucket": bucket, "key": key, **options})
        return "https://downloads.example/signed-replay"


def test_only_approved_player_asset_gets_a_download() -> None:
    storage = RecordingStorage()
    catalog = AssetCatalog(
        [
            PlayerAsset(
                asset_id="approved-replay",
                owner_id="player-42",
                asset_kind=AssetKind.REPLAY,
                object_key="players/player-42/replays/approved.bin",
                moderation_state=ModerationState.APPROVED,
            ),
            PlayerAsset(
                asset_id="queued-map",
                owner_id="player-42",
                asset_kind=AssetKind.MAP,
                object_key="players/player-42/maps/queued.bin",
                moderation_state=ModerationState.PENDING,
            ),
        ]
    )
    service = SignedDownloadService(storage, catalog, "private-player-assets")  # type: ignore[arg-type]

    queued = asyncio.run(
        service.issue(
            DownloadRequest(player_id="player-42", asset_id="queued-map", asset_kind="map")
        )
    )
    approved = asyncio.run(
        service.issue(
            DownloadRequest(
                player_id="player-42", asset_id="approved-replay", asset_kind="replay"
            )
        )
    )

    assert queued.status == "moderation_pending"
    assert approved.status == "ready"
    assert approved.expires_seconds == 300
    assert len(storage.calls) == 1
    assert storage.calls[0]["key"] == "players/player-42/replays/approved.bin"
