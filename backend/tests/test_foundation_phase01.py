import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.cli import main as cli_main
from app.core.config import Settings
from app.core.security import extract_trusted_client_ip
from app.models.profile import ProfessionalProfile, VerificationStatus, WorkExperience
from app.models.user import AccountStatus, AuthRateLimit
from app.schemas.profile import ProfileSeedDocumentSchema
from app.services import profile_service
from app.services.auth_service import create_user_account
from tests.conftest import resolve_test_database_url


def login_and_get_csrf(client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["authenticated"] is True
    assert "csrf_token" in data
    return data["csrf_token"]


def build_sample_seed_dict() -> dict:
    return {
        "schema_version": 1,
        "profile": {
            "full_name": "Pessoa Exemplo",
            "professional_email": "pessoa@example.com",
            "phone": None,
            "city": "Cidade Exemplo",
            "state": "Estado Exemplo",
            "country": "Brasil",
            "professional_title": "Desenvolvedor Backend | Python",
            "professional_summary": "Resumo profissional de teste em rascunho.",
            "linkedin_url": "https://www.linkedin.com/in/exemplo",
            "github_url": "https://github.com/exemplo",
            "portfolio_url": None,
            "verification_status": "pending_validation",
            "preferences": {
                "internships": {
                    "enabled": True,
                    "priority_areas": ["Desenvolvimento Backend", "APIs e integrações"],
                    "preferred_languages": ["Português Brasileiro", "Inglês"],
                    "excluded_areas": ["Suporte técnico"],
                },
                "junior_developer": {
                    "enabled": True,
                    "priority_areas": ["Desenvolvimento Backend"],
                    "block_clt": True,
                    "accepted_contract_types": ["PJ", "Estágio"],
                    "excluded_areas": ["Suporte técnico"],
                },
                "freelance": {
                    "enabled": True,
                    "scopes": ["Brasil"],
                    "priority_categories": ["Python", "Automação"],
                    "preferred_languages": ["Português Brasileiro"],
                },
                "source_restrictions": {
                    "workana_enabled": False,
                    "workana_disabled_reason": "Política configurada pelo usuário.",
                    "gupy_mode": "selective_high_compatibility",
                    "auto_execute_tests": False,
                    "pay_premium_or_fees_without_approval": False,
                    "strict_platform_terms_compliance": True,
                },
            },
        },
        "experiences": [
            {
                "company": "Empresa Exemplo",
                "role": "Desenvolvedor Estagiário",
                "description": "Manutenção de APIs e automações.",
                "start_date": "2025-01-01",
                "end_date": None,
                "is_current": True,
                "experience_type": "internship",
                "technologies": ["Python", "FastAPI"],
                "related_skills": ["APIs"],
                "eligible_as_target_role": True,
                "verification_status": "pending_validation",
            }
        ],
        "educations": [
            {
                "institution": "Instituto Exemplo",
                "course": "Análise e Desenvolvimento de Sistemas",
                "field_of_study": "Tecnologia da Informação",
                "current_semester": "2º semestre",
                "education_status": "in_progress",
                "verification_status": "pending_validation",
            }
        ],
        "skills": [
            {
                "name": "Python",
                "category": "Backend",
                "proficiency_level": "intermediate",
                "notes": "Desenvolvimento de APIs.",
                "verification_status": "pending_validation",
            }
        ],
        "languages": [
            {
                "language_name": "Português Brasileiro",
                "proficiency_level": "native",
                "cefr_level": None,
                "verification_status": "pending_validation",
            },
            {
                "language_name": "Inglês",
                "proficiency_level": "intermediate",
                "cefr_level": "B1",
                "verification_status": "pending_validation",
            },
        ],
        "projects": [
            {
                "name": "Projeto Exemplo",
                "description": "Descrição inicial em rascunho.",
                "role": "Autor",
                "technologies": ["Python", "PostgreSQL"],
                "links": {"GitHub": "https://github.com/exemplo/projeto"},
                "verified_results": None,
                "verification_status": "draft",
            }
        ],
    }


def test_app_initialization_and_openapi(make_client):
    client = make_client()
    openapi_resp = client.get("/api/openapi.json")
    assert openapi_resp.status_code == 200
    schema = openapi_resp.json()
    assert schema["info"]["title"] == "Job Hunter API"
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/profile/bundle" in schema["paths"]
    # Garante que não existem endpoints de cadastro público ou seed pessoal exposto
    assert "/api/v1/auth/register" not in schema["paths"]
    assert "/api/v1/auth/signup" not in schema["paths"]
    assert "/api/v1/profile/seed-initial" not in schema["paths"]
    assert client.post("/api/v1/profile/seed-initial").status_code == 404


def test_health_check(make_client):
    client = make_client()
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_alembic_migrations_up_and_down(tmp_path: Path):
    mig_url = resolve_test_database_url(tmp_path)
    connect_args = {"check_same_thread": False} if mig_url.startswith("sqlite") else {}
    engine = create_engine(mig_url, connect_args=connect_args, future=True)

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", mig_url)

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "head")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected_tables = {
        "users",
        "user_sessions",
        "auth_rate_limits",
        "professional_profiles",
        "work_experiences",
        "educations",
        "skills",
        "languages",
        "professional_projects",
        "alembic_version",
    }
    assert expected_tables.issubset(tables)

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "base")

    inspector_after = inspect(engine)
    remaining_tables = set(inspector_after.get_table_names()) - {"alembic_version"}
    assert len(remaining_tables) == 0
    engine.dispose()


def test_authentication_valid_invalid_and_logout(db_session: Session, make_client):
    user = create_user_account(
        db_session,
        email="admin@example.com",
        display_name="Admin Teste",
        password="StrongPassword!2026",
        is_admin=True,
    )
    client = make_client()

    unauth = client.get("/api/v1/auth/me")
    assert unauth.status_code == 401

    bad_pass = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "WrongPassword123"},
    )
    assert bad_pass.status_code == 401

    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"email": "naoexiste@example.com", "password": "StrongPassword!2026"},
    )
    assert unknown_user.status_code == 401
    # Mesma mensagem controlada sem revelar existência do e-mail
    assert bad_pass.json()["detail"] == unknown_user.json()["detail"]

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "  ADMIN@EXAMPLE.COM ", "password": "StrongPassword!2026"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["user"]["email"] == "admin@example.com"
    assert login_data["user"]["id"] == str(user.id)
    csrf_token = login_data["csrf_token"]

    assert user.password_hash.startswith("$argon2id$")

    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["display_name"] == "Admin Teste"

    logout_no_csrf = client.post("/api/v1/auth/logout")
    assert logout_no_csrf.status_code == 403

    logout_ok = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_ok.status_code == 200

    me_after_logout = client.get("/api/v1/auth/me")
    assert me_after_logout.status_code == 401

    user.account_status = AccountStatus.SUSPENDED.value
    db_session.commit()
    suspended_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "StrongPassword!2026"},
    )
    assert suspended_login.status_code == 401


def test_login_rate_limiting_cooldown_recovery_and_account_isolation(
    db_session: Session,
    make_client,
    monkeypatch,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_account_ip_max_attempts", 3)
    monkeypatch.setattr(settings, "login_ip_max_attempts", 5)
    monkeypatch.setattr(settings, "login_cooldown_seconds", 120)
    monkeypatch.setattr(settings, "login_rate_limit_window_seconds", 900)

    create_user_account(
        db_session,
        email="alvo@example.com",
        display_name="Usuario Alvo",
        password="ValidPassword!2026",
    )

    client_attacker = make_client(client=("127.0.0.1", 50000))
    attacker_headers = {"X-Forwarded-For": "203.0.113.10"}

    # 3 falhas consecutivas do IP atacante contra a conta alvo -> todas 401
    for _ in range(3):
        resp = client_attacker.post(
            "/api/v1/auth/login",
            headers=attacker_headers,
            json={"email": "alvo@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    # 4ª tentativa da mesma origem + conta deve receber 429 com Retry-After
    blocked = client_attacker.post(
        "/api/v1/auth/login",
        headers=attacker_headers,
        json={"email": "alvo@example.com", "password": "ValidPassword!2026"},
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1

    # Conta inexistente também sofre o mesmo comportamento (não revela se e-mail existe)
    for _ in range(3):
        resp = client_attacker.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "203.0.113.11"},
            json={"email": "inexistente@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401
    blocked_nonexistent = client_attacker.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "203.0.113.11"},
        json={"email": "inexistente@example.com", "password": "WrongPassword!"},
    )
    assert blocked_nonexistent.status_code == 429
    assert blocked_nonexistent.json()["detail"] == blocked.json()["detail"]

    # Usuário legítimo em OUTRO IP não sofre DoS e consegue autenticar normalmente
    client_legit = make_client(client=("127.0.0.1", 50001))
    legit_ok = client_legit.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "198.51.100.25"},
        json={"email": "alvo@example.com", "password": "ValidPassword!2026"},
    )
    assert legit_ok.status_code == 200

    # Teste de limite global por IP (5 tentativas totais em contas diferentes)
    spam_ip_headers = {"X-Forwarded-For": "203.0.113.99"}
    for idx in range(5):
        resp = client_attacker.post(
            "/api/v1/auth/login",
            headers=spam_ip_headers,
            json={"email": f"conta{idx}@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    ip_blocked = client_attacker.post(
        "/api/v1/auth/login",
        headers=spam_ip_headers,
        json={"email": "alvo@example.com", "password": "ValidPassword!2026"},
    )
    assert ip_blocked.status_code == 429

    # Verifica que o rate limit está persistido no banco de dados (não apenas em memória)
    persisted_records = db_session.execute(select(AuthRateLimit)).scalars().all()
    assert len(persisted_records) > 0

    # Simula expiração do cooldown no banco e verifica recuperação automática
    for rec in persisted_records:
        rec.blocked_until = datetime.now(UTC) - timedelta(seconds=5)
    db_session.commit()

    recovered = client_attacker.post(
        "/api/v1/auth/login",
        headers=attacker_headers,
        json={"email": "alvo@example.com", "password": "ValidPassword!2026"},
    )
    assert recovered.status_code == 200


def test_trusted_proxy_and_spoofing_protection(monkeypatch):
    from app.core.config import settings

    def fake_request(peer_host: str, headers: dict[str, str]):
        return SimpleNamespace(
            client=SimpleNamespace(host=peer_host),
            headers=headers,
        )

    # 1. Peer NÃO confiável enviando X-Forwarded-For ou CF-Connecting-IP falso -> headers ignorados
    monkeypatch.setattr(settings, "trust_cf_connecting_ip", True)
    untrusted_req = fake_request(
        "198.51.100.77",
        {
            "X-Forwarded-For": "8.8.8.8",
            "X-Real-IP": "1.1.1.1",
            "CF-Connecting-IP": "9.9.9.9",
        },
    )
    assert extract_trusted_client_ip(untrusted_req) == "198.51.100.77"

    # 2. Peer confiável (Nginx/Docker) com X-Forwarded-For contendo IP falsificado à esquerda:
    #    Deve ler da direita para a esquerda, pular proxies confiáveis e ignorar o IP forjado.
    monkeypatch.setattr(settings, "trust_cf_connecting_ip", False)
    proxied_req = fake_request(
        "172.18.0.5",
        {
            "X-Forwarded-For": "8.8.8.8, 203.0.113.50, 172.18.0.2",
        },
    )
    assert extract_trusted_client_ip(proxied_req) == "203.0.113.50"

    # 3. Peer confiável atrás do Cloudflare Tunnel (TRUST_CF_CONNECTING_IP=true)
    monkeypatch.setattr(settings, "trust_cf_connecting_ip", True)
    cf_req = fake_request(
        "127.0.0.1",
        {
            "CF-Connecting-IP": "198.51.100.42",
            "X-Forwarded-For": "203.0.113.50",
        },
    )
    assert extract_trusted_client_ip(cf_req) == "198.51.100.42"


def test_production_settings_validation():
    strong_secret = "Ab9!xQ2#mP7$vL4@kR8&wZ5*nJ3^tH6%yD1"

    # Produção com COOKIE_SECURE=false deve falhar
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            secret_key=strong_secret,
            cookie_secure=False,
            cors_origins="https://jobhunter.ctrls.dev.br",
        )

    # Produção com segredo dev-only deve falhar
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="dev-only-ephemeral-secret-key-must-be-changed-in-production-32b",
            cookie_secure=True,
            cors_origins="https://jobhunter.ctrls.dev.br",
        )

    # CORS curinga com credenciais deve falhar
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            secret_key=strong_secret,
            cookie_secure=True,
            cors_origins="*",
        )

    # Produção com CORS HTTP não-seguro deve falhar
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            secret_key=strong_secret,
            cookie_secure=True,
            cors_origins="http://jobhunter.ctrls.dev.br",
        )

    # Configuração de produção válida deve ser aceita
    prod_settings = Settings(
        _env_file=None,
        environment="production",
        secret_key=strong_secret,
        cookie_secure=True,
        cors_origins="https://jobhunter.ctrls.dev.br",
    )
    assert prod_settings.cookie_secure is True


def test_neutral_profile_for_new_user(db_session: Session, make_client):
    create_user_account(
        db_session,
        email="novo@example.com",
        display_name="Novo Usuario",
        password="StrongPassword!2026",
    )
    client = make_client()
    login_and_get_csrf(client, "novo@example.com", "StrongPassword!2026")

    prof = client.get("/api/v1/profile").json()
    assert prof["city"] is None
    assert prof["state"] is None
    assert prof["country"] is None
    assert prof["verification_status"] == "draft"
    assert prof["preferences"]["junior_developer"]["block_clt"] is False
    assert prof["preferences"]["source_restrictions"]["workana_enabled"] is True
    assert prof["preferences"]["internships"]["priority_areas"] == []


def test_local_seed_import_idempotency_preservation_and_rollback(
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
):
    user = create_user_account(
        db_session,
        email="seeduser@example.com",
        display_name="Seed User",
        password="StrongPassword!2026",
        is_admin=True,
    )

    seed_payload = build_sample_seed_dict()
    seed_file = tmp_path / "profile-seed.local.json"
    seed_file.write_text(json.dumps(seed_payload), encoding="utf-8")

    # Garante que a CLI use o banco de teste atual
    monkeypatch.setattr("app.cli.SessionLocal", lambda: db_session)

    # 1. Validação estrita: arquivo tentando auto-confirmar fatos deve ser rejeitado
    bad_seed = build_sample_seed_dict()
    bad_seed["skills"][0]["verification_status"] = "confirmed"
    bad_file = tmp_path / "bad-seed.json"
    bad_file.write_text(json.dumps(bad_seed), encoding="utf-8")
    assert (
        cli_main(
            [
                "import-profile-seed",
                "--email",
                "seeduser@example.com",
                "--file",
                str(bad_file),
            ]
        )
        == 1
    )

    # 2. Primeira importação bem-sucedida
    exit_code_1 = cli_main(
        [
            "import-profile-seed",
            "--email",
            "seeduser@example.com",
            "--file",
            str(seed_file),
        ]
    )
    assert exit_code_1 == 0

    prof = db_session.execute(
        select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id)
    ).scalar_one()
    assert prof.city == "Cidade Exemplo"
    assert prof.preferences["junior_developer"]["block_clt"] is True

    exps = db_session.execute(
        select(WorkExperience).where(WorkExperience.user_id == user.id)
    ).scalars().all()
    assert len(exps) == 1
    assert exps[0].verification_status == VerificationStatus.PENDING_VALIDATION.value

    # 3. Simula edição humana, personalização de preferências e confirmação de fato
    prof.city = "Cidade Editada Manualmente"
    custom_prefs = dict(prof.preferences)
    custom_prefs["junior_developer"] = dict(custom_prefs["junior_developer"])
    custom_prefs["junior_developer"]["block_clt"] = False
    prof.preferences = custom_prefs
    prof.verification_status = VerificationStatus.CONFIRMED.value

    exps[0].description = "Descrição revisada e confirmada manualmente."
    exps[0].verification_status = VerificationStatus.CONFIRMED.value
    exps[0].confirmed_at = datetime.now(UTC)
    db_session.commit()

    # 4. Segunda importação (idempotência + preservação de edições e preferências)
    seed_doc = ProfileSeedDocumentSchema.model_validate(seed_payload)
    summary_2 = profile_service.import_profile_seed_for_user(db_session, user, seed_doc)
    assert summary_2.profile_created is False
    assert summary_2.preferences_applied is False
    assert summary_2.experiences_created == 0
    assert summary_2.educations_created == 0
    assert summary_2.skills_created == 0
    assert summary_2.languages_created == 0
    assert summary_2.projects_created == 0

    # Adiciona uma nova skill nova ao JSON e mantém a anterior: só a nova deve ser criada
    seed_payload["skills"].append(
        {
            "name": "PostgreSQL",
            "category": "Banco de Dados",
            "proficiency_level": "intermediate",
            "notes": "Relacional e JSONB",
            "verification_status": "pending_validation",
        }
    )
    seed_doc_3 = ProfileSeedDocumentSchema.model_validate(seed_payload)
    summary_3 = profile_service.import_profile_seed_for_user(db_session, user, seed_doc_3)
    assert summary_3.skills_created == 1
    assert summary_3.skills_skipped == 1

    db_session.refresh(prof)
    assert prof.city == "Cidade Editada Manualmente"
    assert prof.preferences["junior_developer"]["block_clt"] is False
    assert prof.verification_status == VerificationStatus.CONFIRMED.value

    db_session.refresh(exps[0])
    assert exps[0].description == "Descrição revisada e confirmada manualmente."
    assert exps[0].verification_status == VerificationStatus.CONFIRMED.value

    # 5. Rollback em caso de falha durante a transação
    seed_payload["projects"].append(
        {
            "name": "Projeto Rollback Teste",
            "description": "Não deve persistir em caso de erro.",
            "role": "Autor",
            "technologies": ["Python"],
            "links": {},
            "verified_results": None,
            "verification_status": "draft",
        }
    )
    seed_doc_fail = ProfileSeedDocumentSchema.model_validate(seed_payload)

    original_commit = db_session.commit

    def failing_commit():
        raise RuntimeError("Falha simulada durante commit.")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="Falha simulada"):
        profile_service.import_profile_seed_for_user(db_session, user, seed_doc_fail)
    monkeypatch.setattr(db_session, "commit", original_commit)

    bundle_after_rollback = profile_service.get_full_profile_bundle(db_session, user)
    assert len(bundle_after_rollback.projects) == 1
    assert bundle_after_rollback.projects[0].name == "Projeto Exemplo"


def test_field_validations_urls_dates_cefr(db_session: Session, make_client):
    create_user_account(
        db_session,
        email="validador@example.com",
        display_name="Validador",
        password="StrongPassword!2026",
    )
    client = make_client()
    csrf = login_and_get_csrf(client, "validador@example.com", "StrongPassword!2026")
    headers = {"X-CSRF-Token": csrf}

    bad_url = client.put(
        "/api/v1/profile",
        headers=headers,
        json={"linkedin_url": "linkedin.com/sem-protocolo"},
    )
    assert bad_url.status_code == 422

    bad_dates = client.post(
        "/api/v1/profile/experiences",
        headers=headers,
        json={
            "company": "Empresa X",
            "role": "Estagiário",
            "start_date": "2025-06-01",
            "end_date": "2025-01-01",
            "is_current": False,
        },
    )
    assert bad_dates.status_code == 422

    bad_cefr = client.post(
        "/api/v1/profile/languages",
        headers=headers,
        json={
            "language_name": "Inglês",
            "proficiency_level": "intermediate",
            "cefr_level": "Z9",
        },
    )
    assert bad_cefr.status_code == 422


def test_crud_professional_entities(db_session: Session, make_client):
    create_user_account(
        db_session,
        email="crud@example.com",
        display_name="Tester CRUD",
        password="StrongPassword!2026",
    )
    client = make_client()
    csrf = login_and_get_csrf(client, "crud@example.com", "StrongPassword!2026")
    headers = {"X-CSRF-Token": csrf}

    exp_resp = client.post(
        "/api/v1/profile/experiences",
        headers=headers,
        json={
            "company": "Empresa Exemplo",
            "role": "Desenvolvedor Estagiário",
            "start_date": "2025-01-01",
            "is_current": True,
            "experience_type": "internship",
            "technologies": ["Python", "FastAPI"],
            "related_skills": ["Automação", "APIs"],
            "eligible_as_target_role": False,
            "verification_status": "confirmed",
        },
    )
    assert exp_resp.status_code == 201
    exp_id = exp_resp.json()["id"]
    assert exp_resp.json()["confirmed_at"] is not None

    exp_upd = client.put(
        f"/api/v1/profile/experiences/{exp_id}",
        headers=headers,
        json={
            "company": "Empresa Exemplo LTDA",
            "role": "Desenvolvedor Backend Júnior",
            "start_date": "2025-01-01",
            "is_current": True,
            "experience_type": "junior",
            "technologies": ["Python", "FastAPI", "PostgreSQL"],
            "related_skills": ["Automação", "APIs"],
            "eligible_as_target_role": True,
            "verification_status": "confirmed",
        },
    )
    assert exp_upd.status_code == 200
    assert exp_upd.json()["role"] == "Desenvolvedor Backend Júnior"

    edu_resp = client.post(
        "/api/v1/profile/educations",
        headers=headers,
        json={
            "institution": "Instituto Exemplo",
            "course": "Análise e Desenvolvimento de Sistemas",
            "field_of_study": "Computação",
            "current_semester": "3º semestre",
            "education_status": "in_progress",
            "verification_status": "confirmed",
        },
    )
    assert edu_resp.status_code == 201
    edu_id = edu_resp.json()["id"]

    skill_resp = client.post(
        "/api/v1/profile/skills",
        headers=headers,
        json={
            "name": "Python",
            "category": "Backend",
            "proficiency_level": "intermediate",
            "notes": "FastAPI, SQLAlchemy e automações.",
            "verification_status": "confirmed",
        },
    )
    assert skill_resp.status_code == 201
    skill_id = skill_resp.json()["id"]

    lang_resp = client.post(
        "/api/v1/profile/languages",
        headers=headers,
        json={
            "language_name": "Inglês",
            "proficiency_level": "intermediate",
            "cefr_level": "B1",
            "verification_status": "confirmed",
        },
    )
    assert lang_resp.status_code == 201
    lang_id = lang_resp.json()["id"]
    assert lang_resp.json()["cefr_level"] == "B1"

    proj_resp = client.post(
        "/api/v1/profile/projects",
        headers=headers,
        json={
            "name": "Projeto Exemplo",
            "description": "Plataforma em desenvolvimento.",
            "role": "Autor",
            "technologies": ["Python", "PostgreSQL"],
            "links": {"GitHub": "https://github.com/exemplo"},
            "verified_results": None,
            "verification_status": "draft",
        },
    )
    assert proj_resp.status_code == 201
    proj_id = proj_resp.json()["id"]

    assert client.delete(f"/api/v1/profile/experiences/{exp_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/profile/educations/{edu_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/profile/skills/{skill_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/profile/languages/{lang_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/profile/projects/{proj_id}", headers=headers).status_code == 204


def test_strict_isolation_between_two_users(db_session: Session, make_client):
    """
    Garante que o Usuário B nunca consiga ler, alterar ou excluir
    quaisquer dados profissionais pertencentes ao Usuário A.
    """
    create_user_account(
        db_session,
        email="alice@example.com",
        display_name="Alice",
        password="AliceStrongPassword!1",
    )
    create_user_account(
        db_session,
        email="bob@example.com",
        display_name="Bob",
        password="BobStrongPassword!2",
    )

    client_alice = make_client()
    csrf_alice = login_and_get_csrf(client_alice, "alice@example.com", "AliceStrongPassword!1")
    headers_alice = {"X-CSRF-Token": csrf_alice}

    client_bob = make_client()
    csrf_bob = login_and_get_csrf(client_bob, "bob@example.com", "BobStrongPassword!2")
    headers_bob = {"X-CSRF-Token": csrf_bob}

    client_alice.put(
        "/api/v1/profile",
        headers=headers_alice,
        json={
            "full_name": "Alice Silva",
            "professional_title": "Engenheira de Software",
        },
    )
    alice_exp_id = client_alice.post(
        "/api/v1/profile/experiences",
        headers=headers_alice,
        json={"company": "Alice Corp", "role": "Backend Dev"},
    ).json()["id"]

    alice_edu_id = client_alice.post(
        "/api/v1/profile/educations",
        headers=headers_alice,
        json={"institution": "Instituto A", "course": "Engenharia de Computação"},
    ).json()["id"]

    alice_skill_id = client_alice.post(
        "/api/v1/profile/skills",
        headers=headers_alice,
        json={"name": "Rust", "category": "Backend"},
    ).json()["id"]

    alice_lang_id = client_alice.post(
        "/api/v1/profile/languages",
        headers=headers_alice,
        json={"language_name": "Alemão", "proficiency_level": "advanced", "cefr_level": "C1"},
    ).json()["id"]

    alice_proj_id = client_alice.post(
        "/api/v1/profile/projects",
        headers=headers_alice,
        json={"name": "Projeto Secreto Alice"},
    ).json()["id"]

    bob_bundle = client_bob.get("/api/v1/profile/bundle").json()
    assert bob_bundle["profile"]["full_name"] == "Bob"
    assert bob_bundle["experiences"] == []
    assert bob_bundle["educations"] == []
    assert bob_bundle["skills"] == []
    assert bob_bundle["languages"] == []
    assert bob_bundle["projects"] == []

    assert client_bob.get(f"/api/v1/profile/experiences/{alice_exp_id}").status_code == 404
    assert client_bob.get(f"/api/v1/profile/educations/{alice_edu_id}").status_code == 404
    assert client_bob.get(f"/api/v1/profile/skills/{alice_skill_id}").status_code == 404
    assert client_bob.get(f"/api/v1/profile/languages/{alice_lang_id}").status_code == 404
    assert client_bob.get(f"/api/v1/profile/projects/{alice_proj_id}").status_code == 404

    assert (
        client_bob.put(
            f"/api/v1/profile/experiences/{alice_exp_id}",
            headers=headers_bob,
            json={"company": "Invadido", "role": "Hacker"},
        ).status_code
        == 404
    )
    assert (
        client_bob.put(
            f"/api/v1/profile/projects/{alice_proj_id}",
            headers=headers_bob,
            json={"name": "Projeto Roubado"},
        ).status_code
        == 404
    )

    assert (
        client_bob.delete(
            f"/api/v1/profile/experiences/{alice_exp_id}",
            headers=headers_bob,
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/profile/educations/{alice_edu_id}",
            headers=headers_bob,
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/profile/skills/{alice_skill_id}",
            headers=headers_bob,
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/profile/languages/{alice_lang_id}",
            headers=headers_bob,
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/profile/projects/{alice_proj_id}",
            headers=headers_bob,
        ).status_code
        == 404
    )

    alice_bundle = client_alice.get("/api/v1/profile/bundle").json()
    assert alice_bundle["profile"]["full_name"] == "Alice Silva"
    assert len(alice_bundle["experiences"]) == 1
    assert alice_bundle["experiences"][0]["company"] == "Alice Corp"
    assert len(alice_bundle["projects"]) == 1
    assert alice_bundle["projects"][0]["name"] == "Projeto Secreto Alice"


def test_cli_create_admin_command(db_session: Session, monkeypatch):
    monkeypatch.setenv("TEST_ADMIN_PASS", "AdminSafePass!2026")
    monkeypatch.setattr("app.cli.SessionLocal", lambda: db_session)

    exit_code = cli_main(
        [
            "create-admin",
            "--email",
            "admin-cli@example.com",
            "--display-name",
            "Admin CLI",
            "--password-env",
            "TEST_ADMIN_PASS",
        ]
    )
    assert exit_code == 0
