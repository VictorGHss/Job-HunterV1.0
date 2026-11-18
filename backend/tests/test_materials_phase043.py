"""Suíte completa da Subfase 04.3 — Exportação Profissional em PDF e DOCX."""
from __future__ import annotations

import io
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote

import docx
import pypdf
import pytest
from sqlalchemy.orm import Session

from app.models.material import (
    ApplicationMaterial,
    ApplicationMaterialVersion,
    MaterialType,
    MaterialVersionOrigin,
)
from app.models.profile import ProfessionalProject, VerificationStatus
from app.services.materials.export import document_validation
from app.services.materials.export.document_validation import (
    MAX_EXPORT_INPUT_CHARS,
    build_safe_filename,
)
from tests.test_materials_phase041 import (
    _create_application,
    _create_confirmed_rich_profile,
    _create_opportunity,
    _csrf_headers,
    _seed_user_and_csrf,
)


def _extract_pdf_text_and_links(pdf_bytes: bytes) -> tuple[list[str], list[str]]:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages_text: list[str] = []
    uris: list[str] = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
        annots = page.get("/Annots") or []
        for annot_ref in annots:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") == "/Link":
                action = annot.get("/A")
                if action and "/URI" in action:
                    uris.append(str(action["/URI"]))
    return pages_text, uris


def _extract_docx_text_and_links(docx_bytes: bytes) -> tuple[str, list[str], str]:
    document = docx.Document(io.BytesIO(docx_bytes))
    chunks: list[str] = []
    for p in document.paragraphs:
        if p.text:
            chunks.append(p.text)
    for tbl in document.tables:
        for row in tbl.rows:
            chunks.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
    hdr_chunks = [p.text for p in document.sections[0].header.paragraphs if p.text]
    ftr_chunks = [p.text for p in document.sections[0].footer.paragraphs if p.text]
    links: list[str] = []
    for rel in document.part.rels.values():
        if rel.reltype == docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK:
            links.append(rel.target_ref)
    return "\n".join(chunks), links, "\n".join(hdr_chunks + ftr_chunks)


def _create_and_approve(
    client,
    csrf: str,
    payload: dict,
) -> tuple[dict, str, str]:
    created = client.post("/api/v1/materials", json=payload, headers=_csrf_headers(csrf))
    assert created.status_code == 201, created.text
    mat = created.json()
    ver_id = mat["versions"][0]["id"]
    approved = client.post(
        f"/api/v1/materials/{mat['id']}/versions/{ver_id}/approve",
        headers=_csrf_headers(csrf),
    )
    assert approved.status_code == 200, approved.text
    return approved.json(), mat["id"], ver_id


def test_tc43_01_07_resume_pdf_docx_templates_and_links(
    make_client,
    db_session: Session,
):
    """TC-43-01 e TC-43-07: currículo PDF/DOCX nos dois templates preserva seções, separação Experiência/Projeto e links."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_resume@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session, title="Desenvolvedor Python Júnior", company_name="Orbit Cloud")

    _, mat_id, ver_id = _create_and_approve(
        client,
        csrf,
        {
            "opportunity_id": str(opp.id),
            "material_type": "resume",
            "target_language": "pt-BR",
        },
    )

    for tpl in ("classic_ats", "modern_minimal"):
        pdf_resp = client.get(
            f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf&template={tpl}"
        )
        assert pdf_resp.status_code == 200, pdf_resp.text
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert pdf_resp.content.startswith(b"%PDF-")
        pages_text, uris = _extract_pdf_text_and_links(pdf_resp.content)
        full_pdf_text = "\n".join(pages_text)
        assert "Victor Silva" in full_pdf_text
        assert "Job Hunter Engine" in full_pdf_text
        assert "Analista de Suporte Técnico" in full_pdf_text
        assert "Em andamento" in full_pdf_text or "em andamento" in full_pdf_text.lower()
        assert "https://github.com/victorsilva" in uris
        assert "https://www.linkedin.com/in/victorsilva" in uris
        assert "RASCUNHO" not in full_pdf_text
        # Uma página única não deve imprimir 'Página 1 de 1'
        if len(pages_text) == 1:
            assert "Página 1 de 1" not in full_pdf_text

        docx_resp = client.get(
            f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=docx&template={tpl}"
        )
        assert docx_resp.status_code == 200, docx_resp.text
        assert docx_resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert docx_resp.content.startswith(b"PK\x03\x04")
        docx_text, docx_links, hdr_ftr = _extract_docx_text_and_links(docx_resp.content)
        assert "Victor Silva" in docx_text
        assert "Job Hunter Engine" in docx_text
        assert "https://github.com/victorsilva" in docx_links
        assert "RASCUNHO" not in hdr_ftr


def test_tc43_02_03_04_05_all_other_material_types_pdf_docx(
    make_client,
    db_session: Session,
):
    """TC-43-02, 03, 04, 05: carta, mensagem (LinkedIn e E-mail), proposta freelance e respostas."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_types@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session, title="Backend Engineer", company_name="Delta Sistemas")

    # 1. Cover letter
    _, cl_id, cl_ver = _create_and_approve(
        client,
        csrf,
        {"opportunity_id": str(opp.id), "material_type": "cover_letter", "target_language": "pt-BR"},
    )
    cl_pdf = client.get(
        f"/api/v1/materials/{cl_id}/versions/{cl_ver}/download?format=pdf&template=modern_minimal"
    )
    cl_docx = client.get(
        f"/api/v1/materials/{cl_id}/versions/{cl_ver}/download?format=docx&template=modern_minimal"
    )
    assert cl_pdf.status_code == 200 and cl_docx.status_code == 200
    cl_pdf_txt, _ = _extract_pdf_text_and_links(cl_pdf.content)
    cl_docx_txt, _, _ = _extract_docx_text_and_links(cl_docx.content)
    assert "Delta Sistemas" in "\n".join(cl_pdf_txt)
    assert "Delta Sistemas" in cl_docx_txt

    # 2. Recruiter message LinkedIn (sem assunto) e E-mail (com assunto)
    _, rm_li_id, rm_li_ver = _create_and_approve(
        client,
        csrf,
        {
            "opportunity_id": str(opp.id),
            "material_type": "recruiter_message",
            "target_language": "pt-BR",
            "writing_options": {"channel": "linkedin"},
        },
    )
    rm_li_pdf = client.get(
        f"/api/v1/materials/{rm_li_id}/versions/{rm_li_ver}/download?format=pdf"
    )
    assert rm_li_pdf.status_code == 200
    li_pages, _ = _extract_pdf_text_and_links(rm_li_pdf.content)
    assert len(li_pages) == 1
    assert "Assunto:" not in li_pages[0]

    _, rm_em_id, rm_em_ver = _create_and_approve(
        client,
        csrf,
        {
            "opportunity_id": str(opp.id),
            "material_type": "recruiter_message",
            "target_language": "en",
            "writing_options": {"channel": "email"},
        },
    )
    rm_em_docx = client.get(
        f"/api/v1/materials/{rm_em_id}/versions/{rm_em_ver}/download?format=docx"
    )
    assert rm_em_docx.status_code == 200
    em_docx_txt, _, _ = _extract_docx_text_and_links(rm_em_docx.content)
    assert "Subject:" in em_docx_txt

    # 3. Freelance proposal (somente campos preenchidos na tabela comercial)
    _, fp_id, fp_ver = _create_and_approve(
        client,
        csrf,
        {
            "opportunity_id": str(opp.id),
            "material_type": "freelance_proposal",
            "target_language": "pt-BR",
            "writing_options": {
                "freelance_inputs": {
                    "availability": "20h semanais",
                    "estimated_delivery": "14 dias corridos",
                    "budget_or_price": "R$ 3.200",
                }
            },
        },
    )
    fp_pdf = client.get(f"/api/v1/materials/{fp_id}/versions/{fp_ver}/download?format=pdf")
    fp_docx = client.get(f"/api/v1/materials/{fp_id}/versions/{fp_ver}/download?format=docx")
    assert fp_pdf.status_code == 200 and fp_docx.status_code == 200
    fp_pdf_txt, _ = _extract_pdf_text_and_links(fp_pdf.content)
    fp_docx_txt, _, _ = _extract_docx_text_and_links(fp_docx.content)
    fp_pdf_full = "\n".join(fp_pdf_txt)
    assert "R$ 3.200" in fp_pdf_full
    assert "R$ 3.200" in fp_docx_txt
    assert "\nbullet\n" not in fp_pdf_full
    # Na tabela comercial do DOCX devem existir apenas cabeçalho + 3 campos preenchidos (sem campos vazios)
    fp_doc = docx.Document(io.BytesIO(fp_docx.content))
    assert len(fp_doc.tables) == 1
    assert len(fp_doc.tables[0].rows) == 4
    table_text = "\n".join(cell.text for row in fp_doc.tables[0].rows for cell in row.cells)
    assert "Dúvidas de Escopo" not in table_text

    # 4. Application answers
    _, qa_id, qa_ver = _create_and_approve(
        client,
        csrf,
        {
            "opportunity_id": str(opp.id),
            "material_type": "application_answers",
            "target_language": "pt-BR",
            "writing_options": {
                "questions": ["Você já trabalhou com Python e FastAPI?"]
            },
        },
    )
    qa_pdf = client.get(f"/api/v1/materials/{qa_id}/versions/{qa_ver}/download?format=pdf")
    qa_docx = client.get(f"/api/v1/materials/{qa_id}/versions/{qa_ver}/download?format=docx")
    assert qa_pdf.status_code == 200 and qa_docx.status_code == 200
    qa_pdf_txt, _ = _extract_pdf_text_and_links(qa_pdf.content)
    qa_docx_txt, _, _ = _extract_docx_text_and_links(qa_docx.content)
    assert "1. Você já trabalhou com Python e FastAPI?" in "\n".join(qa_pdf_txt)
    assert "1. Você já trabalhou com Python e FastAPI?" in qa_docx_txt


def test_tc43_06_unicode_nfc_xml_operators_and_unsupported_font_glyphs(
    make_client,
    db_session: Session,
):
    """TC-43-06 + edge cases: Unicode NFC/NFD, acentos PT-BR/EN, moedas, < > & C++ C#, XML inválido e emoji fora da fonte."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_unicode@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session, title="C++ & C# Backend", company_name="EuroTech €")

    created = client.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp.id), "material_type": "resume", "target_language": "pt-BR"},
        headers=_csrf_headers(csrf),
    ).json()
    mat_id = created["id"]
    ver_id = created["versions"][0]["id"]

    # Injeta NFD ('Cafe\u0301'), moedas (€ £ R$), operadores (< > & C++ C#), controle XML inválido (\x0b) e emoji 🚀 fora da Liberation Sans
    edited_sc = dict(created["versions"][0]["structured_content"])
    edited_sc["manual_notes"] = [
        {
            "id": "note-uni",
            "title": "Stack & Observações Café\u0301 — R$ 50 > R$ 40 & a < b",
            "content": "Experiência em C++ & C#, valores € 1.200 / £ 950 — atenção: 🚀 entrega ágil.\x0b",
            "source_fact_keys": [],
            "provenance": "user_authored",
        }
    ]
    upd = client.put(
        f"/api/v1/materials/{mat_id}/versions/{ver_id}",
        json={"structured_content": edited_sc},
        headers=_csrf_headers(csrf),
    )
    assert upd.status_code == 200, upd.text
    app = client.post(
        f"/api/v1/materials/{mat_id}/versions/{ver_id}/approve",
        headers=_csrf_headers(csrf),
    )
    assert app.status_code == 200

    pdf_resp = client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf")
    docx_resp = client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=docx")
    assert pdf_resp.status_code == 200, pdf_resp.text
    assert docx_resp.status_code == 200, docx_resp.text

    pdf_pages, _ = _extract_pdf_text_and_links(pdf_resp.content)
    pdf_txt = "\n".join(pdf_pages)
    docx_txt, _, _ = _extract_docx_text_and_links(docx_resp.content)

    for expected in ("Café", "R$ 50 > R$ 40 & a < b", "C++ & C#", "€ 1.200", "£ 950"):
        assert expected in pdf_txt
        assert expected in docx_txt
    # Emoji sem glifo na Liberation Sans deve ser sinalizado explicitamente sem apagar o texto vizinho
    assert "[U+1F680]" in pdf_txt
    assert "entrega ágil" in pdf_txt


def test_tc43_08_multipage_pagination_no_truncation(
    make_client,
    db_session: Session,
):
    """TC-43-08: documento longo gera múltiplas páginas, exibe 'Página X de Y' e não trunca conteúdo."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_pages@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session)

    created = client.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp.id), "material_type": "resume", "target_language": "pt-BR"},
        headers=_csrf_headers(csrf),
    ).json()
    mat_id = created["id"]
    ver_id = created["versions"][0]["id"]

    long_notes = [
        {
            "id": f"n-{i}",
            "title": f"Bloco Detalhado {i}",
            "content": f"Registro técnico extenso número {i}: " + ("Arquitetura distribuída com observabilidade. " * 22),
            "source_fact_keys": [],
            "provenance": "user_authored",
        }
        for i in range(1, 10)
    ]
    edited_sc = dict(created["versions"][0]["structured_content"])
    edited_sc["manual_notes"] = long_notes
    upd = client.put(
        f"/api/v1/materials/{mat_id}/versions/{ver_id}",
        json={"structured_content": edited_sc},
        headers=_csrf_headers(csrf),
    )
    assert upd.status_code == 200
    assert (
        client.post(
            f"/api/v1/materials/{mat_id}/versions/{ver_id}/approve",
            headers=_csrf_headers(csrf),
        ).status_code
        == 200
    )

    pdf_resp = client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf")
    assert pdf_resp.status_code == 200
    pages_text, _ = _extract_pdf_text_and_links(pdf_resp.content)
    total = len(pages_text)
    assert total >= 2
    assert f"Página 1 de {total}" in pages_text[0]
    assert f"Página {total} de {total}" in pages_text[-1]
    full_txt = "\n".join(pages_text)
    assert "Registro técnico extenso número 1" in full_txt
    assert "Registro técnico extenso número 9" in full_txt


def test_tc43_09_10_approval_draft_and_pending_blocking_policy(
    make_client,
    db_session: Session,
):
    """TC-43-09 e TC-43-10: política de aprovação, rascunho em todas as páginas e bloqueio por pendência."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_policy@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session, company_name="Orbit Cloud")

    # 1. Currículo não aprovado sem pendências: allow_draft=false -> 422; allow_draft=true -> rascunho marcado
    res_mat = client.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp.id), "material_type": "resume", "target_language": "pt-BR"},
        headers=_csrf_headers(csrf),
    ).json()
    res_id, res_ver = res_mat["id"], res_mat["versions"][0]["id"]

    blocked_final = client.get(f"/api/v1/materials/{res_id}/versions/{res_ver}/download?format=pdf")
    assert blocked_final.status_code == 422

    draft_pdf = client.get(
        f"/api/v1/materials/{res_id}/versions/{res_ver}/download?format=pdf&allow_draft=true"
    )
    assert draft_pdf.status_code == 200
    assert "-rascunho.pdf" in draft_pdf.headers["content-disposition"]
    draft_pages, _ = _extract_pdf_text_and_links(draft_pdf.content)
    assert all("RASCUNHO NÃO APROVADO" in p for p in draft_pages)

    draft_docx = client.get(
        f"/api/v1/materials/{res_id}/versions/{res_ver}/download?format=docx&allow_draft=true"
    )
    assert draft_docx.status_code == 200
    assert "-rascunho.docx" in draft_docx.headers["content-disposition"]
    _, _, hdr_ftr = _extract_docx_text_and_links(draft_docx.content)
    assert "RASCUNHO NÃO APROVADO" in hdr_ftr

    # Após aprovar, allow_draft=true NÃO deve aplicar marcação nem sufixo de rascunho
    assert (
        client.post(
            f"/api/v1/materials/{res_id}/versions/{res_ver}/approve",
            headers=_csrf_headers(csrf),
        ).status_code
        == 200
    )
    approved_with_flag = client.get(
        f"/api/v1/materials/{res_id}/versions/{res_ver}/download?format=pdf&allow_draft=true"
    )
    assert approved_with_flag.status_code == 200
    assert "-rascunho" not in approved_with_flag.headers["content-disposition"]
    app_pages, _ = _extract_pdf_text_and_links(approved_with_flag.content)
    assert all("RASCUNHO" not in p for p in app_pages)

    # 2. Proposta freelance e respostas com pendências bloqueiam mesmo com allow_draft=true
    fp_mat = client.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp.id), "material_type": "freelance_proposal", "target_language": "pt-BR"},
        headers=_csrf_headers(csrf),
    ).json()
    for fmt in ("pdf", "docx"):
        assert (
            client.get(
                f"/api/v1/materials/{fp_mat['id']}/versions/{fp_mat['versions'][0]['id']}/download?format={fmt}&allow_draft=true"
            ).status_code
            == 422
        )

    qa_mat = client.post(
        "/api/v1/materials",
        json={
            "opportunity_id": str(opp.id),
            "material_type": "application_answers",
            "target_language": "pt-BR",
            "writing_options": {"questions": ["Qual sua pretensão salarial?"]},
        },
        headers=_csrf_headers(csrf),
    ).json()
    assert (
        client.get(
            f"/api/v1/materials/{qa_mat['id']}/versions/{qa_mat['versions'][0]['id']}/download?format=pdf&allow_draft=true"
        ).status_code
        == 422
    )


def test_tc43_11_12_historical_snapshot_linked_version_and_determinism(
    make_client,
    db_session: Session,
):
    """TC-43-11 e TC-43-12: v1 histórica exportada após edição no perfil permanece idêntica + determinismo."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_hist@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session, company_name="Orbit Cloud")
    app = _create_application(db_session, user.id, opp)

    _, mat_id, v1_id = _create_and_approve(
        client,
        csrf,
        {"opportunity_id": str(opp.id), "material_type": "resume", "target_language": "pt-BR"},
    )
    assert (
        client.post(
            f"/api/v1/materials/{mat_id}/link",
            json={"application_id": str(app.id), "version_id": v1_id},
            headers=_csrf_headers(csrf),
        ).status_code
        == 200
    )

    # Exportações repetidas de v1 devem ser bit-a-bit idênticas
    pdf_a = client.get(f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=pdf").content
    pdf_b = client.get(f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=pdf").content
    assert pdf_a == pdf_b
    docx_a = client.get(f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=docx").content
    docx_b = client.get(f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=docx").content
    assert docx_a == docx_b

    # Altera perfil e gera v2 -> v1 vinculada deve permanecer exatamente como era antes
    new_proj = ProfessionalProject(
        user_id=user.id,
        name="NovoProjetoFuturoV2",
        role="Autor",
        description="Projeto adicionado depois da v1 aprovada.",
        technologies=["Go", "Kubernetes"],
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=datetime.now(timezone.utc),
    )
    db_session.add(new_proj)
    db_session.commit()

    regen = client.post(
        f"/api/v1/materials/{mat_id}/regenerate",
        json={},
        headers=_csrf_headers(csrf),
    )
    assert regen.status_code == 201
    v2_id = next(v["id"] for v in regen.json()["versions"] if v["version_number"] == 2)

    # Listagem por application_id deve expor exatamente o version_id vinculado (v1), e não v2
    linked_list = client.get(f"/api/v1/materials?application_id={app.id}").json()
    assert len(linked_list) == 1
    assert linked_list[0]["linked_version_id"] == v1_id
    assert linked_list[0]["linked_version_number"] == 1
    assert linked_list[0]["latest_version_number"] == 2

    v1_pdf_after = client.get(f"/api/v1/materials/{mat_id}/versions/{v1_id}/download?format=pdf").content
    v1_pages, _ = _extract_pdf_text_and_links(v1_pdf_after)
    assert "NovoProjetoFuturoV2" not in "\n".join(v1_pages)
    assert v1_pdf_after == pdf_a

    # E v2 já contém o novo projeto ao exportar como rascunho
    v2_pdf_draft = client.get(
        f"/api/v1/materials/{mat_id}/versions/{v2_id}/download?format=pdf&allow_draft=true"
    ).content
    v2_pages, _ = _extract_pdf_text_and_links(v2_pdf_draft)
    assert "NovoProjetoFuturoV2" in "\n".join(v2_pages)


def test_tc43_13_14_15_idor_malicious_filenames_headers_cors_and_no_pii_logs(
    make_client,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
):
    """TC-43-13, 14, 15: IDOR, nomes maliciosos, CORS expose, headers de segurança e logs sem PII."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "owner_a@example.com")
    user_b, client_b, _ = _seed_user_and_csrf(make_client, db_session, "attacker_b@example.com")
    _create_confirmed_rich_profile(db_session, user_a.id)
    _create_confirmed_rich_profile(db_session, user_b.id)

    opp_a = _create_opportunity(
        db_session,
        title="Backend 🚀",
        company_name="../../etc/passwd\r\nCON",
        owner_user_id=user_a.id,
    )
    _, mat_a_id, ver_a_id = _create_and_approve(
        client_a,
        csrf_a,
        {"opportunity_id": str(opp_a.id), "material_type": "resume", "target_language": "pt-BR"},
    )
    # Outro material de A para validar mistura de material_id vs version_id
    _, mat_a2_id, _ = _create_and_approve(
        client_a,
        csrf_a,
        {"opportunity_id": str(opp_a.id), "material_type": "cover_letter", "target_language": "pt-BR"},
    )

    caplog.set_level(logging.INFO)
    resp_ok = client_a.get(
        f"/api/v1/materials/{mat_a_id}/versions/{ver_a_id}/download?format=pdf",
        headers={"Origin": "http://localhost:5180"},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in resp_ok.headers["cache-control"]
    assert resp_ok.headers["pragma"] == "no-cache"
    assert "content-disposition" in resp_ok.headers.get("access-control-expose-headers", "").lower()

    disp = resp_ok.headers["content-disposition"]
    assert disp.startswith("attachment; ")
    assert ".." not in disp and "/" not in disp and "\\" not in disp and "\r" not in disp and "\n" not in disp
    m_fn = re.search(r'filename="([^"]+)"', disp)
    assert m_fn is not None
    assert m_fn.group(1).endswith(".pdf")

    # Teste direto de build_safe_filename com nomes reservados do Windows
    con_ascii, _ = build_safe_filename(
        material_type="resume",
        language="pt-BR",
        version_number=1,
        export_format="pdf",
        company_name="CON",
        title="CON",
    )
    assert con_ascii.upper() != "CON.PDF"
    assert unquote(disp)

    # IDOR B -> A retorna 404 sem revelar metadados
    idor_b = client_b.get(f"/api/v1/materials/{mat_a_id}/versions/{ver_a_id}/download?format=pdf")
    assert idor_b.status_code == 404
    assert "Victor Silva" not in idor_b.text
    assert "etc/passwd" not in idor_b.text

    # Cruzamento material_a2 + version_a1 retorna 404
    cross_ver = client_a.get(f"/api/v1/materials/{mat_a2_id}/versions/{ver_a_id}/download?format=pdf")
    assert cross_ver.status_code == 404

    # Logs nunca contêm PII
    joined_logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Victor Silva" not in joined_logs
    assert "victor.privado@example.com" not in joined_logs
    assert "+55 11 98888-7777" not in joined_logs


def test_edge_cases_empty_content_malformed_links_limits_and_renderer_errors(
    make_client,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Edge cases 15.11: conteúdo vazio, links inseguros neutralizados, limites 120k/5MiB e erro de biblioteca."""
    user, client, csrf = _seed_user_and_csrf(make_client, db_session, "exp_edge@example.com")
    _create_confirmed_rich_profile(db_session, user.id)
    opp = _create_opportunity(db_session)

    # 1. Material sem conteúdo substantivo inserido diretamente no banco -> 422
    empty_mat = ApplicationMaterial(
        user_id=user.id,
        opportunity_id=opp.id,
        material_type=MaterialType.RESUME.value,
        title="Vazio",
        target_language="pt-BR",
    )
    db_session.add(empty_mat)
    db_session.flush()
    empty_ver = ApplicationMaterialVersion(
        material_id=empty_mat.id,
        version_number=1,
        origin=MaterialVersionOrigin.GENERATED.value,
        structured_content={
            "schema_version": 1,
            "language": "pt-BR",
            "header": {
                "full_name": None,
                "professional_title": None,
                "location_text": None,
                "email": None,
                "phone": None,
                "links": [],
                "source_fact_keys": [],
                "provenance": "user_authored",
            },
            "summary": None,
            "target_alignment": None,
            "experiences": [],
            "projects": [],
            "education": [],
            "skills": [],
            "languages": [],
            "manual_notes": [],
            "has_unverified_manual_edits": False,
        },
        source_facts_snapshot={"schema_version": 1, "facts": {}},
        unconfirmed_warnings=[],
        missing_requirements=[],
        is_approved=True,
        approved_at=datetime.now(timezone.utc),
    )
    db_session.add(empty_ver)
    db_session.commit()
    assert (
        client.get(
            f"/api/v1/materials/{empty_mat.id}/versions/{empty_ver.id}/download?format=pdf"
        ).status_code
        == 422
    )

    # 2. Link malformado/perigoso no JSON salvo -> endpoint bloqueia (422) e renderizadores nunca criam link clicável
    _, mat_id, ver_id = _create_and_approve(
        client,
        csrf,
        {"opportunity_id": str(opp.id), "material_type": "resume", "target_language": "pt-BR"},
    )
    db_ver = db_session.get(ApplicationMaterialVersion, uuid.UUID(ver_id))
    assert db_ver is not None
    orig_sc = dict(db_ver.structured_content)
    bad_sc = dict(orig_sc)
    bad_sc["header"] = dict(orig_sc["header"])
    bad_sc["header"]["links"] = [
        {"label": "Safe", "url": "https://github.com/victorsilva"},
        {"label": "XSS", "url": "javascript:alert(1)"},
        {"label": "LocalSSRF", "url": "http://127.0.0.1:8090/secret"},
    ]
    db_ver.structured_content = bad_sc
    db_session.commit()
    assert (
        client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf").status_code
        == 422
    )
    # Restaura structured_content válido para os checks seguintes via HTTP
    db_ver.structured_content = orig_sc
    db_session.commit()

    # Garante também na camada renderizadora direta (via model_construct) que URLs inseguras são descartadas
    from app.schemas.material import ResumeHeaderSection, ResumeLinkItem, ResumeStructuredContent
    from app.services.materials.export.document_templates import get_template_spec
    from app.services.materials.export.docx_exporter import export_material_to_docx
    from app.services.materials.export.pdf_exporter import export_material_to_pdf

    parsed_ok = ResumeStructuredContent.model_validate(orig_sc)
    untrusted_header = ResumeHeaderSection.model_construct(
        **{
            **parsed_ok.header.model_dump(),
            "links": [
                ResumeLinkItem.model_construct(label="Safe", url="https://github.com/victorsilva"),
                ResumeLinkItem.model_construct(label="XSS", url="javascript:alert(1)"),
                ResumeLinkItem.model_construct(label="LocalSSRF", url="http://127.0.0.1:8090/secret"),
            ],
        }
    )
    untrusted_resume = parsed_ok.model_copy(update={"header": untrusted_header})
    spec = get_template_spec("classic_ats")
    raw_pdf = export_material_to_pdf(
        untrusted_resume,
        spec=spec,
        language="pt-BR",
        document_title="Teste Links",
        is_draft=False,
    )
    raw_docx = export_material_to_docx(
        untrusted_resume,
        spec=spec,
        language="pt-BR",
        document_title="Teste Links",
        is_draft=False,
        version_created_at=db_ver.created_at,
        version_updated_at=db_ver.updated_at,
    )
    _, pdf_uris = _extract_pdf_text_and_links(raw_pdf)
    _, docx_uris, _ = _extract_docx_text_and_links(raw_docx)
    assert "https://github.com/victorsilva" in pdf_uris
    assert "https://github.com/victorsilva" in docx_uris
    assert not any("javascript:" in u.lower() or "127.0.0.1" in u for u in pdf_uris)
    assert not any("javascript:" in u.lower() or "127.0.0.1" in u for u in docx_uris)

    # 3. Limite de entrada > MAX_EXPORT_INPUT_CHARS e limite de saída > MAX_EXPORT_FILE_BYTES
    monkeypatch.setattr(document_validation, "MAX_EXPORT_INPUT_CHARS", 20)
    assert MAX_EXPORT_INPUT_CHARS == 120_000
    assert (
        client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf").status_code
        == 422
    )
    monkeypatch.undo()

    monkeypatch.setattr(document_validation, "MAX_EXPORT_FILE_BYTES", 64)
    assert (
        client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf").status_code
        == 422
    )
    monkeypatch.undo()

    # 4. Falha inesperada no exportador -> 500 genérico sem vazar conteúdo pessoal
    from app.services.materials.export import export_service

    def _boom(*_args, **_kwargs):
        raise RuntimeError("Erro interno simulado Victor Silva")

    monkeypatch.setattr(export_service, "export_material_to_pdf", _boom)
    err_resp = client.get(f"/api/v1/materials/{mat_id}/versions/{ver_id}/download?format=pdf")
    assert err_resp.status_code == 500
    assert "Victor Silva" not in err_resp.text
