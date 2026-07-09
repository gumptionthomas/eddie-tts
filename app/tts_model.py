"""
Qwen3-TTS model wrapper
"""

import os
import torch
from typing import Optional, Tuple, Union
import numpy as np

from app.config import Config

# --- torch.compile setup: ~3x faster autoregressive generation on the RTX 5080 ---
# The decode loop is launch/overhead-bound (GPU ~20% busy eager); compiling the
# talker decoder keeps the GPU fed. Windows-safe inductor settings:
#   - short kernel names avoid the 260-char MAX_PATH limit on generated files
#   - the static CUDA launcher has a 32-bit-long pointer-overflow bug on Windows
os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", r"C:\ti")
try:
    import torch._inductor.config as _ind
    _ind.use_static_cuda_launcher = False
    _ind.triton.descriptive_names = False
except Exception as _e:  # pragma: no cover
    print(f"inductor config warning: {_e}")
torch.set_float32_matmul_precision("high")

_COMPILE = os.getenv("COMPILE_MODEL", "true").lower() == "true"

# All GPU generation runs on ONE dedicated thread. torch.compile caches its kernels
# per worker thread, so a single persistent thread (warmed up once) means every
# request reuses the compiled artifacts instead of recompiling / falling back to eager.
import asyncio
from concurrent.futures import ThreadPoolExecutor
infer_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="infer")


def _maybe_compile(model):
    """Compile the talker decoder + code predictor (~3x faster). No-op if disabled/unsupported."""
    if not _COMPILE:
        return model
    try:
        inner = model.model  # Qwen3TTSForConditionalGeneration
        inner.talker.model = torch.compile(inner.talker.model, dynamic=True)
        cp = getattr(inner.talker, "code_predictor", None)
        if cp is not None and hasattr(cp, "model"):
            cp.model = torch.compile(cp.model, dynamic=True)
        print("torch.compile applied to talker decoder + code predictor")
    except Exception as e:
        print(f"torch.compile skipped ({type(e).__name__}: {e})")
    return model


def _warmup_custom_voice():
    """Trigger compilation once at startup so the first real request is already fast."""
    if not _COMPILE:
        return
    try:
        print("Warming up: first generation compiles the model (this takes ~30-90s)...")
        generate_custom_voice(
            text="Warming up the compiled speech model so the first request is fast.",
            language="English", speaker=Config.DEFAULT_SPEAKER,
        )
        print("Warmup complete; compiled kernels cached.")
    except Exception as e:
        print(f"Warmup skipped ({type(e).__name__}: {e})")


# Global model instances
_custom_voice_model = None  # For built-in speakers
_voice_clone_model = None   # For voice cloning
_voice_design_model = None  # For voice design from description
_custom_voice_loading = False
_voice_clone_loading = False
_voice_design_loading = False


def get_dtype():
    """Get torch dtype from config"""
    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return dtype_map.get(Config.DTYPE, torch.bfloat16)


def _seed_rng(seed: Optional[int]) -> None:
    """Seed the global torch RNG for reproducible sampling.

    qwen_tts's generate_* methods take no seed kwarg -- they sample from the global
    torch RNG -- so seeding it right before generation makes the output deterministic.
    """
    if seed is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)


async def initialize_model():
    """Initialize the CustomVoice model for built-in speakers"""
    global _custom_voice_model, _custom_voice_loading

    if _custom_voice_model is not None or _custom_voice_loading:
        return

    _custom_voice_loading = True
    print(f"Loading Qwen3-TTS CustomVoice model: {Config.MODEL_NAME}")
    print(f"  Device: {Config.DEVICE}")
    print(f"  Dtype: {Config.DTYPE}")
    print(f"  Flash Attention: {Config.USE_FLASH_ATTENTION}")

    try:
        from qwen_tts import Qwen3TTSModel

        kwargs = {
            "device_map": Config.DEVICE,
            "dtype": get_dtype(),
            "local_files_only": Config.LOCAL_FILES_ONLY,
        }

        if Config.USE_FLASH_ATTENTION:
            kwargs["attn_implementation"] = "flash_attention_2"
        else:
            kwargs["attn_implementation"] = "sdpa"

        _custom_voice_model = _maybe_compile(Qwen3TTSModel.from_pretrained(Config.MODEL_NAME, **kwargs))
        print(f"CustomVoice model loaded successfully")
        # Warm up (compile) on the same dedicated thread that will serve requests.
        await asyncio.get_event_loop().run_in_executor(infer_pool, _warmup_custom_voice)

    except Exception as e:
        print(f"Failed to load CustomVoice model: {e}")
        raise
    finally:
        _custom_voice_loading = False


async def initialize_voice_clone_model():
    """Initialize the Base model for voice cloning (lazy loaded)"""
    global _voice_clone_model, _voice_clone_loading

    if _voice_clone_model is not None or _voice_clone_loading:
        return

    _voice_clone_loading = True
    print(f"Loading voice clone model: {Config.VOICE_CLONE_MODEL}")

    try:
        from qwen_tts import Qwen3TTSModel

        kwargs = {
            "device_map": Config.DEVICE,
            "dtype": get_dtype(),
            "local_files_only": Config.LOCAL_FILES_ONLY,
        }

        if Config.USE_FLASH_ATTENTION:
            kwargs["attn_implementation"] = "flash_attention_2"
        else:
            kwargs["attn_implementation"] = "sdpa"

        _voice_clone_model = _maybe_compile(Qwen3TTSModel.from_pretrained(Config.VOICE_CLONE_MODEL, **kwargs))
        print(f"Voice clone model loaded successfully")

    except Exception as e:
        print(f"Failed to load voice clone model: {e}")
        raise
    finally:
        _voice_clone_loading = False


async def initialize_voice_design_model():
    """Initialize the voice design model (lazy loaded)"""
    global _voice_design_model, _voice_design_loading

    if _voice_design_model is not None or _voice_design_loading:
        return

    _voice_design_loading = True
    print(f"Loading voice design model: {Config.VOICE_DESIGN_MODEL}")

    try:
        from qwen_tts import Qwen3TTSModel

        kwargs = {
            "device_map": Config.DEVICE,
            "dtype": get_dtype(),
            "local_files_only": Config.LOCAL_FILES_ONLY,
        }

        if Config.USE_FLASH_ATTENTION:
            kwargs["attn_implementation"] = "flash_attention_2"
        else:
            kwargs["attn_implementation"] = "sdpa"

        _voice_design_model = _maybe_compile(Qwen3TTSModel.from_pretrained(Config.VOICE_DESIGN_MODEL, **kwargs))
        print(f"Voice design model loaded successfully")

    except Exception as e:
        print(f"Failed to load voice design model: {e}")
        raise
    finally:
        _voice_design_loading = False


def get_custom_voice_model():
    """Get the CustomVoice model for built-in speakers"""
    return _custom_voice_model


def get_voice_clone_model():
    """Get the Base model for voice cloning"""
    return _voice_clone_model


def get_voice_design_model():
    """Get the voice design model"""
    return _voice_design_model


def is_model_loaded() -> bool:
    """Check if CustomVoice model is loaded"""
    return _custom_voice_model is not None


def is_voice_clone_loaded() -> bool:
    """Check if voice clone model is loaded"""
    return _voice_clone_model is not None


def is_voice_design_loaded() -> bool:
    """Check if voice design model is loaded"""
    return _voice_design_model is not None


def generate_custom_voice(
    text: str,
    language: str = "English",
    speaker: str = "Vivian",
    instruct: Optional[str] = None,
    seed: Optional[int] = None,
    temperature: Optional[float] = None
) -> Tuple[np.ndarray, int]:
    """
    Generate speech using a custom voice (one of the 9 built-in speakers).

    Args:
        text: Text to synthesize
        language: Language for synthesis
        speaker: Speaker name (Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee)
        instruct: Optional instruction for speaking style

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    if _custom_voice_model is None:
        raise RuntimeError("CustomVoice model not loaded")

    if speaker not in Config.SPEAKERS:
        print(f"Warning: Unknown speaker '{speaker}', using default '{Config.DEFAULT_SPEAKER}'")
        speaker = Config.DEFAULT_SPEAKER

    kwargs = {
        "text": text,
        "language": language,
        "speaker": speaker,
    }

    if instruct:
        kwargs["instruct"] = instruct

    if temperature is not None:
        kwargs["temperature"] = temperature

    _seed_rng(seed)
    with torch.no_grad():
        wavs, sr = _custom_voice_model.generate_custom_voice(**kwargs)

    # Return first audio (batch size 1)
    return wavs[0], sr


def generate_voice_clone(
    text: str,
    ref_audio: Union[str, np.ndarray, Tuple[np.ndarray, int]],
    language: str = "English",
    ref_text: Optional[str] = None,
    x_vector_only: bool = False,
    seed: Optional[int] = None,
    temperature: Optional[float] = None
) -> Tuple[np.ndarray, int]:
    """
    Generate speech by cloning a reference voice.

    Args:
        text: Text to synthesize
        ref_audio: Reference audio (file path, URL, numpy array, or (array, sr) tuple)
        language: Language for synthesis
        ref_text: Transcript of reference audio (improves quality)
        x_vector_only: Use only speaker embedding (faster, lower quality)

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    if _voice_clone_model is None:
        raise RuntimeError("Voice clone model not loaded")

    kwargs = {
        "text": text,
        "language": language,
        "ref_audio": ref_audio,
    }

    if ref_text:
        kwargs["ref_text"] = ref_text

    if x_vector_only:
        kwargs["x_vector_only_mode"] = True

    if temperature is not None:
        kwargs["temperature"] = temperature

    _seed_rng(seed)
    with torch.no_grad():
        wavs, sr = _voice_clone_model.generate_voice_clone(**kwargs)

    return wavs[0], sr


def generate_voice_design(
    text: str,
    language: str = "English",
    voice_description: str = "",
    seed: Optional[int] = None,
    temperature: Optional[float] = None
) -> Tuple[np.ndarray, int]:
    """
    Generate speech with a voice designed from a natural language description.

    Args:
        text: Text to synthesize
        language: Language for synthesis
        voice_description: Natural language description of the desired voice

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    if _voice_design_model is None:
        raise RuntimeError("Voice design model not loaded")

    kwargs = {
        "text": text,
        "language": language,
        "instruct": voice_description,
    }

    if temperature is not None:
        kwargs["temperature"] = temperature

    _seed_rng(seed)
    with torch.no_grad():
        wavs, sr = _voice_design_model.generate_voice_design(**kwargs)

    return wavs[0], sr
