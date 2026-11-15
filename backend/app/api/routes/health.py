from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    summary="Verificação de saúde da aplicação e banco de dados",
)
def health_check(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
        http_status = status.HTTP_200_OK
        overall_status = "healthy"
    except Exception:
        db_status = "disconnected"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "degraded"

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "database": db_status,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
