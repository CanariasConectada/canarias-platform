#!/usr/bin/env python3
"""Minimal stdlib client for TypeSafe Jev via the OpenRouter Decisions API.

The API key is read from ~/.claude/.jev-key and only ever sent in the
Authorization header. Every call is cached on disk (keyed by request hash) so
re-runs are free, and the cost reported by the API is accumulated in
cost.jsonl next to the cache.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
KEY_PATH = Path(os.environ.get("JEV_KEY_PATH", "~/.claude/.jev-key")).expanduser()
CACHE_DIR = Path(os.environ.get("JEV_CACHE_DIR", "/home/odoo/Pending/jev-work/cache"))
COST_LOG = CACHE_DIR / "cost.jsonl"


def _key() -> str:
    return KEY_PATH.read_text().strip()


def decide(state: str, questions: dict, tag: str = "", retries: int = 3) -> dict:
    """Send one Decisions request. Returns the parsed response (cached).

    ``questions`` is a record keyed by question name. Each value is one of:
      {"type": "noul",   "instructions": str, "criteria": {"true": str, "false": str}}
      {"type": "choice", "instructions": str, "criteria": {key: description, ...}}
      {"type": "score",  "instructions": str, "criteria": [level0, level1, ...]}
    Answers come back keyed by the same names:
      noul   -> {"noul": p}
      choice -> {"choice": key, "confidence": c, "probabilities": {...}}
      score  -> {"score": x, "confidence": c, "probabilities": {...}}
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"model": MODEL, "state": state, "questions": questions}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    cache_file = CACHE_DIR / f"{digest}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://canariasconectada.es",
            "X-Title": "canarias-microsites-jev",
        },
        method="POST",
    )
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"Jev request failed after {retries} attempts: {last_err}")
    cache_file.write_text(json.dumps(data, ensure_ascii=False))
    cost = (data.get("usage") or {}).get("cost")
    with COST_LOG.open("a") as fh:
        fh.write(json.dumps({"ts": time.time(), "tag": tag, "cost": cost, "hash": digest,
                             "state_chars": len(state), "n_questions": len(questions)}) + "\n")
    return data


def total_cost() -> float:
    if not COST_LOG.exists():
        return 0.0
    return sum((json.loads(ln).get("cost") or 0.0) for ln in COST_LOG.read_text().splitlines() if ln.strip())


if __name__ == "__main__":
    # Smoke test: one tiny request exercising the three question kinds.
    out = decide(
        "Business: 'Churrería Astrid'. It sells churros, chocolate and coffee for breakfast in Las Palmas.",
        {
            "niche": {"type": "choice", "instructions": "Which niche fits this business best?",
                      "criteria": {"restaurant_cafe": "Food and drink served on premises",
                                   "hairdresser": "Hair salon or barber",
                                   "hardware_store": "Tools and building supplies",
                                   "clothing_shop": "Apparel retail"}},
            "is_manual": {"type": "noul",
                          "instructions": "Was this description written specifically for this business?",
                          "criteria": {"true": "Specific, concrete details about this business",
                                       "false": "Generic template or placeholder wording"}},
        },
        tag="smoke",
    )
    print(json.dumps(out, ensure_ascii=False, indent=1)[:1500])
    print("total cost so far:", total_cost())
