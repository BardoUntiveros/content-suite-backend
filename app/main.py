from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.brand_manuals import router as brand_manuals_router
from app.api.creative_assets import router as creative_assets_router
from app.api.governance import router as governance_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.seed import seed_default_users
from app.db.session import SessionLocal
from app.services.gen_ai_service import GenAIService
from app.services.embeddings_service import EmbeddingService
from app.services.observability_service import ObservabilityService
from app.services.rag_service import RagService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_db()
    if settings.seed_default_users:
        with SessionLocal() as db:
            seed_default_users(db)

    ai_service = GenAIService(settings)
    embedding_service = EmbeddingService(settings)
    observability = ObservabilityService(settings)

    app.state.ai_service = ai_service
    app.state.rag_service = RagService(embedding_service)
    app.state.observability = observability

    yield

    observability.flush()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(brand_manuals_router, prefix="/api/v1")
    app.include_router(creative_assets_router, prefix="/api/v1")
    app.include_router(governance_router, prefix="/api/v1")

    return app


app = create_app()
