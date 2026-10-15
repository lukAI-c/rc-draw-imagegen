#!/usr/bin/env python3
"""rc_draw.py - text-to-image via Right Code (rightapi.ai) async draw API.

Supports two upstream interfaces, auto-selected by model name:

  * OpenAI-compatible  -> POST /draw/v1/images/generations   (gpt-image-*, nano-banana-*)
  * Gemini generateContent -> POST /v1beta/models/{model}:generateContent  (gemini-*)

Both are async: submit returns a task_id, then poll GET /v1/tasks/{id}.
"""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error

DRAW_BASE = "https://www.rightapi.ai/draw/v1/images/generations"
GEMINI_BASE = "https://www.rightapi.ai/v1beta/models/{model}:generateContent"
TASK_BASE = "https://www.rightapi.ai/v1/tasks/"

OPENAI_MODELS = ["gpt-image-2", "gpt-image-2-vip", "gpt-image-2.5",
                 "nano-banana-2", "nano-banana-2-lite", "nano-banana-pro"]
GEMINI_MODELS = ["gemini-3-pro-image-preview", "gemini-nano-banana-2.1"]
UA = "Mozilla/5.0 (rc_draw.py)"


def is_gemini(model):
    """Gemini models are routed through the generateContent endpoint."""
    return model.startswith("gemini-") or model in GEMINI_MODELS


def get_key(cli):
    k = cli or os.environ.get("RC_DRAW_API_KEY") or os.environ.get("RIGHTAPI_KEY")
    if not k:
        sys.exit("ERROR: no API key (set RC_DRAW_API_KEY or --api-key).")
    return k if k.startswith("Bearer ") else "Bearer " + k


def _req(url, key, data=None):
    h = {"Authorization": key, "Content-Type": "application/json", "User-Agent": UA}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='ignore')}")


def _img_to_data_url(f):
    """Normalise an image argument (path / http url / data url) to a data URL."""
    if f.startswith("data:"):
        return f, f.split(";")[0].replace("data:", "") or "image/png"
    if f.startswith("http"):
        req = urllib.request.Request(f, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
        ctype = resp.headers.get("Content-Type", "image/png").split(";")[0]
        return "data:%s;base64,%s" % (ctype, base64.b64encode(raw).decode()), ctype
    mime = "image/jpeg" if f.lower().endswith((".jpg", ".jpeg")) else \
           "image/webp" if f.lower().endswith(".webp") else "image/png"
    with open(f, "rb") as fh:
        return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode()), mime


def submit_openai(key, model, prompt, n, size, image_size, imgs):
    p = {"model": model, "prompt": prompt, "n": n, "async": True}
    if size:
        p["size"] = size
    if image_size:
        p["imageSize"] = image_size
    if imgs:
        p["image"] = [_img_to_data_url(f)[0] for f in imgs]
    return _req(DRAW_BASE, key, p)


def submit_gemini(key, model, prompt, n, size, image_size, imgs):
    """Gemini is always one image; n is ignored. Ratio/resolution go in imageConfig."""
    parts = [{"text": prompt}]
    for f in imgs:
        data_url, mime = _img_to_data_url(f)
        parts.append({"inline_data": {"mime_type": mime, "data": data_url.split(";base64,", 1)[1]}})

    payload = {"async": True, "contents": [{"role": "user", "parts": parts}]}

    cfg = {}
    if size and ":" in size:
        cfg["aspectRatio"] = size
    if image_size:
        cfg["imageSize"] = image_size
    if cfg:
        payload["generationConfig"] = {"imageConfig": cfg}

    return _req(GEMINI_BASE.format(model=model), key, payload)


def submit(key, model, prompt, n, size, image_size, imgs):
    if is_gemini(model):
        return submit_gemini(key, model, prompt, n, size, image_size, imgs)
    return submit_openai(key, model, prompt, n, size, image_size, imgs)


def poll(key, tid, timeout, interval):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        r = _req(TASK_BASE + tid, key)
        if r.get("status") == "failed":
            sys.exit("Task failed: " + json.dumps(r.get("error", r)))
        # A done task carries no status field: detect via data / candidates.
        if r.get("data") or r.get("candidates"):
            return r
        last = r
        time.sleep(interval)
    sys.exit("Timed out. Last: " + json.dumps(last))


def urls_of(r):
    u = [i["url"] for i in (r.get("data") or []) if i.get("url")]
    u += ["b64:" + i["b64_json"] for i in (r.get("data") or []) if i.get("b64_json")]
    for c in (r.get("candidates") or []):
        for p in c.get("content", {}).get("parts", []) or []:
            if p.get("text"):
                u.append(p["text"])
    return u


def main():
    ap = argparse.ArgumentParser(
        description="Text-to-image via Right Code (OpenAI + Gemini endpoints).")
    ap.add_argument("-p", "--prompt")
    ap.add_argument("-m", "--model", default="nano-banana-2-lite")
    ap.add_argument("-n", type=int, default=1, help="count (OpenAI endpoint only)")
    ap.add_argument("--size", default="1:1", help="ratio 1:1 / 16:9 / 9:16 / 4:3, or WxH")
    ap.add_argument("--image-size", default="1K", help="1K / 2K / 4K")
    ap.add_argument("--image", action="append", default=[], help="reference image (repeatable)")
    ap.add_argument("-o", "--out", default=".")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--api-key")
    ap.add_argument("--list-models", action="store_true")
    a = ap.parse_args()

    if a.list_models:
        print("OpenAI endpoint:")
        print("\n".join("  " + m for m in OPENAI_MODELS))
        print("Gemini endpoint:")
        print("\n".join("  " + m for m in GEMINI_MODELS))
        return
    if not a.prompt:
        ap.error("-p/--prompt required")

    key = get_key(a.api_key)
    sub = submit(key, a.model, a.prompt, a.n, a.size, a.image_size, a.image)
    tid = sub.get("task_id") or sys.exit("No task_id: " + json.dumps(sub))
    print(f"task_id={tid} via {'gemini' if is_gemini(a.model) else 'openai'} (polling...)")

    r = poll(key, tid, a.timeout, a.interval)
    us = urls_of(r) or sys.exit("No image: " + json.dumps(r)[:400])

    os.makedirs(a.out, exist_ok=True)
    saved = []
    for i, u in enumerate(us):
        ext = ".png"
        if u.startswith("b64:"):
            raw = base64.b64decode(u[4:])
        else:
            if u.endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            with urllib.request.urlopen(
                    urllib.request.Request(u, headers={"User-Agent": UA}), timeout=120) as resp:
                raw = resp.read()
        path = os.path.join(a.out, f"rc_{tid[-8:]}_{i}{ext}")
        with open(path, "wb") as fh:
            fh.write(raw)
        saved.append(path)
        print("saved:", path)
    print(json.dumps({"task_id": tid, "files": saved}))


if __name__ == "__main__":
    main()
