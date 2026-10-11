# rc-draw-imagegen

A [Claude](https://claude.ai) skill + standalone Python script for **text-to-image generation** via the [Right Code (rightapi.ai)](https://www.rightapi.ai) async draw API.

> Verified working 2026-10.  Models available on a standard key:
> `gpt-image-2` · `gpt-image-2-vip` · `gpt-image-2.5` · `nano-banana-2` · `nano-banana-2-lite` · `nano-banana-pro`

---

## Install the Claude skill

1. Download [`rc-draw-imagegen.skill`](../../releases/latest) from Releases.
2. Open it in **Cowork / Claude** — click **Save skill**.
3. That's it.  In any future session just say *"画一张…图"* and the skill triggers automatically.

**The skill needs your API key at runtime** — set the env var or paste the key when prompted:

```bash
export RC_DRAW_API_KEY="sk-xxxxxxxx"
```

---

## Use the standalone script

No dependencies beyond Python 3.8+ stdlib.

```bash
# install
git clone https://github.com/lukAI-c/rc-draw-imagegen.git
cd rc-draw-imagegen

# set your key
export RC_DRAW_API_KEY="sk-xxxxxxxx"

# generate
python3 rc_draw.py -p "a red paper lantern glowing at night, ink painting style" --size 16:9 -o out/

# with reference image (img2img / editing)
python3 rc_draw.py -p "make it cyberpunk" --image ref.png -o out/

# list available models
python3 rc_draw.py --list-models
```

### Full options

| Flag | Default | Description |
|------|---------|-------------|
| `-p` / `--prompt` | *(required)* | Image prompt |
| `-m` / `--model` | `nano-banana-2-lite` | Model name |
| `-n` | `1` | Number of images |
| `--size` | `1:1` | Ratio `1:1` `16:9` `9:16` `4:3`, or pixels `1024x1024` |
| `--image-size` | `1K` | `1K` / `2K` / `4K` — vip / nano-banana models only |
| `--image` | — | Reference image path or URL (repeatable) |
| `-o` / `--out` | `.` | Output directory |
| `--timeout` | `300` | Max seconds to wait |
| `--interval` | `5` | Poll interval (seconds) |
| `--api-key` | — | Override `RC_DRAW_API_KEY` env |
| `--list-models` | — | Print known models and exit |

---

## How it works

Right Code uses an **async two-step flow**:

```
POST /draw/v1/images/generations   { "async": true, ... }
  → { "task_id": "task_xxx" }

GET  /v1/tasks/task_xxx             ← site-level, no /draw prefix
  → { "created": …, "data": [{ "url": "https://…jpg" }] }
```

### Gotchas (hard-won from debugging)

1. **Cloudflare UA block** — The API sits behind Cloudflare which returns `HTTP 403 error 1010` for the default Python `urllib` User-Agent.  Every request (submit, poll, download) sends `User-Agent: Mozilla/5.0`.
2. **No `status: completed`** — A finished task drops the `status` field entirely and the body becomes `{ "created": …, "data": [{…}] }`.  Completion is detected by the presence of `data`/`candidates`, not by checking `status == "completed"`.
3. **Task query is site-level** — `GET https://www.rightapi.ai/v1/tasks/{id}`, **not** `https://www.rightapi.ai/draw/v1/tasks/{id}`.

---

## Repo structure

```
rc-draw-imagegen/
├── rc_draw.py                              # standalone CLI script
├── .claude/
│   └── skills/
│       └── rc-draw-imagegen/
│           └── SKILL.md                   # Claude skill definition
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).
