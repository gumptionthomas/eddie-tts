"""
Entry point for Qwen3-TTS API server
"""

import uvicorn
from app.config import Config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=False,
        workers=1  # Single worker for GPU model
    )
