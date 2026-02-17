from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root and frontend (so VALYU_API_KEY in frontend/.env is available to backend)
_backend_root = Path(__file__).resolve().parents[1]
_project_root = _backend_root.parent
load_dotenv(_project_root / ".env")
load_dotenv(_project_root / "frontend" / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logging_config import setup_logging, logger
from .db import engine, Base
from .routes import health, countries, combined, events, metrics, spikes, brief, history, map as map_router, valyu, analytics


def create_app() -> FastAPI:
    """
    Application factory for the FastAPI app.
    """
    setup_logging()

    logger.info("initializing database schema")
    Base.metadata.create_all(bind=engine)

    app = FastAPI(
        title="Global Events Risk Intelligence Dashboard API",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(countries.router)
    app.include_router(combined.router)
    app.include_router(events.router)
    app.include_router(metrics.router)
    app.include_router(spikes.router)
    app.include_router(brief.router)
    app.include_router(history.router)
    app.include_router(map_router.router)
    app.include_router(valyu.router)
    app.include_router(analytics.router)

    return app


app = create_app()

