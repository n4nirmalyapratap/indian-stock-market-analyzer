#!/usr/bin/env python3
"""kimchi_probe.py — show EXACTLY what Kimchi returns for your API key.

The app logs only show truncated errors. This hits Kimchi directly and prints
the raw HTTP status + request-id + full body, so you can tell the cases apart:

    401 = bad / missing key
    402 = no usable credit (billing not enabled, or that model's provider is dry)
    400 = bad model / request
    403 = model not enabled on your plan
    200 = works

Run it inside the backend container (python is 3.11 there), or with any python3:

    KIMCHI_API_KEY=sk-...  python3 scripts/kimchi_probe.py

It also auto-reads KIMCHI_API_KEY / KIMCHI_BASE_URL from the environment or a
nearby .env file. No third-party deps — pure stdlib.
"""
import json
import os
import sys
import urllib.error
import urllib.request

if sys.version_info[0] < 3:
    sys.exit("Run with python3 (the default `python` here may be 2.x).")

BASE = (os.environ.get("KIMCHI_BASE_URL") or "https://llm.kimchi.dev/openai/v1").rstrip("/")
KEY = os.environ.get("KIMCHI_API_KEY", "")

# Fallback: scan a few likely .env locations for the key.
if not KEY:
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (".env", "../.env", "../../.env", "../../../.env"):
        path = os.path.join(here, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("KIMCHI_API_KEY="):
                        KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except OSError:
            continue
        if KEY:
            print(f"(read KIMCHI_API_KEY from {os.path.normpath(path)})")
            break

if not KEY:
    sys.exit("ERROR: KIMCHI_API_KEY not found in the environment or a nearby .env")

HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
print(f"Base : {BASE}")
print(f"Key  : ...{KEY[-4:]} (len {len(KEY)})\n")


def call(method, path, payload=None):
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return None, {}, f"(transport error) {exc}"


def show(label, status, headers, body):
    rid = headers.get("x-request-id") or headers.get("X-Request-Id") or "-"
    verdict = {
        200: "OK — works",
        400: "bad model / request",
        401: "bad or missing API key",
        402: "no usable credit / billing not enabled",
        403: "forbidden — model not enabled on your plan",
        404: "endpoint / model not found",
        429: "rate-limited",
    }.get(status, "")
    print(f"=== {label} ===")
    tail = f"— {verdict}" if verdict else ""
    print(f"HTTP {status} {tail}   request-id: {rid}")
    try:
        body = json.dumps(json.loads(body), indent=2)
    except Exception:
        pass
    print(body[:2000], "\n")


# 1. What models can this key actually use?
show("GET /models", *call("GET", "/models"))

# 2. Minimal 1-token completion per model.
for model in ("minimax-m3", "kimi-k2.6"):
    show(
        f"POST /chat/completions  [{model}]",
        *call(
            "POST",
            "/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
        ),
    )

print("How to read the codes above:")
print("  401 on everything            -> the API key is wrong/empty")
print("  402 on everything            -> your $50 isn't spendable yet: activate")
print("                                  billing / add a payment method in the")
print("                                  Kimchi dashboard (free credits often need")
print("                                  billing 'enabled' before they apply)")
print("  402 on kimi-k2.6, 200 on m3  -> just set KIMCHI_MODEL=minimax-m3")
print("  200                          -> Kimchi works; the app will use it")
