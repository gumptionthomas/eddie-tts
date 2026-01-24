# qwen3-tts-api

> **This repo provides:** A Dockerfile and FastAPI server that wraps [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) with OpenAI-compatible REST endpoints. The original Qwen3-TTS is a Python library - this repo containerizes it for easy deployment.

Part of the [cornball-ai](https://github.com/cornball-ai) ecosystem, designed to work with the [tts.api](https://github.com/cornball-ai/tts.api) R package for text-to-speech generation.

## Features

- **OpenAI-compatible API**: Drop-in replacement for OpenAI TTS endpoints
- **9 Built-in Voices**: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee
- **Voice Cloning**: Clone any voice from a 3-second audio sample
- **Voice Design**: Generate custom voices from natural language descriptions
- **10 Languages**: Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian
- **Blackwell GPU Support**: Optimized for RTX 50xx series

## Quick Start

### Docker (Recommended)

```bash
# For older GPUs (Ampere, Ada Lovelace)
docker build -t qwen3-tts-api .
docker run --rm --gpus all -p 4123:4123 \
  -v ~/.cache/huggingface:/cache \
  qwen3-tts-api

# For Blackwell GPUs (RTX 50xx)
docker build -f Dockerfile.blackwell -t qwen3-tts-api:blackwell .
docker run --rm --gpus all -p 4123:4123 \
  -v ~/.cache/huggingface:/cache \
  qwen3-tts-api:blackwell
```

### Local Installation

```bash
# Install PyTorch (adjust for your CUDA version)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install Qwen3-TTS and dependencies
pip install qwen-tts
pip install -r requirements.txt

# Optional: Flash Attention for reduced memory
pip install flash-attn --no-build-isolation

# Run server
python main.py
```

## API Endpoints

### Generate Speech (Built-in Voices)

```bash
curl -X POST http://localhost:4123/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello, world!",
    "voice": "Vivian",
    "language": "English"
  }' --output speech.wav
```

### Voice Cloning

```bash
curl -X POST http://localhost:4123/v1/audio/speech/upload \
  -F "input=Hello, this is my cloned voice!" \
  -F "voice_file=@reference.wav" \
  -F "language=English" \
  -F "ref_text=This is the transcript of my reference audio." \
  --output cloned.wav
```

### Voice Design (Generate from Description)

```bash
curl -X POST http://localhost:4123/v1/audio/speech/design \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello, I am a custom designed voice!",
    "language": "English",
    "voice_description": "A warm, friendly female voice with a slight British accent"
  }' --output designed.wav
```

### List Voices

```bash
curl http://localhost:4123/v1/voices
```

### Health Check

```bash
curl http://localhost:4123/health
```

## R Usage (tts.api)

```r
library(tts.api)

# Set the API base to your qwen3-tts-api server
set_tts_base("http://localhost:4123")

# Generate speech with built-in voice
speech("Hello world!", voice = "Vivian", file = "hello.wav")

# Voice cloning
speech_clone(
  input = "Hello with my cloned voice!",
  voice_file = "reference.wav",
  file = "cloned.wav"
)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 4123 | Server port |
| `HOST` | 0.0.0.0 | Server host |
| `DEVICE` | cuda:0 | PyTorch device |
| `DTYPE` | bfloat16 | Model dtype (bfloat16, float16, float32) |
| `USE_FLASH_ATTENTION` | true | Enable Flash Attention 2 |
| `MODEL_NAME` | Qwen/Qwen3-TTS-12Hz-1.7B-Base | Base model |
| `VOICE_DESIGN_MODEL` | Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign | Voice design model |
| `MODEL_CACHE_DIR` | /cache | HuggingFace cache directory |

## GPU Requirements

| Model | VRAM |
|-------|------|
| 0.6B CustomVoice | ~4GB |
| 1.7B CustomVoice | ~8GB |
| 1.7B + Voice Clone | ~12GB |
| 1.7B + Voice Design | ~16GB |

## Model Variants

The Qwen3-TTS family has different model variants for different use cases:

| Model | Use Case | Method |
|-------|----------|--------|
| **CustomVoice** (default) | 9 built-in speakers | `generate_custom_voice()` |
| **Base** | Voice cloning from audio | `generate_voice_clone()` |
| **VoiceDesign** | Create voice from description | `generate_voice_design()` |

This API uses CustomVoice by default and lazy-loads Base/VoiceDesign on first use.

## Tested

- RTX 5060 Ti (Blackwell, 16GB VRAM) with CUDA 12.8 / PyTorch 2.7+
- Generation time: ~5 seconds for a sentence

## License

Apache 2.0 (following Qwen3-TTS license)
