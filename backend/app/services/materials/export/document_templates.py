"""Tokens visuais, margens e rótulos compartilhados entre PDF e DOCX."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.material import TargetLanguage

DocumentTemplateId = Literal["classic_ats", "modern_minimal"]
DocumentFormat = Literal["pdf", "docx"]

SUPPORTED_TEMPLATES: tuple[DocumentTemplateId, ...] = ("classic_ats", "modern_minimal")
SUPPORTED_FORMATS: tuple[DocumentFormat, ...] = ("pdf", "docx")


@dataclass(frozen=True)
class TemplateVisualSpec:
    template_id: DocumentTemplateId
    label_pt: str
    label_en: str
    heading_hex: str
    text_hex: str
    muted_hex: str
    link_hex: str
    divider_hex: str
    table_header_bg_hex: str
    draft_banner_hex: str
    draft_bg_hex: str
    docx_font_family: str
    pdf_font_regular: str
    pdf_font_bold: str
    pdf_font_italic: str
    pdf_font_bold_italic: str
    margin_top_mm: float
    margin_bottom_mm: float
    margin_left_mm: float
    margin_right_mm: float
    name_pt: float
    title_pt: float
    section_heading_pt: float
    subheading_pt: float
    body_pt: float
    meta_pt: float
    footer_pt: float
    section_uppercase: bool
    paragraph_space_after_pt: float
    section_space_before_pt: float
    show_section_rule: bool


TEMPLATES: dict[DocumentTemplateId, TemplateVisualSpec] = {
    "classic_ats": TemplateVisualSpec(
        template_id="classic_ats",
        label_pt="Classic ATS (Padrão)",
        label_en="Classic ATS (Default)",
        heading_hex="#111827",
        text_hex="#1F2937",
        muted_hex="#4B5563",
        link_hex="#1D4ED8",
        divider_hex="#9CA3AF",
        table_header_bg_hex="#F3F4F6",
        draft_banner_hex="#92400E",
        draft_bg_hex="#FEF3C7",
        docx_font_family="Arial",
        pdf_font_regular="LiberationSans",
        pdf_font_bold="LiberationSans-Bold",
        pdf_font_italic="LiberationSans-Italic",
        pdf_font_bold_italic="LiberationSans-BoldItalic",
        margin_top_mm=20.0,
        margin_bottom_mm=20.0,
        margin_left_mm=20.0,
        margin_right_mm=20.0,
        name_pt=17.5,
        title_pt=11.0,
        section_heading_pt=10.5,
        subheading_pt=10.0,
        body_pt=9.5,
        meta_pt=8.5,
        footer_pt=8.0,
        section_uppercase=True,
        paragraph_space_after_pt=4.0,
        section_space_before_pt=10.0,
        show_section_rule=True,
    ),
    "modern_minimal": TemplateVisualSpec(
        template_id="modern_minimal",
        label_pt="Modern Minimalist",
        label_en="Modern Minimalist",
        heading_hex="#0F3D5E",
        text_hex="#1E293B",
        muted_hex="#64748B",
        link_hex="#0F3D5E",
        divider_hex="#CBD5E1",
        table_header_bg_hex="#F1F5F9",
        draft_banner_hex="#9A3412",
        draft_bg_hex="#FFEDD5",
        docx_font_family="Calibri",
        pdf_font_regular="LiberationSans",
        pdf_font_bold="LiberationSans-Bold",
        pdf_font_italic="LiberationSans-Italic",
        pdf_font_bold_italic="LiberationSans-BoldItalic",
        margin_top_mm=18.0,
        margin_bottom_mm=18.0,
        margin_left_mm=20.0,
        margin_right_mm=20.0,
        name_pt=18.5,
        title_pt=11.0,
        section_heading_pt=11.0,
        subheading_pt=10.0,
        body_pt=9.8,
        meta_pt=8.5,
        footer_pt=8.0,
        section_uppercase=False,
        paragraph_space_after_pt=5.0,
        section_space_before_pt=11.0,
        show_section_rule=True,
    ),
}


def get_template_spec(template_id: str) -> TemplateVisualSpec:
    if template_id not in TEMPLATES:
        raise ValueError(f"Template documental inválido: '{template_id}'.")
    return TEMPLATES[template_id]  # type: ignore[index]


_DOCUMENT_LABELS: dict[TargetLanguage, dict[str, str]] = {
    "pt-BR": {
        "draft_banner": "RASCUNHO NÃO APROVADO",
        "draft_watermark": "RASCUNHO NÃO APROVADO",
        "page_of": "Página {page} de {total}",
        "default_resume_title": "Currículo Profissional",
        "default_cover_letter_title": "Carta de Apresentação",
        "default_recruiter_title": "Mensagem para Recrutador",
        "default_proposal_title": "Proposta Técnica Freelance",
        "default_answers_title": "Respostas para Candidatura",
        "target_role": "Direcionamento para a Vaga",
        "matched_requirements": "Requisitos cobertos por fatos confirmados",
        "summary": "Resumo Profissional",
        "experiences": "Experiência Profissional",
        "projects": "Projetos",
        "education": "Formação Acadêmica",
        "skills": "Habilidades Técnicas",
        "languages": "Idiomas",
        "manual_notes": "Notas Adicionais",
        "technologies": "Tecnologias",
        "verified_results": "Resultados verificados",
        "links": "Links",
        "relevant_experience": "Experiências e Projetos Relevantes",
        "opportunity_alignment": "Relação com os Requisitos da Vaga",
        "project_understanding": "Entendimento do Projeto",
        "suggested_approach": "Abordagem Técnica Sugerida",
        "commercial_terms": "Condições Comerciais e Execução",
        "alignment_closing": "Pontos de Alinhamento",
        "term_column": "Parâmetro",
        "value_column": "Informação Definida",
        "email_subject": "Assunto",
        "channel": "Canal",
        "question_label": "Pergunta",
        "manual_answer_note": "Resposta registrada pelo candidato",
        "fact_evidence_note": "Evidências confirmadas",
        "channel_linkedin": "LinkedIn",
        "channel_email": "E-mail",
        "channel_contact_form": "Formulário de contato",
    },
    "en": {
        "draft_banner": "UNAPPROVED DRAFT",
        "draft_watermark": "UNAPPROVED DRAFT",
        "page_of": "Page {page} of {total}",
        "default_resume_title": "Professional Resume",
        "default_cover_letter_title": "Cover Letter",
        "default_recruiter_title": "Recruiter Message",
        "default_proposal_title": "Freelance Technical Proposal",
        "default_answers_title": "Application Question Responses",
        "target_role": "Target Role",
        "matched_requirements": "Matched confirmed evidence",
        "summary": "Professional Summary",
        "experiences": "Professional Experience",
        "projects": "Projects",
        "education": "Education",
        "skills": "Technical Skills",
        "languages": "Languages",
        "manual_notes": "Additional Notes",
        "technologies": "Technologies",
        "verified_results": "Verified results",
        "links": "Links",
        "relevant_experience": "Relevant Experience and Projects",
        "opportunity_alignment": "Alignment with Role Requirements",
        "project_understanding": "Project Understanding",
        "suggested_approach": "Suggested Technical Approach",
        "commercial_terms": "Commercial and Execution Terms",
        "alignment_closing": "Alignment Notes",
        "term_column": "Parameter",
        "value_column": "Confirmed Detail",
        "email_subject": "Subject",
        "channel": "Channel",
        "question_label": "Question",
        "manual_answer_note": "Candidate-authored response",
        "fact_evidence_note": "Confirmed evidence",
        "channel_linkedin": "LinkedIn",
        "channel_email": "Email",
        "channel_contact_form": "Contact form",
    },
}

_EXPERIENCE_TYPE_LABELS: dict[str, dict[str, str]] = {
    "target_role": {"pt-BR": "Atuação na área-alvo", "en": "Target role experience"},
    "related": {"pt-BR": "Experiência correlata", "en": "Related experience"},
    "internship": {"pt-BR": "Estágio", "en": "Internship"},
    "freelance": {"pt-BR": "Freelance", "en": "Freelance"},
    "academic": {"pt-BR": "Acadêmica", "en": "Academic"},
    "other": {"pt-BR": "Experiência complementar", "en": "Supporting experience"},
}


def get_document_labels(language: TargetLanguage) -> dict[str, str]:
    return _DOCUMENT_LABELS["en" if language == "en" else "pt-BR"]


def get_experience_type_label(experience_type: str, language: TargetLanguage) -> str:
    lang = "en" if language == "en" else "pt-BR"
    return _EXPERIENCE_TYPE_LABELS.get(experience_type, {}).get(lang, experience_type)


def format_section_heading(title: str, spec: TemplateVisualSpec) -> str:
    return title.upper() if spec.section_uppercase else title


def hex_to_rgb_tuple(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.lstrip("#")
    if len(cleaned) != 6:
        return (17, 24, 39)
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))
