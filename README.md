# eddie-tts

> A local, **OpenAI-compatible Qwen3-TTS speech server** — FastAPI, with voice cloning,
> voice design, reproducible seeds, and sampling temperature. Runs natively on
> Windows + NVIDIA Blackwell (RTX 50-series) with `torch.compile`, and on Linux/Docker.
> Text goes in, audio comes out. Nothing leaves your machine.

> "Hi there. This is Eddie, your shipboard computer, and I'm feeling just great, guys, and
> I know I'm just going to get a bundle of kicks out of any program you care to run through me."

**Keywords:** Qwen3-TTS · text-to-speech · TTS server · speech synthesis · voice cloning ·
voice design · OpenAI-compatible API · FastAPI · self-hosted · local-first · CUDA · Blackwell

---

## What this is

A thin HTTP wrapper around the open-weight [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
models, exposing OpenAI-style speech endpoints. Point any client at it and get audio back.

It's a fork of [cornball-ai/qwen3-tts-api](https://github.com/cornball-ai/qwen3-tts-api)
(see [Credits](#credits--license)). **This fork adds `seed` and `temperature`** — two
generation controls upstream does not have.

### Why this fork exists

> "I can see this relationship is something we're all going to have to work at."

[ZaphodVox](https://github.com/gumptionthomas/zaphodvox), a CLI for encoding manuscripts
into narrated audio, depends on both:

- `--voice-seed` → this server's **`seed`** parameter (reproducible synthesis)
- `--voice-temperature` → this server's **`temperature`** parameter

Upstream supports neither, so those flags silently do nothing against it. **If you're
running ZaphodVox, run Eddie.** See [Changes from upstream](#changes-from-upstream).

---

## Quick start

### Windows + Blackwell (native, no Docker)

The path this fork is tuned for. See **[WINDOWS.md](WINDOWS.md)** for the full story
(cu128 PyTorch, `triton-windows`, the `torch.compile` workarounds).

```powershell
.\windows\start_server.ps1     # sets env, resolves ffmpeg/sox, runs foreground
.\windows\stop_server.ps1
```

Binds `0.0.0.0:4123` (LAN-reachable). ZaphodVox defaults to `http://127.0.0.1:4123`, so
they line up out of the box.

### Local install (any platform)

Install a CUDA build of PyTorch **first** — Blackwell (sm_120) needs cu128; cu121 lacks
the kernels.

```bash
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install qwen-tts
pip install -r requirements.txt
python main.py
```

On Windows, skip `flash-attn` (it doesn't build) and set `USE_FLASH_ATTENTION=false`;
the server falls back to `attn_implementation="sdpa"`.

### Docker

```bash
# Ampere / Ada
docker build -t eddie-tts . && docker run -d --gpus all --network=host \
  -v ~/.cache/huggingface:/cache -e PORT=4123 eddie-tts

# Blackwell (RTX 50xx)
docker build -f Dockerfile.blackwell -t eddie-tts:blackwell . && docker run -d --gpus all \
  --network=host -v ~/.cache/huggingface:/cache -e PORT=4123 \
  -e USE_FLASH_ATTENTION=false eddie-tts:blackwell
```

`--network=host` gives reliable DNS for HuggingFace downloads. A Proxmox LXC installer
(`install-lxc.sh`) and a Gradio UI mode (`ENABLE_GRADIO=true`, port 7860) are inherited
from upstream.

---

## API

Three synthesis endpoints. All accept `seed` and `temperature`.

| Endpoint | Picks the voice by | Style control |
|---|---|---|
| `POST /v1/audio/speech` | built-in `voice` (Ryan, Vivian, …) | `instruct` |
| `POST /v1/audio/speech/upload` | your `voice_file` reference clip | the reference clip itself |
| `POST /v1/audio/speech/design` | `voice_description` text | the description itself |

Plus `GET /v1/voices` and `GET /health`.

### Built-in voices

`Vivian` · `Serena` · `Uncle_Fu` · `Dylan` · `Eric` · `Ryan` · `Aiden` · `Ono_Anna` · `Sohee`

**Languages:** English, Chinese, Japanese, Korean, German, French, Russian, Portuguese,
Spanish, Italian.

### Built-in voice

```bash
curl -X POST http://localhost:4123/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Hello, world!","voice":"Ryan","language":"English",
       "instruct":"calm narrator","seed":42,"temperature":0.65}' \
  --output speech.wav
```

### Voice cloning

**ICL mode** (higher quality) — supply the reference transcript:

```bash
curl -X POST http://localhost:4123/v1/audio/speech/upload \
  -F "input=Hello, this is my cloned voice." \
  -F "voice_file=@reference.wav" \
  -F "ref_text=Transcript of the reference audio." \
  -F "seed=42" -F "temperature=0.65" --output cloned.wav
```

**x-vector mode** (faster, no transcript) — add `-F "x_vector_only=true"` and drop `ref_text`.

| Parameter | Required | Description |
|---|---|---|
| `input` | yes | Text to synthesize |
| `voice_file` | yes | Reference audio (3+ seconds recommended) |
| `ref_text` | no* | Transcript of the reference audio (enables ICL mode) |
| `x_vector_only` | no | `true` for fast mode without a transcript |
| `language` | no | Default `English` |
| `seed` / `temperature` | no | See below |

\* Provide either `ref_text` or `x_vector_only=true`.

### Voice design

```bash
curl -X POST http://localhost:4123/v1/audio/speech/design \
  -H "Content-Type: application/json" \
  -d '{"input":"Hello there, welcome in.",
       "voice_description":"warm gravelly older man, unhurried","seed":42}' \
  --output designed.wav
```

---

## Generation parameters

### `seed` (int, optional)

Reproducible synthesis. Same seed + same inputs → **byte-identical audio**. Omit it and
each call varies. Seeds the global torch RNG immediately before generation (the
`qwen_tts` sampler draws from it).

### `temperature` (float, default `0.65`)

**This is a run-to-run variability knob, not an expressiveness dial.** Low values make
successive renders of the same text more alike; high values make them differ more. Same
voice, same words — it only nudges delivery and timing. Measured on an RTX 5080:

| temperature | cross-seed pitch divergence | duration spread |
|---|---|---|
| 0.1 | 44.7 Hz | 8.9s vs 9.3s |
| 0.9 | 57.9 Hz | 12.0s vs 10.7s |
| 1.5 | 60.7 Hz | 10.0s vs 13.9s |

Variability rises monotonically with temperature, but `0.3` vs `1.0` on the same sentence
is barely distinguishable by ear. The default of **`0.65`** is tuned for steady narration
(Qwen's own default is ~`0.9`).

### Controlling *style*, not variability

For actual "flat vs dramatic," use the style channel, not temperature:

- **`instruct`** — preset voices only. e.g. `"depressed, morose"`, `"bright and eager"`.
- **`voice_description`** — the design endpoint. *"warm gravelly older man"* vs *"bright
  cheerful young woman"* yields **117 Hz vs 357 Hz** mean pitch, from the description alone.
- **Cloned voices: change the reference clip.** `instruct` is **silently ignored** on the
  clone path — passing it produces byte-identical audio. The clone model takes *all* of its
  style, timbre and delivery both, from the reference. Match the reference's mood to what
  you want out.

---

## Changes from upstream

Per Apache 2.0 §4(b), the modifications in this fork:

- **`seed`** on all three synthesis endpoints (new).
- **`temperature`** on all three synthesis endpoints (new), default `0.65`.
- **`torch.compile`** on the talker decoder + code predictor — the autoregressive decode
  loop is launch-bound in eager mode (RTF ≈ 1.9×); compiled it runs **faster than realtime
  (RTF ≈ 0.6×)**, roughly a 3× speedup. Warmed up once at startup.
- **Windows `torch.compile` workarounds** — short TorchInductor cache dir (`MAX_PATH`),
  non-descriptive kernel names, static CUDA launcher disabled (32-bit pointer overflow).
- **Single dedicated inference thread**, so compiled kernels are reused instead of
  recompiled per request.
- **`windows/`** — PowerShell launch/stop scripts and a PowerShell cheat sheet.
- Quieted the per-generation `pad_token_id` log line; prefer the local HF cache and
  disable the HuggingFace telemetry ping at startup.
- Docs: examples use the actual default port `4123` (upstream's examples said `7811`).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `4123` | API server port |
| `HOST` | `0.0.0.0` | Bind address |
| `DEVICE` | `cuda:0` | PyTorch device |
| `DTYPE` | `bfloat16` | `bfloat16`, `float16`, `float32` |
| `USE_FLASH_ATTENTION` | `true` | Set `false` on Windows/Blackwell → uses `sdpa` |
| `COMPILE_MODEL` | `true` | `torch.compile` the decoder (this fork) |
| `TORCHINDUCTOR_CACHE_DIR` | — | Set short (e.g. `C:\ti`) on Windows |
| `LOCAL_FILES_ONLY` | `true` | Load models from cache only; no re-download |
| `MODEL_CACHE_DIR` | `/cache` | HuggingFace cache directory |
| `ENABLE_GRADIO` | `false` | Launch the Gradio UI instead of the API |

> **Note:** do **not** set `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`. `qwen_tts` makes a
> `model_info` call with no cache fallback, so hard offline mode crashes model load.
> Inference is fully local regardless — no text or audio ever leaves the machine; only
> benign model-metadata checks reach HuggingFace at startup.

## Models

Lazy-loaded on first use of the matching endpoint.

| Model | Use | VRAM |
|---|---|---|
| `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | built-in speakers (default) | ~8 GB |
| `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | voice cloning | +~4 GB |
| `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | voice design | +~4 GB |

Pre-download them:

```bash
python -c "from huggingface_hub import snapshot_download; \
  [snapshot_download(f'Qwen/Qwen3-TTS-12Hz-1.7B-{m}') \
   for m in ('CustomVoice','Base','VoiceDesign')]"
```

## Performance

| | |
|---|---|
| Cold start (load + compile warmup) | ~60–90 s |
| Generation, compiled | RTF ≈ **0.6×** (faster than realtime) |
| Generation, eager | RTF ≈ 1.9× |

Measured on an RTX 5080 (Blackwell, 16 GB, sm_120), CUDA 12.8 / PyTorch 2.9, `sdpa`.

---

## Credits & license

- **Models:** [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) by QwenLM (Alibaba).
- **Upstream server:** [cornball-ai/qwen3-tts-api](https://github.com/cornball-ai/qwen3-tts-api)
  — the FastAPI wrapper, OpenAI-compatible endpoint design, Dockerfiles, and LXC installer
  are theirs. Eddie is a fork of it; see [Changes from upstream](#changes-from-upstream).
  Upstream also ships an [R client, `tts.api`](https://github.com/cornball-ai/tts.api).
- **Client:** [ZaphodVox](https://github.com/gumptionthomas/zaphodvox) — the CLI this
  server was tuned for.

Licensed under **Apache 2.0**, following upstream and Qwen3-TTS. See [LICENSE](LICENSE).
