#!/usr/bin/env python3
"""Certbot manual DNS-01 hook for IONOS DNS (auth and cleanup).

Used as both --manual-auth-hook and --manual-cleanup-hook:

    ionos_dns_hook.py auth      # creates _acme-challenge TXT, waits until visible
    ionos_dns_hook.py cleanup   # deletes the TXT created for this validation

Certbot provides CERTBOT_DOMAIN and CERTBOT_VALIDATION in the environment.
The API key ("<public prefix>.<secret>" from the IONOS developer portal) is read
from /etc/letsencrypt/ionos-api.ini (line IONOS_API_KEY=...), which must be
chmod 600. The key is never printed.
"""
import json
import os
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.hosting.ionos.com/dns/v1"
CREDENTIALS = os.environ.get("IONOS_API_INI", "/etc/letsencrypt/ionos-api.ini")
PROPAGATION_TIMEOUT = 600   # seconds to wait for the TXT on the authoritative servers
PROPAGATION_EXTRA = 30      # extra settle time once visible


def log(msg):
    print(f"[ionos-dns-hook] {msg}", file=sys.stderr, flush=True)


def api_key():
    mode = stat.S_IMODE(os.stat(CREDENTIALS).st_mode)
    if mode & 0o077:
        sys.exit(f"{CREDENTIALS} must be chmod 600 (is {oct(mode)})")
    with open(CREDENTIALS, encoding="utf-8") as fh:
        for line in fh:
            if line.strip().startswith("IONOS_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit(f"IONOS_API_KEY missing in {CREDENTIALS}")


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-API-Key": api_key(), "Accept": "application/json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        sys.exit(f"IONOS API {method} {path} -> HTTP {exc.code}: {exc.read().decode()[:300]}")


def zone_for(domain):
    """The IONOS zone whose name is the longest suffix of ``domain``."""
    zones = call("GET", "/zones") or []
    matches = [z for z in zones if domain == z["name"] or domain.endswith("." + z["name"])]
    if not matches:
        sys.exit(f"no IONOS zone found for {domain}")
    return max(matches, key=lambda z: len(z["name"]))


def authoritative_ns(zone_name):
    out = subprocess.run(["dig", "+short", "NS", zone_name], capture_output=True, text=True).stdout
    return [ns.rstrip(".") for ns in out.split()] or []


def txt_visible(record, value, nameservers):
    for ns in nameservers:
        out = subprocess.run(["dig", "+short", f"@{ns}", record, "TXT"], capture_output=True, text=True).stdout
        if value not in out:
            return False
    return bool(nameservers)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    domain = os.environ["CERTBOT_DOMAIN"].removeprefix("*.")
    value = os.environ["CERTBOT_VALIDATION"]
    record = f"_acme-challenge.{domain}"
    zone = zone_for(domain)
    if action == "auth":
        call("POST", f"/zones/{zone['id']}/records",
             [{"name": record, "type": "TXT", "content": value, "ttl": 60, "prio": 0, "disabled": False}])
        log(f"created TXT {record}; waiting for the authoritative servers")
        nameservers = authoritative_ns(zone["name"])
        deadline = time.time() + PROPAGATION_TIMEOUT
        while time.time() < deadline:
            if txt_visible(record, value, nameservers):
                time.sleep(PROPAGATION_EXTRA)
                log("TXT visible on all authoritative servers")
                return 0
            time.sleep(15)
        sys.exit(f"TXT {record} not visible after {PROPAGATION_TIMEOUT}s")
    if action == "cleanup":
        detail = call("GET", f"/zones/{zone['id']}?recordName={record}&recordType=TXT") or {}
        for rec in detail.get("records", []):
            if rec.get("name") == record and value in rec.get("content", ""):
                call("DELETE", f"/zones/{zone['id']}/records/{rec['id']}")
                log(f"deleted TXT {record} ({rec['id']})")
        return 0
    sys.exit("usage: ionos_dns_hook.py auth|cleanup")


if __name__ == "__main__":
    sys.exit(main())
