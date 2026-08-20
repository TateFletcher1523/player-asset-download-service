import json
import os
from urllib.request import Request, urlopen


payload = json.dumps(
    {"player_id": "player-42", "asset_id": "replay-7f3", "asset_kind": "replay"}
).encode()
request = Request(
    os.environ.get("GAME_BACKEND_URL", "http://127.0.0.1:8000") + "/downloads",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request) as response:
    print(json.dumps(json.load(response), indent=2))
