"""
Main FastAPI application for the eddie-tts API
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Config
from app.tts_model import initialize_model, infer_pool
from app.api.router import api_router

# Quiet transformers' per-generation chatter (e.g. the repeated
# "Setting `pad_token_id` to `eos_token_id`" line). Uvicorn request logs are unaffected.
import transformers
transformers.logging.set_verbosity_error()


ascii_art = r"""
          _     _ _            _   _
  ___  __| | __| (_) ___      | |_| |_ ___
 / _ \/ _` |/ _` | |/ _ \_____| __| __/ __|
|  __/ (_| | (_| | |  __/_____| |_| |_\__ \
 \___|\__,_|\__,_|_|\___|      \__|\__|___/

"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    print(ascii_art)
    print("eddie-tts API Server")
    print(f"  Model: {Config.MODEL_NAME}")
    print(f"  Device: {Config.DEVICE}")
    print(f"  Dtype: {Config.DTYPE}")
    print()

    # Route all `run_in_executor(None, ...)` generation calls onto the single
    # dedicated inference thread, so they reuse the warmed-up compiled kernels.
    asyncio.get_running_loop().set_default_executor(infer_pool)

    # Start model loading in background
    model_task = asyncio.create_task(initialize_model())

    yield

    # Shutdown
    if not model_task.done():
        model_task.cancel()
        try:
            await model_task
        except asyncio.CancelledError:
            pass


# Create FastAPI app
app = FastAPI(
    title="eddie-tts API",
    description="REST API for Qwen3-TTS with OpenAI-compatible endpoints",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
cors_origins = Config.CORS_ORIGINS
if cors_origins == "*":
    allowed_origins = ["*"]
else:
    allowed_origins = [origin.strip() for origin in cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail if isinstance(exc.detail, dict) else {"error": {"message": str(exc.detail)}}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": f"Internal server error: {str(exc)}",
                "type": "internal_error"
            }
        }
    )
