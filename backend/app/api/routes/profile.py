import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.profile import (
    EducationCreate,
    EducationResponse,
    EducationUpdate,
    FullProfileBundleResponse,
    LanguageCreate,
    LanguageResponse,
    LanguageUpdate,
    ProfileConfirmBatchRequest,
    ProfileConfirmBatchResponse,
    ProfessionalProfileResponse,
    ProfessionalProfileUpdate,
    ProfessionalProjectCreate,
    ProfessionalProjectResponse,
    ProfessionalProjectUpdate,
    SkillCreate,
    SkillResponse,
    SkillUpdate,
    WorkExperienceCreate,
    WorkExperienceResponse,
    WorkExperienceUpdate,
)
from app.services import profile_service
from app.services.profile_service import (
    ProfileBatchInvalidStatusError,
    ProfileBatchNotFoundError,
)

router = APIRouter(prefix="/profile", tags=["Perfil Profissional"])


@router.get(
    "/bundle",
    response_model=FullProfileBundleResponse,
    summary="Consulta o perfil profissional completo do usuário autenticado",
)
def get_profile_bundle(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FullProfileBundleResponse:
    return profile_service.get_full_profile_bundle(db, current_user)


@router.get(
    "",
    response_model=ProfessionalProfileResponse,
    summary="Consulta os dados centrais e preferências do perfil do usuário autenticado",
)
def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfessionalProfileResponse:
    profile = profile_service.get_or_create_profile(db, current_user)
    return ProfessionalProfileResponse.model_validate(profile)


@router.put(
    "",
    response_model=ProfessionalProfileResponse,
    summary="Atualiza os dados centrais e preferências do perfil do usuário autenticado",
)
def update_my_profile(
    payload: ProfessionalProfileUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfessionalProfileResponse:
    profile = profile_service.update_profile(db, current_user, payload)
    return ProfessionalProfileResponse.model_validate(profile)


@router.post(
    "/confirm-batch",
    response_model=ProfileConfirmBatchResponse,
    summary="Confirma em lote itens pendentes revisados explicitamente pelo usuário",
)
def confirm_profile_items_batch(
    payload: ProfileConfirmBatchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileConfirmBatchResponse:
    try:
        return profile_service.confirm_profile_batch(db, current_user, payload)
    except ProfileBatchNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ProfileBatchInvalidStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# --- WorkExperience Endpoints ---
@router.get(
    "/experiences",
    response_model=list[WorkExperienceResponse],
    summary="Lista todas as experiências profissionais do usuário autenticado",
)
def list_my_experiences(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[WorkExperienceResponse]:
    items = profile_service.list_experiences(db, current_user)
    return [WorkExperienceResponse.model_validate(item) for item in items]


@router.post(
    "/experiences",
    response_model=WorkExperienceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona uma nova experiência profissional ao perfil do usuário autenticado",
)
def create_my_experience(
    payload: WorkExperienceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkExperienceResponse:
    exp = profile_service.create_experience(db, current_user, payload)
    return WorkExperienceResponse.model_validate(exp)


@router.get(
    "/experiences/{experience_id}",
    response_model=WorkExperienceResponse,
    summary="Obtém uma experiência profissional específica do usuário autenticado",
)
def get_my_experience(
    experience_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkExperienceResponse:
    exp = profile_service.get_experience(db, current_user, experience_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiência profissional não encontrada.",
        )
    return WorkExperienceResponse.model_validate(exp)


@router.put(
    "/experiences/{experience_id}",
    response_model=WorkExperienceResponse,
    summary="Atualiza uma experiência profissional do usuário autenticado",
)
def update_my_experience(
    experience_id: uuid.UUID,
    payload: WorkExperienceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkExperienceResponse:
    exp = profile_service.get_experience(db, current_user, experience_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiência profissional não encontrada.",
        )
    updated = profile_service.update_experience(db, exp, payload)
    return WorkExperienceResponse.model_validate(updated)


@router.delete(
    "/experiences/{experience_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma experiência profissional do usuário autenticado",
)
def delete_my_experience(
    experience_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    exp = profile_service.get_experience(db, current_user, experience_id)
    if exp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiência profissional não encontrada.",
        )
    profile_service.delete_experience(db, exp)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Education Endpoints ---
@router.get(
    "/educations",
    response_model=list[EducationResponse],
    summary="Lista todas as formações acadêmicas do usuário autenticado",
)
def list_my_educations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[EducationResponse]:
    items = profile_service.list_educations(db, current_user)
    return [EducationResponse.model_validate(item) for item in items]


@router.post(
    "/educations",
    response_model=EducationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona uma formação acadêmica ao perfil do usuário autenticado",
)
def create_my_education(
    payload: EducationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EducationResponse:
    edu = profile_service.create_education(db, current_user, payload)
    return EducationResponse.model_validate(edu)


@router.get(
    "/educations/{education_id}",
    response_model=EducationResponse,
    summary="Obtém uma formação acadêmica específica do usuário autenticado",
)
def get_my_education(
    education_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EducationResponse:
    edu = profile_service.get_education(db, current_user, education_id)
    if edu is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formação acadêmica não encontrada.",
        )
    return EducationResponse.model_validate(edu)


@router.put(
    "/educations/{education_id}",
    response_model=EducationResponse,
    summary="Atualiza uma formação acadêmica do usuário autenticado",
)
def update_my_education(
    education_id: uuid.UUID,
    payload: EducationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EducationResponse:
    edu = profile_service.get_education(db, current_user, education_id)
    if edu is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formação acadêmica não encontrada.",
        )
    updated = profile_service.update_education(db, edu, payload)
    return EducationResponse.model_validate(updated)


@router.delete(
    "/educations/{education_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma formação acadêmica do usuário autenticado",
)
def delete_my_education(
    education_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    edu = profile_service.get_education(db, current_user, education_id)
    if edu is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formação acadêmica não encontrada.",
        )
    profile_service.delete_education(db, edu)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Skill Endpoints ---
@router.get(
    "/skills",
    response_model=list[SkillResponse],
    summary="Lista todas as habilidades técnicas do usuário autenticado",
)
def list_my_skills(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SkillResponse]:
    items = profile_service.list_skills(db, current_user)
    return [SkillResponse.model_validate(item) for item in items]


@router.post(
    "/skills",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona uma habilidade ao perfil do usuário autenticado",
)
def create_my_skill(
    payload: SkillCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SkillResponse:
    skill = profile_service.create_skill(db, current_user, payload)
    return SkillResponse.model_validate(skill)


@router.get(
    "/skills/{skill_id}",
    response_model=SkillResponse,
    summary="Obtém uma habilidade específica do usuário autenticado",
)
def get_my_skill(
    skill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SkillResponse:
    skill = profile_service.get_skill(db, current_user, skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habilidade não encontrada.",
        )
    return SkillResponse.model_validate(skill)


@router.put(
    "/skills/{skill_id}",
    response_model=SkillResponse,
    summary="Atualiza uma habilidade do usuário autenticado",
)
def update_my_skill(
    skill_id: uuid.UUID,
    payload: SkillUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SkillResponse:
    skill = profile_service.get_skill(db, current_user, skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habilidade não encontrada.",
        )
    updated = profile_service.update_skill(db, skill, payload)
    return SkillResponse.model_validate(updated)


@router.delete(
    "/skills/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma habilidade do usuário autenticado",
)
def delete_my_skill(
    skill_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    skill = profile_service.get_skill(db, current_user, skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habilidade não encontrada.",
        )
    profile_service.delete_skill(db, skill)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Language Endpoints ---
@router.get(
    "/languages",
    response_model=list[LanguageResponse],
    summary="Lista todos os idiomas do usuário autenticado",
)
def list_my_languages(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[LanguageResponse]:
    items = profile_service.list_languages(db, current_user)
    return [LanguageResponse.model_validate(item) for item in items]


@router.post(
    "/languages",
    response_model=LanguageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona um idioma ao perfil do usuário autenticado",
)
def create_my_language(
    payload: LanguageCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LanguageResponse:
    lang = profile_service.create_language(db, current_user, payload)
    return LanguageResponse.model_validate(lang)


@router.get(
    "/languages/{language_id}",
    response_model=LanguageResponse,
    summary="Obtém um idioma específico do usuário autenticado",
)
def get_my_language(
    language_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LanguageResponse:
    lang = profile_service.get_language(db, current_user, language_id)
    if lang is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idioma não encontrado.",
        )
    return LanguageResponse.model_validate(lang)


@router.put(
    "/languages/{language_id}",
    response_model=LanguageResponse,
    summary="Atualiza um idioma do usuário autenticado",
)
def update_my_language(
    language_id: uuid.UUID,
    payload: LanguageUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LanguageResponse:
    lang = profile_service.get_language(db, current_user, language_id)
    if lang is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idioma não encontrado.",
        )
    updated = profile_service.update_language(db, lang, payload)
    return LanguageResponse.model_validate(updated)


@router.delete(
    "/languages/{language_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um idioma do usuário autenticado",
)
def delete_my_language(
    language_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    lang = profile_service.get_language(db, current_user, language_id)
    if lang is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idioma não encontrado.",
        )
    profile_service.delete_language(db, lang)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- ProfessionalProject Endpoints ---
@router.get(
    "/projects",
    response_model=list[ProfessionalProjectResponse],
    summary="Lista todos os projetos profissionais do usuário autenticado",
)
def list_my_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ProfessionalProjectResponse]:
    items = profile_service.list_projects(db, current_user)
    return [ProfessionalProjectResponse.model_validate(item) for item in items]


@router.post(
    "/projects",
    response_model=ProfessionalProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona um projeto profissional ao perfil do usuário autenticado",
)
def create_my_project(
    payload: ProfessionalProjectCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfessionalProjectResponse:
    proj = profile_service.create_project(db, current_user, payload)
    return ProfessionalProjectResponse.model_validate(proj)


@router.get(
    "/projects/{project_id}",
    response_model=ProfessionalProjectResponse,
    summary="Obtém um projeto profissional específico do usuário autenticado",
)
def get_my_project(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfessionalProjectResponse:
    proj = profile_service.get_project(db, current_user, project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto profissional não encontrado.",
        )
    return ProfessionalProjectResponse.model_validate(proj)


@router.put(
    "/projects/{project_id}",
    response_model=ProfessionalProjectResponse,
    summary="Atualiza um projeto profissional do usuário autenticado",
)
def update_my_project(
    project_id: uuid.UUID,
    payload: ProfessionalProjectUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfessionalProjectResponse:
    proj = profile_service.get_project(db, current_user, project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto profissional não encontrado.",
        )
    updated = profile_service.update_project(db, proj, payload)
    return ProfessionalProjectResponse.model_validate(updated)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove um projeto profissional do usuário autenticado",
)
def delete_my_project(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    proj = profile_service.get_project(db, current_user, project_id)
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto profissional não encontrado.",
        )
    profile_service.delete_project(db, proj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
