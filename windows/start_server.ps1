# Starts the eddie-tts server on Windows + RTX 50-series (Blackwell), no Docker.
# Usage:  powershell -ExecutionPolicy Bypass -File .\windows\start_server.ps1
#
# This script lives in <repo>\windows\. It runs the server from the repo root and
# auto-locates the Python venv. Venv search order:
#   1. $env:EDDIE_TTS_VENV               (explicit override -- full path to python.exe)
#   2. $env:QWEN_TTS_VENV                (pre-rename name for the same override)
#   3. <repo>\.venv\Scripts\python.exe   (venv created inside the repo)
#   4. <repo>\..\.venv\Scripts\python.exe (venv in the parent working dir)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot        # <repo> (contains main.py, app/)

function Resolve-VenvPython {
    foreach ($o in @($env:EDDIE_TTS_VENV, $env:QWEN_TTS_VENV)) {
        if ($o -and (Test-Path $o)) { return $o }
    }
    $candidates = @(
        (Join-Path $repo ".venv\Scripts\python.exe"),
        (Join-Path (Split-Path $repo) ".venv\Scripts\python.exe")
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}
$vpy = Resolve-VenvPython
if (-not $vpy) {
    Write-Error "No venv python found. Create a venv (.venv in the repo root) or set EDDIE_TTS_VENV to python.exe."
    exit 1
}

# Resolve sox + ffmpeg from their winget install dirs (version-agnostic) and put them on PATH.
$pkgs = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
$soxDir = Split-Path (Get-ChildItem $pkgs -Recurse -Filter sox.exe    -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)
$ffDir  = Split-Path (Get-ChildItem $pkgs -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)
$env:PATH = "$soxDir;$ffDir;$env:PATH"

# Runtime config (Blackwell / Windows / no-Docker).
$env:USE_FLASH_ATTENTION = "false"   # no flash-attn on Windows -> wrapper uses attn_implementation="sdpa"
$env:HOST                = "0.0.0.0"    # listen on all interfaces (reachable from the LAN)
$env:PORT                = "4123"
$env:DEVICE              = "cuda:0"
$env:DTYPE               = "bfloat16"

# Prefer the local cache and disable HF's telemetry ping. Inference is fully local
# regardless; on startup the HF stack still makes benign model-metadata checks (no
# text/audio -- and telemetry is off below).
# NOTE: do NOT set HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE here -- qwen_tts makes a
# model_info call with no cache fallback (and loads its processor without forwarding
# local_files_only, inference/qwen3_tts_model.py:118), so hard offline mode makes
# model load CRASH. A firewall block "works" but adds a multi-minute retry-backoff
# cold start. Left as-is intentionally: fast startup, nothing sensitive leaves.
$env:LOCAL_FILES_ONLY        = "true"   # prefer cache; skip HF file re-download
$env:HF_HUB_DISABLE_TELEMETRY = "1"     # kill the anonymous usage ping

# torch.compile: ~3x faster generation (RTF ~1.9x -> ~0.6x, faster than realtime).
# Compilation runs once at startup (warmup), so the first request is already fast.
$env:COMPILE_MODEL                    = "true"
$env:TORCHINDUCTOR_CACHE_DIR          = "C:\ti"   # short path (Windows MAX_PATH headroom)
$env:TORCHINDUCTOR_STATIC_CUDA_LAUNCHER = "0"     # Windows pointer-overflow workaround
New-Item -ItemType Directory -Force -Path "C:\ti" | Out-Null

Write-Host "python: $vpy"
Write-Host "sox   : $soxDir"
Write-Host "ffmpeg: $ffDir"
Write-Host "Starting eddie-tts on http://$($env:HOST):$($env:PORT)  (Ctrl+C to stop)"
# Run from the repo dir so `main.py`'s `app` package imports resolve, but restore
# the caller's location afterward -- including on Ctrl+C (finally still runs), so
# stopping the server doesn't leave your shell stranded inside the repo.
Push-Location $repo
try {
    & $vpy main.py
}
finally {
    Pop-Location
}
