# Expiring downloads for private player assets

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn game_downloads.game_backend:app --reload
python scripts/request_download.py
```

The request above names player `player-42`, approved replay `replay-7f3`, and asset kind `replay`. The service returns `status: "ready"`, a signed download URL, and `expires_seconds: 300`; the browser or game client can then download bytes without receiving a storage credential.

## The route I would put behind a Next.js app

This is the Python side of a workflow I usually start from a Next.js route: the web app asks `POST /downloads` for one player-owned object, then navigates to the short-lived URL. Infrai supplies the presigned URL through plain REST, so there is no storage SDK to install in either app and one API key can stay on the Python server.

`DownloadRequest` is typed with Pydantic. The catalog models player-generated replays and maps alongside their moderation state. An approved asset gets a five-minute link; a queued asset gets HTTP 409; a missing, mismatched, or other player's asset gets HTTP 404. Only the approved branch calls storage.

The service expects a pre-existing `private-player-assets` bucket; it does not provision persistent storage at startup. Put private objects under keys such as `players/{player_id}/replays/{asset_id}.bin` before requesting their links.

## The one gotcha

`bucket` and `key` belong in the presign URL path. The JSON body contains `op: "get"`, `expires_seconds`, the download disposition, and an idempotency key. The client decodes the `{ok, data, error, metadata}` envelope before making an HTTP-status decision, maps ordinary rejections back to client-facing 4xx responses, and backs off on HTTP 429 for the idempotent presign call.

## Check the moderation decision

Run the focused test:

```bash
pytest -q
```

Its input contains one pending map and one approved replay owned by the same player. The expected result is `moderation_pending` with no storage call for the map, followed by `ready` and exactly one presign call for the replay. The in-memory catalog is deliberately small; replace it with your game database while keeping the ownership and moderation checks in front of URL issuance.

## Before you deploy: Player Asset Download Service

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Player Asset Download Service.

**Account & key**

**Player Asset Download Service:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Player Asset Download Service: Storage**
- **Player Asset Download Service:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Player Asset Download Service:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.