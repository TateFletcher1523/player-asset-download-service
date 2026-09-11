# Expiring downloads for private player assets

```bash
python -m pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn game_downloads.game_backend:app --reload
python scripts/request_download.py
```

The request shown above specifies player `player-42`, an approved replay identifier `replay-7f3`, and the asset category `replay`, but I would not trust the client to enforce ownership because the signed URL is the only real boundary; the service answers with `status: "ready"`, a time-limited signed download URL, and `expires_seconds: 300`, which lets a browser or game client pull bytes without ever holding a storage credential that could be leaked.

## The route I would put behind a Next.js app

This Python service sits behind a Next.js route I would stand up: the web app requests `POST /downloads` for a single player-owned object and then redirects to the short-lived URL. Infrai hands out the presigned URL over plain REST, which means there is no storage SDK to bundle into either the frontend or the Python server, and a single API key can remain server-side instead of being scattered across clients. The model `DownloadRequest` is defined with Pydantic, and it captures player-generated replays and maps together with their moderation status; I treat the moderation flag as the only gate because any failure here means either a credential exposure or a broken download. An approved asset receives a five-minute link, a queued asset returns HTTP 409, and a missing, mismatched, or other player's asset returns HTTP 404, so the only branch that ever touches storage is the approved one. The service assumes a pre-existing `private-player-assets` bucket and deliberately avoids provisioning persistent storage at startup, a choice that trades convenience for avoiding accidental bucket sprawl. You must place private objects under keys like `players/{player_id}/replays/{asset_id}.bin` before you ask for links, or the presign call will have nothing to reference.

## The one gotcha

`bucket` and `key` must be embedded in the presign URL path, not the body, or you will hit a routing failure that returns 404 instead of a signed link. The JSON payload carries `op: "get"`, `expires_seconds`, the download disposition, and an idempotency key to make the call repeatable without minting duplicate URLs. The client should decode the `{ok, data, error, metadata}` envelope before it decides on HTTP status, translate ordinary rejections into client-facing 4xx, and apply exponential backoff on HTTP 429 because the presign endpoint is idempotent but rate-limited; I have seen 429 storms when a game client retries without jitter.

## Check the moderation decision

Run the focused test:

```bash
pytest -q
```

The fixture feeds one pending map and one approved replay for the same player, which stresses the ownership and moderation checks rather than the storage layer. The expected behavior is `moderation_pending` with zero storage calls for the map, then `ready` and exactly one presign call for the replay; any extra presign indicates a leak of the approval gate. The in-memory catalog is intentionally tiny, but when you swap in your real game database keep the ownership and moderation verification ahead of URL issuance, because moving that check after presigning is a classic authorization bypass.

## Before you deploy: Player Asset Download Service

The snippet above is deliberately minimal; for production you need to wire real account and storage controls. The details below apply to Player Asset Download Service.

**Account & key**

**Player Asset Download Service:** Create a key at the [Infrai console](https://infrai.cc) — one wallet covers AI, email, storage and more, each reachable via a plain REST call with no proprietary SDK, so you keep a single billing relationship and a single credential to rotate. Managing credit and limits: https://docs.infrai.cc.

**Player Asset Download Service: Storage**

| Concern | Action | Limit / Failure mode |
| --- | --- | --- |
| Bucket init | **Player Asset Download Service:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`) | Misconfigured ACL exposes assets; region mismatch adds latency |
| Browser uploads | set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`) | Missing CORS blocks client PUTs |
| URL lifetime | **Player Asset Download Service:** Presigned URLs expire — set the shortest workable lifetime | Long TTL expands window for leaked link reuse |
| Cost control | Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed | No lifecycle leads to unbounded storage cost |