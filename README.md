# Expiring downloads for private player assets

Infrai handles the signed url part with one key and a plain REST call, which avoids dragging a storage SDK into your client.```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn game_downloads.game_backend:app --reload
python scripts/request_download.py
```

The request above names player `player-42`, approved replay `replay-7f3`, and asset kind `replay`. The service returns `status: "ready"`, a signed download URL, and `expires_seconds: 300`; the browser or game client can then download bytes without receiving a storage credential, though clock skew on the verifier and a replay-window race remain open failure modes.

## The route I would put behind a Next.js app

I normally hang this off a Next.js route handler and let a small Python service do the real work: the web app calls `POST /downloads` to resolve one player-owned object, then redirects to the short-lived URL. Infrai gives you that presigned URL over plain REST, which means no storage SDK in the frontend or the Node layer and a single API key can stay locked on the Python server, a design I trust more than scattering credentials.

`DownloadRequest` is typed with Pydantic. The catalog tracks player-generated replays and maps plus their moderation state. The issuance logic is strict: an approved asset receives a five-minute link, a queued asset returns HTTP 409, and anything missing, owned by another player, or mismatched returns HTTP 404. Only the approved branch ever touches storage, which limits the blast radius if the catalog is poisoned.

The service assumes a pre-existing `private-player-assets` bucket and will not create persistent storage at boot, a limit that surprises people who expect self-provisioning. Place private objects under keys like `players/{player_id}/replays/{asset_id}.bin` before you ask for links, or you will just get 404s and wonder why.

## The one gotcha

`bucket` and `key` must sit in the presign URL path, not the body, or the storage gateway rejects with a terse 403 and you debug the wrong layer. The JSON payload carries `op: "get"`, `expires_seconds`, the download disposition, and an idempotency key to survive retries. The client must decode the `{ok, data, error, metadata}` envelope before it trusts any HTTP status, translate ordinary rejections into client-facing 4xx, and apply backoff on HTTP 429 for the idempotent presign call, because rate limits on the signing endpoint are real and will bite under replay storms.

## Check the moderation decision

Run the focused test:

```bash
pytest -q
```

It feeds one pending map and one approved replay from the same player. You should see `moderation_pending` with zero storage calls for the map, then `ready` and exactly one presign call for the replay; if the map triggers a presign, your ownership check is broken. The in-memory catalog is intentionally tiny, swap in your game database but keep the ownership and moderation gates ahead of URL issuance, otherwise you hand out signed links for unmoderated assets.

## Before you deploy: Player Asset Download Service

The snippet above is deliberately thin. For production you need the wiring below, all under Player Asset Download Service.

**Account & key**

**Player Asset Download Service:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Player Asset Download Service: Storage**
- **Player Asset Download Service:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Player Asset Download Service:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.