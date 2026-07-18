#!/usr/bin/env python3
"""Home Assistant REST API client.

Connects to a Home Assistant instance over its REST API to test the
connection, list entities, read states, and control devices.

Configuration is read from environment variables (or a local .env file):

    HA_URL    Base URL of your Home Assistant, e.g. https://myhome.duckdns.org
    HA_TOKEN  A Long-Lived Access Token (Profile -> Security -> Create Token)

Usage:
    python ha_client.py ping                       # verify the connection
    python ha_client.py list [FILTER]              # list entities (optional substring filter)
    python ha_client.py get ENTITY_ID              # show one entity's state
    python ha_client.py call DOMAIN SERVICE ENTITY # call a service, e.g. call light turn_on light.kitchen
    python ha_client.py on  ENTITY_ID              # shortcut for turn_on
    python ha_client.py off ENTITY_ID              # shortcut for turn_off
    python ha_client.py toggle ENTITY_ID           # shortcut for toggle
"""

import os
import sys
import json

import requests


def load_dotenv(path=".env"):
    """Minimal .env loader so we don't add a dependency."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.split("#", 1)[0].strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class HomeAssistant:
    def __init__(self, url=None, token=None, timeout=15):
        self.url = (url or os.environ.get("HA_URL", "")).rstrip("/")
        self.token = token or os.environ.get("HA_TOKEN", "")
        self.timeout = timeout
        if not self.url or not self.token:
            raise SystemExit(
                "Missing configuration. Set HA_URL and HA_TOKEN "
                "(environment variables or a .env file)."
            )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )

    def _get(self, path):
        r = self.session.get(f"{self.url}/api/{path}", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path, payload):
        r = self.session.post(
            f"{self.url}/api/{path}", json=payload, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json() if r.text else {}

    def ping(self):
        """Return the API root message; raises on auth/connection failure."""
        return self._get("")

    def config(self):
        return self._get("config")

    def states(self):
        return self._get("states")

    def state(self, entity_id):
        return self._get(f"states/{entity_id}")

    def call_service(self, domain, service, entity_id=None, **data):
        payload = dict(data)
        if entity_id:
            payload["entity_id"] = entity_id
        return self._post(f"services/{domain}/{service}", payload)


def _domain_of(entity_id):
    return entity_id.split(".", 1)[0]


def main(argv):
    load_dotenv()
    if not argv:
        print(__doc__)
        return 1

    cmd = argv[0]
    ha = HomeAssistant()

    if cmd == "ping":
        try:
            msg = ha.ping()
            cfg = ha.config()
            print(f"Connected to Home Assistant at {ha.url}")
            print(f"  API says: {msg.get('message')}")
            print(
                f"  Location: {cfg.get('location_name')}  "
                f"Version: {cfg.get('version')}"
            )
            print(f"  Entities: {len(ha.states())}")
            return 0
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            if code == 401:
                print("Connection reached HA, but the token was rejected (401).")
            else:
                print(f"HTTP error {code}: {e}")
            return 2
        except requests.exceptions.RequestException as e:
            print(f"Could not reach Home Assistant at {ha.url}: {e}")
            return 2

    if cmd == "list":
        filt = argv[1].lower() if len(argv) > 1 else ""
        rows = sorted(ha.states(), key=lambda s: s["entity_id"])
        for s in rows:
            eid = s["entity_id"]
            if filt and filt not in eid.lower():
                continue
            name = s.get("attributes", {}).get("friendly_name", "")
            print(f"{eid:45} {s['state']:12} {name}")
        return 0

    if cmd == "get":
        if len(argv) < 2:
            print("Usage: get ENTITY_ID")
            return 1
        print(json.dumps(ha.state(argv[1]), indent=2, ensure_ascii=False))
        return 0

    if cmd == "call":
        if len(argv) < 4:
            print("Usage: call DOMAIN SERVICE ENTITY_ID")
            return 1
        _, domain, service, entity = argv[:4]
        result = ha.call_service(domain, service, entity)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if cmd in ("on", "off", "toggle"):
        if len(argv) < 2:
            print(f"Usage: {cmd} ENTITY_ID")
            return 1
        entity = argv[1]
        service = {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[cmd]
        domain = _domain_of(entity)
        # homeassistant.turn_on/off works across most domains as a fallback
        if domain in ("switch", "light", "fan", "cover", "climate", "media_player"):
            target_domain = domain
        else:
            target_domain = "homeassistant"
        result = ha.call_service(target_domain, service, entity)
        print(f"Called {target_domain}.{service} on {entity}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"Unknown command: {cmd}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
