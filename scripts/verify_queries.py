"""Quick verification of key queries against the live app."""
import json
import urllib.request

BASE = "https://web-production-bbe17.up.railway.app"
QUERIES = [
    "boat race",
    "boat races this weekend",
    "live music",
    "concert tonight",
    "kids activities",
    "things to do this weekend",
]

for i, msg in enumerate(QUERIES):
    req = urllib.request.Request(
        f"{BASE}/chat",
        data=json.dumps({"session_id": f"verify-{i}", "message": msg}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    d = json.loads(urllib.request.urlopen(req, timeout=15).read())
    count = d.get("data", {}).get("count", "?")
    lines = [ln for ln in d.get("response", "").splitlines() if ln.strip()]
    first_event = lines[1] if len(lines) > 1 else (lines[0] if lines else "?")
    safe = first_event.encode("ascii", "replace").decode()
    print(f"[{str(count):>3}] {msg!r:<35} -> {safe[:65]}")
