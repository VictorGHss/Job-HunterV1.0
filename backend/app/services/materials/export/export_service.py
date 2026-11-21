"""Serviço orquestrador de exportação em PDF e DOCX a partir de versões históricas."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.material import ApplicationMaterial, ApplicationMaterialVersion
from app.models.user import User
from app.schemas.material import TargetLanguage
from app.services.materials.export.document_templates import (
    DocumentFormat,
    DocumentTemplateId,
    get_template_spec,
)
from app.services.materials.export.document_validation import (
    DOCX_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    DocumentExportError,
    DocumentExportRenderError,
    DocumentExportValidationError,
    build_content_disposition,
    build_safe_filename,
    validate_export_parameters,
    validate_generated_binary,
    validate_structured_content_for_export,
)
from app.services.materials.export.docx_exporter import export_material_to_docx
from app.services.materials.export.pdf_exporter import export_material_to_pdf
from app.services.materials.material_service import (
    _count_blocking_pending_fields,
    _get_user_material,
    _parse_structured_for_type,
)

logger = logging.getLogger("job_hunter.materials.export")


@dataclass(frozen=True)
class ExportedDocumentArtifact:
    material_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    material_type: str
    export_format: DocumentFormat
    template_id: DocumentTemplateId
    is_approved: bool
    is_draft: bool
    media_type: str
    filename: str
    utf8_filename: str
    content_disposition: str
    content: bytes


def _locate_version_or_raise(
    material: ApplicationMaterial,
    version_id: uuid.UUID,
) -> ApplicationMaterialVersion:
    for version in material.versions:
        if version.id == version_id:
            return version
    from app.services.materials.material_service import MaterialNotFoundError

    raise MaterialNotFoundError("Versão de material não encontrada.")


def export_material_document(
    db: Session,
    user: User,
    *,
    material_id: uuid.UUID,
    version_id: uuid.UUID,
    export_format: str,
    template_id: str = "classic_ats",
    allow_draft: bool = False,
) -> ExportedDocumentArtifact:
    """Valida posse, política de aprovação/pendência e renderiza PDF/DOCX em memória."""
    started = time.perf_counter()
    material = _get_user_material(db, user, material_id)
    version = _locate_version_or_raise(material, version_id)

    if getattr(version, "is_rejected", False):
        raise DocumentExportValidationError(
            "Versão rejeitada não pode ser exportada como documento final ou rascunho."
        )

    mat_type, fmt, tpl_id = validate_export_parameters(
        material.material_type, export_format, template_id
    )
    spec = get_template_spec(tpl_id)

    try:
        structured = _parse_structured_for_type(mat_type, version.structured_content)
    except Exception as exc:
        raise DocumentExportValidationError(
            "Conteúdo estruturado da versão solicitada é inválido para exportação."
        ) from exc

    blocking_count = _count_blocking_pending_fields(structured)
    if blocking_count > 0:
        raise DocumentExportValidationError(
            f"Há {blocking_count} informação(ões) obrigatória(s) pendente(s) que impedem a exportação."
        )

    if not version.is_approved and not allow_draft:
        raise DocumentExportValidationError(
            "Versão ainda não aprovada. Aprove a versão antes da exportação final ou solicite modo rascunho."
        )

    is_draft = bool(allow_draft and not version.is_approved)
    validate_structured_content_for_export(structured)

    lang: TargetLanguage = "en" if getattr(structured, "language", material.target_language) == "en" else "pt-BR"
    company_name = material.opportunity.company_name if material.opportunity else None
    ascii_name, utf8_name = build_safe_filename(
        material_type=mat_type,
        language=lang,
        version_number=version.version_number,
        export_format=fmt,
        company_name=company_name,
        title=material.title,
        is_draft=is_draft,
    )
    content_disposition = build_content_disposition(ascii_name, utf8_name)

    try:
        if fmt == "pdf":
            raw_bytes = export_material_to_pdf(
                structured,
                spec=spec,
                language=lang,
                document_title=material.title,
                is_draft=is_draft,
                version_created_at=version.created_at,
            )
            media_type = PDF_MEDIA_TYPE
        else:
            raw_bytes = export_material_to_docx(
                structured,
                spec=spec,
                language=lang,
                document_title=material.title,
                is_draft=is_draft,
                version_created_at=version.created_at,
                version_updated_at=version.updated_at,
            )
            media_type = DOCX_MEDIA_TYPE

        validated_bytes = validate_generated_binary(raw_bytes, fmt)
    except DocumentExportError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "Falha controlada na exportação documental material_id=%s version=%s format=%s template=%s draft=%s duration_ms=%d error_class=%s",
            str(material.id),
            version.version_number,
            fmt,
            tpl_id,
            is_draft,
            elapsed_ms,
            exc.__class__.__name__,
        )
        raise
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error(
            "Erro inesperado na exportação documental material_id=%s version=%s format=%s template=%s draft=%s duration_ms=%d error_class=%s",
            str(material.id),
            version.version_number,
            fmt,
            tpl_id,
            is_draft,
            elapsed_ms,
            exc.__class__.__name__,
        )
        raise DocumentExportRenderError(
            "Não foi possível gerar o arquivo solicitado."
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "Exportação documental concluída material_id=%s version=%s format=%s template=%s draft=%s bytes=%d duration_ms=%d",
        str(material.id),
        version.version_number,
        fmt,
        tpl_id,
        is_draft,
        len(validated_bytes),
        elapsed_ms,
    )

    return ExportedDocumentArtifact(
        material_id=material.id,
        version_id=version.id,
        version_number=version.version_number,
        material_type=mat_type,
        export_format=fmt,
        template_id=tpl_id,
        is_approved=version.is_approved,
        is_draft=is_draft,
        media_type=media_type,
        filename=ascii_name,
        utf8_filename=utf8_name,
        content_disposition=content_disposition,
        content=validated_bytes,
    )
