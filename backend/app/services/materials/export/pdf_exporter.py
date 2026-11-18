"""Exportador PDF profissional com ReportLab Platypus, 100% em memória e determinístico."""
from __future__ import annotations

import io
import threading
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.material import (
    AnyMaterialStructuredContent,
    ApplicationAnswersStructuredContent,
    CoverLetterStructuredContent,
    FreelanceProposalStructuredContent,
    RecruiterMessageStructuredContent,
    ResumeHeaderSection,
    ResumeManualNoteItem,
    ResumeStructuredContent,
    TargetLanguage,
)
from app.services.materials.export.document_templates import (
    TemplateVisualSpec,
    format_section_heading,
    get_document_labels,
    get_experience_type_label,
)
from app.services.materials.export.document_validation import (
    DocumentExportRenderError,
    escape_pdf_paragraph_text,
    get_supported_pdf_codepoints,
    group_skills_by_category,
    resolve_controlled_fonts,
    safe_hyperlink_url,
)

_FONT_REG_LOCK = threading.Lock()
_FONTS_REGISTERED = False


def ensure_pdf_fonts_registered() -> None:
    """Registra a família Liberation Sans (SIL OFL 1.1) uma única vez com validação SHA-256."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    with _FONT_REG_LOCK:
        if _FONTS_REGISTERED:
            return
        font_paths = resolve_controlled_fonts()
        pdfmetrics.registerFont(TTFont("LiberationSans", str(font_paths.regular)))
        pdfmetrics.registerFont(TTFont("LiberationSans-Bold", str(font_paths.bold)))
        pdfmetrics.registerFont(TTFont("LiberationSans-Italic", str(font_paths.italic)))
        pdfmetrics.registerFont(TTFont("LiberationSans-BoldItalic", str(font_paths.bold_italic)))
        registerFontFamily(
            "LiberationSans",
            normal="LiberationSans",
            bold="LiberationSans-Bold",
            italic="LiberationSans-Italic",
            boldItalic="LiberationSans-BoldItalic",
        )
        _FONTS_REGISTERED = True


class _NumberedDeterministicCanvas(canvas.Canvas):
    """Canvas duas passagens determinístico (invariant=1) para rascunho e Página X de Y."""

    def __init__(
        self,
        *args: Any,
        spec: TemplateVisualSpec,
        labels: dict[str, str],
        is_draft: bool,
        **kwargs: Any,
    ) -> None:
        kwargs["invariant"] = 1
        super().__init__(*args, **kwargs)
        self._spec = spec
        self._labels = labels
        self._is_draft = is_draft
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_chrome(total_pages)
            super().showPage()
        super().save()

    def _draw_page_chrome(self, total_pages: int) -> None:
        page_w, page_h = A4
        page_num = self.getPageNumber()

        if self._is_draft:
            # Marca d'água diagonal discreta no fundo de todas as páginas
            self.saveState()
            self.translate(page_w / 2.0, page_h / 2.0)
            self.rotate(38)
            self.setFillColor(colors.HexColor("#9CA3AF"), alpha=0.14)
            self.setFont(self._spec.pdf_font_bold, 38)
            self.drawCentredString(0, 0, self._labels["draft_watermark"])
            self.restoreState()

            # Faixa fixa discreta no topo de todas as páginas
            self.saveState()
            bar_h = 6.5 * mm
            bar_y = page_h - 10.5 * mm
            self.setFillColor(colors.HexColor(self._spec.draft_bg_hex))
            self.rect(
                self._spec.margin_left_mm * mm,
                bar_y,
                page_w - (self._spec.margin_left_mm + self._spec.margin_right_mm) * mm,
                bar_h,
                fill=1,
                stroke=0,
            )
            self.setFillColor(colors.HexColor(self._spec.draft_banner_hex))
            self.setFont(self._spec.pdf_font_bold, self._spec.footer_pt)
            self.drawCentredString(page_w / 2.0, bar_y + 2.0 * mm, self._labels["draft_banner"])
            self.restoreState()

        # Rodapé "Página X de Y" apenas quando houver mais de 1 página
        if total_pages > 1:
            self.saveState()
            self.setFillColor(colors.HexColor(self._spec.muted_hex))
            self.setFont(self._spec.pdf_font_regular, self._spec.footer_pt)
            footer_txt = self._labels["page_of"].format(page=page_num, total=total_pages)
            right_x = page_w - self._spec.margin_right_mm * mm
            self.drawRightString(right_x, 10.0 * mm, footer_txt)
            if self._is_draft:
                self.setFillColor(colors.HexColor(self._spec.draft_banner_hex))
                self.drawString(self._spec.margin_left_mm * mm, 10.0 * mm, self._labels["draft_banner"])
            self.restoreState()


def _build_styles(spec: TemplateVisualSpec) -> dict[str, ParagraphStyle]:
    return {
        "name": ParagraphStyle(
            name="JHName",
            fontName=spec.pdf_font_bold,
            fontSize=spec.name_pt,
            leading=spec.name_pt * 1.22,
            textColor=colors.HexColor(spec.heading_hex),
            alignment=TA_LEFT,
            spaceAfter=2,
            keepWithNext=True,
        ),
        "title": ParagraphStyle(
            name="JHTitle",
            fontName=spec.pdf_font_bold if spec.template_id == "modern_minimal" else spec.pdf_font_regular,
            fontSize=spec.title_pt,
            leading=spec.title_pt * 1.25,
            textColor=colors.HexColor(spec.muted_hex),
            spaceAfter=3,
            keepWithNext=True,
        ),
        "meta": ParagraphStyle(
            name="JHMeta",
            fontName=spec.pdf_font_regular,
            fontSize=spec.meta_pt,
            leading=spec.meta_pt * 1.35,
            textColor=colors.HexColor(spec.muted_hex),
            spaceAfter=4,
        ),
        "meta_italic": ParagraphStyle(
            name="JHMetaItalic",
            fontName=spec.pdf_font_italic,
            fontSize=spec.meta_pt,
            leading=spec.meta_pt * 1.32,
            textColor=colors.HexColor(spec.muted_hex),
            spaceAfter=2.5,
            keepWithNext=True,
        ),
        "section": ParagraphStyle(
            name="JHSection",
            fontName=spec.pdf_font_bold,
            fontSize=spec.section_heading_pt,
            leading=spec.section_heading_pt * 1.25,
            textColor=colors.HexColor(spec.heading_hex),
            spaceBefore=spec.section_space_before_pt,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "subheading": ParagraphStyle(
            name="JHSubheading",
            fontName=spec.pdf_font_bold,
            fontSize=spec.subheading_pt,
            leading=spec.subheading_pt * 1.3,
            textColor=colors.HexColor(spec.heading_hex),
            spaceBefore=3,
            spaceAfter=1.5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            name="JHBody",
            fontName=spec.pdf_font_regular,
            fontSize=spec.body_pt,
            leading=spec.body_pt * 1.42,
            textColor=colors.HexColor(spec.text_hex),
            spaceAfter=spec.paragraph_space_after_pt,
            splitLongWords=1,
        ),
        "bullet_text": ParagraphStyle(
            name="JHBullet",
            fontName=spec.pdf_font_regular,
            fontSize=spec.body_pt,
            leading=spec.body_pt * 1.38,
            textColor=colors.HexColor(spec.text_hex),
            spaceAfter=1.5,
            splitLongWords=1,
        ),
        "table_header": ParagraphStyle(
            name="JHTableHeader",
            fontName=spec.pdf_font_bold,
            fontSize=spec.body_pt,
            leading=spec.body_pt * 1.3,
            textColor=colors.HexColor(spec.heading_hex),
        ),
        "table_cell": ParagraphStyle(
            name="JHTableCell",
            fontName=spec.pdf_font_regular,
            fontSize=spec.body_pt,
            leading=spec.body_pt * 1.35,
            textColor=colors.HexColor(spec.text_hex),
            splitLongWords=1,
        ),
    }


def _esc(raw: str | None, cmap: frozenset[int]) -> str:
    escaped, _ = escape_pdf_paragraph_text(raw, supported_codepoints=cmap)
    return escaped


def _esc_multiline(raw: str | None, cmap: frozenset[int]) -> str:
    return _esc(raw, cmap).replace("\n", "<br/>")


def _link_markup(label: str, safe_url: str, spec: TemplateVisualSpec, cmap: frozenset[int]) -> str:
    esc_label = _esc(label, cmap)
    esc_url = _esc(safe_url, cmap)
    return f'<a href="{esc_url}" color="{spec.link_hex}"><u>{esc_label}</u></a>'


def _append_section_heading(
    story: list[Any],
    title: str,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    cmap: frozenset[int],
) -> None:
    heading_txt = format_section_heading(title, spec)
    story.append(CondPageBreak(18 * mm))
    heading_p = Paragraph(_esc(heading_txt, cmap), styles["section"])
    if spec.show_section_rule:
        rule = HRFlowable(
            width="100%",
            thickness=0.6,
            color=colors.HexColor(spec.divider_hex),
            spaceBefore=1,
            spaceAfter=4,
        )
        story.append(KeepTogether([heading_p, rule]))
    else:
        story.append(heading_p)


def _append_header_block(
    story: list[Any],
    header: ResumeHeaderSection,
    fallback_title: str,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    cmap: frozenset[int],
) -> None:
    block: list[Any] = []
    block.append(Paragraph(_esc(header.full_name or fallback_title, cmap), styles["name"]))
    if header.professional_title:
        block.append(Paragraph(_esc(header.professional_title, cmap), styles["title"]))

    contact_markups = [_esc(b, cmap) for b in (header.location_text, header.email, header.phone) if b and b.strip()]
    for lk in header.links:
        safe_url = safe_hyperlink_url(lk.url)
        if safe_url:
            contact_markups.append(_link_markup(lk.label or safe_url, safe_url, spec, cmap))
    if contact_markups:
        block.append(Paragraph("  |  ".join(contact_markups), styles["meta"]))
    block.append(Spacer(1, 3 * mm))
    story.append(KeepTogether(block))


def _append_bullet_list(
    story: list[Any],
    items_markup: list[str],
    styles: dict[str, ParagraphStyle],
    spec: TemplateVisualSpec,
) -> None:
    if not items_markup:
        return
    list_items = [
        ListItem(Paragraph(markup, styles["bullet_text"]), leftIndent=10)
        for markup in items_markup
    ]
    story.append(
        ListFlowable(
            list_items,
            bulletType="bullet",
            start="•",
            bulletFontName=spec.pdf_font_regular,
            bulletFontSize=spec.body_pt,
            leftIndent=12,
            bulletOffsetY=-1,
            spaceBefore=1,
            spaceAfter=3,
        )
    )


def _append_manual_notes(
    story: list[Any],
    notes: list[ResumeManualNoteItem],
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    labels: dict[str, str],
    cmap: frozenset[int],
) -> None:
    if not notes:
        return
    _append_section_heading(story, labels["manual_notes"], spec, styles, cmap)
    for note in notes:
        story.append(Paragraph(_esc(note.title, cmap), styles["subheading"]))
        story.append(Paragraph(_esc_multiline(note.content, cmap), styles["body"]))


def _build_resume_story(
    story: list[Any],
    content: ResumeStructuredContent,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    labels: dict[str, str],
    lang: TargetLanguage,
    cmap: frozenset[int],
) -> None:
    _append_header_block(story, content.header, labels["default_resume_title"], spec, styles, cmap)

    if content.target_alignment:
        ta = content.target_alignment
        _append_section_heading(story, labels["target_role"], spec, styles, cmap)
        bullets: list[str] = []
        role_txt = f"<b>{_esc(ta.target_role, cmap)}</b>"
        if ta.company_name:
            role_txt += f" — {_esc(ta.company_name, cmap)}"
        bullets.append(role_txt)
        if ta.highlighted_requirements:
            bullets.append(
                f"<b>{_esc(labels['matched_requirements'], cmap)}:</b> {_esc(', '.join(ta.highlighted_requirements), cmap)}"
            )
        if ta.alignment_note:
            bullets.append(_esc(ta.alignment_note, cmap))
        _append_bullet_list(story, bullets, styles, spec)

    if content.summary:
        _append_section_heading(story, labels["summary"], spec, styles, cmap)
        story.append(Paragraph(_esc_multiline(content.summary.text, cmap), styles["body"]))

    if content.experiences:
        _append_section_heading(story, labels["experiences"], spec, styles, cmap)
        for exp in content.experiences:
            exp_type_lbl = get_experience_type_label(exp.experience_type, lang)
            meta_parts = [p for p in (exp.period_label, exp_type_lbl) if p]
            story.append(Paragraph(_esc(f"{exp.role} — {exp.company}", cmap), styles["subheading"]))
            if meta_parts:
                story.append(Paragraph(_esc(" · ".join(meta_parts), cmap), styles["meta_italic"]))
            if exp.description:
                story.append(Paragraph(_esc_multiline(exp.description, cmap), styles["body"]))
            if exp.technologies:
                _append_bullet_list(
                    story,
                    [f"<b>{_esc(labels['technologies'], cmap)}:</b> {_esc(', '.join(exp.technologies), cmap)}"],
                    styles,
                    spec,
                )

    if content.projects:
        _append_section_heading(story, labels["projects"], spec, styles, cmap)
        for proj in content.projects:
            title_txt = proj.name + (f" ({proj.role})" if proj.role else "")
            story.append(Paragraph(_esc(title_txt, cmap), styles["subheading"]))
            if proj.description:
                story.append(Paragraph(_esc_multiline(proj.description, cmap), styles["body"]))
            proj_bullets: list[str] = []
            if proj.verified_results:
                proj_bullets.append(
                    f"<b>{_esc(labels['verified_results'], cmap)}:</b> {_esc(proj.verified_results, cmap)}"
                )
            if proj.technologies:
                proj_bullets.append(
                    f"<b>{_esc(labels['technologies'], cmap)}:</b> {_esc(', '.join(proj.technologies), cmap)}"
                )
            link_parts = [
                _link_markup(lk.label or safe_url, safe_url, spec, cmap)
                for lk in proj.links
                if (safe_url := safe_hyperlink_url(lk.url)) is not None
            ]
            if link_parts:
                proj_bullets.append(f"<b>{_esc(labels['links'], cmap)}:</b> {' · '.join(link_parts)}")
            _append_bullet_list(story, proj_bullets, styles, spec)

    if content.education:
        _append_section_heading(story, labels["education"], spec, styles, cmap)
        edu_bullets: list[str] = []
        for edu in content.education:
            extras = [p for p in (edu.current_semester, edu.period_label, edu.field_of_study) if p]
            line = f"<b>{_esc(edu.course, cmap)}</b> — {_esc(edu.institution, cmap)} ({_esc(edu.status_label, cmap)})"
            if extras:
                line += f" · {_esc(' · '.join(extras), cmap)}"
            edu_bullets.append(line)
        _append_bullet_list(story, edu_bullets, styles, spec)

    if content.skills:
        _append_section_heading(story, labels["skills"], spec, styles, cmap)
        sk_bullets = [
            f"<b>{_esc(category, cmap)}:</b> {_esc(', '.join(f'{it.name} ({it.proficiency_label})' for it in items), cmap)}"
            for category, items in group_skills_by_category(content.skills).items()
        ]
        _append_bullet_list(story, sk_bullets, styles, spec)

    if content.languages:
        _append_section_heading(story, labels["languages"], spec, styles, cmap)
        lang_bullets: list[str] = []
        for lang_item in content.languages:
            cefr = f" · {_esc(lang_item.cefr_level, cmap)}" if lang_item.cefr_level else ""
            lang_bullets.append(
                f"<b>{_esc(lang_item.language_name, cmap)}:</b> {_esc(lang_item.proficiency_label, cmap)}{cefr}"
            )
        _append_bullet_list(story, lang_bullets, styles, spec)

    _append_manual_notes(story, content.manual_notes, spec, styles, labels, cmap)


def _build_cover_letter_story(
    story: list[Any],
    content: CoverLetterStructuredContent,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    labels: dict[str, str],
    cmap: frozenset[int],
) -> None:
    _append_header_block(story, content.header, labels["default_cover_letter_title"], spec, styles, cmap)
    story.append(
        KeepTogether(
            [
                Paragraph(_esc_multiline(content.recipient_line.text, cmap), styles["meta"]),
                Spacer(1, 2.5 * mm),
                Paragraph(_esc_multiline(content.greeting.text, cmap), styles["body"]),
            ]
        )
    )
    story.append(Paragraph(_esc_multiline(content.opening.text, cmap), styles["body"]))

    if content.relevance_highlights:
        _append_section_heading(story, labels["relevant_experience"], spec, styles, cmap)
        _append_bullet_list(
            story,
            [
                f"<b>{_esc(block.title, cmap)}:</b> {_esc(block.summary_text, cmap)}"
                for block in content.relevance_highlights
            ],
            styles,
            spec,
        )

    if content.opportunity_alignment:
        _append_section_heading(story, labels["opportunity_alignment"], spec, styles, cmap)
        story.append(Paragraph(_esc_multiline(content.opportunity_alignment.text, cmap), styles["body"]))

    story.append(Spacer(1, 3 * mm))
    story.append(KeepTogether([Paragraph(_esc_multiline(content.closing.text, cmap), styles["body"])]))
    _append_manual_notes(story, content.manual_notes, spec, styles, labels, cmap)


def _build_recruiter_message_story(
    story: list[Any],
    content: RecruiterMessageStructuredContent,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    labels: dict[str, str],
    cmap: frozenset[int],
) -> None:
    channel_label = labels.get(f"channel_{content.channel}", content.channel)
    title_block: list[Any] = [
        Paragraph(_esc(labels["default_recruiter_title"], cmap), styles["name"]),
        Paragraph(_esc(f"{labels['channel']}: {channel_label}", cmap), styles["meta"]),
    ]
    if spec.show_section_rule:
        title_block.append(
            HRFlowable(
                width="100%",
                thickness=0.6,
                color=colors.HexColor(spec.divider_hex),
                spaceBefore=1,
                spaceAfter=4,
            )
        )
    story.append(KeepTogether(title_block))

    if content.channel == "email" and content.subject:
        subj_markup = f"<b>{_esc(labels['email_subject'], cmap)}:</b> {_esc(content.subject.text, cmap)}"
        avail_w = A4[0] - (spec.margin_left_mm + spec.margin_right_mm) * mm
        tbl = Table([[Paragraph(subj_markup, styles["table_cell"])]], colWidths=[avail_w])
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(spec.table_header_bg_hex)),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(spec.divider_hex)),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(tbl)
        story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(_esc_multiline(content.greeting.text, cmap), styles["body"]))
    story.append(Paragraph(_esc_multiline(content.body.text, cmap), styles["body"]))
    story.append(Spacer(1, 2 * mm))
    story.append(KeepTogether([Paragraph(_esc_multiline(content.sign_off.text, cmap), styles["body"])]))
    _append_manual_notes(story, content.manual_notes, spec, styles, labels, cmap)


def _build_freelance_proposal_story(
    story: list[Any],
    content: FreelanceProposalStructuredContent,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    labels: dict[str, str],
    cmap: frozenset[int],
) -> None:
    _append_header_block(story, content.header, labels["default_proposal_title"], spec, styles, cmap)
    story.append(Paragraph(_esc_multiline(content.introduction.text, cmap), styles["body"]))

    _append_section_heading(story, labels["project_understanding"], spec, styles, cmap)
    story.append(Paragraph(_esc_multiline(content.project_understanding.text, cmap), styles["body"]))

    if content.relevant_evidence:
        _append_section_heading(story, labels["relevant_experience"], spec, styles, cmap)
        _append_bullet_list(
            story,
            [
                f"<b>{_esc(block.title, cmap)}:</b> {_esc(block.summary_text, cmap)}"
                for block in content.relevant_evidence
            ],
            styles,
            spec,
        )

    _append_section_heading(story, labels["suggested_approach"], spec, styles, cmap)
    story.append(Paragraph(_esc_multiline(content.suggested_approach.text, cmap), styles["body"]))

    provided_fields = [
        f for f in content.pending_fields if f.status == "provided" and f.user_value and f.user_value.strip()
    ]
    if provided_fields:
        _append_section_heading(story, labels["commercial_terms"], spec, styles, cmap)
        avail_w = A4[0] - (spec.margin_left_mm + spec.margin_right_mm) * mm
        rows: list[list[Any]] = [
            [
                Paragraph(_esc(labels["term_column"], cmap), styles["table_header"]),
                Paragraph(_esc(labels["value_column"], cmap), styles["table_header"]),
            ]
        ]
        for field in provided_fields:
            rows.append(
                [
                    Paragraph(f"<b>{_esc(field.label, cmap)}</b>", styles["table_cell"]),
                    Paragraph(_esc_multiline(field.user_value or "", cmap), styles["table_cell"]),
                ]
            )
        tbl = Table(rows, colWidths=[avail_w * 0.36, avail_w * 0.64], repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(spec.table_header_bg_hex)),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(spec.divider_hex)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tbl)
        story.append(Spacer(1, 3 * mm))

    if content.alignment_points and content.alignment_points.text.strip():
        _append_section_heading(story, labels["alignment_closing"], spec, styles, cmap)
        story.append(Paragraph(_esc_multiline(content.alignment_points.text, cmap), styles["body"]))

    story.append(Spacer(1, 3 * mm))
    story.append(KeepTogether([Paragraph(_esc_multiline(content.closing.text, cmap), styles["body"])]))
    _append_manual_notes(story, content.manual_notes, spec, styles, labels, cmap)


def _build_application_answers_story(
    story: list[Any],
    content: ApplicationAnswersStructuredContent,
    spec: TemplateVisualSpec,
    styles: dict[str, ParagraphStyle],
    labels: dict[str, str],
    cmap: frozenset[int],
) -> None:
    title_block: list[Any] = [Paragraph(_esc(labels["default_answers_title"], cmap), styles["name"])]
    if spec.show_section_rule:
        title_block.append(
            HRFlowable(
                width="100%",
                thickness=0.6,
                color=colors.HexColor(spec.divider_hex),
                spaceBefore=2,
                spaceAfter=5,
            )
        )
    story.append(KeepTogether(title_block))

    for idx, item in enumerate(content.items, start=1):
        story.append(CondPageBreak(18 * mm))
        story.append(Paragraph(_esc(f"{idx}. {item.question}", cmap), styles["subheading"]))
        if item.answer_text:
            story.append(Paragraph(_esc_multiline(item.answer_text, cmap), styles["body"]))
        if item.evidence_notes:
            ev_txt = f"{labels['fact_evidence_note']}: {'; '.join(item.evidence_notes)}"
            story.append(Paragraph(_esc(ev_txt, cmap), styles["meta_italic"]))
        story.append(Spacer(1, 2 * mm))

    _append_manual_notes(story, content.manual_notes, spec, styles, labels, cmap)


def export_material_to_pdf(
    structured: AnyMaterialStructuredContent,
    *,
    spec: TemplateVisualSpec,
    language: TargetLanguage,
    document_title: str,
    is_draft: bool,
    version_created_at: datetime | None = None,
) -> bytes:
    """Gera documento PDF profissional com Platypus + Liberation Sans + invariant=1 em memória."""
    _ = version_created_at
    ensure_pdf_fonts_registered()
    cmap = get_supported_pdf_codepoints()
    labels = get_document_labels(language)
    styles = _build_styles(spec)

    story: list[Any] = []
    if isinstance(structured, ResumeStructuredContent):
        _build_resume_story(story, structured, spec, styles, labels, language, cmap)
    elif isinstance(structured, CoverLetterStructuredContent):
        _build_cover_letter_story(story, structured, spec, styles, labels, cmap)
    elif isinstance(structured, RecruiterMessageStructuredContent):
        _build_recruiter_message_story(story, structured, spec, styles, labels, cmap)
    elif isinstance(structured, FreelanceProposalStructuredContent):
        _build_freelance_proposal_story(story, structured, spec, styles, labels, cmap)
    elif isinstance(structured, ApplicationAnswersStructuredContent):
        _build_application_answers_story(story, structured, spec, styles, labels, cmap)
    else:
        raise DocumentExportRenderError("Estrutura de material não suportada para exportação PDF.")

    top_extra = 5.0 if is_draft else 0.0
    bottom_extra = 4.0
    top_margin = (spec.margin_top_mm + top_extra) * mm
    bottom_margin = (spec.margin_bottom_mm + bottom_extra) * mm
    left_margin = spec.margin_left_mm * mm
    right_margin = spec.margin_right_mm * mm
    page_w, page_h = A4

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        leftMargin=left_margin,
        rightMargin=right_margin,
        title=document_title,
        author="Job Hunter",
        creator="Job Hunter Deterministic Exporter",
    )
    frame = Frame(
        left_margin,
        bottom_margin,
        page_w - left_margin - right_margin,
        page_h - top_margin - bottom_margin,
        id="main_frame",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="A4SingleColumn", frames=[frame])])

    try:
        doc.build(
            story,
            canvasmaker=lambda *args, **kwargs: _NumberedDeterministicCanvas(
                *args,
                spec=spec,
                labels=labels,
                is_draft=is_draft,
                **kwargs,
            ),
        )
    except Exception as exc:
        raise DocumentExportRenderError("Falha interna ao renderizar o documento PDF.") from exc

    return buf.getvalue()
