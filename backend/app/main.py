import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import applications, auth, health, materials, opportunities, profile
from app.core.config import settings

logger = logging.getLogger("job_hunter")


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
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Accept"],
        expose_headers=["Content-Disposition"],
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
