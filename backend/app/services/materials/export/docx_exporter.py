"""Exportador DOCX profissional com python-docx, 100% em memória e multi-template."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from typing import Iterable

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Mm, Pt, RGBColor

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
    hex_to_rgb_tuple,
)
from app.services.materials.export.document_validation import (
    format_docx_text,
    group_skills_by_category,
    safe_hyperlink_url,
)


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor(*hex_to_rgb_tuple(hex_color))


def _set_paragraph_bottom_border(paragraph, color_hex: str, size_eighths_pt: str = "6") -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'<w:bottom w:val="single" w:sz="{size_eighths_pt}" w:space="3" w:color="{color_hex.lstrip("#")}"/>'
        "</w:pBdr>"
    )
    p_pr.append(p_bdr)


def _set_cell_shading(cell, fill_hex: str) -> None:
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex.lstrip("#")}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _set_row_cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:cantSplit"))


def _set_row_tbl_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:tblHeader"))


def _add_hyperlink(paragraph, text: str, url: str, spec: TemplateVisualSpec, font_size_pt: float) -> None:
    safe_url = safe_hyperlink_url(url)
    label = format_docx_text(text) or (safe_url or "")
    if not safe_url:
        run = paragraph.add_run(label)
        run.font.name = spec.docx_font_family
        run.font.size = Pt(font_size_pt)
        run.font.color.rgb = _rgb(spec.muted_hex)
        return

    part = paragraph.part
    r_id = part.relate_to(
        safe_url,
        docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK,
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")

    r_fonts = OxmlElement("w:rFonts")
    r_fonts.set(qn("w:ascii"), spec.docx_font_family)
    r_fonts.set(qn("w:hAnsi"), spec.docx_font_family)
    r_pr.append(r_fonts)

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(font_size_pt * 2)))
    r_pr.append(sz)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), spec.link_hex.lstrip("#"))
    r_pr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.append(underline)

    new_run.append(r_pr)
    t_elem = OxmlElement("w:t")
    t_elem.set(qn("xml:space"), "preserve")
    t_elem.text = label
    new_run.append(t_elem)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _add_page_field_runs(paragraph, spec: TemplateVisualSpec, lang: TargetLanguage) -> None:
    """Adiciona numeração Page X of Y no rodapé compatível com Word/LibreOffice."""
    prefix = "Página " if lang != "en" else "Page "
    middle = " de " if lang != "en" else " of "

    def _add_text_run(txt: str):
        r = paragraph.add_run(txt)
        r.font.name = spec.docx_font_family
        r.font.size = Pt(spec.footer_pt)
        r.font.color.rgb = _rgb(spec.muted_hex)

    def _add_field(field_name: str):
        r_begin = paragraph.add_run()
        r_begin.font.name = spec.docx_font_family
        r_begin.font.size = Pt(spec.footer_pt)
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        r_begin._r.append(fld_begin)

        r_instr = paragraph.add_run()
        r_instr.font.name = spec.docx_font_family
        r_instr.font.size = Pt(spec.footer_pt)
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = f" {field_name} "
        r_instr._r.append(instr)

        r_sep = paragraph.add_run()
        r_sep.font.name = spec.docx_font_family
        r_sep.font.size = Pt(spec.footer_pt)
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        r_sep._r.append(fld_sep)

        r_val = paragraph.add_run("1")
        r_val.font.name = spec.docx_font_family
        r_val.font.size = Pt(spec.footer_pt)
        r_val.font.color.rgb = _rgb(spec.muted_hex)

        r_end = paragraph.add_run()
        r_end.font.name = spec.docx_font_family
        r_end.font.size = Pt(spec.footer_pt)
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        r_end._r.append(fld_end)

    _add_text_run(prefix)
    _add_field("PAGE")
    _add_text_run(middle)
    _add_field("NUMPAGES")


def _configure_document_base(
    doc: docx.Document,
    spec: TemplateVisualSpec,
    labels: dict[str, str],
    lang: TargetLanguage,
    *,
    title: str,
    is_draft: bool,
    created_at: datetime | None,
    updated_at: datetime | None,
) -> None:
    normal_style = doc.styles["Normal"]
    normal_style.font.name = spec.docx_font_family
    normal_style.font.size = Pt(spec.body_pt)
    normal_style.font.color.rgb = _rgb(spec.text_hex)
    normal_style.paragraph_format.space_after = Pt(spec.paragraph_space_after_pt)
    normal_style.paragraph_format.line_spacing = 1.15
    normal_style.paragraph_format.widow_control = True

    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(spec.margin_top_mm)
    section.bottom_margin = Mm(spec.margin_bottom_mm)
    section.left_margin = Mm(spec.margin_left_mm)
    section.right_margin = Mm(spec.margin_right_mm)
    section.header_distance = Mm(8)
    section.footer_distance = Mm(8)

    # Metadados documentais com datas da versão (sem timestamp aleatório)
    core = doc.core_properties
    core.title = format_docx_text(title)
    core.author = "Job Hunter"
    core.language = lang
    core.revision = 1
    if created_at is not None:
        core.created = created_at.astimezone(timezone.utc).replace(tzinfo=None)
    if updated_at is not None:
        core.modified = updated_at.astimezone(timezone.utc).replace(tzinfo=None)

    if is_draft:
        hdr = section.header
        hp = hdr.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hp.paragraph_format.space_after = Pt(4)
        hr = hp.add_run(labels["draft_banner"])
        hr.bold = True
        hr.font.name = spec.docx_font_family
        hr.font.size = Pt(spec.footer_pt)
        hr.font.color.rgb = _rgb(spec.draft_banner_hex)
        _set_paragraph_bottom_border(hp, spec.draft_banner_hex, size_eighths_pt="4")

    ftr = section.footer
    fp = ftr.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if is_draft:
        dr = fp.add_run(f"{labels['draft_banner']}  |  ")
        dr.bold = True
        dr.font.name = spec.docx_font_family
        dr.font.size = Pt(spec.footer_pt)
        dr.font.color.rgb = _rgb(spec.draft_banner_hex)
    _add_page_field_runs(fp, spec, lang)


def _add_section_heading(doc: docx.Document, text: str, spec: TemplateVisualSpec) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(spec.section_space_before_pt)
    p.paragraph_format.space_after = Pt(4.0)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.widow_control = True
    run = p.add_run(format_section_heading(format_docx_text(text), spec))
    run.bold = True
    run.font.name = spec.docx_font_family
    run.font.size = Pt(spec.section_heading_pt)
    run.font.color.rgb = _rgb(spec.heading_hex)
    if spec.show_section_rule:
        _set_paragraph_bottom_border(p, spec.divider_hex, size_eighths_pt="6")


def _add_body_paragraph(
    doc: docx.Document,
    text: str,
    spec: TemplateVisualSpec,
    *,
    bold_prefix: str | None = None,
    space_after_pt: float | None = None,
    italic: bool = False,
    muted: bool = False,
    keep_with_next: bool = False,
) -> docx.text.paragraph.Paragraph:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(
        spec.paragraph_space_after_pt if space_after_pt is None else space_after_pt
    )
    p.paragraph_format.widow_control = True
    p.paragraph_format.keep_with_next = keep_with_next
    color_rgb = _rgb(spec.muted_hex if muted else spec.text_hex)
    if bold_prefix:
        rb = p.add_run(format_docx_text(bold_prefix))
        rb.bold = True
        rb.font.name = spec.docx_font_family
        rb.font.size = Pt(spec.body_pt)
        rb.font.color.rgb = _rgb(spec.heading_hex)
    for idx, line in enumerate(format_docx_text(text).splitlines()):
        if idx > 0:
            p.add_run().add_break()
        r = p.add_run(line)
        r.italic = italic
        r.font.name = spec.docx_font_family
        r.font.size = Pt(spec.body_pt)
        r.font.color.rgb = color_rgb
    return p


def _add_bullet_paragraph(
    doc: docx.Document,
    text: str,
    spec: TemplateVisualSpec,
    *,
    bold_prefix: str | None = None,
) -> docx.text.paragraph.Paragraph:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2.5)
    p.paragraph_format.widow_control = True
    if bold_prefix:
        rb = p.add_run(format_docx_text(bold_prefix))
        rb.bold = True
        rb.font.name = spec.docx_font_family
        rb.font.size = Pt(spec.body_pt)
        rb.font.color.rgb = _rgb(spec.heading_hex)
    r = p.add_run(format_docx_text(text))
    r.font.name = spec.docx_font_family
    r.font.size = Pt(spec.body_pt)
    r.font.color.rgb = _rgb(spec.text_hex)
    return p


def _add_header_block(
    doc: docx.Document,
    header: ResumeHeaderSection,
    spec: TemplateVisualSpec,
    fallback_title: str,
    *,
    compact: bool = False,
) -> None:
    name_p = doc.add_paragraph()
    name_p.paragraph_format.space_before = Pt(0)
    name_p.paragraph_format.space_after = Pt(2.0)
    name_p.paragraph_format.keep_with_next = True
    name_run = name_p.add_run(format_docx_text(header.full_name or fallback_title))
    name_run.bold = True
    name_run.font.name = spec.docx_font_family
    name_run.font.size = Pt(spec.title_pt + 2 if compact else spec.name_pt)
    name_run.font.color.rgb = _rgb(spec.heading_hex)

    if header.professional_title:
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_after = Pt(3.0)
        title_p.paragraph_format.keep_with_next = True
        tr = title_p.add_run(format_docx_text(header.professional_title))
        tr.bold = spec.template_id == "modern_minimal"
        tr.font.name = spec.docx_font_family
        tr.font.size = Pt(spec.title_pt)
        tr.font.color.rgb = _rgb(spec.muted_hex)

    contact_bits = [
        b
        for b in (header.location_text, header.email, header.phone)
        if b and b.strip()
    ]
    valid_links = [
        (lk.label, safe_url)
        for lk in header.links
        if (safe_url := safe_hyperlink_url(lk.url)) is not None
    ]
    if contact_bits or valid_links:
        cp = doc.add_paragraph()
        cp.paragraph_format.space_after = Pt(6.0)
        cp.paragraph_format.keep_with_next = True
        first = True
        for item in contact_bits:
            if not first:
                sep = cp.add_run("  |  ")
                sep.font.name = spec.docx_font_family
                sep.font.size = Pt(spec.meta_pt)
                sep.font.color.rgb = _rgb(spec.muted_hex)
            r = cp.add_run(format_docx_text(item))
            r.font.name = spec.docx_font_family
            r.font.size = Pt(spec.meta_pt)
            r.font.color.rgb = _rgb(spec.muted_hex)
            first = False
        for label, url in valid_links:
            if not first:
                sep = cp.add_run("  |  ")
                sep.font.name = spec.docx_font_family
                sep.font.size = Pt(spec.meta_pt)
                sep.font.color.rgb = _rgb(spec.muted_hex)
            _add_hyperlink(cp, label, url, spec, spec.meta_pt)
            first = False


def _add_manual_notes(
    doc: docx.Document,
    notes: Iterable[ResumeManualNoteItem],
    spec: TemplateVisualSpec,
    labels: dict[str, str],
) -> None:
    note_list = list(notes)
    if not note_list:
        return
    _add_section_heading(doc, labels["manual_notes"], spec)
    for note in note_list:
        tp = doc.add_paragraph()
        tp.paragraph_format.space_before = Pt(3)
        tp.paragraph_format.space_after = Pt(1.5)
        tp.paragraph_format.keep_with_next = True
        r = tp.add_run(format_docx_text(note.title))
        r.bold = True
        r.font.name = spec.docx_font_family
        r.font.size = Pt(spec.subheading_pt)
        r.font.color.rgb = _rgb(spec.heading_hex)
        _add_body_paragraph(doc, note.content, spec)


def _render_resume_docx(
    doc: docx.Document,
    content: ResumeStructuredContent,
    spec: TemplateVisualSpec,
    labels: dict[str, str],
    lang: TargetLanguage,
) -> None:
    _add_header_block(doc, content.header, spec, labels["default_resume_title"])

    if content.target_alignment:
        ta = content.target_alignment
        _add_section_heading(doc, labels["target_role"], spec)
        role_text = f"{ta.target_role}" + (f" — {ta.company_name}" if ta.company_name else "")
        _add_body_paragraph(doc, role_text, spec, bold_prefix=None, space_after_pt=2.0)
        if ta.highlighted_requirements:
            _add_bullet_paragraph(
                doc,
                ", ".join(ta.highlighted_requirements),
                spec,
                bold_prefix=f"{labels['matched_requirements']}: ",
            )
        if ta.alignment_note:
            _add_bullet_paragraph(doc, ta.alignment_note, spec)

    if content.summary:
        _add_section_heading(doc, labels["summary"], spec)
        _add_body_paragraph(doc, content.summary.text, spec)

    if content.experiences:
        _add_section_heading(doc, labels["experiences"], spec)
        for exp in content.experiences:
            hp = doc.add_paragraph()
            hp.paragraph_format.space_before = Pt(4)
            hp.paragraph_format.space_after = Pt(1.5)
            hp.paragraph_format.keep_with_next = True
            r = hp.add_run(format_docx_text(f"{exp.role} — {exp.company}"))
            r.bold = True
            r.font.name = spec.docx_font_family
            r.font.size = Pt(spec.subheading_pt)
            r.font.color.rgb = _rgb(spec.heading_hex)

            exp_type_lbl = get_experience_type_label(exp.experience_type, lang)
            meta_parts = [p for p in [exp.period_label, exp_type_lbl] if p]
            if meta_parts:
                mp = doc.add_paragraph()
                mp.paragraph_format.space_after = Pt(2)
                mp.paragraph_format.keep_with_next = True
                mr = mp.add_run(format_docx_text(" · ".join(meta_parts)))
                mr.italic = True
                mr.font.name = spec.docx_font_family
                mr.font.size = Pt(spec.meta_pt)
                mr.font.color.rgb = _rgb(spec.muted_hex)
            if exp.description:
                _add_body_paragraph(doc, exp.description, spec, space_after_pt=2.5)
            if exp.technologies:
                _add_bullet_paragraph(
                    doc,
                    ", ".join(exp.technologies),
                    spec,
                    bold_prefix=f"{labels['technologies']}: ",
                )

    if content.projects:
        _add_section_heading(doc, labels["projects"], spec)
        for proj in content.projects:
            pp = doc.add_paragraph()
            pp.paragraph_format.space_before = Pt(4)
            pp.paragraph_format.space_after = Pt(1.5)
            pp.paragraph_format.keep_with_next = True
            title_txt = proj.name + (f" ({proj.role})" if proj.role else "")
            pr = pp.add_run(format_docx_text(title_txt))
            pr.bold = True
            pr.font.name = spec.docx_font_family
            pr.font.size = Pt(spec.subheading_pt)
            pr.font.color.rgb = _rgb(spec.heading_hex)
            if proj.description:
                _add_body_paragraph(doc, proj.description, spec, space_after_pt=2.5)
            if proj.verified_results:
                _add_bullet_paragraph(
                    doc,
                    proj.verified_results,
                    spec,
                    bold_prefix=f"{labels['verified_results']}: ",
                )
            if proj.technologies:
                _add_bullet_paragraph(
                    doc,
                    ", ".join(proj.technologies),
                    spec,
                    bold_prefix=f"{labels['technologies']}: ",
                )
            valid_links = [
                (lk.label, safe_url)
                for lk in proj.links
                if (safe_url := safe_hyperlink_url(lk.url)) is not None
            ]
            if valid_links:
                lp = doc.add_paragraph(style="List Bullet")
                lp.paragraph_format.space_after = Pt(2.5)
                rb = lp.add_run(f"{labels['links']}: ")
                rb.bold = True
                rb.font.name = spec.docx_font_family
                rb.font.size = Pt(spec.body_pt)
                rb.font.color.rgb = _rgb(spec.heading_hex)
                for idx, (lbl, url) in enumerate(valid_links):
                    if idx > 0:
                        sep = lp.add_run(" · ")
                        sep.font.name = spec.docx_font_family
                        sep.font.size = Pt(spec.body_pt)
                    _add_hyperlink(lp, lbl, url, spec, spec.body_pt)

    if content.education:
        _add_section_heading(doc, labels["education"], spec)
        for edu in content.education:
            extras = [p for p in [edu.current_semester, edu.period_label, edu.field_of_study] if p]
            suffix = f" — {edu.institution} ({edu.status_label})"
            if extras:
                suffix += f" · {' · '.join(extras)}"
            _add_bullet_paragraph(doc, suffix, spec, bold_prefix=edu.course)

    if content.skills:
        _add_section_heading(doc, labels["skills"], spec)
        for category, items in group_skills_by_category(content.skills).items():
            formatted = ", ".join(f"{it.name} ({it.proficiency_label})" for it in items)
            _add_bullet_paragraph(doc, formatted, spec, bold_prefix=f"{category}: ")

    if content.languages:
        _add_section_heading(doc, labels["languages"], spec)
        for lang_item in content.languages:
            cefr = f" · {lang_item.cefr_level}" if lang_item.cefr_level else ""
            _add_bullet_paragraph(
                doc,
                f"{lang_item.proficiency_label}{cefr}",
                spec,
                bold_prefix=f"{lang_item.language_name}: ",
            )

    _add_manual_notes(doc, content.manual_notes, spec, labels)


def _render_cover_letter_docx(
    doc: docx.Document,
    content: CoverLetterStructuredContent,
    spec: TemplateVisualSpec,
    labels: dict[str, str],
) -> None:
    _add_header_block(doc, content.header, spec, labels["default_cover_letter_title"])

    rp = _add_body_paragraph(doc, content.recipient_line.text, spec, space_after_pt=6.0, muted=True)
    rp.paragraph_format.keep_with_next = True

    gp = _add_body_paragraph(doc, content.greeting.text, spec, space_after_pt=6.0)
    gp.paragraph_format.keep_with_next = True

    _add_body_paragraph(doc, content.opening.text, spec, space_after_pt=6.0)

    if content.relevance_highlights:
        _add_section_heading(doc, labels["relevant_experience"], spec)
        for block in content.relevance_highlights:
            _add_bullet_paragraph(doc, block.summary_text, spec, bold_prefix=f"{block.title}: ")

    if content.opportunity_alignment:
        _add_section_heading(doc, labels["opportunity_alignment"], spec)
        _add_body_paragraph(doc, content.opportunity_alignment.text, spec, space_after_pt=6.0)

    closing_p = _add_body_paragraph(doc, content.closing.text, spec, space_after_pt=4.0)
    closing_p.paragraph_format.space_before = Pt(6.0)
    closing_p.paragraph_format.keep_together = True

    _add_manual_notes(doc, content.manual_notes, spec, labels)


def _render_recruiter_message_docx(
    doc: docx.Document,
    content: RecruiterMessageStructuredContent,
    spec: TemplateVisualSpec,
    labels: dict[str, str],
) -> None:
    channel_key = f"channel_{content.channel}"
    channel_label = labels.get(channel_key, content.channel)

    tp = doc.add_paragraph()
    tp.paragraph_format.space_after = Pt(6.0)
    tp.paragraph_format.keep_with_next = True
    r_title = tp.add_run(format_section_heading(labels["default_recruiter_title"], spec))
    r_title.bold = True
    r_title.font.name = spec.docx_font_family
    r_title.font.size = Pt(spec.title_pt + 2)
    r_title.font.color.rgb = _rgb(spec.heading_hex)
    r_chan = tp.add_run(f"  ·  {labels['channel']}: {channel_label}")
    r_chan.font.name = spec.docx_font_family
    r_chan.font.size = Pt(spec.meta_pt)
    r_chan.font.color.rgb = _rgb(spec.muted_hex)
    if spec.show_section_rule:
        _set_paragraph_bottom_border(tp, spec.divider_hex)

    if content.channel == "email" and content.subject:
        tbl = doc.add_table(rows=1, cols=1)
        cell = tbl.cell(0, 0)
        _set_cell_shading(cell, spec.table_header_bg_hex)
        _set_row_cant_split(tbl.rows[0])
        sp = cell.paragraphs[0]
        sp.paragraph_format.space_after = Pt(2)
        rb = sp.add_run(f"{labels['email_subject']}: ")
        rb.bold = True
        rb.font.name = spec.docx_font_family
        rb.font.size = Pt(spec.subheading_pt)
        rb.font.color.rgb = _rgb(spec.heading_hex)
        rs = sp.add_run(format_docx_text(content.subject.text))
        rs.bold = True
        rs.font.name = spec.docx_font_family
        rs.font.size = Pt(spec.subheading_pt)
        rs.font.color.rgb = _rgb(spec.text_hex)
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(4)

    gp = _add_body_paragraph(doc, content.greeting.text, spec, space_after_pt=5.0)
    gp.paragraph_format.keep_with_next = True
    _add_body_paragraph(doc, content.body.text, spec, space_after_pt=6.0)
    sign_p = _add_body_paragraph(doc, content.sign_off.text, spec, space_after_pt=4.0)
    sign_p.paragraph_format.keep_together = True

    _add_manual_notes(doc, content.manual_notes, spec, labels)


def _render_freelance_proposal_docx(
    doc: docx.Document,
    content: FreelanceProposalStructuredContent,
    spec: TemplateVisualSpec,
    labels: dict[str, str],
) -> None:
    _add_header_block(doc, content.header, spec, labels["default_proposal_title"])
    _add_body_paragraph(doc, content.introduction.text, spec, space_after_pt=5.0)

    _add_section_heading(doc, labels["project_understanding"], spec)
    _add_body_paragraph(doc, content.project_understanding.text, spec)

    if content.relevant_evidence:
        _add_section_heading(doc, labels["relevant_experience"], spec)
        for block in content.relevant_evidence:
            _add_bullet_paragraph(doc, block.summary_text, spec, bold_prefix=f"{block.title}: ")

    _add_section_heading(doc, labels["suggested_approach"], spec)
    _add_body_paragraph(doc, content.suggested_approach.text, spec)

    provided_fields = [
        f for f in content.pending_fields if f.status == "provided" and f.user_value and f.user_value.strip()
    ]
    if provided_fields:
        _add_section_heading(doc, labels["commercial_terms"], spec)
        tbl = doc.add_table(rows=1 + len(provided_fields), cols=2)
        tbl.autofit = False
        col_widths = (Mm(62), Mm(108))
        header_row = tbl.rows[0]
        _set_row_tbl_header(header_row)
        _set_row_cant_split(header_row)
        for idx, col_title in enumerate((labels["term_column"], labels["value_column"])):
            cell = header_row.cells[idx]
            cell.width = col_widths[idx]
            _set_cell_shading(cell, spec.table_header_bg_hex)
            hp = cell.paragraphs[0]
            hp.paragraph_format.space_after = Pt(2)
            hr = hp.add_run(col_title)
            hr.bold = True
            hr.font.name = spec.docx_font_family
            hr.font.size = Pt(spec.body_pt)
            hr.font.color.rgb = _rgb(spec.heading_hex)

        for r_idx, field in enumerate(provided_fields, start=1):
            row = tbl.rows[r_idx]
            _set_row_cant_split(row)
            c0, c1 = row.cells[0], row.cells[1]
            c0.width, c1.width = col_widths[0], col_widths[1]
            p0 = c0.paragraphs[0]
            p0.paragraph_format.space_after = Pt(2)
            r0 = p0.add_run(format_docx_text(field.label))
            r0.bold = True
            r0.font.name = spec.docx_font_family
            r0.font.size = Pt(spec.body_pt)
            r0.font.color.rgb = _rgb(spec.heading_hex)

            p1 = c1.paragraphs[0]
            p1.paragraph_format.space_after = Pt(2)
            r1 = p1.add_run(format_docx_text(field.user_value or ""))
            r1.font.name = spec.docx_font_family
            r1.font.size = Pt(spec.body_pt)
            r1.font.color.rgb = _rgb(spec.text_hex)

        sp_after = doc.add_paragraph()
        sp_after.paragraph_format.space_after = Pt(3)

    if content.alignment_points and content.alignment_points.text.strip():
        _add_section_heading(doc, labels["alignment_closing"], spec)
        _add_body_paragraph(doc, content.alignment_points.text, spec)

    closing_p = _add_body_paragraph(doc, content.closing.text, spec, space_after_pt=4.0)
    closing_p.paragraph_format.space_before = Pt(6.0)
    closing_p.paragraph_format.keep_together = True

    _add_manual_notes(doc, content.manual_notes, spec, labels)


def _render_application_answers_docx(
    doc: docx.Document,
    content: ApplicationAnswersStructuredContent,
    spec: TemplateVisualSpec,
    labels: dict[str, str],
) -> None:
    tp = doc.add_paragraph()
    tp.paragraph_format.space_after = Pt(6.0)
    tp.paragraph_format.keep_with_next = True
    r = tp.add_run(format_section_heading(labels["default_answers_title"], spec))
    r.bold = True
    r.font.name = spec.docx_font_family
    r.font.size = Pt(spec.title_pt + 2)
    r.font.color.rgb = _rgb(spec.heading_hex)
    if spec.show_section_rule:
        _set_paragraph_bottom_border(tp, spec.divider_hex)

    for idx, item in enumerate(content.items, start=1):
        qp = doc.add_paragraph()
        qp.paragraph_format.space_before = Pt(6.0)
        qp.paragraph_format.space_after = Pt(2.5)
        qp.paragraph_format.keep_with_next = True
        qr = qp.add_run(format_docx_text(f"{idx}. {item.question}"))
        qr.bold = True
        qr.font.name = spec.docx_font_family
        qr.font.size = Pt(spec.subheading_pt)
        qr.font.color.rgb = _rgb(spec.heading_hex)

        if item.answer_text:
            _add_body_paragraph(doc, item.answer_text, spec, space_after_pt=2.0)
        if item.evidence_notes:
            _add_body_paragraph(
                doc,
                f"{labels['fact_evidence_note']}: {'; '.join(item.evidence_notes)}",
                spec,
                space_after_pt=4.0,
                italic=True,
                muted=True,
            )

    _add_manual_notes(doc, content.manual_notes, spec, labels)


def _normalize_docx_zip_timestamps(raw_bytes: bytes, stamp: datetime | None) -> bytes:
    """Garante reprodutibilidade binária fixando datas das entradas ZIP pela data da versão."""
    dt = (stamp or datetime(2026, 1, 1, tzinfo=timezone.utc)).astimezone(timezone.utc)
    zip_dt = (max(1980, dt.year), dt.month, dt.day, dt.hour, dt.minute, dt.second - (dt.second % 2))
    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zin, zipfile.ZipFile(
        out_buf, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for info in sorted(zin.infolist(), key=lambda i: i.filename):
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=zip_dt)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.external_attr = info.external_attr
            zout.writestr(new_info, zin.read(info.filename))
    return out_buf.getvalue()


def export_material_to_docx(
    structured: AnyMaterialStructuredContent,
    *,
    spec: TemplateVisualSpec,
    language: TargetLanguage,
    document_title: str,
    is_draft: bool,
    version_created_at: datetime | None,
    version_updated_at: datetime | None,
) -> bytes:
    """Gera documento DOCX profissional e determinístico em memória (io.BytesIO)."""
    labels = get_document_labels(language)
    doc = docx.Document()
    _configure_document_base(
        doc,
        spec,
        labels,
        language,
        title=document_title,
        is_draft=is_draft,
        created_at=version_created_at,
        updated_at=version_updated_at,
    )

    if isinstance(structured, ResumeStructuredContent):
        _render_resume_docx(doc, structured, spec, labels, language)
    elif isinstance(structured, CoverLetterStructuredContent):
        _render_cover_letter_docx(doc, structured, spec, labels)
    elif isinstance(structured, RecruiterMessageStructuredContent):
        _render_recruiter_message_docx(doc, structured, spec, labels)
    elif isinstance(structured, FreelanceProposalStructuredContent):
        _render_freelance_proposal_docx(doc, structured, spec, labels)
    elif isinstance(structured, ApplicationAnswersStructuredContent):
        _render_application_answers_docx(doc, structured, spec, labels)
    else:
        raise ValueError("Estrutura de material não suportada para exportação DOCX.")

    raw_buf = io.BytesIO()
    doc.save(raw_buf)
    return _normalize_docx_zip_timestamps(raw_buf.getvalue(), version_updated_at or version_created_at)
