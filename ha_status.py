"""
Home Assistant Status Query
Queries a Home Assistant instance via its REST API and prints entity states.

Reads configuration from the environment (and a local .env file if present):
    HA_URL       Base URL of the instance, e.g. http://192.168.1.50:8123
    HA_TOKEN     Long-Lived Access Token (Profile -> Long-Lived Access Tokens)
    HA_ENTITIES  Optional comma-separated entity_ids to query, e.g.
                 sensor.temperature,light.living_room
                 If omitted, prints a summary of every entity.

Usage:
    python ha_status.py                       # use HA_ENTITIES / all entities
    python ha_status.py sensor.temperature    # query specific entities
"""

import json
import os
import sys
import urllib.error
import urllib.request


def load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE lines from a .env file without overriding real env vars."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            # Strip inline comments and surrounding quotes
            value = value.split("#", 1)[0].strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def api_get(base_url: str, path: str, token: str) -> object:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def check_api(base_url: str, token: str) -> bool:
    try:
        result = api_get(base_url, "/api/", token)
        message = result.get("message", "") if isinstance(result, dict) else ""
        print(f"✅ API reachable: {message or 'OK'}  ({base_url})")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("❌ Authentication failed (401) — check HA_TOKEN.")
        else:
            print(f"❌ API error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"❌ Cannot reach {base_url}: {e.reason}")
    return False


def print_state(state: dict) -> None:
    entity_id = state.get("entity_id", "?")
    value = state.get("state", "?")
    attrs = state.get("attributes", {})
    unit = attrs.get("unit_of_measurement", "")
    name = attrs.get("friendly_name", entity_id)
    changed = state.get("last_changed", "")
    unit_str = f" {unit}" if unit else ""
    print(f"  {entity_id:<40} {value}{unit_str:<8}  ({name})  last_changed={changed}")


def query_entities(base_url: str, token: str, entity_ids: list[str]) -> None:
    print(f"\nQuerying {len(entity_ids)} entit{'y' if len(entity_ids) == 1 else 'ies'}:")
    for entity_id in entity_ids:
        try:
            state = api_get(base_url, f"/api/states/{entity_id}", token)
            print_state(state)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  {entity_id:<40} ❌ not found (404)")
            else:
                print(f"  {entity_id:<40} ❌ error {e.code}: {e.reason}")


def query_all(base_url: str, token: str) -> None:
    states = api_get(base_url, "/api/states", token)
    if not isinstance(states, list):
        print("Unexpected response from /api/states")
        return

    # Group counts by domain (the part before the first dot)
    by_domain: dict[str, int] = {}
    for state in states:
        domain = state.get("entity_id", "").split(".", 1)[0] or "unknown"
        by_domain[domain] = by_domain.get(domain, 0) + 1

    print(f"\nTotal entities: {len(states)}")
    print("By domain:")
    for domain in sorted(by_domain):
        print(f"  {domain:<24} {by_domain[domain]}")


def run() -> int:
    load_dotenv()

    base_url = os.environ.get("HA_URL", "").strip()
    token = os.environ.get("HA_TOKEN", "").strip()

    if not base_url or not token:
        print("Missing config. Set HA_URL and HA_TOKEN in .env (see .env.example).")
        return 1

    if not check_api(base_url, token):
        return 1

    # Entities from CLI args take precedence, then HA_ENTITIES env var.
    entity_ids = [e for e in sys.argv[1:] if e.strip()]
    if not entity_ids:
        env_entities = os.environ.get("HA_ENTITIES", "").strip()
        entity_ids = [e.strip() for e in env_entities.split(",") if e.strip()]

    if entity_ids:
        query_entities(base_url, token, entity_ids)
    else:
        query_all(base_url, token)

    return 0


if __name__ == "__main__":
    sys.exit(run())
