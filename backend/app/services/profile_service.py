import uuid
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import (
    Education,
    Language,
    ProfessionalProfile,
    ProfessionalProject,
    Skill,
    VerificationStatus,
    WorkExperience,
    default_career_preferences,
)
from app.models.user import User
from app.schemas.profile import (
    EducationCreate,
    EducationUpdate,
    FullProfileBundleResponse,
    LanguageCreate,
    LanguageUpdate,
    ProfileConfirmBatchRequest,
    ProfileConfirmBatchResponse,
    ProfessionalProfileResponse,
    ProfessionalProfileUpdate,
    ProfessionalProjectCreate,
    ProfessionalProjectUpdate,
    ProfileSeedDocumentSchema,
    ProfileSeedImportSummary,
    ProfileValidationSummary,
    SkillCreate,
    SkillUpdate,
    WorkExperienceCreate,
    WorkExperienceUpdate,
)

ModelT = TypeVar(
    "ModelT",
    WorkExperience,
    Education,
    Skill,
    Language,
    ProfessionalProject,
)

_PROFILE_FACTUAL_FIELDS = frozenset(
    {
        "full_name",
        "professional_email",
        "phone",
        "city",
        "state",
        "country",
        "professional_title",
        "professional_summary",
        "linkedin_url",
        "github_url",
        "portfolio_url",
    }
)


class ProfileBatchNotFoundError(LookupError):
    """Lançada quando algum ID do lote não existe ou pertence a outro usuário."""


class ProfileBatchInvalidStatusError(ValueError):
    """Lançada quando algum item do lote não está em `pending_validation` (ex.: `draft`)."""


def _resolve_confirmed_at(
    new_status: str,
    current_confirmed_at: datetime | None,
    *,
    facts_changed: bool = False,
) -> datetime | None:
    if new_status == VerificationStatus.CONFIRMED.value:
        if facts_changed or current_confirmed_at is None:
            return datetime.now(UTC)
        return current_confirmed_at
    return None


def _normalize_factual_value(value: object) -> object:
    """Normaliza um valor factual para igualdade semântica.

    - None e string vazia são equivalentes ("ausente").
    - Listas de tags são comparadas sem ordem (sacola ordenada de strings).
    - Dicionários (ex.: links) são comparados sem ordem de chaves.
    - Demais tipos permanecem inalterados.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return sorted(str(x) for x in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), "" if v is None else str(v)) for k, v in value.items()))
    return value


def _requested_verification_status(payload: object) -> str | None:
    """Retorna o status enviado pelo cliente, ou None se o campo foi omitido.

    Distingue omissão real de default do schema via `model_fields_set`.
    """
    fields_set = getattr(payload, "model_fields_set", set())
    if "verification_status" not in fields_set:
        return None
    status = getattr(payload, "verification_status", None)
    if status is None:
        return None
    return status.value if hasattr(status, "value") else str(status)


def _has_factual_changes(
    entity: object,
    data: dict[str, object],
    *,
    unordered_list_fields: frozenset[str] = frozenset(),
    nullable_str_fields: frozenset[str] = frozenset(),
    unordered_mapping_fields: frozenset[str] = frozenset(),
) -> bool:
    for key, new_value in data.items():
        current_value = getattr(entity, key)
        use_semantic = (
            key in unordered_list_fields
            or key in nullable_str_fields
            or key in unordered_mapping_fields
        )
        if use_semantic:
            if _normalize_factual_value(current_value) != _normalize_factual_value(new_value):
                return True
        elif current_value != new_value:
            return True
    return False


def _apply_confirmation_policy(
    *,
    requested_status: str | None,
    current_status: str,
    current_confirmed_at: datetime | None,
    facts_changed: bool,
) -> tuple[str, datetime | None]:
    """Aplica a matriz de transição de verificação.

    `requested_status` é None quando o cliente omitiu o campo (defaults do
    schema não contam como intenção). Registro `confirmed` com alteração
    factual sempre reabre, mesmo se o cliente reenviar `confirmed`.
    Confirmação explícita a partir de `draft` ou `pending_validation` é
    intencional e permitida, inclusive quando o conteúdo também mudou.
    """
    confirmed = VerificationStatus.CONFIRMED.value
    pending = VerificationStatus.PENDING_VALIDATION.value
    draft = VerificationStatus.DRAFT.value

    if current_status == confirmed and facts_changed:
        return pending, None

    if requested_status is None:
        return current_status, current_confirmed_at

    if requested_status == confirmed:
        if current_status == confirmed and current_confirmed_at is not None:
            return confirmed, current_confirmed_at
        return confirmed, datetime.now(UTC)

    if requested_status == pending:
        return pending, None

    if requested_status == draft:
        if current_status == draft:
            return draft, current_confirmed_at
        return draft, None

    return requested_status, None


def _persist_status_update(
    db: Session,
    entity: object,
    payload: object,
    *,
    enum_overrides: dict[str, str] | None = None,
    unordered_list_fields: frozenset[str] = frozenset(),
    nullable_str_fields: frozenset[str] = frozenset(),
    unordered_mapping_fields: frozenset[str] = frozenset(),
):
    data = payload.model_dump()
    if enum_overrides:
        data.update(enum_overrides)
    requested_status = _requested_verification_status(payload)
    data.pop("verification_status", None)

    facts_changed = _has_factual_changes(
        entity,
        data,
        unordered_list_fields=unordered_list_fields,
        nullable_str_fields=nullable_str_fields,
        unordered_mapping_fields=unordered_mapping_fields,
    )
    final_status, final_confirmed_at = _apply_confirmation_policy(
        requested_status=requested_status,
        current_status=entity.verification_status,
        current_confirmed_at=entity.confirmed_at,
        facts_changed=facts_changed,
    )
    for key, value in data.items():
        setattr(entity, key, value)
    entity.verification_status = final_status
    entity.confirmed_at = final_confirmed_at
    db.commit()
    db.refresh(entity)
    return entity


def get_or_create_profile(db: Session, user: User) -> ProfessionalProfile:
    stmt = select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id)
    profile = db.execute(stmt).scalar_one_or_none()

    if profile is None:
        profile = ProfessionalProfile(
            user_id=user.id,
            full_name=user.display_name,
            professional_email=user.email,
            city=None,
            state=None,
            country=None,
            preferences=default_career_preferences(),
            verification_status=VerificationStatus.DRAFT.value,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return profile


def update_profile(
    db: Session,
    user: User,
    payload: ProfessionalProfileUpdate,
) -> ProfessionalProfile:
    profile = get_or_create_profile(db, user)
    update_data = payload.model_dump(exclude_unset=True)

    if "preferences" in update_data and payload.preferences is not None:
        profile.preferences = payload.preferences.model_dump()
        del update_data["preferences"]

    requested_status = _requested_verification_status(payload)
    update_data.pop("verification_status", None)

    factual_data = {
        field: value
        for field, value in update_data.items()
        if field in _PROFILE_FACTUAL_FIELDS
    }
    factual_changed = _has_factual_changes(
        profile,
        factual_data,
        nullable_str_fields=_PROFILE_FACTUAL_FIELDS,
    )

    for field, value in update_data.items():
        setattr(profile, field, value)

    final_status, final_confirmed_at = _apply_confirmation_policy(
        requested_status=requested_status,
        current_status=profile.verification_status,
        current_confirmed_at=profile.confirmed_at,
        facts_changed=factual_changed,
    )
    profile.verification_status = final_status
    profile.confirmed_at = final_confirmed_at

    db.commit()
    db.refresh(profile)
    return profile


def import_profile_seed_for_user(
    db: Session,
    user: User,
    seed: ProfileSeedDocumentSchema,
) -> ProfileSeedImportSummary:
    """
    Importa um arquivo JSON local validado para o perfil do usuário especificado.

    Garantias:
    - Transacional: executa em uma única transação com rollback completo em qualquer falha.
    - Idempotente: não duplica experiências, formações, habilidades, idiomas ou projetos.
    - Não destrutivo: nunca sobrescreve campos já preenchidos, preferências personalizadas
      ou registros confirmados pelo usuário.
    - Nunca confirma fatos automaticamente (novos itens entram como rascunho ou pendente).
    """
    try:
        profile = db.execute(
            select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id)
        ).scalar_one_or_none()

        profile_created = False
        if profile is None:
            profile = ProfessionalProfile(
                user_id=user.id,
                full_name=user.display_name,
                professional_email=user.email,
                preferences=default_career_preferences(),
                verification_status=seed.profile.verification_status,
                confirmed_at=None,
            )
            db.add(profile)
            db.flush()
            profile_created = True

        scalar_fields = (
            "full_name",
            "professional_email",
            "phone",
            "city",
            "state",
            "country",
            "professional_title",
            "professional_summary",
            "linkedin_url",
            "github_url",
            "portfolio_url",
        )
        profile_fields_filled = 0
        for field in scalar_fields:
            current_value = getattr(profile, field)
            seed_value = getattr(seed.profile, field)
            is_empty = current_value is None or (
                isinstance(current_value, str) and not current_value.strip()
            )
            if is_empty and seed_value is not None:
                setattr(profile, field, seed_value)
                profile_fields_filled += 1

        # Preserva estado confirmado; só promove de draft se o perfil acabou de ser criado
        if (
            profile_created
            and profile.verification_status != VerificationStatus.CONFIRMED.value
        ):
            profile.verification_status = seed.profile.verification_status
            profile.confirmed_at = None

        # Só aplica preferências do seed se o perfil ainda estiver com o padrão neutro intocado
        preferences_applied = False
        if seed.profile.preferences is not None:
            neutral_defaults = default_career_preferences()
            if profile_created or not profile.preferences or profile.preferences == neutral_defaults:
                profile.preferences = seed.profile.preferences.model_dump()
                preferences_applied = True

        # 1. Experiências (chave natural: empresa + cargo)
        existing_exp_keys = {
            (exp.company.strip().lower(), exp.role.strip().lower())
            for exp in db.execute(
                select(WorkExperience).where(WorkExperience.user_id == user.id)
            )
            .scalars()
            .all()
        }
        experiences_created = 0
        experiences_skipped = 0
        for item in seed.experiences:
            key = (item.company.strip().lower(), item.role.strip().lower())
            if key in existing_exp_keys:
                experiences_skipped += 1
                continue
            existing_exp_keys.add(key)
            db.add(
                WorkExperience(
                    user_id=user.id,
                    company=item.company,
                    role=item.role,
                    description=item.description,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    is_current=item.is_current,
                    experience_type=item.experience_type.value,
                    technologies=item.technologies,
                    related_skills=item.related_skills,
                    eligible_as_target_role=item.eligible_as_target_role,
                    verification_status=item.verification_status.value,
                    confirmed_at=None,
                )
            )
            experiences_created += 1

        # 2. Formação acadêmica (chave natural: instituição + curso)
        existing_edu_keys = {
            (edu.institution.strip().lower(), edu.course.strip().lower())
            for edu in db.execute(
                select(Education).where(Education.user_id == user.id)
            )
            .scalars()
            .all()
        }
        educations_created = 0
        educations_skipped = 0
        for item in seed.educations:
            key = (item.institution.strip().lower(), item.course.strip().lower())
            if key in existing_edu_keys:
                educations_skipped += 1
                continue
            existing_edu_keys.add(key)
            db.add(
                Education(
                    user_id=user.id,
                    institution=item.institution,
                    course=item.course,
                    field_of_study=item.field_of_study,
                    current_semester=item.current_semester,
                    start_date=item.start_date,
                    expected_graduation_date=item.expected_graduation_date,
                    education_status=item.education_status.value,
                    verification_status=item.verification_status.value,
                    confirmed_at=None,
                )
            )
            educations_created += 1

        # 3. Habilidades (chave natural: nome + categoria)
        existing_skill_keys = {
            (sk.name.strip().lower(), sk.category.strip().lower())
            for sk in db.execute(select(Skill).where(Skill.user_id == user.id))
            .scalars()
            .all()
        }
        skills_created = 0
        skills_skipped = 0
        for item in seed.skills:
            key = (item.name.strip().lower(), item.category.strip().lower())
            if key in existing_skill_keys:
                skills_skipped += 1
                continue
            existing_skill_keys.add(key)
            db.add(
                Skill(
                    user_id=user.id,
                    name=item.name,
                    category=item.category,
                    proficiency_level=item.proficiency_level.value,
                    notes=item.notes,
                    verification_status=item.verification_status.value,
                    confirmed_at=None,
                )
            )
            skills_created += 1

        # 4. Idiomas (chave natural: nome do idioma)
        existing_lang_keys = {
            lang.language_name.strip().lower()
            for lang in db.execute(select(Language).where(Language.user_id == user.id))
            .scalars()
            .all()
        }
        languages_created = 0
        languages_skipped = 0
        for item in seed.languages:
            key = item.language_name.strip().lower()
            if key in existing_lang_keys:
                languages_skipped += 1
                continue
            existing_lang_keys.add(key)
            db.add(
                Language(
                    user_id=user.id,
                    language_name=item.language_name,
                    proficiency_level=item.proficiency_level.value,
                    cefr_level=item.cefr_level,
                    verification_status=item.verification_status.value,
                    confirmed_at=None,
                )
            )
            languages_created += 1

        # 5. Projetos profissionais (chave natural: nome do projeto)
        existing_proj_keys = {
            proj.name.strip().lower()
            for proj in db.execute(
                select(ProfessionalProject).where(ProfessionalProject.user_id == user.id)
            )
            .scalars()
            .all()
        }
        projects_created = 0
        projects_skipped = 0
        for item in seed.projects:
            key = item.name.strip().lower()
            if key in existing_proj_keys:
                projects_skipped += 1
                continue
            existing_proj_keys.add(key)
            db.add(
                ProfessionalProject(
                    user_id=user.id,
                    name=item.name,
                    description=item.description,
                    role=item.role,
                    technologies=item.technologies,
                    links=item.links,
                    verified_results=item.verified_results,
                    verification_status=item.verification_status.value,
                    confirmed_at=None,
                )
            )
            projects_created += 1

        db.commit()
        return ProfileSeedImportSummary(
            profile_created=profile_created,
            profile_fields_filled=profile_fields_filled,
            preferences_applied=preferences_applied,
            experiences_created=experiences_created,
            experiences_skipped=experiences_skipped,
            educations_created=educations_created,
            educations_skipped=educations_skipped,
            skills_created=skills_created,
            skills_skipped=skills_skipped,
            languages_created=languages_created,
            languages_skipped=languages_skipped,
            projects_created=projects_created,
            projects_skipped=projects_skipped,
        )
    except Exception:
        db.rollback()
        raise


def _get_owned_entity(
    db: Session,
    model_cls: type[ModelT],
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> ModelT | None:
    stmt = select(model_cls).where(
        model_cls.id == entity_id,
        model_cls.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


# --- WorkExperience CRUD ---
def list_experiences(db: Session, user: User) -> list[WorkExperience]:
    stmt = (
        select(WorkExperience)
        .where(WorkExperience.user_id == user.id)
        .order_by(WorkExperience.is_current.desc(), WorkExperience.start_date.desc().nullslast(), WorkExperience.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_experience(db: Session, user: User, experience_id: uuid.UUID) -> WorkExperience | None:
    return _get_owned_entity(db, WorkExperience, user.id, experience_id)


def create_experience(
    db: Session,
    user: User,
    payload: WorkExperienceCreate,
) -> WorkExperience:
    data = payload.model_dump()
    status_val = payload.verification_status.value
    data["verification_status"] = status_val
    data["experience_type"] = payload.experience_type.value
    exp = WorkExperience(
        user_id=user.id,
        confirmed_at=_resolve_confirmed_at(status_val, None),
        **data,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def update_experience(
    db: Session,
    exp: WorkExperience,
    payload: WorkExperienceUpdate,
) -> WorkExperience:
    return _persist_status_update(
        db,
        exp,
        payload,
        enum_overrides={"experience_type": payload.experience_type.value},
        unordered_list_fields=frozenset({"technologies", "related_skills"}),
        nullable_str_fields=frozenset({"description"}),
    )


def delete_experience(db: Session, exp: WorkExperience) -> None:
    db.delete(exp)
    db.commit()


# --- Education CRUD ---
def list_educations(db: Session, user: User) -> list[Education]:
    stmt = (
        select(Education)
        .where(Education.user_id == user.id)
        .order_by(Education.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_education(db: Session, user: User, education_id: uuid.UUID) -> Education | None:
    return _get_owned_entity(db, Education, user.id, education_id)


def create_education(db: Session, user: User, payload: EducationCreate) -> Education:
    data = payload.model_dump()
    status_val = payload.verification_status.value
    data["verification_status"] = status_val
    data["education_status"] = payload.education_status.value
    edu = Education(
        user_id=user.id,
        confirmed_at=_resolve_confirmed_at(status_val, None),
        **data,
    )
    db.add(edu)
    db.commit()
    db.refresh(edu)
    return edu


def update_education(
    db: Session,
    edu: Education,
    payload: EducationUpdate,
) -> Education:
    return _persist_status_update(
        db,
        edu,
        payload,
        enum_overrides={"education_status": payload.education_status.value},
        nullable_str_fields=frozenset({"field_of_study", "current_semester"}),
    )


def delete_education(db: Session, edu: Education) -> None:
    db.delete(edu)
    db.commit()


# --- Skill CRUD ---
def list_skills(db: Session, user: User) -> list[Skill]:
    stmt = (
        select(Skill)
        .where(Skill.user_id == user.id)
        .order_by(Skill.category.asc(), Skill.name.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_skill(db: Session, user: User, skill_id: uuid.UUID) -> Skill | None:
    return _get_owned_entity(db, Skill, user.id, skill_id)


def create_skill(db: Session, user: User, payload: SkillCreate) -> Skill:
    data = payload.model_dump()
    status_val = payload.verification_status.value
    data["verification_status"] = status_val
    data["proficiency_level"] = payload.proficiency_level.value
    skill = Skill(
        user_id=user.id,
        confirmed_at=_resolve_confirmed_at(status_val, None),
        **data,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill(db: Session, skill: Skill, payload: SkillUpdate) -> Skill:
    return _persist_status_update(
        db,
        skill,
        payload,
        enum_overrides={"proficiency_level": payload.proficiency_level.value},
        nullable_str_fields=frozenset({"notes"}),
    )


def delete_skill(db: Session, skill: Skill) -> None:
    db.delete(skill)
    db.commit()


# --- Language CRUD ---
def list_languages(db: Session, user: User) -> list[Language]:
    stmt = (
        select(Language)
        .where(Language.user_id == user.id)
        .order_by(Language.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_language(db: Session, user: User, language_id: uuid.UUID) -> Language | None:
    return _get_owned_entity(db, Language, user.id, language_id)


def create_language(db: Session, user: User, payload: LanguageCreate) -> Language:
    data = payload.model_dump()
    status_val = payload.verification_status.value
    data["verification_status"] = status_val
    data["proficiency_level"] = payload.proficiency_level.value
    lang = Language(
        user_id=user.id,
        confirmed_at=_resolve_confirmed_at(status_val, None),
        **data,
    )
    db.add(lang)
    db.commit()
    db.refresh(lang)
    return lang


def update_language(db: Session, lang: Language, payload: LanguageUpdate) -> Language:
    return _persist_status_update(
        db,
        lang,
        payload,
        enum_overrides={"proficiency_level": payload.proficiency_level.value},
        nullable_str_fields=frozenset({"cefr_level"}),
    )


def delete_language(db: Session, lang: Language) -> None:
    db.delete(lang)
    db.commit()


# --- ProfessionalProject CRUD ---
def list_projects(db: Session, user: User) -> list[ProfessionalProject]:
    stmt = (
        select(ProfessionalProject)
        .where(ProfessionalProject.user_id == user.id)
        .order_by(ProfessionalProject.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_project(
    db: Session,
    user: User,
    project_id: uuid.UUID,
) -> ProfessionalProject | None:
    return _get_owned_entity(db, ProfessionalProject, user.id, project_id)


def create_project(
    db: Session,
    user: User,
    payload: ProfessionalProjectCreate,
) -> ProfessionalProject:
    data = payload.model_dump()
    status_val = payload.verification_status.value
    data["verification_status"] = status_val
    proj = ProfessionalProject(
        user_id=user.id,
        confirmed_at=_resolve_confirmed_at(status_val, None),
        **data,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def update_project(
    db: Session,
    proj: ProfessionalProject,
    payload: ProfessionalProjectUpdate,
) -> ProfessionalProject:
    return _persist_status_update(
        db,
        proj,
        payload,
        unordered_list_fields=frozenset({"technologies"}),
        nullable_str_fields=frozenset({"description", "role", "verified_results"}),
        unordered_mapping_fields=frozenset({"links"}),
    )


def delete_project(db: Session, proj: ProfessionalProject) -> None:
    db.delete(proj)
    db.commit()


def get_full_profile_bundle(db: Session, user: User) -> FullProfileBundleResponse:
    profile = get_or_create_profile(db, user)
    experiences = list_experiences(db, user)
    educations = list_educations(db, user)
    skills = list_skills(db, user)
    languages = list_languages(db, user)
    projects = list_projects(db, user)

    all_records = [*experiences, *educations, *skills, *languages, *projects]
    confirmed_items = sum(
        1 for item in all_records if item.verification_status == VerificationStatus.CONFIRMED.value
    )
    profile_confirmed = profile.verification_status == VerificationStatus.CONFIRMED.value
    if profile_confirmed:
        confirmed_items += 1

    total_items = len(all_records) + 1
    pending_or_draft = total_items - confirmed_items

    summary = ProfileValidationSummary(
        profile_confirmed=profile_confirmed,
        confirmed_count=confirmed_items,
        pending_or_draft_count=pending_or_draft,
        total_items=total_items,
        ready_for_future_applications=profile_confirmed and confirmed_items >= 2,
    )

    return FullProfileBundleResponse(
        profile=ProfessionalProfileResponse.model_validate(profile),
        experiences=experiences,
        educations=educations,
        skills=skills,
        languages=languages,
        projects=projects,
        validation_summary=summary,
    )


def _fetch_pending_batch_items(
    db: Session,
    model_cls: type[ModelT],
    user_id: uuid.UUID,
    entity_ids: list[uuid.UUID],
    label_pt: str,
) -> list[ModelT]:
    if not entity_ids:
        return []
    found = list(
        db.execute(
            select(model_cls).where(
                model_cls.user_id == user_id,
                model_cls.id.in_(entity_ids),
            )
        )
        .scalars()
        .all()
    )
    if len(found) != len(entity_ids):
        raise ProfileBatchNotFoundError(
            f"Um ou mais registros de {label_pt} não foram encontrados ou não pertencem ao usuário."
        )
    for item in found:
        if item.verification_status != VerificationStatus.PENDING_VALIDATION.value:
            raise ProfileBatchInvalidStatusError(
                f"Somente registros de {label_pt} em 'pending_validation' podem ser confirmados em lote "
                f"(itens em 'draft' devem ser completados e revisados antes da confirmação)."
            )
    return found


def confirm_profile_batch(
    db: Session,
    user: User,
    payload: ProfileConfirmBatchRequest,
) -> ProfileConfirmBatchResponse:
    """
    Confirma em lote exclusivamente os itens `pending_validation` explicitamente
    selecionados pelo usuário autenticado, de forma atômica (tudo ou nada).
    """
    now = datetime.now(UTC)
    try:
        profile_to_confirm: ProfessionalProfile | None = None
        if payload.confirm_profile:
            profile = get_or_create_profile(db, user)
            if profile.verification_status != VerificationStatus.PENDING_VALIDATION.value:
                raise ProfileBatchInvalidStatusError(
                    "Os dados gerais do perfil só podem ser confirmados em lote quando estiverem em 'pending_validation'."
                )
            profile_to_confirm = profile

        exps = _fetch_pending_batch_items(
            db, WorkExperience, user.id, payload.experience_ids, "experiência"
        )
        edus = _fetch_pending_batch_items(
            db, Education, user.id, payload.education_ids, "formação acadêmica"
        )
        skills = _fetch_pending_batch_items(
            db, Skill, user.id, payload.skill_ids, "habilidade"
        )
        langs = _fetch_pending_batch_items(
            db, Language, user.id, payload.language_ids, "idioma"
        )
        projs = _fetch_pending_batch_items(
            db, ProfessionalProject, user.id, payload.project_ids, "projeto"
        )

        if profile_to_confirm is not None:
            profile_to_confirm.verification_status = VerificationStatus.CONFIRMED.value
            profile_to_confirm.confirmed_at = now

        for entity in (*exps, *edus, *skills, *langs, *projs):
            entity.verification_status = VerificationStatus.CONFIRMED.value
            entity.confirmed_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise

    bundle = get_full_profile_bundle(db, user)
    total_confirmed = (
        (1 if profile_to_confirm is not None else 0)
        + len(exps)
        + len(edus)
        + len(skills)
        + len(langs)
        + len(projs)
    )
    return ProfileConfirmBatchResponse(
        confirmed_at=now,
        profile_confirmed=profile_to_confirm is not None,
        experiences_confirmed=len(exps),
        educations_confirmed=len(edus),
        skills_confirmed=len(skills),
        languages_confirmed=len(langs),
        projects_confirmed=len(projs),
        total_confirmed=total_confirmed,
        validation_summary=bundle.validation_summary,
    )
