from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import applications, auth, health, materials, opportunities, profile
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.services.opportunities.sync_service import ensure_default_sources

logger = logging.getLogger("job_hunter")


@asynccontextmanager
async def _app_lifespan(application: FastAPI):
    """
    Inicializa fontes padrão no startup da aplicação de forma idempotente e segura
    para múltiplos workers, evitando qualquer escrita colateral em rotas GET.
    Em ambiente de testes (`ENVIRONMENT=testing` ou `PYTEST_CURRENT_TEST`), nunca
    acessa o banco padrão da máquina se não houver override explícito de `get_db`.
    """
    override_get_db = application.dependency_overrides.get(get_db)
    is_test_runtime = settings.environment == "testing" or bool(
        os.environ.get("PYTEST_CURRENT_TEST")
    )
    if override_get_db is not None:
        gen = override_get_db()
        try:
            db = next(gen)
            ensure_default_sources(db)
        except SQLAlchemyError:
            logger.warning("Não foi possível inicializar fontes padrão no lifespan (override).")
        finally:
            try:
                next(gen)
            except StopIteration:
                pass
    elif not is_test_runtime:
        with SessionLocal() as db:
            try:
                ensure_default_sources(db)
            except SQLAlchemyError:
                db.rollback()
                logger.warning(
                    "Falha ao inicializar fontes padrão no startup; execute 'python -m app.cli init-sources'."
                )
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=(
            "API da plataforma Job Hunter (Fase 01: Fundação arquitetural e perfil profissional). "
            "Arquitetura multiusuário isolada por user_id, sessões seguras com Argon2id e "
            "fonte única de verdade para experiências, formação, habilidades, idiomas e projetos."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_app_lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Accept"],
        expose_headers=["Content-Disposition", "X-AI-Error-Code", "Retry-After"],
    )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error("Erro interno não tratado na rota %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Erro interno do servidor."},
        )

    api_prefix = "/api/v1"
    application.include_router(health.router, prefix=api_prefix)
    application.include_router(auth.router, prefix=api_prefix)
    application.include_router(profile.router, prefix=api_prefix)
    application.include_router(opportunities.router, prefix=api_prefix)
    application.include_router(applications.router, prefix=api_prefix)
    application.include_router(materials.router, prefix=api_prefix)

    return application


app = create_app()
