from __future__ import annotations

import re
import uuid
from typing import Any

from app.schemas.material import (
    ApplicationAnswerItem,
    ApplicationAnswersStructuredContent,
    ContactInclusionOptions,
    PendingUserInputField,
    TargetLanguage,
    WritingGenerationOptions,
)
from app.services.materials.fact_selector import (
    AuthorizedFactBundle,
    _exp_haystack,
    _matches_requirement,
    _project_haystack,
    _skill_haystack,
)
from app.services.materials.writing_common import (
    LANGUAGE_LEVEL_PROSE,
    SKILL_LEVEL_PROSE,
    build_snapshot_for_bundle,
    education_prose_snippet,
    markdown_to_plain_text,
    reconcile_manual_notes,
    validate_strict_fact_keys,
)
from app.services.opportunities.matching import _TECH_ALIASES, _contains_term
from app.services.opportunities.sanitization import sanitize_plain_text

_COMPENSATION_KEYWORDS = (
    "salário",
    "salario",
    "pretensão",
    "pretensao",
    "remuneração",
    "remuneracao",
    "salary",
    "compensation",
    "pay",
    "hourly rate",
    "valor hora",
    "rate",
    "budget",
    "orçamento",
    "orcamento",
)
_AVAILABILITY_KEYWORDS = (
    "disponibilidade",
    "quando pode começar",
    "inicio imediato",
    "início imediato",
    "aviso prévio",
    "aviso previo",
    "availability",
    "available",
    "start date",
    "notice period",
    "horas por semana",
    "hours per week",
)
_MOTIVATION_KEYWORDS = (
    "por que deseja",
    "por que quer",
    "porque quer",
    "por que gostaria",
    "por que trabalhar",
    "o que te atrai",
    "motivação",
    "motivacao",
    "why do you want",
    "why this company",
    "why are you interested",
    "why us",
    "what motivates",
)
_PROJECT_KEYWORDS = (
    "projeto",
    "projetos",
    "portfólio",
    "portfolio",
    "project",
    "projects",
)
_EDUCATION_KEYWORDS = (
    "formação",
    "formacao",
    "graduação",
    "graduacao",
    "faculdade",
    "universidade",
    "curso",
    "semestre",
    "education",
    "degree",
    "university",
    "college",
    "graduation",
)
_LANGUAGE_KEYWORDS = (
    "idioma",
    "idiomas",
    "inglês",
    "ingles",
    "espanhol",
    "language",
    "languages",
    "english",
    "spanish",
    "fluent",
    "fluência",
)

_DB_FAMILY_TERMS = (
    "postgresql",
    "postgres",
    "mysql",
    "sqlite",
    "sql",
    "mongodb",
    "redis",
    "sqlalchemy",
    "banco de dados",
    "bancos de dados",
    "database",
    "databases",
)
_API_REST_FAMILY_TERMS = (
    "rest",
    "restful",
    "api",
    "apis",
    "fastapi",
    "django",
    "flask",
    "express",
    "nestjs",
    "spring",
)
_ASKED_TOPIC_PATTERN = re.compile(
    r"(?:experiência|experiencia|experience|trabalhou|worked|conhecimento|knowledge|familiarity|domínio|dominio|uso)\s+"
    r"(?:com|em|de|with|in|on)\s+([a-zA-Z0-9#+._-]{2,32})",
    re.IGNORECASE,
)
_TOPIC_STOPWORDS = frozenset(
    {
        "bancos",
        "banco",
        "dados",
        "apis",
        "api",
        "rest",
        "software",
        "tecnologia",
        "projetos",
        "projeto",
        "sistemas",
        "desenvolvimento",
        "development",
        "databases",
        "database",
        "backend",
        "frontend",
        "fullstack",
        "essa",
        "esta",
        "isso",
        "tecnologias",
    }
)


def _extract_asked_topics(question: str) -> tuple[list[str], bool, bool]:
    """Retorna (tech_tokens, is_db_question, is_api_question)."""
    q_norm = question.lower()
    techs: list[str] = []
    for tech in _TECH_ALIASES:
        if _matches_requirement(q_norm, tech):
            techs.append(tech)

    is_db = any(term in q_norm for term in ("banco de dados", "bancos de dados", "database", "databases"))
    is_api = any(term in q_norm for term in ("api rest", "apis rest", "rest api", "rest apis"))

    for match in _ASKED_TOPIC_PATTERN.finditer(question):
        token = match.group(1).strip(".,?!:;()[]").lower()
        if token and token not in _TOPIC_STOPWORDS and token not in techs:
            techs.append(token)

    return list(dict.fromkeys(techs)), is_db, is_api


def _classify_question(
    question: str,
) -> LiteralKind:  # type: ignore[name-defined]
    q_norm = question.lower()
    if any(k in q_norm for k in _COMPENSATION_KEYWORDS):
        return "compensation"
    if any(k in q_norm for k in _AVAILABILITY_KEYWORDS):
        return "availability"
    if any(k in q_norm for k in _MOTIVATION_KEYWORDS):
        return "motivation"
    if any(k in q_norm for k in _LANGUAGE_KEYWORDS):
        return "language"
    if any(k in q_norm for k in _EDUCATION_KEYWORDS):
        return "education"
    techs, is_db, is_api = _extract_asked_topics(question)
    if techs or is_db or is_api:
        return "technical_experience"
    if any(k in q_norm for k in _PROJECT_KEYWORDS):
        return "project_example"
    return "general_personal"


LiteralKind = str


def _answer_single_question(
    bundle: AuthorizedFactBundle,
    question: str,
    *,
    language: TargetLanguage,
    idx: int,
    user_answer_override: str | None = None,
) -> ApplicationAnswerItem:
    qid = f"q-{idx + 1}"
    q_kind = _classify_question(question)
    clean_override = sanitize_plain_text(user_answer_override, max_length=4000) if user_answer_override else None

    if clean_override:
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind=q_kind,  # type: ignore[arg-type]
            answer_text=clean_override,
            requires_user_input=False,
            status="user_answered",
            follow_up_prompt=None,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    # Perguntas subjetivas / pessoais nunca são inventadas
    if q_kind == "compensation":
        prompt = (
            "Please enter your expected salary or rate manually."
            if language == "en"
            else "Informe manualmente sua pretensão salarial ou valor/hora desejado."
        )
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="compensation",
            answer_text=None,
            requires_user_input=True,
            status="needs_user_input",
            follow_up_prompt=prompt,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    if q_kind == "availability":
        prompt = (
            "Please enter your actual start date availability and schedule manually."
            if language == "en"
            else "Informe manualmente sua disponibilidade real de início e carga horária."
        )
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="availability",
            answer_text=None,
            requires_user_input=True,
            status="needs_user_input",
            follow_up_prompt=prompt,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    if q_kind == "motivation":
        prompt = (
            "Please explain your personal motivation and specific interest in this company or role."
            if language == "en"
            else "Informe manualmente sua motivação pessoal e os motivos de interesse nesta empresa ou vaga."
        )
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="motivation",
            answer_text=None,
            requires_user_input=True,
            status="needs_user_input",
            follow_up_prompt=prompt,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    if q_kind == "education":
        edu_text, edu_keys = education_prose_snippet(bundle, language)
        if edu_text and edu_keys:
            ans = (
                f"I hold confirmed {edu_text}."
                if language == "en"
                else f"Possuo {edu_text}."
            )
            notes = [f"{bundle.educations[0].course} — {bundle.educations[0].institution}"]
            return ApplicationAnswerItem(
                question_id=qid,
                question=question,
                question_kind="education",
                answer_text=ans,
                requires_user_input=False,
                status="answered_from_facts",
                follow_up_prompt=None,
                source_fact_keys=edu_keys,
                evidence_notes=notes,
                provenance="confirmed_fact",
            )
        prompt = (
            "No confirmed education entry was found in your profile. Confirm your academic background or write an answer manually."
            if language == "en"
            else "Não há formação acadêmica confirmada no perfil. Confirme sua formação ou preencha esta resposta manualmente."
        )
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="education",
            answer_text=None,
            requires_user_input=True,
            status="needs_user_input",
            follow_up_prompt=prompt,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    if q_kind == "language":
        if bundle.languages:
            q_low = question.lower()
            matching_langs = [
                lg
                for lg in bundle.languages
                if lg.language_name.lower() in q_low
                or ("inglês" in q_low and "ingl" in lg.language_name.lower())
                or ("english" in q_low and "engl" in lg.language_name.lower())
            ]
            target_langs = matching_langs or bundle.languages[:3]
            if ("ingl" in q_low or "english" in q_low) and not matching_langs:
                prompt = (
                    "No confirmed English language proficiency was found in your profile."
                    if language == "en"
                    else "Não há proficiência confirmada em Inglês no perfil. Confirme no Perfil ou responda manualmente."
                )
                return ApplicationAnswerItem(
                    question_id=qid,
                    question=question,
                    question_kind="language",
                    answer_text=None,
                    requires_user_input=True,
                    status="needs_user_input",
                    follow_up_prompt=prompt,
                    source_fact_keys=[],
                    evidence_notes=[],
                    provenance="user_authored",
                )
            snippets: list[str] = []
            keys: list[str] = []
            notes: list[str] = []
            for lg in target_langs:
                lvl = LANGUAGE_LEVEL_PROSE.get(lg.proficiency_level, {}).get(
                    language, lg.proficiency_level
                )
                cefr = f" (CEFR {lg.cefr_level})" if lg.cefr_level else ""
                snippets.append(f"{lg.language_name}: {lvl}{cefr}")
                keys.append(f"language:{lg.id}")
                notes.append(f"{lg.language_name} ({lg.proficiency_level})")
            ans = (
                f"Confirmed language proficiency: {', '.join(snippets)}."
                if language == "en"
                else f"Proficiência confirmada em idiomas: {', '.join(snippets)}."
            )
            return ApplicationAnswerItem(
                question_id=qid,
                question=question,
                question_kind="language",
                answer_text=ans,
                requires_user_input=False,
                status="answered_from_facts",
                follow_up_prompt=None,
                source_fact_keys=keys,
                evidence_notes=notes,
                provenance="confirmed_fact",
            )
        prompt = (
            "No confirmed languages were found in your profile."
            if language == "en"
            else "Não há idiomas confirmados no perfil. Confirme no Perfil ou preencha manualmente."
        )
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="language",
            answer_text=None,
            requires_user_input=True,
            status="needs_user_input",
            follow_up_prompt=prompt,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    if q_kind == "project_example":
        if bundle.projects:
            proj = bundle.projects[0]
            techs = ", ".join((proj.technologies or [])[:6])
            if language == "en":
                parts = [f"A verified project in my portfolio is {proj.name}" + (f" ({proj.role})" if proj.role else "") + "."]
                if proj.description:
                    parts.append(proj.description.strip())
                if techs:
                    parts.append(f"Technologies used: {techs}.")
                if proj.verified_results:
                    parts.append(f"Verified outcomes: {proj.verified_results.strip()}")
            else:
                parts = [f"Um projeto confirmado em meu histórico é o {proj.name}" + (f" ({proj.role})" if proj.role else "") + "."]
                if proj.description:
                    parts.append(proj.description.strip())
                if techs:
                    parts.append(f"Tecnologias aplicadas: {techs}.")
                if proj.verified_results:
                    parts.append(f"Resultados verificados: {proj.verified_results.strip()}")
            return ApplicationAnswerItem(
                question_id=qid,
                question=question,
                question_kind="project_example",
                answer_text=" ".join(parts),
                requires_user_input=False,
                status="answered_from_facts",
                follow_up_prompt=None,
                source_fact_keys=[f"project:{proj.id}"],
                evidence_notes=[f"Projeto: {proj.name}"],
                provenance="confirmed_fact",
            )
        prompt = (
            "No confirmed project was found in your profile. Confirm an existing project or describe one manually."
            if language == "en"
            else "Nenhum projeto confirmado encontrado no perfil. Confirme um projeto no Perfil ou descreva manualmente."
        )
        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="project_example",
            answer_text=None,
            requires_user_input=True,
            status="needs_user_input",
            follow_up_prompt=prompt,
            source_fact_keys=[],
            evidence_notes=[],
            provenance="user_authored",
        )

    if q_kind == "technical_experience":
        tech_tokens, is_db, is_api = _extract_asked_topics(question)
        search_terms = list(tech_tokens)
        if is_db:
            search_terms.extend(_DB_FAMILY_TERMS)
        if is_api:
            search_terms.extend(_API_REST_FAMILY_TERMS)

        def _matches_any(haystack: str) -> bool:
            if not haystack:
                return False
            for term in search_terms:
                if term in _TECH_ALIASES:
                    if _matches_requirement(haystack, term):
                        return True
                elif _contains_term(haystack, term):
                    return True
            return False

        matched_exps = [e for e in bundle.experiences if _matches_any(_exp_haystack(e))]
        matched_projs = [p for p in bundle.projects if _matches_any(_project_haystack(p))]
        matched_skills = [s for s in bundle.skills if _matches_any(_skill_haystack(s))]

        if not (matched_exps or matched_projs or matched_skills):
            topic_lbl = (
                ", ".join(tech_tokens)
                if tech_tokens
                else ("databases" if is_db else "REST APIs" if is_api else "this topic")
            )
            prompt = (
                f"No confirmed evidence mentioning '{topic_lbl}' was found in your profile. Provide your real experience manually."
                if language == "en"
                else f"Não há evidência confirmada no perfil para '{topic_lbl}'. Descreva sua experiência real manualmente ou confirme itens relacionados."
            )
            return ApplicationAnswerItem(
                question_id=qid,
                question=question,
                question_kind="technical_experience",
                answer_text=None,
                requires_user_input=True,
                status="needs_user_input",
                follow_up_prompt=prompt,
                source_fact_keys=[],
                evidence_notes=[],
                provenance="user_authored",
            )

        fact_keys: list[str] = []
        notes: list[str] = []
        sentences: list[str] = []

        if matched_skills:
            skill_desc: list[str] = []
            for sk in matched_skills[:4]:
                fact_keys.append(f"skill:{sk.id}")
                lvl = SKILL_LEVEL_PROSE.get(sk.proficiency_level, {}).get(
                    language, sk.proficiency_level
                )
                skill_desc.append(f"{sk.name} ({lvl})")
                notes.append(f"Habilidade: {sk.name} ({lvl})")
            if language == "en":
                sentences.append(f"My profile lists verified competencies in {', '.join(skill_desc)}.")
            else:
                sentences.append(f"No perfil, possuo competência confirmada em {', '.join(skill_desc)}.")

        if matched_exps:
            exp = matched_exps[0]
            fact_keys.append(f"experience:{exp.id}")
            notes.append(f"Experiência: {exp.role} em {exp.company}")
            if language == "en":
                s = f"In my role as {exp.role} at {exp.company}"
                if exp.description:
                    s += f", {exp.description.strip()}"
                else:
                    s += "."
                sentences.append(s)
            else:
                s = f"Na experiência como {exp.role} em {exp.company}"
                if exp.description:
                    s += f": {exp.description.strip()}"
                else:
                    s += "."
                sentences.append(s)

        if matched_projs:
            proj = matched_projs[0]
            fact_keys.append(f"project:{proj.id}")
            notes.append(f"Projeto: {proj.name}")
            if language == "en":
                p_sent = f"In project {proj.name}"
                if proj.description:
                    p_sent += f", {proj.description.strip()}"
                else:
                    p_sent += "."
                if proj.verified_results:
                    p_sent += f" Verified results: {proj.verified_results.strip()}"
                sentences.append(p_sent)
            else:
                p_sent = f"No projeto {proj.name}"
                if proj.description:
                    p_sent += f": {proj.description.strip()}"
                else:
                    p_sent += "."
                if proj.verified_results:
                    p_sent += f" Resultados verificados: {proj.verified_results.strip()}"
                sentences.append(p_sent)

        return ApplicationAnswerItem(
            question_id=qid,
            question=question,
            question_kind="technical_experience",
            answer_text=" ".join(sentences),
            requires_user_input=False,
            status="answered_from_facts",
            follow_up_prompt=None,
            source_fact_keys=list(dict.fromkeys(fact_keys)),
            evidence_notes=notes,
            provenance="confirmed_fact",
        )

    # Pergunta geral sem alvo factual objetivo
    prompt = (
        "Please provide an answer tailored with your own details for this question."
        if language == "en"
        else "Esta pergunta exige resposta pessoal do candidato; preencha manualmente antes de aprovar."
    )
    return ApplicationAnswerItem(
        question_id=qid,
        question=question,
        question_kind="general_personal",
        answer_text=None,
        requires_user_input=True,
        status="needs_user_input",
        follow_up_prompt=prompt,
        source_fact_keys=[],
        evidence_notes=[],
        provenance="user_authored",
    )


def analyze_questions_preview(
    bundle: AuthorizedFactBundle,
    *,
    target_language: TargetLanguage,
    writing_options: WritingGenerationOptions | None = None,
) -> list[PendingUserInputField]:
    """Pré-analisa perguntas submetidas e indica quais dependem de entrada do usuário."""
    opts = writing_options or WritingGenerationOptions()
    override_map = {
        item.question.strip().lower(): item.user_answer
        for item in opts.initial_answers
        if item.user_answer
    }
    raw_questions = opts.questions or [item.question for item in opts.initial_answers]
    pending: list[PendingUserInputField] = []
    for idx, q in enumerate(raw_questions):
        ans_item = _answer_single_question(
            bundle,
            q,
            language=target_language,
            idx=idx,
            user_answer_override=override_map.get(q.strip().lower()),
        )
        if ans_item.requires_user_input:
            pending.append(
                PendingUserInputField(
                    field_id=ans_item.question_id,
                    label=q[:140],
                    question=ans_item.follow_up_prompt or q,
                    required=True,
                    user_value=None,
                )
            )
    return pending


def compose_application_answers(
    bundle: AuthorizedFactBundle,
    *,
    target_language: TargetLanguage,
    contact_options: ContactInclusionOptions,
    writing_options: WritingGenerationOptions | None = None,
    user_instructions: str | None = None,
) -> tuple[ApplicationAnswersStructuredContent, dict[str, Any]]:
    """Responde perguntas de candidatura somente com evidências confirmadas ou solicita entrada manual."""
    if not bundle.can_generate:
        raise ValueError(
            "; ".join(bundle.blocking_reasons)
            or "Não há fatos substantivos confirmados suficientes para responder perguntas."
        )

    _ = contact_options, user_instructions
    opts = writing_options or WritingGenerationOptions()
    raw_questions = opts.questions or [item.question for item in opts.initial_answers]
    if not raw_questions:
        raise ValueError(
            "Informe ao menos uma pergunta de candidatura em writing_options.questions."
        )

    override_map = {
        item.question.strip().lower(): item.user_answer
        for item in opts.initial_answers
        if item.user_answer
    }

    items: list[ApplicationAnswerItem] = [
        _answer_single_question(
            bundle,
            q,
            language=target_language,
            idx=idx,
            user_answer_override=override_map.get(q.strip().lower()),
        )
        for idx, q in enumerate(raw_questions)
    ]

    has_manual = any(it.provenance != "confirmed_fact" for it in items)
    structured = ApplicationAnswersStructuredContent(
        schema_version=1,
        material_type="application_answers",
        language=target_language,
        items=items,
        manual_notes=[],
        has_unverified_manual_edits=has_manual,
    )
    snapshot = build_snapshot_for_bundle(bundle, target_language)
    return structured, snapshot


def reconcile_application_answers(
    previous: ApplicationAnswersStructuredContent,
    edited: ApplicationAnswersStructuredContent,
    snapshot: dict[str, Any],
) -> ApplicationAnswersStructuredContent:
    snapshot_facts: dict[str, Any] = dict(snapshot.get("facts") or {})
    prev_by_id = {it.question_id: it for it in previous.items}
    reconciled_items: list[ApplicationAnswerItem] = []

    for item in edited.items:
        valid_keys = validate_strict_fact_keys(item.source_fact_keys, snapshot_facts)
        prev = prev_by_id.get(item.question_id)
        has_answer = bool(item.answer_text and item.answer_text.strip())

        if (
            prev is not None
            and prev.provenance == "confirmed_fact"
            and prev.status == "answered_from_facts"
            and item.answer_text == prev.answer_text
            and item.question == prev.question
            and prev.source_fact_keys
            and all(k in snapshot_facts for k in prev.source_fact_keys)
        ):
            reconciled_items.append(
                item.model_copy(
                    update={
                        "question_id": item.question_id or str(uuid.uuid4()),
                        "source_fact_keys": prev.source_fact_keys,
                        "status": "answered_from_facts",
                        "requires_user_input": False,
                        "provenance": "confirmed_fact",
                    }
                )
            )
        elif has_answer:
            provenance = "manual_edit" if valid_keys and prev is not None and prev.source_fact_keys else "user_authored"
            reconciled_items.append(
                item.model_copy(
                    update={
                        "question_id": item.question_id or str(uuid.uuid4()),
                        "answer_text": item.answer_text.strip() if item.answer_text else None,
                        "source_fact_keys": valid_keys if provenance == "manual_edit" else [],
                        "status": "user_answered",
                        "requires_user_input": False,
                        "provenance": provenance,
                    }
                )
            )
        else:
            reconciled_items.append(
                item.model_copy(
                    update={
                        "question_id": item.question_id or str(uuid.uuid4()),
                        "answer_text": None,
                        "source_fact_keys": [],
                        "status": "needs_user_input",
                        "requires_user_input": True,
                        "provenance": "user_authored",
                    }
                )
            )

    notes = reconcile_manual_notes(edited.manual_notes)
    has_manual = any(it.provenance != "confirmed_fact" for it in reconciled_items) or len(notes) > 0
    return ApplicationAnswersStructuredContent(
        schema_version=1,
        material_type="application_answers",
        language=edited.language,
        items=reconciled_items,
        manual_notes=notes,
        has_unverified_manual_edits=has_manual,
    )


def render_application_answers_markdown(
    content: ApplicationAnswersStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    lang: TargetLanguage = language or content.language
    lines: list[str] = [
        f"# {'Application Question Responses' if lang == 'en' else 'Respostas a Perguntas de Candidatura'}",
        "",
    ]
    for idx, item in enumerate(content.items, start=1):
        lines.append(f"### {idx}. {item.question}")
        if item.answer_text:
            lines.append(item.answer_text)
        else:
            pending_msg = (
                f"*Pending candidate input: {item.follow_up_prompt or 'Additional information required.'}*"
                if lang == "en"
                else f"*Aguardando preenchimento do candidato: {item.follow_up_prompt or 'Informação adicional necessária.'}*"
            )
            lines.append(pending_msg)
        lines.append("")

    if content.manual_notes:
        lines.append(f"## {'Additional Notes' if lang == 'en' else 'Notas Adicionais'}")
        for note in content.manual_notes:
            lines.append(f"- **{note.title}:** {note.content}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_application_answers_plain_text(
    content: ApplicationAnswersStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    return markdown_to_plain_text(render_application_answers_markdown(content, language=language))
