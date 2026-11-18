"""Validação, normalização Unicode, controle de fontes, limites e nomes seguros para exportação."""
from __future__ import annotations

import hashlib
import io
import re
import struct
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import docx

from app.models.material import MaterialType
from app.schemas.material import (
    AnyMaterialStructuredContent,
    ApplicationAnswersStructuredContent,
    CoverLetterStructuredContent,
    FreelanceProposalStructuredContent,
    RecruiterMessageStructuredContent,
    ResumeSkillItem,
    ResumeStructuredContent,
    TargetLanguage,
)
from app.services.materials.export.document_templates import (
    SUPPORTED_FORMATS,
    SUPPORTED_TEMPLATES,
    DocumentFormat,
    DocumentTemplateId,
)
from app.services.opportunities.sanitization import validate_safe_external_url

MAX_EXPORT_INPUT_CHARS = 120_000
MAX_EXPORT_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

FONTS_DIR = Path(__file__).resolve().parent / "fonts"

FONT_SHA256_MANIFEST: dict[str, str] = {
    "LiberationSans-Regular.ttf": "bade59d822652f76e6941aa87b40a87c13d1cc70db98ededb5011127efafd1d3",
    "LiberationSans-Bold.ttf": "1b5f2da6f4cadce4c05b9ecebe3a6fcd374eb95ae443605e799f4c3287978939",
    "LiberationSans-Italic.ttf": "93ff5260834141b6f9d8f2b846d427f3a5dc492dbdce8ebdad406e38a38f34bb",
    "LiberationSans-BoldItalic.ttf": "352e9dc2be89f210dbd3c0fd5dfaf97135de70e0beb5f22378601861462493a7",
}

_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)

_FILENAME_SLUG_RE = re.compile(r"[^a-z0-9]+")
_COMBINING_MARKS_RE = re.compile(r"[\u0300-\u036f]")


class DocumentExportError(Exception):
    """Erro base de exportação documental."""


class DocumentExportValidationError(DocumentExportError):
    """Violação de contrato, conteúdo vazio ou política de aprovação/pendência (HTTP 422)."""


class DocumentExportLimitError(DocumentExportValidationError):
    """Conteúdo ou artefato final excede os limites seguros configurados (HTTP 422)."""


class DocumentExportRenderError(DocumentExportError):
    """Falha interna ao montar ou validar o arquivo binário (HTTP 500)."""


@dataclass(frozen=True)
class ControlledFontPaths:
    regular: Path
    bold: Path
    italic: Path
    bold_italic: Path
    license_file: Path


@lru_cache(maxsize=1)
def resolve_controlled_fonts() -> ControlledFontPaths:
    """Resolve e verifica integridade SHA-256 das fontes Liberation Sans do projeto."""
    for filename, expected_sha in FONT_SHA256_MANIFEST.items():
        path = FONTS_DIR / filename
        if not path.is_file():
            raise DocumentExportRenderError(
                f"Recurso de fonte obrigatório ausente: {filename}."
            )
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise DocumentExportRenderError(
                f"Falha na verificação de integridade SHA-256 da fonte {filename}."
            )
    license_path = FONTS_DIR / "LICENSE.txt"
    if not license_path.is_file():
        raise DocumentExportRenderError("Arquivo de licença SIL OFL 1.1 das fontes ausente.")
    return ControlledFontPaths(
        regular=FONTS_DIR / "LiberationSans-Regular.ttf",
        bold=FONTS_DIR / "LiberationSans-Bold.ttf",
        italic=FONTS_DIR / "LiberationSans-Italic.ttf",
        bold_italic=FONTS_DIR / "LiberationSans-BoldItalic.ttf",
        license_file=license_path,
    )


def _read_ttf_cmap_codepoints(ttf_path: Path) -> frozenset[int]:
    """Lê os codepoints Unicode reais cobertos pela tabela cmap do arquivo TrueType."""
    data = ttf_path.read_bytes()
    if len(data) < 12:
        raise DocumentExportRenderError(f"Arquivo TrueType inválido: {ttf_path.name}.")
    num_tables = struct.unpack(">H", data[4:6])[0]
    cmap_offset = None
    for idx in range(num_tables):
        entry_off = 12 + idx * 16
        if entry_off + 16 > len(data):
            break
        tag = data[entry_off : entry_off + 4]
        if tag == b"cmap":
            cmap_offset = struct.unpack(">I", data[entry_off + 8 : entry_off + 12])[0]
            break
    if cmap_offset is None or cmap_offset + 4 > len(data):
        raise DocumentExportRenderError(f"Tabela cmap ausente na fonte {ttf_path.name}.")

    num_subtables = struct.unpack(">H", data[cmap_offset + 2 : cmap_offset + 4])[0]
    supported: set[int] = set()
    for i in range(num_subtables):
        rec_off = cmap_offset + 4 + i * 8
        if rec_off + 8 > len(data):
            break
        platform_id, encoding_id, rel_offset = struct.unpack(">HHI", data[rec_off : rec_off + 8])
        if platform_id not in (0, 3):
            continue
        sub_off = cmap_offset + rel_offset
        if sub_off + 4 > len(data):
            continue
        fmt = struct.unpack(">H", data[sub_off : sub_off + 2])[0]
        if fmt == 4 and (platform_id, encoding_id) in ((3, 1), (0, 3), (0, 4), (3, 10)):
            if sub_off + 14 > len(data):
                continue
            seg_count_x2 = struct.unpack(">H", data[sub_off + 6 : sub_off + 8])[0]
            seg_count = seg_count_x2 // 2
            end_codes_off = sub_off + 14
            start_codes_off = end_codes_off + 2 * seg_count + 2
            id_delta_off = start_codes_off + 2 * seg_count
            id_range_off = id_delta_off + 2 * seg_count
            if id_range_off + 2 * seg_count > len(data):
                continue
            for seg in range(seg_count):
                end_code = struct.unpack(">H", data[end_codes_off + 2 * seg : end_codes_off + 2 * seg + 2])[0]
                start_code = struct.unpack(">H", data[start_codes_off + 2 * seg : start_codes_off + 2 * seg + 2])[0]
                id_delta = struct.unpack(">h", data[id_delta_off + 2 * seg : id_delta_off + 2 * seg + 2])[0]
                range_offset = struct.unpack(">H", data[id_range_off + 2 * seg : id_range_off + 2 * seg + 2])[0]
                if start_code == 0xFFFF and end_code == 0xFFFF:
                    continue
                for cp in range(start_code, end_code + 1):
                    if range_offset == 0:
                        glyph_idx = (cp + id_delta) & 0xFFFF
                    else:
                        addr = id_range_off + 2 * seg + range_offset + 2 * (cp - start_code)
                        if addr + 2 > len(data):
                            glyph_idx = 0
                        else:
                            glyph_val = struct.unpack(">H", data[addr : addr + 2])[0]
                            glyph_idx = ((glyph_val + id_delta) & 0xFFFF) if glyph_val != 0 else 0
                    if glyph_idx != 0:
                        supported.add(cp)
        elif fmt == 12:
            if sub_off + 16 > len(data):
                continue
            num_groups = struct.unpack(">I", data[sub_off + 12 : sub_off + 16])[0]
            groups_off = sub_off + 16
            for g in range(num_groups):
                g_off = groups_off + g * 12
                if g_off + 12 > len(data):
                    break
                start_cp, end_cp, _ = struct.unpack(">III", data[g_off : g_off + 12])
                if end_cp - start_cp <= 20000:
                    supported.update(range(start_cp, end_cp + 1))

    # Whitespace/control de quebra de linha são tratados pelo layout engine
    supported.update({9, 10, 13, 32})
    return frozenset(supported)


@lru_cache(maxsize=1)
def get_supported_pdf_codepoints() -> frozenset[int]:
    fonts = resolve_controlled_fonts()
    return _read_ttf_cmap_codepoints(fonts.regular)


def strip_invalid_xml_chars(text: str) -> str:
    """Normaliza NFC e remove caracteres de controle proibidos em XML 1.0 (mantém tabs e quebras)."""
    nfc = unicodedata.normalize("NFC", text)
    out: list[str] = []
    for ch in nfc:
        cp = ord(ch)
        if cp in (0x9, 0xA, 0xD) or (0x20 <= cp <= 0xD7FF) or (0xE000 <= cp <= 0xFFFD) or (0x10000 <= cp <= 0x10FFFF):
            out.append(ch)
    return "".join(out)


def normalize_document_text(raw: str | None) -> str:
    if not raw:
        return ""
    return strip_invalid_xml_chars(raw).strip()


def format_docx_text(raw: str | None) -> str:
    return strip_invalid_xml_chars(raw or "")


def format_pdf_plain_with_explicit_unsupported(
    raw: str | None,
    *,
    supported_codepoints: frozenset[int] | None = None,
) -> tuple[str, list[str]]:
    """Prepara texto NFC limpo para PDF tratando explicitamente glifos fora da fonte.

    Nunca remove silenciosamente conteúdo relevante; substitui somente o caractere
    sem glifo na fonte controlada por ``[U+XXXX]`` e retorna a lista de avisos.
    """
    cleaned = strip_invalid_xml_chars(raw or "")
    if not cleaned:
        return "", []
    cmap = supported_codepoints if supported_codepoints is not None else get_supported_pdf_codepoints()
    chars: list[str] = []
    unsupported_tokens: list[str] = []
    for ch in cleaned:
        cp = ord(ch)
        if cp in cmap or ch in ("\n", "\r", "\t"):
            chars.append(ch)
        elif ch == "\u00A0":
            chars.append(" ")
        else:
            marker = f"[U+{cp:04X}]"
            chars.append(marker)
            if marker not in unsupported_tokens:
                unsupported_tokens.append(marker)
    return "".join(chars), unsupported_tokens


def escape_pdf_paragraph_text(
    raw: str | None,
    *,
    supported_codepoints: frozenset[int] | None = None,
) -> tuple[str, list[str]]:
    """Escapa XML antes de qualquer markup controlado pelo exportador ReportLab."""
    prepared, unsupported = format_pdf_plain_with_explicit_unsupported(
        raw,
        supported_codepoints=supported_codepoints,
    )
    escaped = xml_escape(prepared, entities={'"': "&quot;", "'": "&apos;"})
    return escaped, unsupported


def safe_hyperlink_url(raw_url: str | None) -> str | None:
    """Valida URL externa para links clicáveis com proteção SSRF e esquemas proibidos."""
    if not raw_url or not isinstance(raw_url, str):
        return None
    cleaned = normalize_document_text(raw_url)
    if not cleaned:
        return None
    try:
        return validate_safe_external_url(cleaned, allow_localhost=False)
    except ValueError:
        return None


def validate_export_parameters(
    material_type: str,
    export_format: str,
    template_id: str,
) -> tuple[str, DocumentFormat, DocumentTemplateId]:
    if material_type not in {mt.value for mt in MaterialType}:
        raise DocumentExportValidationError(f"Tipo de material não suportado: '{material_type}'.")
    if export_format not in SUPPORTED_FORMATS:
        raise DocumentExportValidationError(
            f"Formato documental inválido: '{export_format}'. Utilize 'pdf' ou 'docx'."
        )
    if template_id not in SUPPORTED_TEMPLATES:
        raise DocumentExportValidationError(
            f"Template visual inválido: '{template_id}'. Utilize 'classic_ats' ou 'modern_minimal'."
        )
    return material_type, export_format, template_id  # type: ignore[return-value]


def _collect_text_strings(value: Any, acc: list[str]) -> None:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            acc.append(cleaned)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_text_strings(v, acc)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_text_strings(item, acc)


def count_substantive_chars(structured: AnyMaterialStructuredContent) -> int:
    """Calcula total de caracteres substantivos do conteúdo estruturado (ignora metadata interna)."""
    texts: list[str] = []
    if isinstance(structured, ResumeStructuredContent):
        _collect_text_strings(
            structured.model_dump(
                mode="json",
                exclude={
                    "schema_version",
                    "language",
                    "has_unverified_manual_edits",
                },
            ),
            texts,
        )
        # Ignora contagem apenas de source_fact_keys / provenance repetidos
        substantive = _extract_resume_substantive_strings(structured)
        return sum(len(s) for s in substantive)
    if isinstance(structured, CoverLetterStructuredContent):
        parts = [
            structured.header.full_name or "",
            structured.header.professional_title or "",
            structured.recipient_line.text,
            structured.greeting.text,
            structured.opening.text,
            *(f"{b.title} {b.summary_text}" for b in structured.relevance_highlights),
            structured.opportunity_alignment.text if structured.opportunity_alignment else "",
            structured.closing.text,
            *(f"{n.title} {n.content}" for n in structured.manual_notes),
        ]
        return sum(len(p.strip()) for p in parts if p and p.strip())
    if isinstance(structured, RecruiterMessageStructuredContent):
        parts = [
            structured.subject.text if structured.subject else "",
            structured.greeting.text,
            structured.body.text,
            structured.sign_off.text,
            *(f"{n.title} {n.content}" for n in structured.manual_notes),
        ]
        return sum(len(p.strip()) for p in parts if p and p.strip())
    if isinstance(structured, FreelanceProposalStructuredContent):
        parts = [
            structured.header.full_name or "",
            structured.header.professional_title or "",
            structured.introduction.text,
            structured.project_understanding.text,
            *(f"{b.title} {b.summary_text}" for b in structured.relevant_evidence),
            structured.suggested_approach.text,
            structured.alignment_points.text,
            *(f"{f.label} {f.user_value or ''}" for f in structured.pending_fields if f.status == "provided"),
            structured.closing.text,
            *(f"{n.title} {n.content}" for n in structured.manual_notes),
        ]
        return sum(len(p.strip()) for p in parts if p and p.strip())
    if isinstance(structured, ApplicationAnswersStructuredContent):
        parts = [
            *(f"{it.question} {it.answer_text or ''}" for it in structured.items),
            *(f"{n.title} {n.content}" for n in structured.manual_notes),
        ]
        return sum(len(p.strip()) for p in parts if p and p.strip())
    return 0


def _extract_resume_substantive_strings(structured: ResumeStructuredContent) -> list[str]:
    strings: list[str] = []
    h = structured.header
    for val in (h.full_name, h.professional_title, h.location_text, h.email, h.phone):
        if val and val.strip():
            strings.append(val.strip())
    for lk in h.links:
        if lk.label.strip():
            strings.append(lk.label.strip())
    if structured.summary and structured.summary.text.strip():
        strings.append(structured.summary.text.strip())
    if structured.target_alignment:
        ta = structured.target_alignment
        for val in (ta.target_role, ta.company_name, ta.alignment_note, *ta.highlighted_requirements):
            if val and val.strip():
                strings.append(val.strip())
    for exp in structured.experiences:
        for val in (exp.role, exp.company, exp.period_label, exp.description, *exp.technologies):
            if val and val.strip():
                strings.append(val.strip())
    for proj in structured.projects:
        for val in (proj.name, proj.role, proj.description, proj.verified_results, *proj.technologies):
            if val and val.strip():
                strings.append(val.strip())
    for edu in structured.education:
        for val in (edu.course, edu.institution, edu.status_label, edu.current_semester, edu.period_label, edu.field_of_study):
            if val and val.strip():
                strings.append(val.strip())
    for sk in structured.skills:
        for val in (sk.name, sk.category, sk.proficiency_label, sk.notes):
            if val and val.strip():
                strings.append(val.strip())
    for lg in structured.languages:
        for val in (lg.language_name, lg.proficiency_label, lg.cefr_level):
            if val and val.strip():
                strings.append(val.strip())
    for note in structured.manual_notes:
        if note.title.strip():
            strings.append(note.title.strip())
        if note.content.strip():
            strings.append(note.content.strip())
    return strings


def has_substantive_body_content(structured: AnyMaterialStructuredContent) -> bool:
    if isinstance(structured, ResumeStructuredContent):
        has_any_section = any(
            [
                bool(structured.summary and structured.summary.text.strip()),
                bool(structured.target_alignment),
                bool(structured.experiences),
                bool(structured.projects),
                bool(structured.education),
                bool(structured.skills),
                bool(structured.languages),
                bool(structured.manual_notes),
            ]
        )
        has_header = bool(structured.header.full_name and structured.header.full_name.strip())
        return has_any_section or has_header
    return count_substantive_chars(structured) > 0


def validate_structured_content_for_export(structured: AnyMaterialStructuredContent) -> int:
    if not has_substantive_body_content(structured):
        raise DocumentExportValidationError(
            "Material não possui conteúdo substantivo suficiente para exportação."
        )
    total_chars = count_substantive_chars(structured)
    if total_chars == 0:
        raise DocumentExportValidationError(
            "Material não possui conteúdo textual válido para exportação."
        )
    if total_chars > MAX_EXPORT_INPUT_CHARS:
        raise DocumentExportLimitError(
            f"O conteúdo do material excede o limite máximo permitido de {MAX_EXPORT_INPUT_CHARS} caracteres."
        )
    return total_chars


def validate_generated_binary(
    content: bytes,
    export_format: DocumentFormat,
) -> bytes:
    if not content:
        raise DocumentExportRenderError("Exportador gerou arquivo vazio.")
    if len(content) > MAX_EXPORT_FILE_BYTES:
        raise DocumentExportLimitError(
            f"Arquivo gerado excede o limite máximo permitido de {MAX_EXPORT_FILE_BYTES // (1024 * 1024)} MiB."
        )
    if export_format == "pdf":
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
            raise DocumentExportRenderError("Assinatura binária PDF inválida.")
    elif export_format == "docx":
        if not content.startswith(b"PK\x03\x04"):
            raise DocumentExportRenderError("Assinatura binária DOCX (ZIP) inválida.")
        try:
            doc = docx.Document(io.BytesIO(content))
            _ = len(doc.paragraphs) + len(doc.tables)
        except Exception as exc:
            raise DocumentExportRenderError("Falha ao validar integridade estrutural do DOCX gerado.") from exc
    return content


def _to_ascii_slug(raw: str | None, *, max_len: int = 40) -> str:
    if not raw:
        return ""
    cleaned = strip_invalid_xml_chars(raw)
    # Remove sequências suspeitas de traversal ou quebras antes da normalização
    cleaned = cleaned.replace("..", " ").replace("/", " ").replace("\\", " ")
    decomposed = unicodedata.normalize("NFKD", cleaned)
    ascii_only = _COMBINING_MARKS_RE.sub("", decomposed).encode("ascii", "ignore").decode("ascii")
    slug = _FILENAME_SLUG_RE.sub("-", ascii_only.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    if slug.upper() in _WINDOWS_RESERVED_NAMES:
        slug = f"doc-{slug}"
    return slug


_FILENAME_PREFIXES: dict[str, dict[str, str]] = {
    MaterialType.RESUME.value: {"pt-BR": "curriculo", "en": "resume"},
    MaterialType.COVER_LETTER.value: {"pt-BR": "carta-apresentacao", "en": "cover-letter"},
    MaterialType.RECRUITER_MESSAGE.value: {"pt-BR": "mensagem-recrutador", "en": "recruiter-message"},
    MaterialType.FREELANCE_PROPOSAL.value: {"pt-BR": "proposta-freelance", "en": "freelance-proposal"},
    MaterialType.APPLICATION_ANSWERS.value: {"pt-BR": "respostas-candidatura", "en": "application-answers"},
}


def build_safe_filename(
    *,
    material_type: str,
    language: TargetLanguage,
    version_number: int,
    export_format: DocumentFormat,
    company_name: str | None = None,
    title: str | None = None,
    is_draft: bool = False,
) -> tuple[str, str]:
    """Retorna (ascii_filename, utf8_filename) estritamente sanitizados via allowlist."""
    lang = "en" if language == "en" else "pt-BR"
    prefix = _FILENAME_PREFIXES.get(material_type, {}).get(lang, "documento")
    context_slug = _to_ascii_slug(company_name, max_len=36)
    if not context_slug and title:
        # Evita repetir o próprio prefixo quando vem do título padrão
        title_slug = _to_ascii_slug(title, max_len=36)
        if title_slug and title_slug != prefix:
            context_slug = title_slug

    parts = [prefix]
    if context_slug:
        parts.append(context_slug)
    parts.append(f"v{max(1, int(version_number))}")
    if is_draft:
        parts.append("draft" if lang == "en" else "rascunho")

    stem = "-".join(p for p in parts if p)
    if len(stem) > 90:
        stem = stem[:90].rstrip("-")
    if not stem or stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"documento-v{max(1, int(version_number))}"

    ascii_name = f"{stem}.{export_format}"
    # UTF-8 mantém os caracteres seguros NFC caso título/empresa tenha acentuação leve no futuro,
    # mas sempre dentro de allowlist rigorosa sem controles/separadores/traversal.
    return ascii_name, ascii_name


def build_content_disposition(ascii_filename: str, utf8_filename: str) -> str:
    safe_ascii = re.sub(r"[^A-Za-z0-9._-]", "-", ascii_filename).strip(".-") or "documento.pdf"
    encoded_utf8 = quote(utf8_filename, safe="A-Za-z0-9._-")
    return f'attachment; filename="{safe_ascii}"; filename*=UTF-8\'\'{encoded_utf8}'


def group_skills_by_category(skills: list[ResumeSkillItem]) -> dict[str, list[ResumeSkillItem]]:
    grouped: dict[str, list[ResumeSkillItem]] = {}
    for skill in skills:
        grouped.setdefault(skill.category, []).append(skill)
    return grouped
