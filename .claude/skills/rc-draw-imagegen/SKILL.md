---
name: "rc-draw-imagegen"
description: "Generate images from a text prompt (or reference image) via the Right Code / rightapi.ai async draw API — submit task, poll, download. Use when the user asks to generate, draw, or create an image/picture/illustration."
---

# Right Code image generation (rc_draw)

Text-to-image (and reference-image editing) via Right Code's **async** draw API. Two steps: submit a task, then poll until the result URL appears.

## Auth

Requires an API key (`sk-...`). Read it from the environment:

```bash
export RC_DRAW_API_KEY="sk-xxxxxxxx"
```

Script also accepts `--api-key` or env `RIGHTAPI_KEY`. Never hard-code the key into files that get committed.

## Endpoints

- Submit: `POST https://www.rightapi.ai/draw/v1/images/generations`
- Poll:   `GET  https://www.rightapi.ai/v1/tasks/{task_id}`  ← **site-level, no `/draw` prefix**
- Header: `Authorization: Bearer sk-xxxxx`
- Model list: `GET https://www.rightapi.ai/v1/models`

## Models

`gpt-image-2`, `gpt-image-2-vip`, `gpt-image-2.5`, `nano-banana-2`, `nano-banana-2-lite`, `nano-banana-pro`.
Default to `nano-banana-2-lite` (cheap/fast). `imageSize` (1K/2K/4K) only works on vip / nano-banana models.

## Key gotchas (verified)

1. **Cloudflare blocks the default python-urllib User-Agent** with `HTTP 403 error code: 1010`. Always send a normal `User-Agent` header on every request (submit, poll, and image download).
2. **A completed task returns NO `status` field** — the body flips straight to `{"created":..., "data":[{"url":...}]}`. Detect completion by presence of `data` (Images) or `candidates` (Gemini), not by `status=="completed"`.
3. Poll `status` while in progress is `queued`/`in_progress` (or initial `processing`); failure is `{"status":"failed","error":{"message":...}}`.
4. Result is usually a **URL** (download it yourself); can sometimes be `b64_json`.
5. Request body must include `"async": true`.

## Submit example

```bash
curl -sS -X POST "https://www.rightapi.ai/draw/v1/images/generations" \
  -H "Authorization: Bearer $RC_DRAW_API_KEY" \
  -H "Content-Type: application/json" \
  -A "Mozilla/5.0" \
  -d '{"model":"nano-banana-2-lite","prompt":"a red paper lantern at night, ink painting",
       "n":1,"size":"16:9","imageSize":"1K","async":true}'
# -> {"task_id":"task_...","status":"processing",...}
```

`size`: ratio `1:1` `16:9` `9:16` `4:3`, or pixels `1024x1024`.
`image`: optional array of reference images as data URLs `["data:image/png;base64,..."]` for img2img / editing.

## Poll

```bash
curl -sS "https://www.rightapi.ai/v1/tasks/task_xxx" \
  -H "Authorization: Bearer $RC_DRAW_API_KEY" -A "Mozilla/5.0"
# done -> {"created":...,"data":[{"url":"https://...jpeg"}]}
```

## Ready-to-use script

Save as `rc_draw.py` and run:

```bash
export RC_DRAW_API_KEY="sk-xxxxxxxx"
python3 rc_draw.py -p "your prompt" -m nano-banana-2-lite --size 16:9 -o outdir
python3 rc_draw.py -p "make it cyberpunk" -m nano-banana-2-lite --image ref.png -o outdir  # with reference image
python3 rc_draw.py --list-models
```

```python
#!/usr/bin/env python3
"""rc_draw.py - text-to-image via Right Code (rightapi.ai) async draw API."""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error

DRAW_BASE = "https://www.rightapi.ai/draw/v1/images/generations"
TASK_BASE = "https://www.rightapi.ai/v1/tasks/"
MODELS = ["gpt-image-2","gpt-image-2-vip","gpt-image-2.5",
          "nano-banana-2","nano-banana-2-lite","nano-banana-pro"]
UA = "Mozilla/5.0 (rc_draw.py)"

def get_key(cli):
    k = cli or os.environ.get("RC_DRAW_API_KEY") or os.environ.get("RIGHTAPI_KEY")
    if not k: sys.exit("ERROR: no API key (set RC_DRAW_API_KEY or --api-key).")
    return k if k.startswith("Bearer ") else "Bearer " + k

def _req(url, key, data=None):
    h = {"Authorization": key, "Content-Type": "application/json", "User-Agent": UA}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='ignore')}")

def submit(key, model, prompt, n, size, image_size, imgs):
    p = {"model": model, "prompt": prompt, "n": n, "async": True}
    if size: p["size"] = size
    if image_size: p["imageSize"] = image_size
    if imgs:
        out = []
        for f in imgs:
            if f.startswith(("data:","http")): out.append(f)
            else:
                out.append("data:image/png;base64," + base64.b64encode(open(f,"rb").read()).decode())
        p["image"] = out
    return _req(DRAW_BASE, key, p)

def poll(key, tid, timeout, interval):
    end = time.time() + timeout; last = None
    while time.time() < end:
        r = _req(TASK_BASE + tid, key)
        if r.get("status") == "failed":
            sys.exit("Task failed: " + json.dumps(r.get("error", r)))
        if r.get("data") or r.get("candidates"):
            return r
        last = r; time.sleep(interval)
    sys.exit("Timed out. Last: " + json.dumps(last))

def urls_of(r):
    u = [i["url"] for i in (r.get("data") or []) if i.get("url")]
    u += ["b64:"+i["b64_json"] for i in (r.get("data") or []) if i.get("b64_json")]
    for c in (r.get("candidates") or []):
        for p in c.get("content",{}).get("parts",[]) or []:
            if p.get("text"): u.append(p["text"])
    return u

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p","--prompt"); ap.add_argument("-m","--model",default="nano-banana-2-lite")
    ap.add_argument("-n",type=int,default=1); ap.add_argument("--size",default="1:1")
    ap.add_argument("--image-size",default="1K"); ap.add_argument("--image",action="append",default=[])
    ap.add_argument("-o","--out",default="."); ap.add_argument("--timeout",type=int,default=300)
    ap.add_argument("--interval",type=int,default=5); ap.add_argument("--api-key")
    ap.add_argument("--list-models",action="store_true")
    a = ap.parse_args()
    if a.list_models:
        print("\n".join(MODELS)); return
    if not a.prompt: ap.error("-p/--prompt required")
    key = get_key(a.api_key)
    sub = submit(key, a.model, a.prompt, a.n, a.size, a.image_size, a.image)
    tid = sub.get("task_id") or sys.exit("No task_id: " + json.dumps(sub))
    print(f"task_id={tid} (polling...)")
    r = poll(key, tid, a.timeout, a.interval)
    us = urls_of(r) or sys.exit("No image: " + json.dumps(r)[:400])
    os.makedirs(a.out, exist_ok=True); saved = []
    for i, u in enumerate(us):
        ext = ".png"
        if u.startswith("b64:"):
            raw = base64.b64decode(u[4:])
        else:
            if u.endswith((".jpg",".jpeg")): ext = ".jpg"
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=120) as resp:
                raw = resp.read()
        path = os.path.join(a.out, f"rc_{tid[-8:]}_{i}{ext}")
        open(path,"wb").write(raw); saved.append(path); print("saved:", path)
    print(json.dumps({"task_id": tid, "files": saved}))

if __name__ == "__main__":
    main()
```

## Output

Save images into the user's outputs/working folder and present them with a `computer://` link. Confirm the image actually downloaded (check file size / open it) before claiming success.

