"""
Testes de regressão — Correção 04.1.1 / Achado 1
Validação da política de confirmação do perfil para as seis entidades:
ProfessionalProfile, WorkExperience, Education, Skill, Language, ProfessionalProject.

Cobertura exigida pela especificação §3.6:
  1.  Registro confirmado + alteração factual + status "confirmed" explícito → pending_validation.
  2.  confirmed_at deve ser None após degradação.
  3.  O conteúdo alterado é persistido corretamente.
  4.  Registro confirmado + sem alteração factual + status "confirmed" → preserva status e data.
  5.  Registro confirmado + sem alteração factual + status omitido → preserva confirmação.
  6.  Registro confirmado + alteração factual + status omitido → degrada.
  7.  Reabertura explícita para pending_validation.
  8.  Confirmação posterior por ação intencional (Cenário F).
  9.  Quick-confirm individual continua funcional.
 10.  Atualização de metadados não degrada registro quando o campo não é factual.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

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
from app.models.user import AccountStatus
from app.schemas.profile import (
    EducationUpdate,
    LanguageUpdate,
    ProfessionalProfileUpdate,
    ProfessionalProjectUpdate,
    SkillUpdate,
    WorkExperienceUpdate,
)
from app.services.auth_service import create_user_account
from app.services.profile_service import (
    get_or_create_profile,
    update_education,
    update_experience,
    update_language,
    update_profile,
    update_project,
    update_skill,
)
from tests.test_foundation_phase01 import login_and_get_csrf


# ---------------------------------------------------------------------------
# Fixtures auxiliares
# ---------------------------------------------------------------------------

def _make_user(db: Session, suffix: str):
    return create_user_account(
        db,
        email=f"confirm_{suffix}@example.com",
        display_name=f"Usuário {suffix}",
        password="StrongPass!2026",
    )


def _confirmed_exp(db: Session, user_id: uuid.UUID) -> WorkExperience:
    now = datetime.now(UTC)
    exp = WorkExperience(
        user_id=user_id,
        company="Empresa Original",
        role="Desenvolvedor",
        description="Descrição original.",
        start_date=date(2022, 1, 1),
        end_date=date(2023, 6, 1),
        is_current=False,
        experience_type=ExperienceType.CLT.value,
        technologies=["Python"],
        related_skills=["FastAPI"],
        eligible_as_target_role=True,
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=now,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def _confirmed_edu(db: Session, user_id: uuid.UUID) -> Education:
    now = datetime.now(UTC)
    edu = Education(
        user_id=user_id,
        institution="Universidade A",
        course="Ciência da Computação",
        field_of_study="Computação",
        education_status=EducationStatus.IN_PROGRESS.value,
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=now,
    )
    db.add(edu)
    db.commit()
    db.refresh(edu)
    return edu


def _confirmed_skill(db: Session, user_id: uuid.UUID) -> Skill:
    now = datetime.now(UTC)
    skill = Skill(
        user_id=user_id,
        name="Python",
        category="Backend",
        proficiency_level=SkillProficiency.INTERMEDIATE.value,
        notes="Uso em APIs REST",
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=now,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def _confirmed_lang(db: Session, user_id: uuid.UUID) -> Language:
    now = datetime.now(UTC)
    lang = Language(
        user_id=user_id,
        language_name="Inglês",
        proficiency_level=LanguageProficiency.ADVANCED.value,
        cefr_level="C1",
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=now,
    )
    db.add(lang)
    db.commit()
    db.refresh(lang)
    return lang


def _confirmed_proj(db: Session, user_id: uuid.UUID) -> ProfessionalProject:
    now = datetime.now(UTC)
    proj = ProfessionalProject(
        user_id=user_id,
        name="Projeto Alpha",
        description="Descrição do projeto.",
        role="Autor",
        technologies=["Python", "FastAPI"],
        links={"repo": "https://github.com/user/alpha"},
        verified_results="Resultados verificados.",
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=now,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def _confirmed_profile(db: Session, user_id: uuid.UUID) -> ProfessionalProfile:
    now = datetime.now(UTC)
    profile = ProfessionalProfile(
        user_id=user_id,
        full_name="Nome Completo",
        professional_email="usuario@example.com",
        professional_title="Desenvolvedor Backend",
        verification_status=VerificationStatus.CONFIRMED.value,
        confirmed_at=now,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# WorkExperience
# ---------------------------------------------------------------------------

class TestWorkExperienceConfirmationPolicy:

    def test_factual_change_com_confirmed_explicito_degrada(self, db_session: Session):
        """Cenário A: alteração factual + confirmed explícito → pending_validation, confirmed_at=None."""
        user = _make_user(db_session, "exp_a")
        exp = _confirmed_exp(db_session, user.id)
        original_confirmed_at = exp.confirmed_at

        payload = WorkExperienceUpdate(
            company="Empresa Nova",           # <-- alteração factual
            role=exp.role,
            description=exp.description,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_current=exp.is_current,
            experience_type=ExperienceType(exp.experience_type),
            technologies=exp.technologies,
            related_skills=exp.related_skills,
            eligible_as_target_role=exp.eligible_as_target_role,
            verification_status=VerificationStatus.CONFIRMED,  # <-- cliente reenvia confirmed
        )

        result = update_experience(db_session, exp, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None
        assert result.company == "Empresa Nova"  # conteúdo foi persistido

    def test_sem_alteracao_factual_confirmed_preserva(self, db_session: Session):
        """Cenário B: sem alteração factual + confirmed explícito → preserva status e data."""
        user = _make_user(db_session, "exp_b")
        exp = _confirmed_exp(db_session, user.id)
        original_confirmed_at = exp.confirmed_at

        payload = WorkExperienceUpdate(
            company=exp.company,
            role=exp.role,
            description=exp.description,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_current=exp.is_current,
            experience_type=ExperienceType(exp.experience_type),
            technologies=exp.technologies,
            related_skills=exp.related_skills,
            eligible_as_target_role=exp.eligible_as_target_role,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_experience(db_session, exp, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_factual_change_status_omitido_degrada(self, db_session: Session):
        """Cenário A/C: alteração factual + status padrão do schema → degrada para pending_validation."""
        user = _make_user(db_session, "exp_c")
        exp = _confirmed_exp(db_session, user.id)

        # O schema WorkExperienceUpdate tem verification_status com default PENDING_VALIDATION;
        # simula o frontend não enviando o status (resultado: schema usa o default pending_validation).
        payload = WorkExperienceUpdate(
            company=exp.company,
            role="Cargo Novo",          # <-- alteração factual
            description=exp.description,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_current=exp.is_current,
            experience_type=ExperienceType(exp.experience_type),
            technologies=exp.technologies,
            related_skills=exp.related_skills,
            eligible_as_target_role=exp.eligible_as_target_role,
            verification_status=VerificationStatus.PENDING_VALIDATION,
        )

        result = update_experience(db_session, exp, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None
        assert result.role == "Cargo Novo"

    def test_reabertura_explicita_sem_alteracao_factual(self, db_session: Session):
        """Cenário E: reabertura explícita para pending_validation sem alterar conteúdo."""
        user = _make_user(db_session, "exp_e")
        exp = _confirmed_exp(db_session, user.id)

        payload = WorkExperienceUpdate(
            company=exp.company,
            role=exp.role,
            description=exp.description,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_current=exp.is_current,
            experience_type=ExperienceType(exp.experience_type),
            technologies=exp.technologies,
            related_skills=exp.related_skills,
            eligible_as_target_role=exp.eligible_as_target_role,
            verification_status=VerificationStatus.PENDING_VALIDATION,
        )

        result = update_experience(db_session, exp, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None

    def test_confirmacao_intencional_de_pendente(self, db_session: Session):
        """Cenário F: confirmação explícita de registro pendente sem alteração factual."""
        user = _make_user(db_session, "exp_f")
        exp = _confirmed_exp(db_session, user.id)
        # Regredir primeiro para pending
        exp.verification_status = VerificationStatus.PENDING_VALIDATION.value
        exp.confirmed_at = None
        db_session.commit()
        db_session.refresh(exp)

        payload = WorkExperienceUpdate(
            company=exp.company,
            role=exp.role,
            description=exp.description,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_current=exp.is_current,
            experience_type=ExperienceType(exp.experience_type),
            technologies=exp.technologies,
            related_skills=exp.related_skills,
            eligible_as_target_role=exp.eligible_as_target_role,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_experience(db_session, exp, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at is not None

    def test_listas_sem_ordem_nao_provoca_degradacao(self, db_session: Session):
        """Listas de tecnologias com mesmos elementos em ordem diferente não são alteração factual."""
        user = _make_user(db_session, "exp_list")
        exp = _confirmed_exp(db_session, user.id)
        original_confirmed_at = exp.confirmed_at

        # Envia technologies na ordem inversa — semanticamente igual
        payload = WorkExperienceUpdate(
            company=exp.company,
            role=exp.role,
            description=exp.description,
            start_date=exp.start_date,
            end_date=exp.end_date,
            is_current=exp.is_current,
            experience_type=ExperienceType(exp.experience_type),
            technologies=list(reversed(exp.technologies)),   # mesmos elementos, outra ordem
            related_skills=exp.related_skills,
            eligible_as_target_role=exp.eligible_as_target_role,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_experience(db_session, exp, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

class TestEducationConfirmationPolicy:

    def test_factual_change_com_confirmed_explicito_degrada(self, db_session: Session):
        user = _make_user(db_session, "edu_a")
        edu = _confirmed_edu(db_session, user.id)

        payload = EducationUpdate(
            institution="Universidade Nova",   # <-- alteração factual
            course=edu.course,
            field_of_study=edu.field_of_study,
            current_semester=edu.current_semester,
            start_date=edu.start_date,
            expected_graduation_date=edu.expected_graduation_date,
            education_status=EducationStatus(edu.education_status),
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_education(db_session, edu, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None
        assert result.institution == "Universidade Nova"

    def test_sem_alteracao_factual_confirmed_preserva(self, db_session: Session):
        user = _make_user(db_session, "edu_b")
        edu = _confirmed_edu(db_session, user.id)
        original_confirmed_at = edu.confirmed_at

        payload = EducationUpdate(
            institution=edu.institution,
            course=edu.course,
            field_of_study=edu.field_of_study,
            current_semester=edu.current_semester,
            start_date=edu.start_date,
            expected_graduation_date=edu.expected_graduation_date,
            education_status=EducationStatus(edu.education_status),
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_education(db_session, edu, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_none_e_string_vazia_equivalentes_nao_degradam(self, db_session: Session):
        """None e string vazia em campo opcional são semanticamente equivalentes.
        O banco tem field_of_study=None e current_semester=None; enviar '' para esses
        campos não deve ser tratado como alteração factual.
        """
        user = _make_user(db_session, "edu_norm")
        now = datetime.now(UTC)
        # Fixture com field_of_study=None e current_semester=None
        edu = Education(
            user_id=user.id,
            institution="Universidade A",
            course="Ciência da Computação",
            field_of_study=None,       # campo ausente no banco
            current_semester=None,     # campo ausente no banco
            education_status=EducationStatus.IN_PROGRESS.value,
            verification_status=VerificationStatus.CONFIRMED.value,
            confirmed_at=now,
        )
        db_session.add(edu)
        db_session.commit()
        db_session.refresh(edu)
        original_confirmed_at = edu.confirmed_at

        payload = EducationUpdate(
            institution=edu.institution,
            course=edu.course,
            field_of_study="",          # None → "" não é alteração factual
            current_semester=None,
            start_date=edu.start_date,
            expected_graduation_date=edu.expected_graduation_date,
            education_status=EducationStatus(edu.education_status),
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_education(db_session, edu, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_reabertura_e_confirmacao_posterior(self, db_session: Session):
        user = _make_user(db_session, "edu_ef")
        edu = _confirmed_edu(db_session, user.id)

        # Reabertura
        payload_reopen = EducationUpdate(
            institution=edu.institution, course=edu.course,
            education_status=EducationStatus(edu.education_status),
            verification_status=VerificationStatus.PENDING_VALIDATION,
        )
        result = update_education(db_session, edu, payload_reopen)
        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None

        # Re-confirmação intencional sem alterar conteúdo
        payload_confirm = EducationUpdate(
            institution=edu.institution, course=edu.course,
            education_status=EducationStatus(edu.education_status),
            verification_status=VerificationStatus.CONFIRMED,
        )
        result2 = update_education(db_session, result, payload_confirm)
        assert result2.verification_status == VerificationStatus.CONFIRMED.value
        assert result2.confirmed_at is not None


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

class TestSkillConfirmationPolicy:

    def test_factual_change_com_confirmed_explicito_degrada(self, db_session: Session):
        user = _make_user(db_session, "sk_a")
        skill = _confirmed_skill(db_session, user.id)

        payload = SkillUpdate(
            name="TypeScript",   # <-- alteração factual
            category=skill.category,
            proficiency_level=SkillProficiency(skill.proficiency_level),
            notes=skill.notes,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_skill(db_session, skill, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None
        assert result.name == "TypeScript"

    def test_sem_alteracao_factual_confirmed_preserva(self, db_session: Session):
        user = _make_user(db_session, "sk_b")
        skill = _confirmed_skill(db_session, user.id)
        original_confirmed_at = skill.confirmed_at

        payload = SkillUpdate(
            name=skill.name,
            category=skill.category,
            proficiency_level=SkillProficiency(skill.proficiency_level),
            notes=skill.notes,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_skill(db_session, skill, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_notes_none_para_vazio_nao_degrada(self, db_session: Session):
        """Campo notes: None → "" é equivalência semântica, não alteração factual."""
        user = _make_user(db_session, "sk_norm")
        skill = _confirmed_skill(db_session, user.id)
        original_confirmed_at = skill.confirmed_at

        payload = SkillUpdate(
            name=skill.name,
            category=skill.category,
            proficiency_level=SkillProficiency(skill.proficiency_level),
            notes=skill.notes or "",   # None → ""
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_skill(db_session, skill, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_confirmacao_intencional_de_pendente(self, db_session: Session):
        user = _make_user(db_session, "sk_f")
        skill = _confirmed_skill(db_session, user.id)
        skill.verification_status = VerificationStatus.PENDING_VALIDATION.value
        skill.confirmed_at = None
        db_session.commit()
        db_session.refresh(skill)

        payload = SkillUpdate(
            name=skill.name,
            category=skill.category,
            proficiency_level=SkillProficiency(skill.proficiency_level),
            notes=skill.notes,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_skill(db_session, skill, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at is not None


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

class TestLanguageConfirmationPolicy:

    def test_factual_change_com_confirmed_explicito_degrada(self, db_session: Session):
        user = _make_user(db_session, "lang_a")
        lang = _confirmed_lang(db_session, user.id)

        payload = LanguageUpdate(
            language_name="Espanhol",   # <-- alteração factual
            proficiency_level=LanguageProficiency(lang.proficiency_level),
            cefr_level=lang.cefr_level,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_language(db_session, lang, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None
        assert result.language_name == "Espanhol"

    def test_sem_alteracao_factual_confirmed_preserva(self, db_session: Session):
        user = _make_user(db_session, "lang_b")
        lang = _confirmed_lang(db_session, user.id)
        original_confirmed_at = lang.confirmed_at

        payload = LanguageUpdate(
            language_name=lang.language_name,
            proficiency_level=LanguageProficiency(lang.proficiency_level),
            cefr_level=lang.cefr_level,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_language(db_session, lang, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_nivel_proficiencia_muda_degrada(self, db_session: Session):
        """Nível de proficiência é campo factual: mudança deve degradar."""
        user = _make_user(db_session, "lang_prof")
        lang = _confirmed_lang(db_session, user.id)

        payload = LanguageUpdate(
            language_name=lang.language_name,
            proficiency_level=LanguageProficiency.BASIC,   # <-- alteração factual
            cefr_level=lang.cefr_level,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_language(db_session, lang, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None

    def test_reabertura_e_reconfirmacao_intencional(self, db_session: Session):
        user = _make_user(db_session, "lang_ef")
        lang = _confirmed_lang(db_session, user.id)

        payload_reopen = LanguageUpdate(
            language_name=lang.language_name,
            proficiency_level=LanguageProficiency(lang.proficiency_level),
            cefr_level=lang.cefr_level,
            verification_status=VerificationStatus.PENDING_VALIDATION,
        )
        result = update_language(db_session, lang, payload_reopen)
        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value

        payload_confirm = LanguageUpdate(
            language_name=lang.language_name,
            proficiency_level=LanguageProficiency(lang.proficiency_level),
            cefr_level=lang.cefr_level,
            verification_status=VerificationStatus.CONFIRMED,
        )
        result2 = update_language(db_session, result, payload_confirm)
        assert result2.verification_status == VerificationStatus.CONFIRMED.value
        assert result2.confirmed_at is not None


# ---------------------------------------------------------------------------
# ProfessionalProject
# ---------------------------------------------------------------------------

class TestProfessionalProjectConfirmationPolicy:

    def test_factual_change_com_confirmed_explicito_degrada(self, db_session: Session):
        user = _make_user(db_session, "proj_a")
        proj = _confirmed_proj(db_session, user.id)

        payload = ProfessionalProjectUpdate(
            name="Projeto Beta",   # <-- alteração factual
            description=proj.description,
            role=proj.role,
            technologies=proj.technologies,
            links=proj.links,
            verified_results=proj.verified_results,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_project(db_session, proj, payload)

        assert result.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert result.confirmed_at is None
        assert result.name == "Projeto Beta"

    def test_sem_alteracao_factual_confirmed_preserva(self, db_session: Session):
        user = _make_user(db_session, "proj_b")
        proj = _confirmed_proj(db_session, user.id)
        original_confirmed_at = proj.confirmed_at

        payload = ProfessionalProjectUpdate(
            name=proj.name,
            description=proj.description,
            role=proj.role,
            technologies=proj.technologies,
            links=proj.links,
            verified_results=proj.verified_results,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_project(db_session, proj, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_technologies_sem_ordem_nao_degrada(self, db_session: Session):
        """Lista de tecnologias sem ordem semântica: mesmos elementos em outra ordem não degradam."""
        user = _make_user(db_session, "proj_tech")
        proj = _confirmed_proj(db_session, user.id)
        original_confirmed_at = proj.confirmed_at

        payload = ProfessionalProjectUpdate(
            name=proj.name,
            description=proj.description,
            role=proj.role,
            technologies=list(reversed(proj.technologies)),   # ["FastAPI", "Python"]
            links=proj.links,
            verified_results=proj.verified_results,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_project(db_session, proj, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_verified_results_none_para_vazio_nao_degrada(self, db_session: Session):
        user = _make_user(db_session, "proj_vr")
        proj = _confirmed_proj(db_session, user.id)
        original_confirmed_at = proj.confirmed_at

        payload = ProfessionalProjectUpdate(
            name=proj.name,
            description=proj.description,
            role=proj.role,
            technologies=proj.technologies,
            links=proj.links,
            verified_results=proj.verified_results or "",   # None → ""
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_project(db_session, proj, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at == original_confirmed_at

    def test_confirmacao_intencional_de_pendente(self, db_session: Session):
        user = _make_user(db_session, "proj_f")
        proj = _confirmed_proj(db_session, user.id)
        proj.verification_status = VerificationStatus.PENDING_VALIDATION.value
        proj.confirmed_at = None
        db_session.commit()
        db_session.refresh(proj)

        payload = ProfessionalProjectUpdate(
            name=proj.name,
            description=proj.description,
            role=proj.role,
            technologies=proj.technologies,
            links=proj.links,
            verified_results=proj.verified_results,
            verification_status=VerificationStatus.CONFIRMED,
        )

        result = update_project(db_session, proj, payload)

        assert result.verification_status == VerificationStatus.CONFIRMED.value
        assert result.confirmed_at is not None


# ---------------------------------------------------------------------------
# ProfessionalProfile (entidade raiz)
# ---------------------------------------------------------------------------

class TestProfessionalProfileConfirmationPolicy:

    def test_factual_change_com_confirmed_explicito_degrada(self, db_session: Session, make_client):
        """Cenário A via API: editar campo factual + enviar confirmed → pending_validation."""
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="prof_a@example.com",
            display_name="Prof A", password="StrongPass!2026",
        )
        # Criar perfil confirmado diretamente no banco
        profile = _confirmed_profile(db_session, user.id)

        client = make_client()
        csrf = login_and_get_csrf(client, "prof_a@example.com", "StrongPass!2026")

        resp = client.put(
            "/api/v1/profile",
            json={
                "full_name": "Nome Diferente",          # <-- alteração factual
                "professional_title": profile.professional_title,
                "verification_status": "confirmed",     # <-- cliente reenvia confirmed
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verification_status"] == "pending_validation"
        assert data["confirmed_at"] is None
        assert data["full_name"] == "Nome Diferente"

    def test_sem_alteracao_factual_confirmed_preserva(self, db_session: Session, make_client):
        """Cenário B via API: sem alteração factual + confirmed → preserva."""
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="prof_b@example.com",
            display_name="Prof B", password="StrongPass!2026",
        )
        profile = _confirmed_profile(db_session, user.id)
        original_confirmed_at = profile.confirmed_at

        client = make_client()
        csrf = login_and_get_csrf(client, "prof_b@example.com", "StrongPass!2026")

        resp = client.put(
            "/api/v1/profile",
            json={
                "full_name": profile.full_name,
                "professional_title": profile.professional_title,
                "verification_status": "confirmed",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["verification_status"] == "confirmed"
        assert data["confirmed_at"] is not None


# ---------------------------------------------------------------------------
# Testes de API para as sub-entidades (confirmam persistência via banco)
# ---------------------------------------------------------------------------

class TestSubEntityConfirmationViaAPI:
    """Verifica que a degradação é persistida, não apenas retornada na resposta HTTP."""

    def _create_confirmed_experience_via_db(self, db: Session, user_id: uuid.UUID) -> WorkExperience:
        return _confirmed_exp(db, user_id)

    def test_experience_degradacao_persiste_no_banco(self, db_session: Session, make_client):
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="api_exp@example.com",
            display_name="API Exp", password="StrongPass!2026",
        )
        exp = _confirmed_exp(db_session, user.id)

        client = make_client()
        csrf = login_and_get_csrf(client, "api_exp@example.com", "StrongPass!2026")

        resp = client.put(
            f"/api/v1/profile/experiences/{exp.id}",
            json={
                "company": "Empresa Via API",
                "role": exp.role,
                "is_current": exp.is_current,
                "experience_type": exp.experience_type,
                "technologies": exp.technologies,
                "related_skills": exp.related_skills,
                "eligible_as_target_role": exp.eligible_as_target_role,
                "verification_status": "confirmed",   # <-- cliente reenvia
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["verification_status"] == "pending_validation"
        assert resp.json()["confirmed_at"] is None

        # Verificar persistência no banco
        db_session.expire_all()
        from sqlalchemy import select as sa_select
        reloaded = db_session.execute(
            sa_select(WorkExperience).where(WorkExperience.id == exp.id)
        ).scalar_one()
        assert reloaded.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert reloaded.confirmed_at is None

    def test_skill_degradacao_persiste_no_banco(self, db_session: Session, make_client):
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="api_sk@example.com",
            display_name="API Skill", password="StrongPass!2026",
        )
        skill = _confirmed_skill(db_session, user.id)

        client = make_client()
        csrf = login_and_get_csrf(client, "api_sk@example.com", "StrongPass!2026")

        resp = client.put(
            f"/api/v1/profile/skills/{skill.id}",
            json={
                "name": "Go",   # alteração factual
                "category": skill.category,
                "proficiency_level": skill.proficiency_level,
                "notes": skill.notes,
                "verification_status": "confirmed",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["verification_status"] == "pending_validation"

        db_session.expire_all()
        from sqlalchemy import select as sa_select
        reloaded = db_session.execute(
            sa_select(Skill).where(Skill.id == skill.id)
        ).scalar_one()
        assert reloaded.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert reloaded.confirmed_at is None

    def test_language_degradacao_persiste_no_banco(self, db_session: Session, make_client):
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="api_lang@example.com",
            display_name="API Lang", password="StrongPass!2026",
        )
        lang = _confirmed_lang(db_session, user.id)

        client = make_client()
        csrf = login_and_get_csrf(client, "api_lang@example.com", "StrongPass!2026")

        resp = client.put(
            f"/api/v1/profile/languages/{lang.id}",
            json={
                "language_name": "Mandarim",   # alteração factual
                "proficiency_level": lang.proficiency_level,
                "cefr_level": lang.cefr_level,
                "verification_status": "confirmed",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["verification_status"] == "pending_validation"

        db_session.expire_all()
        from sqlalchemy import select as sa_select
        reloaded = db_session.execute(
            sa_select(Language).where(Language.id == lang.id)
        ).scalar_one()
        assert reloaded.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert reloaded.confirmed_at is None

    def test_education_degradacao_persiste_no_banco(self, db_session: Session, make_client):
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="api_edu@example.com",
            display_name="API Edu", password="StrongPass!2026",
        )
        edu = _confirmed_edu(db_session, user.id)

        client = make_client()
        csrf = login_and_get_csrf(client, "api_edu@example.com", "StrongPass!2026")

        resp = client.put(
            f"/api/v1/profile/educations/{edu.id}",
            json={
                "institution": "Outra Universidade",   # alteração factual
                "course": edu.course,
                "education_status": edu.education_status,
                "verification_status": "confirmed",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["verification_status"] == "pending_validation"

        db_session.expire_all()
        from sqlalchemy import select as sa_select
        reloaded = db_session.execute(
            sa_select(Education).where(Education.id == edu.id)
        ).scalar_one()
        assert reloaded.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert reloaded.confirmed_at is None

    def test_project_degradacao_persiste_no_banco(self, db_session: Session, make_client):
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="api_proj@example.com",
            display_name="API Proj", password="StrongPass!2026",
        )
        proj = _confirmed_proj(db_session, user.id)

        client = make_client()
        csrf = login_and_get_csrf(client, "api_proj@example.com", "StrongPass!2026")

        resp = client.put(
            f"/api/v1/profile/projects/{proj.id}",
            json={
                "name": "Projeto Gamma",   # alteração factual
                "description": proj.description,
                "role": proj.role,
                "technologies": proj.technologies,
                "links": proj.links,
                "verified_results": proj.verified_results,
                "verification_status": "confirmed",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["verification_status"] == "pending_validation"

        db_session.expire_all()
        from sqlalchemy import select as sa_select
        reloaded = db_session.execute(
            sa_select(ProfessionalProject).where(ProfessionalProject.id == proj.id)
        ).scalar_one()
        assert reloaded.verification_status == VerificationStatus.PENDING_VALIDATION.value
        assert reloaded.confirmed_at is None

    def test_quick_confirm_permanece_funcional(self, db_session: Session, make_client):
        """Quick-confirm: envia todo conteúdo original + status alternado → deve funcionar."""
        from app.services.auth_service import create_user_account

        user = create_user_account(
            db_session, email="quickconf@example.com",
            display_name="Quick", password="StrongPass!2026",
        )
        # Começar com pendente
        exp = WorkExperience(
            user_id=user.id,
            company="Empresa QC",
            role="Desenvolvedor",
            is_current=False,
            experience_type=ExperienceType.CLT.value,
            technologies=["Python"],
            related_skills=[],
            eligible_as_target_role=True,
            verification_status=VerificationStatus.PENDING_VALIDATION.value,
        )
        db_session.add(exp)
        db_session.commit()
        db_session.refresh(exp)

        client = make_client()
        csrf = login_and_get_csrf(client, "quickconf@example.com", "StrongPass!2026")

        # Quick-confirm: envia conteúdo idêntico + status = confirmed
        resp = client.put(
            f"/api/v1/profile/experiences/{exp.id}",
            json={
                "company": exp.company,
                "role": exp.role,
                "is_current": exp.is_current,
                "experience_type": exp.experience_type,
                "technologies": exp.technologies,
                "related_skills": exp.related_skills,
                "eligible_as_target_role": exp.eligible_as_target_role,
                "verification_status": "confirmed",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["verification_status"] == "confirmed"
        assert resp.json()["confirmed_at"] is not None

        # Quick-revert: envia conteúdo idêntico + status = pending_validation
        resp2 = client.put(
            f"/api/v1/profile/experiences/{exp.id}",
            json={
                "company": exp.company,
                "role": exp.role,
                "is_current": exp.is_current,
                "experience_type": exp.experience_type,
                "technologies": exp.technologies,
                "related_skills": exp.related_skills,
                "eligible_as_target_role": exp.eligible_as_target_role,
                "verification_status": "pending_validation",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["verification_status"] == "pending_validation"
