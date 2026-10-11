#!/usr/bin/env python3
"""
rc_draw.py — Text-to-image (and reference-image editing) via Right Code (rightapi.ai) async draw API.

Usage:
    export RC_DRAW_API_KEY="sk-xxxxxxxx"
    python3 rc_draw.py -p "your prompt"
    python3 rc_draw.py -p "your prompt" -m nano-banana-2-lite --size 16:9 --image-size 1K -o outdir
    python3 rc_draw.py -p "make it cyberpunk" --image ref.png -o outdir
    python3 rc_draw.py --list-models

Auth (in priority order):
    --api-key flag  >  RC_DRAW_API_KEY env  >  RIGHTAPI_KEY env
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

DRAW_BASE = "https://www.rightapi.ai/draw/v1/images/generations"
TASK_BASE = "https://www.rightapi.ai/v1/tasks/"

MODELS = [
    "gpt-image-2", "gpt-image-2-vip", "gpt-image-2.5",
    "nano-banana-2", "nano-banana-2-lite", "nano-banana-pro",
]

# NOTE: Cloudflare blocks the default python-urllib UA with HTTP 403 (error 1010).
#       Send this header on EVERY request: submit, poll, and image download.
UA = "Mozilla/5.0 (rc_draw.py)"


def get_key(cli_key):
    k = cli_key or os.environ.get("RC_DRAW_API_KEY") or os.environ.get("RIGHTAPI_KEY")
    if not k:
        sys.exit("ERROR: no API key.\nSet RC_DRAW_API_KEY env var or pass --api-key sk-xxx")
    return k if k.startswith("Bearer ") else "Bearer " + k


def _req(url, key, data=None):
    headers = {"Authorization": key, "Content-Type": "application/json", "User-Agent": UA}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='ignore')}")


def submit(key, model, prompt, n, size, image_size, image_paths):
    payload = {"model": model, "prompt": prompt, "n": n, "async": True}
    if size:        payload["size"]      = size
    if image_size:  payload["imageSize"] = image_size
    if image_paths:
        refs = []
        for p in image_paths:
            if p.startswith(("data:", "http")):
                refs.append(p)
            else:
                with open(p, "rb") as f:
                    refs.append("data:image/png;base64," + base64.b64encode(f.read()).decode())
        payload["image"] = refs
    return _req(DRAW_BASE, key, payload)


def poll(key, task_id, timeout, interval):
    """
    Key insight: a completed task returns NO 'status' field.
    The body switches to {created, data:[{url}]}.
    Detect completion by presence of 'data' or 'candidates', not status=='completed'.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = _req(TASK_BASE + task_id, key)
        if r.get("status") == "failed":
            sys.exit("Task failed: " + json.dumps(r.get("error", r), ensure_ascii=False))
        if r.get("data") or r.get("candidates"):
            return r
        last = r
        time.sleep(interval)
    sys.exit("Timed out. Last: " + json.dumps(last, ensure_ascii=False))


def extract_urls(result):
    urls = []
    for item in result.get("data") or []:
        if item.get("url"):       urls.append(item["url"])
        elif item.get("b64_json"): urls.append("b64:" + item["b64_json"])
    for cand in result.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            if part.get("text"): urls.append(part["text"])
    return urls


def main():
    ap = argparse.ArgumentParser(description="Text-to-image via Right Code async draw API.")
    ap.add_argument("-p", "--prompt",     default=None)
    ap.add_argument("-m", "--model",      default="nano-banana-2-lite")
    ap.add_argument("-n",                 type=int, default=1)
    ap.add_argument("--size",             default="1:1",
                    help="Ratio 1:1/16:9/9:16/4:3 or pixels 1024x1024")
    ap.add_argument("--image-size",       default="1K",  help="1K/2K/4K")
    ap.add_argument("--image",            action="append", default=[], metavar="PATH_OR_URL")
    ap.add_argument("-o", "--out",        default=".")
    ap.add_argument("--timeout",          type=int, default=300)
    ap.add_argument("--interval",         type=int, default=5)
    ap.add_argument("--api-key",          default=None)
    ap.add_argument("--list-models",      action="store_true")
    a = ap.parse_args()

    if a.list_models:
        print("\n".join(MODELS)); return
    if not a.prompt:
        ap.error("-p/--prompt is required")

    key = get_key(a.api_key)
    sub = submit(key, a.model, a.prompt, a.n, a.size, a.image_size, a.image)
    tid = sub.get("task_id")
    if not tid:
        sys.exit("No task_id: " + json.dumps(sub, ensure_ascii=False))
    print(f"Submitted → task_id={tid}  (polling every {a.interval}s…)")

    result = poll(key, tid, a.timeout, a.interval)
    urls   = extract_urls(result)
    if not urls:
        sys.exit("No image in result: " + json.dumps(result, ensure_ascii=False)[:500])

    os.makedirs(a.out, exist_ok=True)
    saved = []
    for i, u in enumerate(urls):
        ext = ".png"
        if u.startswith("b64:"):
            raw = base64.b64decode(u[4:])
        else:
            if u.endswith((".jpg", ".jpeg")): ext = ".jpg"
            with urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": UA}), timeout=120
            ) as r:
                raw = r.read()
        path = os.path.join(a.out, f"rc_{tid[-8:]}_{i}{ext}")
        with open(path, "wb") as f: f.write(raw)
        saved.append(path)
        print("Saved:", path)

    print(json.dumps({"task_id": tid, "files": saved}, ensure_ascii=False))


if __name__ == "__main__":
    main()
