"""
Qwen3-TTS model wrapper
"""

import os
import torch
from typing import Optional, Tuple, Union
import numpy as np

from app.config import Config

# Global model instances
_base_model = None
_voice_design_model = None
_model_loading = False
_voice_design_loading = False


def get_dtype():
    """Get torch dtype from config"""
    dtype_map = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    return dtype_map.get(Config.DTYPE, torch.bfloat16)


async def initialize_model():
    """Initialize the base TTS model"""
    global _base_model, _model_loading

    if _base_model is not None or _model_loading:
        return

    _model_loading = True
    print(f"Loading Qwen3-TTS model: {Config.MODEL_NAME}")
    print(f"  Device: {Config.DEVICE}")
    print(f"  Dtype: {Config.DTYPE}")
    print(f"  Flash Attention: {Config.USE_FLASH_ATTENTION}")

    try:
        from qwen_tts import Qwen3TTSModel

        kwargs = {
            "device_map": Config.DEVICE,
            "dtype": get_dtype(),
        }

        if Config.USE_FLASH_ATTENTION:
            kwargs["attn_implementation"] = "flash_attention_2"

        _base_model = Qwen3TTSModel.from_pretrained(Config.MODEL_NAME, **kwargs)
        print(f"Base model loaded successfully")

    except Exception as e:
        print(f"Failed to load base model: {e}")
        raise
    finally:
        _model_loading = False


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
        }

        if Config.USE_FLASH_ATTENTION:
            kwargs["attn_implementation"] = "flash_attention_2"

        _voice_design_model = Qwen3TTSModel.from_pretrained(Config.VOICE_DESIGN_MODEL, **kwargs)
        print(f"Voice design model loaded successfully")

    except Exception as e:
        print(f"Failed to load voice design model: {e}")
        raise
    finally:
        _voice_design_loading = False


def get_base_model():
    """Get the base TTS model"""
    return _base_model


def get_voice_design_model():
    """Get the voice design model"""
    return _voice_design_model


def is_model_loaded() -> bool:
    """Check if base model is loaded"""
    return _base_model is not None


def is_voice_design_loaded() -> bool:
    """Check if voice design model is loaded"""
    return _voice_design_model is not None


def generate_custom_voice(
    text: str,
    language: str = "English",
    speaker: str = "Vivian",
    instruct: Optional[str] = None
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
    if _base_model is None:
        raise RuntimeError("Model not loaded")

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

    with torch.no_grad():
        wavs, sr = _base_model.generate_custom_voice(**kwargs)

    # Return first audio (batch size 1)
    return wavs[0], sr


def generate_voice_clone(
    text: str,
    ref_audio: Union[str, np.ndarray, Tuple[np.ndarray, int]],
    language: str = "English",
    ref_text: Optional[str] = None,
    x_vector_only: bool = False
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
    if _base_model is None:
        raise RuntimeError("Model not loaded")

    kwargs = {
        "text": text,
        "language": language,
        "ref_audio": ref_audio,
    }

    if ref_text:
        kwargs["ref_text"] = ref_text

    if x_vector_only:
        kwargs["x_vector_only_mode"] = True

    with torch.no_grad():
        wavs, sr = _base_model.generate_voice_clone(**kwargs)

    return wavs[0], sr


def generate_voice_design(
    text: str,
    language: str = "English",
    voice_description: str = ""
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

    with torch.no_grad():
        wavs, sr = _voice_design_model.generate_voice_design(
            text=text,
            language=language,
            instruct=voice_description
        )

    return wavs[0], sr
