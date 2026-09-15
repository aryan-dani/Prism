"""Prism FastAPI application entrypoint.

Run: uv run uvicorn prism.api.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prism.api.routes import router
from prism.core.config import EMBED_MODEL, GEN_MODEL, TITLE_MODEL


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm Ollama models so the first user turn does not pay a cold-load spike.
    try:
        from prism.core.ollama_client import warm_models

        warm_models([EMBED_MODEL, TITLE_MODEL, GEN_MODEL])
    except Exception:
        pass
    yield


app = FastAPI(title="Prism API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"name": "Prism API", "docs": "/docs"}
