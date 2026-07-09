# Windows / Blackwell fork notes

This is a fork of [cornball-ai/qwen3-tts-api](https://github.com/cornball-ai/qwen3-tts-api),
adapted to run natively on **Windows 11 + NVIDIA RTX 50-series (Blackwell, sm_120)**
without Docker, with latency optimization and a couple of extra generation controls.
All credit for the original FastAPI wrapper and OpenAI-compatible design goes to
cornball-ai; this fork only layers on the changes below.

## What this fork adds

**Latency (~3x faster generation)**
- `torch.compile` applied to the talker decoder + code predictor. On an RTX 5080 the
  autoregressive decode loop is launch/overhead-bound in eager mode (~RTF 1.9x);
  compiling it reaches faster-than-realtime (~RTF 0.6x).
- Windows-specific TorchInductor workarounds, without which compile fails on Windows:
  - `TORCHINDUCTOR_CACHE_DIR=C:\ti` — short path, avoids the 260-char `MAX_PATH` limit
    on generated kernel filenames.
  - `triton.descriptive_names = False` — same MAX_PATH reason.
  - `use_static_cuda_launcher = False` — the static launcher has a 32-bit pointer
    overflow on Windows.
- A single dedicated inference thread (`ThreadPoolExecutor(max_workers=1)` set as the
  event loop's default executor). `torch.compile` caches kernels per worker thread, so
  a single warmed thread means every request reuses the compiled artifacts instead of
  recompiling / falling back to eager.
- Warmup at startup so the first real request is already fast.

**New generation parameters** (all synthesis endpoints)
- `seed` (int, optional) — reproducible synthesis. Same seed + same inputs → identical
  audio. Seeds the global torch RNG before generation (qwen_tts samples from it).
- `temperature` (float, default `0.65`) — run-to-run sampling variability (Qwen's own
  default is ~0.9). Lower = steadier/more consistent across runs; higher = more varied.
  Note: this is a *variability* knob, not an expressiveness dial — same voice, same
  words, it only nudges delivery. For actual style control use `instruct` (built-in
  voices) or the voice-design endpoint's `voice_description`. `instruct` has no effect
  on the voice-clone path (the clone model takes all style from the reference clip).

**Misc**
- `attn_implementation="sdpa"` (no flash-attn on Windows).
- Quieted transformers' per-generation `pad_token_id` log line.
- Prefers the local HF cache and disables the HF telemetry ping at startup. Hard offline
  mode (`HF_HUB_OFFLINE`) is intentionally *not* used — qwen_tts makes a `model_info`
  call with no cache fallback, so it crashes model load. Inference is fully local
  regardless; only benign model-metadata checks reach HuggingFace on startup.

## Running on Windows (no Docker)

Create a Python 3.12 venv, install cu128 PyTorch **first** (Blackwell needs sm_120
kernels that cu121 lacks), then the package + `triton-windows>=3.5,<3.6` (3.7 is
incompatible with torch 2.9). Set the env vars above and launch `main.py`.

Convenience launch scripts (`start_server.ps1`, `stop_server.ps1`) and a PowerShell
cheat sheet live in the parent working directory of this repo; they set all the env
vars, resolve ffmpeg/sox from winget, bind `0.0.0.0:4123` for LAN access, and run the
server in the foreground.

## API additions at a glance

```bash
# built-in voice, reproducible + steadier delivery
curl -X POST http://localhost:4123/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"...","voice":"Ryan","seed":42,"temperature":0.3}'

# voice clone upload (multipart) — temperature as a form field
curl -X POST http://localhost:4123/v1/audio/speech/upload \
  -F "input=..." -F "voice_file=@ref.wav" -F "temperature=0.3" -F "seed=42"

# voice design from a description
curl -X POST http://localhost:4123/v1/audio/speech/design \
  -H "Content-Type: application/json" \
  -d '{"input":"...","voice_description":"warm gravelly older man","temperature":0.65}'
```
