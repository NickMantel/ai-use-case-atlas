from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_framework, get_settings
from .db import SessionLocal, init_db
from .routes import api, exports, pages, rounds, usecases
from .seed import seed_if_empty

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().seed_demo_data:
        with SessionLocal() as db:
            seed_if_empty(db, get_framework())
    yield


def create_app() -> FastAPI:
    fw = get_framework()
    app = FastAPI(title=fw.raw["brand"]["product_name"], lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    for module in (pages, rounds, usecases, exports, api):
        app.include_router(module.router)
    return app


app = create_app()
