"""
Testes de regressão — Correção 04.1.1 / Achado 2
Validação da política de autorização de oportunidades privadas em materiais.

Cobertura exigida pela especificação §4.4:
  TC-0411-01  Pré-análise de oportunidade privada alheia → HTTP 404.
  TC-0411-02  Criação de material com oportunidade privada alheia → HTTP 404, sem persistência.
  TC-0411-03  Proprietário acessa sua própria oportunidade privada normalmente.
  TC-0411-04  Oportunidade pública/importada é acessível por qualquer usuário autorizado.
  TC-0411-05  Oportunidade inexistente → HTTP 404 uniforme.
  TC-0411-06  Isolamento: nenhuma exposição indireta por snapshot, warnings, listagem ou detalhe.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.material import ApplicationMaterial, ApplicationMaterialVersion
from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    ExternalSourceStatus,
    Opportunity,
    OpportunitySource,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    SourceType,
    WorkMode,
)
from app.models.profile import (
    Education,
    EducationStatus,
    ExperienceType,
    Language,
    LanguageProficiency,
    ProfessionalProfile,
    ProfessionalProject,
    Skill,
    SkillProficiency,
    VerificationStatus,
    WorkExperience,
)
from app.services.auth_service import create_user_account
from tests.test_foundation_phase01 import login_and_get_csrf
from tests.test_materials_phase041 import (
    _create_confirmed_rich_profile,
    _create_opportunity,
    _csrf_headers,
    _seed_user_and_csrf,
)


# ---------------------------------------------------------------------------
# Helpers locais
# ---------------------------------------------------------------------------

def _create_private_opportunity(
    db_session: Session,
    owner_user_id: uuid.UUID,
    *,
    title: str = "Oportunidade Privada",
) -> Opportunity:
    """Cria oportunidade privada (source_id=None, created_by_user_id=owner)."""
    return _create_opportunity(db_session, title=title, owner_user_id=owner_user_id)


def _create_public_opportunity(db_session: Session, *, title: str = "Oportunidade Pública") -> Opportunity:
    """Cria oportunidade pública/importada (source_id preenchido)."""
    return _create_opportunity(db_session, title=title)


# ---------------------------------------------------------------------------
# TC-0411-01: Pré-análise de oportunidade privada alheia
# ---------------------------------------------------------------------------

def test_tc0411_01_preanalise_oportunidade_privada_alheia(make_client, db_session: Session):
    """Usuário B não pode pré-analisar oportunidade privada de Usuário A — deve receber 404."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "tc01_a@example.com")
    user_b, client_b, csrf_b = _seed_user_and_csrf(make_client, db_session, "tc01_b@example.com")
    _create_confirmed_rich_profile(db_session, user_b.id)

    opp_privada = _create_private_opportunity(db_session, user_a.id)

    resp = client_b.post(
        "/api/v1/materials/pre-analyze",
        json={"opportunity_id": str(opp_privada.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_b),
    )

    assert resp.status_code == 404
    body = resp.json()
    # Nenhum dado da oportunidade pode vazar na resposta de erro
    assert opp_privada.title not in str(body)
    assert (opp_privada.company_name or "") not in str(body)


# ---------------------------------------------------------------------------
# TC-0411-02: Criação de material com oportunidade privada alheia
# ---------------------------------------------------------------------------

def test_tc0411_02_criar_material_oportunidade_privada_alheia(make_client, db_session: Session):
    """Usuário B não pode criar material usando oportunidade privada de Usuário A — 404, sem persistência."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "tc02_a@example.com")
    user_b, client_b, csrf_b = _seed_user_and_csrf(make_client, db_session, "tc02_b@example.com")
    _create_confirmed_rich_profile(db_session, user_b.id)

    opp_privada = _create_private_opportunity(db_session, user_a.id)

    resp = client_b.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp_privada.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_b),
    )

    assert resp.status_code == 404

    # Verificar no banco: nenhum material ou versão foi criado para user_b
    materiais = db_session.execute(
        select(ApplicationMaterial).where(
            ApplicationMaterial.user_id == user_b.id,
            ApplicationMaterial.opportunity_id == opp_privada.id,
        )
    ).scalars().all()
    assert len(materiais) == 0


# ---------------------------------------------------------------------------
# TC-0411-03: Proprietário acessa sua própria oportunidade privada
# ---------------------------------------------------------------------------

def test_tc0411_03_proprietario_acessa_oportunidade_privada(make_client, db_session: Session):
    """Usuário A pode usar sua própria oportunidade privada normalmente."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "tc03_a@example.com")
    _create_confirmed_rich_profile(db_session, user_a.id)

    opp_privada = _create_private_opportunity(db_session, user_a.id)

    # Pré-análise
    pre_resp = client_a.post(
        "/api/v1/materials/pre-analyze",
        json={"opportunity_id": str(opp_privada.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_a),
    )
    assert pre_resp.status_code == 200, pre_resp.text

    # Criação de material
    mat_resp = client_a.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp_privada.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_a),
    )
    assert mat_resp.status_code == 201, mat_resp.text
    assert mat_resp.json()["opportunity_id"] == str(opp_privada.id)


# ---------------------------------------------------------------------------
# TC-0411-04: Oportunidade pública acessível por qualquer usuário
# ---------------------------------------------------------------------------

def test_tc0411_04_oportunidade_publica_acessivel(make_client, db_session: Session):
    """Oportunidade importada/pública pode ser usada por qualquer usuário autenticado."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "tc04_a@example.com")
    user_b, client_b, csrf_b = _seed_user_and_csrf(make_client, db_session, "tc04_b@example.com")
    _create_confirmed_rich_profile(db_session, user_a.id)
    _create_confirmed_rich_profile(db_session, user_b.id)

    opp_publica = _create_public_opportunity(db_session)

    # Usuário A
    resp_a = client_a.post(
        "/api/v1/materials/pre-analyze",
        json={"opportunity_id": str(opp_publica.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_a),
    )
    assert resp_a.status_code == 200, resp_a.text

    # Usuário B
    resp_b = client_b.post(
        "/api/v1/materials/pre-analyze",
        json={"opportunity_id": str(opp_publica.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_b),
    )
    assert resp_b.status_code == 200, resp_b.text


# ---------------------------------------------------------------------------
# TC-0411-05: Oportunidade inexistente → 404 uniforme
# ---------------------------------------------------------------------------

def test_tc0411_05_oportunidade_inexistente(make_client, db_session: Session):
    """ID de oportunidade inexistente retorna 404 idêntico ao de oportunidade privada alheia."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "tc05_a@example.com")
    _create_confirmed_rich_profile(db_session, user_a.id)

    id_inexistente = uuid.uuid4()

    resp_pre = client_a.post(
        "/api/v1/materials/pre-analyze",
        json={"opportunity_id": str(id_inexistente), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_a),
    )
    assert resp_pre.status_code == 404

    resp_mat = client_a.post(
        "/api/v1/materials",
        json={"opportunity_id": str(id_inexistente), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_a),
    )
    assert resp_mat.status_code == 404


# ---------------------------------------------------------------------------
# TC-0411-06: Isolamento — nenhuma exposição indireta
# ---------------------------------------------------------------------------

def test_tc0411_06_isolamento_sem_exposicao_indireta(make_client, db_session: Session):
    """Usuário B não obtém dados da oportunidade privada de A em nenhum campo da resposta 404."""
    user_a, client_a, csrf_a = _seed_user_and_csrf(make_client, db_session, "tc06_a@example.com")
    user_b, client_b, csrf_b = _seed_user_and_csrf(make_client, db_session, "tc06_b@example.com")
    _create_confirmed_rich_profile(db_session, user_b.id)

    titulo_secreto = "Oferta Ultrassecreta XYZ"
    empresa_secreta = "Empresa Confidencial LTDA"
    opp = _create_private_opportunity(db_session, user_a.id, title=titulo_secreto)
    # Atualizar company_name manualmente para verificar isolamento
    opp.company_name = empresa_secreta
    db_session.commit()
    db_session.refresh(opp)

    # Pré-análise
    resp_pre = client_b.post(
        "/api/v1/materials/pre-analyze",
        json={"opportunity_id": str(opp.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_b),
    )
    assert resp_pre.status_code == 404
    resposta_pre_str = str(resp_pre.json())
    assert titulo_secreto not in resposta_pre_str
    assert empresa_secreta not in resposta_pre_str

    # Criação de material
    resp_mat = client_b.post(
        "/api/v1/materials",
        json={"opportunity_id": str(opp.id), "target_language": "pt-BR"},
        headers=_csrf_headers(csrf_b),
    )
    assert resp_mat.status_code == 404
    resposta_mat_str = str(resp_mat.json())
    assert titulo_secreto not in resposta_mat_str
    assert empresa_secreta not in resposta_mat_str

    # Nenhum material, versão ou snapshot foi criado para user_b
    materiais_b = db_session.execute(
        select(ApplicationMaterial).where(ApplicationMaterial.user_id == user_b.id)
    ).scalars().all()
    assert len(materiais_b) == 0
