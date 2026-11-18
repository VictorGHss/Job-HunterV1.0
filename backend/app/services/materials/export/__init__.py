"""Módulo de exportação profissional em PDF e DOCX para materiais de candidatura."""

from app.services.materials.export.document_templates import (
    DocumentFormat,
    DocumentTemplateId,
    TemplateVisualSpec,
    get_document_labels,
    get_template_spec,
)
from app.services.materials.export.document_validation import (
    MAX_EXPORT_FILE_BYTES,
    MAX_EXPORT_INPUT_CHARS,
    DocumentExportError,
    DocumentExportLimitError,
    DocumentExportRenderError,
    DocumentExportValidationError,
    build_content_disposition,
    build_safe_filename,
)
from app.services.materials.export.export_service import (
    ExportedDocumentArtifact,
    export_material_document,
)

__all__ = [
    "DocumentExportError",
    "DocumentExportLimitError",
    "DocumentExportRenderError",
    "DocumentExportValidationError",
    "DocumentFormat",
    "DocumentTemplateId",
    "ExportedDocumentArtifact",
    "MAX_EXPORT_FILE_BYTES",
    "MAX_EXPORT_INPUT_CHARS",
    "TemplateVisualSpec",
    "build_content_disposition",
    "build_safe_filename",
    "export_material_document",
    "get_document_labels",
    "get_template_spec",
]
