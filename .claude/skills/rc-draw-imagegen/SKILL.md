---
name: "rc-draw-imagegen"
description: "Generate images from a text prompt (or reference image) via the Right Code / rightapi.ai async draw API — supports OpenAI and Gemini endpoints. Use when the user asks to generate, draw, or create an image/picture/illustration."
---

# Right Code image generation (rc_draw)

Text-to-image (and reference-image editing) via Right Code's **async** draw API. Supports **two upstream interfaces** (auto-selected by model name):

- **OpenAI-compatible** → `POST /draw/v1/images/generations`  
  Models: `gpt-image-2`, `gpt-image-2-vip`, `gpt-image-2.5`, `nano-banana-2`, `nano-banana-2-lite`, `nano-banana-pro`

- **Gemini generateContent** → `POST /v1beta/models/{model}:generateContent`  
  Models: `gemini-3-pro-image-preview`, `gemini-nano-banana-2.1`

Both use the same async flow: submit a task, poll `GET /v1/tasks/{task_id}` until the result URL appears.

## Auth

Requires an API key (`sk-...`). Read it from the environment:

```bash
export RC_DRAW_API_KEY="sk-xxxxxxxx"
```

Script also accepts `--api-key` or env `RIGHTAPI_KEY`. Never hard-code the key into files that get committed.

## Endpoints

- OpenAI submit: `POST https://www.rightapi.ai/draw/v1/images/generations`
- Gemini submit: `POST https://www.rightapi.ai/v1beta/models/{model}:generateContent`
- Poll (shared):  `GET  https://www.rightapi.ai/v1/tasks/{task_id}`  ← **site-level, no `/draw` prefix**
- Header: `Authorization: Bearer sk-xxxxx`
- Model list: `GET https://www.rightapi.ai/v1/models`

## Models

**OpenAI endpoint** (default): `nano-banana-2-lite` (cheap/fast), `gpt-image-2`, `gpt-image-2-vip`, `gpt-image-2.5`, `nano-banana-2`, `nano-banana-pro`.  
`imageSize` (1K/2K/4K) only works on vip / nano-banana models.

**Gemini endpoint**: `gemini-3-pro-image-preview`, `gemini-nano-banana-2.1`.  
Gemini generates one image per call (ignores `-n`).

## Key gotchas (verified)

1. **Cloudflare blocks the default python-urllib User-Agent** with `HTTP 403 error code: 1010`. Always send a normal `User-Agent` header on every request (submit, poll, and image download).
2. **A completed task returns NO `status` field** — the body flips straight to `{"created":..., "data":[{"url":...}]}`. Detect completion by presence of `data` (OpenAI) or `candidates` (Gemini), not by `status=="completed"`.
3. Poll `status` while in progress is `queued`/`in_progress` (or initial `processing`); failure is `{"status":"failed","error":{"message":...}}`.
4. Result is usually a **URL** (download it yourself); can sometimes be `b64_json`.
5. Request body must include `"async": true`.
6. **Task query is site-level** — `GET https://www.rightapi.ai/v1/tasks/{id}`, not under `/draw`.

## OpenAI submit example

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

## Gemini submit example

```bash
curl -sS -X POST "https://www.rightapi.ai/v1beta/models/gemini-3-pro-image-preview:generateContent" \
  -H "Authorization: Bearer $RC_DRAW_API_KEY" \
  -H "Content-Type: application/json" \
  -A "Mozilla/5.0" \
  -d '{"async":true,"contents":[{"role":"user","parts":[{"text":"a futuristic city at sunset"}]}],
       "generationConfig":{"imageConfig":{"aspectRatio":"16:9","imageSize":"1K"}}}'
# -> {"task_id":"task_...","status":"processing",...}
```

For reference images, add `{"inline_data":{"mime_type":"image/png","data":"<base64>"}}` to `parts`.

## Poll

```bash
curl -sS "https://www.rightapi.ai/v1/tasks/task_xxx" \
  -H "Authorization: Bearer $RC_DRAW_API_KEY" -A "Mozilla/5.0"
# done -> {"created":...,"data":[{"url":"https://...jpeg"}]}  (OpenAI)
# or     {"created":...,"candidates":[{"content":{"parts":[{"text":"https://..."}]}}]}  (Gemini)
```

## Ready-to-use script

The unified `rc_draw.py` script auto-detects which endpoint to use from the model name. Save and run:

```bash
export RC_DRAW_API_KEY="sk-xxxxxxxx"

# OpenAI endpoint (default)
python3 rc_draw.py -p "your prompt" -m nano-banana-2-lite --size 16:9 -o outdir

# Gemini endpoint
python3 rc_draw.py -p "cyberpunk city" -m gemini-3-pro-image-preview --size 16:9 -o outdir

# with reference image
python3 rc_draw.py -p "make it cyberpunk" --image ref.png -o outdir

# list available models
python3 rc_draw.py --list-models
```

The script is in the repo at `https://github.com/lukAI-c/rc-draw-imagegen/blob/main/rc_draw.py`.

## Output

Save images into the user's outputs/working folder and present them with a `computer://` link. Confirm the image actually downloaded (check file size / open it) before claiming success.
