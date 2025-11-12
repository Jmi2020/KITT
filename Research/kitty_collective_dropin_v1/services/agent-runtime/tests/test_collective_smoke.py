
import os, requests

BASE = os.getenv("COLLECTIVE_BASE","http://localhost:8093/api/collective")

def test_council_smoke():
    r = requests.post(f"{BASE}/run", json={"task":"Propose infill & wall settings for a fast PETG print on Voron.","pattern":"council","k":3})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "verdict" in data and isinstance(data["verdict"], str)
    assert len(data.get("proposals",[])) >= 2
