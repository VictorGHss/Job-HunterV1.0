from datetime import UTC, datetime, timedelta
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text

from app.models.application import (
    ApplicationAssessment,
    ApplicationContact,
    ApplicationInterview,
    ApplicationStatusHistory,
)
from app.models.opportunity import (
    EmploymentType,
    Opportunity,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    WorkMode,
)
from app.services.auth_service import create_user_account
from app.services.opportunities.sync_service import ensure_default_sources
from tests.conftest import resolve_test_database_url


def login_and_get_csrf(client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _seed_users_and_opportunity(db_session):
    sources = {s.slug: s for s in ensure_default_sources(db_session)}
    src = sources["remote_ok"]

    alice = create_user_account(
        db_session,
        email="alice.p32@example.com",
        display_name="Alice Desenvolvedora",
        password="StrongPassword123!",
        is_admin=False,
    )
    bob = create_user_account(
        db_session,
        email="bob.p32@example.com",
        display_name="Bob Engenheiro",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.flush()

    now = datetime.now(UTC)
    global_opp = Opportunity(
        source_id=src.id,
        external_id="rk-p32-1",
        title="Backend Python Junior Engineer",
        company_name="Nebula Tech",
        description="APIs FastAPI e PostgreSQL.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Worldwide"],
        source_url="https://remoteok.com/remote-jobs/nebula-p32-1",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-p32-opp-1",
    )
    db_session.add(global_opp)
    db_session.commit()
    return alice, bob, global_opp


def test_phase032_interviews_assessments_contacts_isolation_and_urls(
    db_session, make_client
):
    alice, bob, global_opp = _seed_users_and_opportunity(db_session)

    client_alice = make_client(("10.20.0.10", 50000))
    csrf_alice = login_and_get_csrf(
        client_alice, "alice.p32@example.com", "StrongPassword123!"
    )
    client_bob = make_client(("10.20.0.11", 50000))
    csrf_bob = login_and_get_csrf(
        client_bob, "bob.p32@example.com", "StrongPassword123!"
    )

    app_alice = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(global_opp.id), "status": "interview"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    app_id = app_alice["id"]

    # TC-32-27: Índice único parcial de candidaturas ativas permanece íntegro
    dup_active = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(global_opp.id)},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert dup_active.status_code == 409

    now = datetime.now(UTC)
    iv_dt_1 = (now + timedelta(days=4)).replace(microsecond=0)
    iv_dt_2 = (now + timedelta(days=2)).replace(microsecond=0)

    # TC-32-01: Criar entrevistas futuras e manter Application.interview_at sincronizado com a mais próxima
    r_iv1 = client_alice.post(
        f"/api/v1/applications/{app_id}/interviews",
        json={
            "round_name": "Entrevista Técnica",
            "interview_format": "online",
            "scheduled_at": iv_dt_1.isoformat(),
            "duration_minutes": 60,
            "meeting_url": "https://meet.google.com/abc-defg-hij",
            "interviewers": "Carlos (Tech Lead)",
            "notes": "<script>alert(1)</script>Revisar FastAPI e SQL.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_iv1.status_code == 201, r_iv1.text
    iv1 = r_iv1.json()
    assert "<script>" not in iv1["notes"]

    detail_1 = client_alice.get(f"/api/v1/applications/{app_id}").json()
    assert datetime.fromisoformat(detail_1["interview_at"]) == iv_dt_1

    r_iv2 = client_alice.post(
        f"/api/v1/applications/{app_id}/interviews",
        json={
            "round_name": "Triagem RH",
            "interview_format": "phone",
            "scheduled_at": iv_dt_2.isoformat(),
            "duration_minutes": 30,
            "interviewers": "Marina (RH)",
            "notes": "Alinhamento inicial.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_iv2.status_code == 201
    iv2 = r_iv2.json()

    # Mais próxima agora deve ser iv_dt_2 (daqui 2 dias < 4 dias)
    detail_2 = client_alice.get(f"/api/v1/applications/{app_id}").json()
    assert datetime.fromisoformat(detail_2["interview_at"]) == iv_dt_2

    # TC-32-02: Editar notas e feedback de uma entrevista sem alterar outras rodadas
    upd_iv1 = client_alice.patch(
        f"/api/v1/applications/{app_id}/interviews/{iv1['id']}",
        json={
            "notes": "Revisar índices parciais PostgreSQL.",
            "feedback_received": "Boa base em APIs REST.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert upd_iv1.status_code == 200
    assert upd_iv1.json()["feedback_received"] == "Boa base em APIs REST."

    iv_list = client_alice.get(f"/api/v1/applications/{app_id}/interviews").json()
    assert len(iv_list) == 2
    iv2_check = next(i for i in iv_list if i["id"] == iv2["id"])
    assert iv2_check["notes"] == "Alinhamento inicial."
    assert iv2_check["feedback_received"] is None

    # TC-32-03: Isolamento multiusuário em entrevistas (404 uniforme)
    assert client_bob.get(f"/api/v1/applications/{app_id}/interviews").status_code == 404
    assert (
        client_bob.post(
            f"/api/v1/applications/{app_id}/interviews",
            json={
                "round_name": "Invasão",
                "interview_format": "online",
                "scheduled_at": iv_dt_1.isoformat(),
            },
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )
    assert (
        client_bob.patch(
            f"/api/v1/applications/{app_id}/interviews/{iv1['id']}",
            json={"notes": "Alteração indevida"},
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/applications/{app_id}/interviews/{iv1['id']}",
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )

    # TC-32-04 & TC-32-19: Contatos múltiplos (e-mail, LinkedIn) e edição preservando dados
    r_ct1 = client_alice.post(
        f"/api/v1/applications/{app_id}/contacts",
        json={
            "name": "Marina Souza",
            "role_title": "Tech Recruiter",
            "email": "marina@nebulatech.example.com",
            "linkedin_url": "https://www.linkedin.com/in/marina-souza-rh",
            "notes": "Contato inicial no LinkedIn.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_ct1.status_code == 201
    ct1 = r_ct1.json()
    assert ct1["email"] == "marina@nebulatech.example.com"

    r_ct2 = client_alice.post(
        f"/api/v1/applications/{app_id}/contacts",
        json={
            "name": "Carlos Mendes",
            "role_title": "Tech Lead",
            "email": "carlos@nebulatech.example.com",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_ct2.status_code == 201

    upd_ct1 = client_alice.patch(
        f"/api/v1/applications/{app_id}/contacts/{ct1['id']}",
        json={"role_title": "Senior Talent Acquisition"},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert upd_ct1.status_code == 200
    assert upd_ct1.json()["role_title"] == "Senior Talent Acquisition"
    assert upd_ct1.json()["linkedin_url"] == "https://www.linkedin.com/in/marina-souza-rh"
    assert upd_ct1.json()["email"] == "marina@nebulatech.example.com"

    # TC-32-05: Impedir leitura, edição e exclusão cruzada de contatos
    assert client_bob.get(f"/api/v1/applications/{app_id}/contacts").status_code == 404
    assert (
        client_bob.patch(
            f"/api/v1/applications/{app_id}/contacts/{ct1['id']}",
            json={"name": "Outro"},
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/applications/{app_id}/contacts/{ct1['id']}",
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )

    # TC-32-06 & TC-32-07: Múltiplos testes técnicos + entrega + feedback + isolamento
    due_1 = (now + timedelta(days=3)).replace(microsecond=0)
    due_2 = (now + timedelta(days=6)).replace(microsecond=0)
    r_asmt1 = client_alice.post(
        f"/api/v1/applications/{app_id}/assessments",
        json={
            "title": "Desafio Backend FastAPI",
            "description": "<b>Criar API REST</b> com testes unitários.",
            "platform": "GitHub",
            "instructions_url": "https://github.com/nebulatech/backend-challenge",
            "deadline_at": due_1.isoformat(),
            "status": "in_progress",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_asmt1.status_code == 201
    asmt1 = r_asmt1.json()
    assert "<b>" not in asmt1["description"]

    r_asmt2 = client_alice.post(
        f"/api/v1/applications/{app_id}/assessments",
        json={
            "title": "Questionário SQL PostgreSQL",
            "platform": "HackerRank",
            "instructions_url": "https://www.hackerrank.com/test/abc",
            "deadline_at": due_2.isoformat(),
            "status": "pending",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_asmt2.status_code == 201
    assert len(client_alice.get(f"/api/v1/applications/{app_id}/assessments").json()) == 2

    # Registrar entrega e depois feedback
    upd_asmt1 = client_alice.patch(
        f"/api/v1/applications/{app_id}/assessments/{asmt1['id']}",
        json={
            "submission_url": "https://github.com/alice/backend-challenge-sol",
            "status": "submitted",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert upd_asmt1.status_code == 200
    assert upd_asmt1.json()["status"] == "submitted"
    assert upd_asmt1.json()["submitted_at"] is not None

    fb_asmt1 = client_alice.patch(
        f"/api/v1/applications/{app_id}/assessments/{asmt1['id']}",
        json={
            "status": "feedback_received",
            "feedback": "Arquitetura limpa e boa cobertura de testes.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert fb_asmt1.status_code == 200
    assert fb_asmt1.json()["feedback"] == "Arquitetura limpa e boa cobertura de testes."

    # Isolamento de testes técnicos
    assert client_bob.get(f"/api/v1/applications/{app_id}/assessments").status_code == 404
    assert (
        client_bob.patch(
            f"/api/v1/applications/{app_id}/assessments/{asmt1['id']}",
            json={"feedback": "Hack"},
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )

    # TC-32-08: Rejeitar URLs inseguras, XSS schemes e destinos SSRF
    for bad_url in (
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "http://127.0.0.1:8000/internal",
        "http://169.254.169.254/latest/meta-data",
        "https://user:secret@example.com/meeting",
    ):
        assert (
            client_alice.post(
                f"/api/v1/applications/{app_id}/interviews",
                json={
                    "round_name": "Teste URL",
                    "interview_format": "online",
                    "scheduled_at": iv_dt_1.isoformat(),
                    "meeting_url": bad_url,
                },
                headers={"X-CSRF-Token": csrf_alice},
            ).status_code
            == 422
        )
        assert (
            client_alice.post(
                f"/api/v1/applications/{app_id}/assessments",
                json={"title": "Desafio URL", "instructions_url": bad_url},
                headers={"X-CSRF-Token": csrf_alice},
            ).status_code
            == 422
        )
        assert (
            client_alice.post(
                f"/api/v1/applications/{app_id}/assessments",
                json={"title": "Desafio Sub URL", "submission_url": bad_url},
                headers={"X-CSRF-Token": csrf_alice},
            ).status_code
            == 422
        )
        assert (
            client_alice.post(
                f"/api/v1/applications/{app_id}/contacts",
                json={"name": "Contato URL", "linkedin_url": bad_url},
                headers={"X-CSRF-Token": csrf_alice},
            ).status_code
            == 422
        )


def test_phase032_agenda_reschedule_cancel_complete_and_timezone(
    db_session, make_client
):
    alice, bob, _ = _seed_users_and_opportunity(db_session)
    client_alice = make_client(("10.20.0.20", 50000))
    csrf_alice = login_and_get_csrf(
        client_alice, "alice.p32@example.com", "StrongPassword123!"
    )
    client_bob = make_client(("10.20.0.21", 50000))
    csrf_bob = login_and_get_csrf(
        client_bob, "bob.p32@example.com", "StrongPassword123!"
    )

    now = datetime.now(UTC)

    # Candidatura 1: possui entrevista e desafio estruturados (não deve duplicar campos legados!)
    app1 = client_alice.post(
        "/api/v1/applications",
        json={
            "role_title": "Dev Python Backend Jr",
            "company_name": "Alpha Systems",
            "status": "interview",
        },
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # Candidatura 2: possui apenas prazos legados sem entidades filhas estruturadas (fallback sem duplicação)
    legacy_asmt_due = (now + timedelta(hours=10)).replace(microsecond=0)
    app2 = client_alice.post(
        "/api/v1/applications",
        json={
            "role_title": "Estágio Engenharia Backend",
            "company_name": "Beta Labs",
            "status": "assessment",
            "assessment_deadline_at": legacy_asmt_due.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # Candidatura 3 do Bob (não pode vazar na agenda da Alice)
    app_bob = client_bob.post(
        "/api/v1/applications",
        json={"role_title": "Vaga Privada Bob", "status": "interview"},
        headers={"X-CSRF-Token": csrf_bob},
    ).json()
    client_bob.post(
        f"/api/v1/applications/{app_bob['id']}/interviews",
        json={
            "round_name": "Entrevista Secreta Bob",
            "interview_format": "online",
            "scheduled_at": (now + timedelta(hours=5)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_bob},
    )

    # TC-32-25: Rejeitar datetime naive sem offset e converter -03:00 para UTC corretamente
    naive_resp = client_alice.post(
        f"/api/v1/applications/{app1['id']}/interviews",
        json={
            "round_name": "Entrevista Sem TZ",
            "interview_format": "online",
            "scheduled_at": "2026-11-25T15:00:00",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert naive_resp.status_code == 422

    # Offset -03:00 -> 15:00-03:00 == 18:00Z em UTC (dentro de 24h)
    from datetime import timezone

    imminent_utc = (now + timedelta(hours=6)).replace(microsecond=0)
    brt_tz = timezone(timedelta(hours=-3))
    imminent_brt_iso = imminent_utc.astimezone(brt_tz).isoformat()

    r_iv_tz = client_alice.post(
        f"/api/v1/applications/{app1['id']}/interviews",
        json={
            "round_name": "Rodada Técnica BRT",
            "interview_format": "online",
            "scheduled_at": imminent_brt_iso,
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert r_iv_tz.status_code == 201
    iv_tz = r_iv_tz.json()
    returned_dt = datetime.fromisoformat(iv_tz["scheduled_at"])
    assert returned_dt.tzinfo is not None
    assert returned_dt.astimezone(UTC) == imminent_utc

    # Criar desafio vencido (-1 dia) na app1 para testar vencidos + iminentes
    overdue_asmt_due = (now - timedelta(days=1)).replace(microsecond=0)
    client_alice.post(
        f"/api/v1/applications/{app1['id']}/assessments",
        json={
            "title": "Desafio Vencido",
            "deadline_at": overdue_asmt_due.isoformat(),
            "status": "pending",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )

    # TC-32-09, TC-32-10, TC-32-11: Agenda cronológica, sem duplicatas, vencidos & 24h, sem dados do Bob
    agenda_resp = client_alice.get("/api/v1/applications/agenda?days=30")
    assert agenda_resp.status_code == 200
    agenda = agenda_resp.json()
    events = agenda["events"]

    # Ordem cronológica real pelo timestamp
    timestamps = [datetime.fromisoformat(e["scheduled_at"]).timestamp() for e in events]
    assert timestamps == sorted(timestamps)

    # Nenhuma entrevista do Bob aparece
    assert all(e["application_id"] != app_bob["id"] for e in events)

    # Não duplica `interview_at` da app1 (somente 1 evento de entrevista para app1)
    app1_interviews = [
        e for e in events if e["application_id"] == app1["id"] and e["event_type"] == "interview"
    ]
    assert len(app1_interviews) == 1
    assert app1_interviews[0]["is_imminent"] is True
    assert app1_interviews[0]["urgency"] == "imminent"

    # Não duplica `assessment_deadline_at` da app1 (apenas 1 estruturado vencido), enquanto app2 usa legado 1 vez
    app1_asmts = [
        e for e in events if e["application_id"] == app1["id"] and e["event_type"] == "assessment"
    ]
    assert len(app1_asmts) == 1
    assert app1_asmts[0]["is_overdue"] is True
    assert app1_asmts[0]["urgency"] == "overdue"

    app2_asmts = [
        e for e in events if e["application_id"] == app2["id"] and e["event_type"] == "assessment"
    ]
    assert len(app2_asmts) == 1
    assert app2_asmts[0]["source_kind"] == "legacy"
    assert app2_asmts[0]["is_imminent"] is True

    # TC-32-20: Reagendar entrevista mantendo-a scheduled e na agenda
    new_dt = (now + timedelta(days=3)).replace(microsecond=0)
    resched = client_alice.patch(
        f"/api/v1/applications/{app1['id']}/interviews/{iv_tz['id']}",
        json={"scheduled_at": new_dt.isoformat()},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert resched.status_code == 200
    resched_body = resched.json()
    assert resched_body["status"] == "scheduled"
    assert datetime.fromisoformat(resched_body["previous_scheduled_at"]).astimezone(UTC) == imminent_utc
    assert datetime.fromisoformat(resched_body["scheduled_at"]).astimezone(UTC) == new_dt

    app1_after_resched = client_alice.get(f"/api/v1/applications/{app1['id']}").json()
    assert datetime.fromisoformat(app1_after_resched["interview_at"]).astimezone(UTC) == new_dt
    # Ainda presente na agenda com a nova data!
    agenda_after_resched = client_alice.get("/api/v1/applications/agenda?days=30").json()
    ev_resched = next(
        e for e in agenda_after_resched["events"] if e["entity_id"] == iv_tz["id"]
    )
    assert datetime.fromisoformat(ev_resched["scheduled_at"]).astimezone(UTC) == new_dt

    # Criar outra entrevista e testá-la sendo cancelada e a primeira sendo concluída
    extra_dt = (now + timedelta(days=5)).replace(microsecond=0)
    iv_extra = client_alice.post(
        f"/api/v1/applications/{app1['id']}/interviews",
        json={
            "round_name": "Entrevista Cancelável",
            "interview_format": "phone",
            "scheduled_at": extra_dt.isoformat(),
        },
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # TC-32-21: Cancelar entrevista retira da agenda futura
    cancel_resp = client_alice.patch(
        f"/api/v1/applications/{app1['id']}/interviews/{iv_extra['id']}",
        json={"status": "cancelled"},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    agenda_after_cancel = client_alice.get("/api/v1/applications/agenda?days=30").json()
    assert all(e["entity_id"] != iv_extra["id"] for e in agenda_after_cancel["events"])

    # TC-32-22: Concluir entrevista registra completed_at, atualiza last_external_interaction_at e limpa interview_at sem outras futuras
    completed_dt = (now - timedelta(hours=1)).replace(microsecond=0)
    comp_resp = client_alice.patch(
        f"/api/v1/applications/{app1['id']}/interviews/{iv_tz['id']}",
        json={
            "status": "completed",
            "completed_at": completed_dt.isoformat(),
            "feedback_received": "Conversa muito produtiva sobre PostgreSQL.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert comp_resp.status_code == 200
    assert datetime.fromisoformat(comp_resp.json()["completed_at"]).astimezone(UTC) == completed_dt

    app1_after_complete = client_alice.get(f"/api/v1/applications/{app1['id']}").json()
    assert app1_after_complete["interview_at"] is None
    assert (
        datetime.fromisoformat(app1_after_complete["last_external_interaction_at"]).astimezone(UTC)
        == completed_dt
    )
    assert app1_after_complete["last_external_interaction_type"] == "interview"


def test_phase032_stale_detection_followup_cascade_and_regression_isolation(
    db_session, make_client
):
    alice, bob, global_opp = _seed_users_and_opportunity(db_session)
    client_alice = make_client(("10.20.0.30", 50000))
    csrf_alice = login_and_get_csrf(
        client_alice, "alice.p32@example.com", "StrongPassword123!"
    )
    client_bob = make_client(("10.20.0.31", 50000))
    csrf_bob = login_and_get_csrf(
        client_bob, "bob.p32@example.com", "StrongPassword123!"
    )

    now = datetime.now(UTC)

    # 1. `applied` há 12 dias (> 10d) -> deve aparecer em /stale
    app_applied_stale = client_alice.post(
        "/api/v1/applications",
        json={
            "opportunity_id": str(global_opp.id),
            "status": "applied",
            "applied_at": (now - timedelta(days=12)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # 2. `applied` há 8 dias (<= 10d) -> NÃO deve aparecer no critério padrão
    app_applied_fresh = client_alice.post(
        "/api/v1/applications",
        json={
            "role_title": "Dev API Recente",
            "company_name": "Fresh Co",
            "status": "applied",
            "applied_at": (now - timedelta(days=8)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # 3. `interview` com entrevista concluída há 9 dias (> 7d) e sem futura marcada -> deve aparecer
    app_iv_stale = client_alice.post(
        "/api/v1/applications",
        json={"role_title": "Engenheiro Full Stack", "company_name": "Orbit Co", "status": "interview"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    client_alice.post(
        f"/api/v1/applications/{app_iv_stale['id']}/interviews",
        json={
            "round_name": "Entrevista com Tech Lead",
            "interview_format": "online",
            "scheduled_at": (now - timedelta(days=9)).isoformat(),
            "completed_at": (now - timedelta(days=9)).isoformat(),
            "status": "completed",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )

    # 4. `interview` com entrevista futura marcada -> NÃO deve aparecer em /stale (TC-32-17)
    app_iv_future = client_alice.post(
        "/api/v1/applications",
        json={"role_title": "Dev Python Futuro", "company_name": "Future Corp", "status": "interview"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    client_alice.post(
        f"/api/v1/applications/{app_iv_future['id']}/interviews",
        json={
            "round_name": "Final Gestor",
            "interview_format": "online",
            "scheduled_at": (now + timedelta(days=2)).isoformat(),
            "status": "scheduled",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )

    # 5. Encerrada antiga -> NUNCA deve aparecer em /stale (TC-32-16)
    app_closed_old = client_alice.post(
        "/api/v1/applications",
        json={
            "role_title": "Vaga Encerrada Antiga",
            "status": "rejected",
            "applied_at": (now - timedelta(days=30)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # 6. `interested` e `interview` sem referência real -> NUNCA devem aparecer em /stale
    app_interested = client_alice.post(
        "/api/v1/applications",
        json={"role_title": "Em Triagem", "status": "interested"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    app_iv_no_ref = client_alice.post(
        "/api/v1/applications",
        json={"role_title": "Entrevista Sem Data", "status": "interview"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # 7. Candidatura antiga do Bob (isolamento estrito)
    client_bob.post(
        "/api/v1/applications",
        json={
            "role_title": "Bob Stale App",
            "status": "applied",
            "applied_at": (now - timedelta(days=20)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_bob},
    )

    # TC-32-14: Editar notas ou cadastrar contato atualiza updated_at mas NÃO altera elegibilidade nem contador de estagnação
    client_alice.put(
        f"/api/v1/applications/{app_applied_stale['id']}",
        json={"notes": "Anotação interna editada hoje."},
        headers={"X-CSRF-Token": csrf_alice},
    )
    client_alice.post(
        f"/api/v1/applications/{app_applied_stale['id']}/contacts",
        json={"name": "Recrutadora Ana", "role_title": "Recruiter"},
        headers={"X-CSRF-Token": csrf_alice},
    )

    # TC-32-12, TC-32-13, TC-32-16, TC-32-17
    stale_resp = client_alice.get("/api/v1/applications/stale?stale_days=7")
    assert stale_resp.status_code == 200
    stale_body = stale_resp.json()
    stale_ids = {item["application_id"] for item in stale_body["items"]}
    assert stale_ids == {app_applied_stale["id"], app_iv_stale["id"]}
    assert app_applied_fresh["id"] not in stale_ids
    assert app_iv_future["id"] not in stale_ids
    assert app_closed_old["id"] not in stale_ids
    assert app_interested["id"] not in stale_ids
    assert app_iv_no_ref["id"] not in stale_ids

    applied_item = next(
        i for i in stale_body["items"] if i["application_id"] == app_applied_stale["id"]
    )
    assert applied_item["days_without_external_interaction"] >= 12
    assert "ghosting" not in (applied_item["notice"] + applied_item["recommended_follow_up"]).lower()

    # TC-32-18: Follow-up determinístico (com contato real vs neutro sem inventar)
    tpl_with_contact = client_alice.get(
        f"/api/v1/applications/{app_applied_stale['id']}/follow-up-template"
    ).json()
    assert "Olá, Recrutadora," in tpl_with_contact["message"]
    assert "Nebula Tech" in tpl_with_contact["message"]
    assert "Backend Python Junior Engineer" in tpl_with_contact["message"]

    tpl_neutral = client_alice.get(
        f"/api/v1/applications/{app_interested['id']}/follow-up-template"
    ).json()
    assert tpl_neutral["recipient_name"] is None
    assert tpl_neutral["message"].startswith("Olá,\n")
    assert "entrevista" not in tpl_neutral["message"].lower()

    tpl_iv = client_alice.get(
        f"/api/v1/applications/{app_iv_stale['id']}/follow-up-template"
    ).json()
    assert "Entrevista com Tech Lead" in tpl_iv["message"]
    assert client_bob.get(
        f"/api/v1/applications/{app_applied_stale['id']}/follow-up-template"
    ).status_code == 404

    # TC-32-15: Registro explícito de interação externa recalcula / remove da lista de estagnação
    future_ext = client_alice.post(
        f"/api/v1/applications/{app_applied_stale['id']}/external-interaction",
        json={
            "interaction_type": "email",
            "interaction_at": (now + timedelta(hours=2)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert future_ext.status_code == 422

    ext_ok = client_alice.post(
        f"/api/v1/applications/{app_applied_stale['id']}/external-interaction",
        json={
            "interaction_type": "linkedin",
            "interaction_at": (now - timedelta(hours=1)).isoformat(),
            "note": "Recrutadora respondeu informando próxima semana.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert ext_ok.status_code == 200
    assert ext_ok.json()["last_external_interaction_type"] == "linkedin"

    stale_after_ext = client_alice.get("/api/v1/applications/stale?stale_days=7").json()
    assert app_applied_stale["id"] not in {i["application_id"] for i in stale_after_ext["items"]}

    # TC-32-23 & TC-32-24 & TC-32-28: Exclusão em cascata atômica preserva oportunidade global e dados de Bob
    client_alice.post(
        f"/api/v1/applications/{app_applied_stale['id']}/assessments",
        json={"title": "Desafio Cascata"},
        headers={"X-CSRF-Token": csrf_alice},
    )
    app_stale_uuid = uuid.UUID(app_applied_stale["id"])

    del_no_confirm = client_alice.delete(
        f"/api/v1/applications/{app_applied_stale['id']}",
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert del_no_confirm.status_code == 409

    del_confirm = client_alice.delete(
        f"/api/v1/applications/{app_applied_stale['id']}?confirm_history_deletion=true",
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert del_confirm.status_code == 204

    db_session.expire_all()
    assert db_session.get(Opportunity, global_opp.id) is not None
    assert (
        db_session.scalars(
            select(ApplicationContact).where(
                ApplicationContact.application_id == app_stale_uuid
            )
        ).all()
        == []
    )
    assert (
        db_session.scalars(
            select(ApplicationAssessment).where(
                ApplicationAssessment.application_id == app_stale_uuid
            )
        ).all()
        == []
    )
    assert (
        db_session.scalars(
            select(ApplicationStatusHistory).where(
                ApplicationStatusHistory.application_id == app_stale_uuid
            )
        ).all()
        == []
    )
    assert client_bob.get("/api/v1/applications").json()["total"] == 1
    assert client_alice.get("/api/v1/applications/kanban").json()["indicators"]["total_count"] >= 4


def test_phase032_migration_0009_upgrade_and_downgrade_preserves_existing_data(
    tmp_path,
):
    mig_url = resolve_test_database_url(tmp_path)
    connect_args = {"check_same_thread": False} if mig_url.startswith("sqlite") else {}
    engine = create_engine(mig_url, connect_args=connect_args, future=True)

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", mig_url)

    script_dir = ScriptDirectory.from_config(alembic_cfg)
    assert len(script_dir.get_heads()) == 1
    assert script_dir.get_revision("0009_followup_interview_logs") is not None

    user_id = uuid.uuid4()
    app_id = uuid.uuid4()
    now = datetime.now(UTC)

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "0008_active_app_uniq")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, display_name, password_hash, account_status, is_admin, created_at, updated_at) "
                "VALUES (:id, :email, :name, :pwd, 'active', :is_admin, :now, :now)"
            ),
            {
                "id": str(user_id) if engine.dialect.name == "sqlite" else user_id,
                "email": "mig0009@example.com",
                "name": "Migration 0009 Tester",
                "pwd": "hash",
                "is_admin": False,
                "now": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO applications (id, user_id, opportunity_id, role_title, employment_type, work_mode, seniority_level, status, created_at, updated_at) "
                "VALUES (:id, :uid, NULL, 'Dev Backend Jr', 'pj', 'remote', 'junior', 'applied', :now, :now)"
            ),
            {
                "id": str(app_id) if engine.dialect.name == "sqlite" else app_id,
                "uid": str(user_id) if engine.dialect.name == "sqlite" else user_id,
                "now": now,
            },
        )

    # Upgrade incremental 0008 -> 0009 (head)
    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "head")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "application_interviews",
        "application_assessments",
        "application_contacts",
    }.issubset(tables)

    app_cols = {col["name"] for col in inspector.get_columns("applications")}
    assert {
        "last_external_interaction_at",
        "last_external_interaction_type",
        "last_external_interaction_note",
    }.issubset(app_cols)

    app_indexes = {idx["name"] for idx in inspector.get_indexes("applications")}
    assert "uq_active_application_per_user_opp" in app_indexes

    # Insere registros nas tabelas da 0009 para comprovar que o downgrade remove somente esses objetos sem perder a candidatura prévia
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO application_contacts (id, application_id, name, created_at, updated_at) "
                "VALUES (:id, :app_id, 'Contato Teste', :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()) if engine.dialect.name == "sqlite" else uuid.uuid4(),
                "app_id": str(app_id) if engine.dialect.name == "sqlite" else app_id,
                "now": now,
            },
        )

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "0008_active_app_uniq")

    tables_after_down = set(inspect(engine).get_table_names())
    assert "application_interviews" not in tables_after_down
    assert "application_assessments" not in tables_after_down
    assert "application_contacts" not in tables_after_down

    with engine.connect() as conn:
        apps_count = conn.execute(text("SELECT COUNT(*) FROM applications")).scalar_one()
        assert apps_count == 1

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "base")
    engine.dispose()


def test_phase0321_external_interaction_temporal_monotonicity_and_history(
    db_session, make_client
):
    from datetime import timezone

    from app.services.application_process_service import get_stale_applications

    alice, _, global_opp = _seed_users_and_opportunity(db_session)
    client = make_client(("10.20.0.40", 50000))
    csrf = login_and_get_csrf(client, "alice.p32@example.com", "StrongPassword123!")

    now = datetime.now(UTC).replace(microsecond=0)
    d_minus_1 = now - timedelta(days=1)
    d_minus_15 = now - timedelta(days=15)

    app_data = client.post(
        "/api/v1/applications",
        json={
            "opportunity_id": str(global_opp.id),
            "status": "interview",
            "applied_at": (now - timedelta(days=20)).isoformat(),
        },
        headers={"X-CSRF-Token": csrf},
    ).json()
    app_id = app_data["id"]

    # TC-0321-03: Primeira interação registrada preenche os 3 campos
    first_resp = client.post(
        f"/api/v1/applications/{app_id}/external-interaction",
        json={
            "interaction_type": "email",
            "interaction_at": d_minus_15.isoformat(),
            "note": "E-mail inicial recebido há 15 dias.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert first_resp.status_code == 200, first_resp.text
    first_body = first_resp.json()
    assert datetime.fromisoformat(first_body["last_external_interaction_at"]).astimezone(UTC) == d_minus_15
    assert first_body["last_external_interaction_type"] == "email"
    assert first_body["last_external_interaction_note"] == "E-mail inicial recebido há 15 dias."

    # TC-0321-02: Nova interação mais recente (conclusão de entrevista em D-1) atualiza os 3 campos
    iv_resp = client.post(
        f"/api/v1/applications/{app_id}/interviews",
        json={
            "round_name": "Entrevista Técnica D-1",
            "interview_format": "online",
            "scheduled_at": d_minus_1.isoformat(),
            "completed_at": d_minus_1.isoformat(),
            "status": "completed",
            "feedback_received": "Conversa recente muito positiva.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert iv_resp.status_code == 201
    after_iv = client.get(f"/api/v1/applications/{app_id}").json()
    assert datetime.fromisoformat(after_iv["last_external_interaction_at"]).astimezone(UTC) == d_minus_1
    assert after_iv["last_external_interaction_type"] == "interview"
    assert "Entrevista Técnica D-1" in after_iv["last_external_interaction_note"]
    history_count_before_retro = len(after_iv["status_history"])
    saved_note_d1 = after_iv["last_external_interaction_note"]

    # TC-0321-01 & TC-0321-07: Registro retroativo em D-15 NÃO sobrescreve D-1 no resumo,
    # mas preserva entrada histórica com data efetiva real D-15 sem transição artificial de status.
    d_minus_14 = now - timedelta(days=14)
    retro_resp = client.post(
        f"/api/v1/applications/{app_id}/external-interaction",
        json={
            "interaction_type": "phone",
            "interaction_at": d_minus_14.isoformat(),
            "note": "Ligação retroativa esquecida de D-14.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert retro_resp.status_code == 200
    retro_body = retro_resp.json()
    assert datetime.fromisoformat(retro_body["last_external_interaction_at"]).astimezone(UTC) == d_minus_1
    assert retro_body["last_external_interaction_type"] == "interview"
    assert retro_body["last_external_interaction_note"] == saved_note_d1

    hist = retro_body["status_history"]
    assert len(hist) == history_count_before_retro + 1
    retro_entries = [
        h for h in hist if "Ligação retroativa esquecida de D-14." in (h["note"] or "")
    ]
    assert len(retro_entries) == 1
    assert datetime.fromisoformat(retro_entries[0]["changed_at"]).astimezone(UTC) == d_minus_14
    assert retro_entries[0]["from_status"] == "interview"
    assert retro_entries[0]["to_status"] == "interview"
    # Histórico ordenado decrescentemente por data efetiva real
    hist_timestamps = [datetime.fromisoformat(h["changed_at"]).timestamp() for h in hist]
    assert hist_timestamps == sorted(hist_timestamps, reverse=True)

    # TC-0321-05: Detecção de estagnação continua usando D-1 (nenhum falso alerta após registro retroativo)
    stale_now = client.get("/api/v1/applications/stale?stale_days=7").json()
    assert all(item["application_id"] != app_id for item in stale_now["items"])
    # Em D+7 (8 dias após D-1), calcula exatamente ~8 dias (referência D-1, não D-14)
    stale_future = get_stale_applications(
        db_session, alice, stale_days=7, now=now + timedelta(days=7)
    )
    app_stale = next(i for i in stale_future.items if str(i.application_id) == app_id)
    assert app_stale.reference_timestamp_at.astimezone(UTC) == d_minus_1
    assert app_stale.days_without_external_interaction == 8

    # TC-0321-04: Timestamp idêntico (`==`) atualiza os 3 campos como unidade atômica determinística
    same_ts_resp = client.post(
        f"/api/v1/applications/{app_id}/external-interaction",
        json={
            "interaction_type": "linkedin",
            "interaction_at": d_minus_1.isoformat(),
            "note": "Mensagem no LinkedIn no mesmo instante.",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert same_ts_resp.status_code == 200
    same_body = same_ts_resp.json()
    assert datetime.fromisoformat(same_body["last_external_interaction_at"]).astimezone(UTC) == d_minus_1
    assert same_body["last_external_interaction_type"] == "linkedin"
    assert same_body["last_external_interaction_note"] == "Mensagem no LinkedIn no mesmo instante."

    # TC-0321-06: Normalização e comparação por instante real UTC entre offsets distintos
    app_tz = client.post(
        "/api/v1/applications",
        json={"role_title": "Dev Timezone Test", "status": "applied"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    tz_brt = timezone(timedelta(hours=-3))
    base_utc = (now - timedelta(hours=4)).replace(microsecond=0)
    older_brt = (base_utc - timedelta(seconds=1)).astimezone(tz_brt)
    newer_brt = (base_utc + timedelta(seconds=1)).astimezone(tz_brt)

    r_base = client.post(
        f"/api/v1/applications/{app_tz['id']}/external-interaction",
        json={"interaction_type": "email", "interaction_at": base_utc.isoformat(), "note": "Base UTC"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_base.status_code == 200

    # 1 segundo antes em -03:00 -> não sobrescreve
    r_older_tz = client.post(
        f"/api/v1/applications/{app_tz['id']}/external-interaction",
        json={"interaction_type": "phone", "interaction_at": older_brt.isoformat(), "note": "Anterior BRT"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_older_tz.status_code == 200
    assert r_older_tz.json()["last_external_interaction_type"] == "email"
    assert r_older_tz.json()["last_external_interaction_note"] == "Base UTC"

    # 1 segundo depois em -03:00 -> atualiza corretamente para UTC normalizado
    r_newer_tz = client.post(
        f"/api/v1/applications/{app_tz['id']}/external-interaction",
        json={"interaction_type": "linkedin", "interaction_at": newer_brt.isoformat(), "note": "Posterior BRT"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_newer_tz.status_code == 200
    assert (
        datetime.fromisoformat(r_newer_tz.json()["last_external_interaction_at"]).astimezone(UTC)
        == base_utc + timedelta(seconds=1)
    )
    assert r_newer_tz.json()["last_external_interaction_type"] == "linkedin"
    assert r_newer_tz.json()["last_external_interaction_note"] == "Posterior BRT"


def test_phase0321_concurrent_external_interaction_monotonicity(
    db_engine, db_session, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time

    from sqlalchemy import func
    from sqlalchemy.orm import sessionmaker

    from app.models.application import Application, ApplicationStatus
    from app.models.user import User
    from app.schemas.application import ApplicationCreate, ExternalInteractionRecordRequest
    import app.services.application_process_service as proc_svc
    from app.services.application_service import create_application

    user = create_user_account(
        db_session,
        email="race.ext@example.com",
        display_name="Race External",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.flush()

    now = datetime.now(UTC).replace(microsecond=0)
    d_minus_20 = now - timedelta(days=20)
    d_minus_15 = now - timedelta(days=15)
    d_minus_1 = now - timedelta(days=1)

    app_dto = create_application(
        db_session,
        user,
        ApplicationCreate(role_title="Dev Concorrencia Interacao", status=ApplicationStatus.INTERVIEW),
    )
    proc_svc.record_external_interaction(
        db_session,
        user,
        app_dto.id,
        ExternalInteractionRecordRequest(
            interaction_type="email",
            interaction_at=d_minus_20,
            note="Interação inicial D-20.",
        ),
    )
    user_id = user.id
    app_id = app_dto.id

    SessionFactory = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # Barreira garante que ambas as sessões leiam D-20 antes que qualquer uma aplique o UPDATE,
    # e força a transação retroativa (D-15) a finalizar depois da mais recente (D-1).
    read_barrier = threading.Barrier(2, timeout=10)
    orig_apply = proc_svc._apply_monotonic_external_interaction_summary

    def _synchronized_apply(db, **kwargs):
        interaction_at = kwargs["interaction_at"]
        if db_engine.dialect.name == "sqlite":
            # Libera eventuais locks de leitura antes da barreira em SQLite
            db.commit()
        read_barrier.wait()
        if interaction_at == d_minus_15:
            time.sleep(0.08)
        return orig_apply(db, **kwargs)

    monkeypatch.setattr(
        proc_svc, "_apply_monotonic_external_interaction_summary", _synchronized_apply
    )

    def _worker(interaction_at: datetime, interaction_type: str, note: str) -> None:
        thread_db = SessionFactory()
        try:
            thread_user = thread_db.execute(
                select(User).where(User.id == user_id)
            ).scalar_one()
            proc_svc.record_external_interaction(
                thread_db,
                thread_user,
                app_id,
                ExternalInteractionRecordRequest(
                    interaction_type=interaction_type,
                    interaction_at=interaction_at,
                    note=note,
                ),
            )
        finally:
            thread_db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_recent = pool.submit(_worker, d_minus_1, "interview", "Contato recente D-1")
        f_retro = pool.submit(_worker, d_minus_15, "phone", "Contato retroativo D-15")
        f_recent.result(timeout=15)
        f_retro.result(timeout=15)

    monkeypatch.undo()
    db_session.expire_all()
    final_app = db_session.get(Application, app_id)
    assert final_app is not None
    assert proc_svc.ensure_utc(final_app.last_external_interaction_at) == d_minus_1
    assert final_app.last_external_interaction_type == "interview"
    assert final_app.last_external_interaction_note == "Contato recente D-1"

    hist_count = db_session.scalar(
        select(func.count(ApplicationStatusHistory.id)).where(
            ApplicationStatusHistory.application_id == app_id
        )
    )
    # 1 inicial + D-20 + D-1 + D-15 = 4 registros preservados
    assert hist_count == 4


def test_phase0321_same_user_cross_application_child_isolation(db_session, make_client):
    _seed_users_and_opportunity(db_session)
    client = make_client(("10.20.0.41", 50000))
    csrf = login_and_get_csrf(client, "alice.p32@example.com", "StrongPassword123!")

    app_a = client.post(
        "/api/v1/applications",
        json={"role_title": "Candidatura A", "company_name": "Empresa A", "status": "interview"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    app_b = client.post(
        "/api/v1/applications",
        json={"role_title": "Candidatura B", "company_name": "Empresa B", "status": "interview"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    app_a_id = app_a["id"]
    app_b_id = app_b["id"]

    now = datetime.now(UTC).replace(microsecond=0)

    # TC-0321-08: Entrevista pertence apenas a app_a; acesso via app_b retorna 404 sem alterações
    iv_a = client.post(
        f"/api/v1/applications/{app_a_id}/interviews",
        json={
            "round_name": "Entrevista Original A",
            "interview_format": "online",
            "scheduled_at": (now + timedelta(days=2)).isoformat(),
            "notes": "Nota original da A",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()

    assert client.get(f"/api/v1/applications/{app_b_id}/interviews").json() == []
    assert (
        client.patch(
            f"/api/v1/applications/{app_b_id}/interviews/{iv_a['id']}",
            json={"notes": "Sobrescrita cruzada"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/applications/{app_b_id}/interviews/{iv_a['id']}",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    iv_list_a = client.get(f"/api/v1/applications/{app_a_id}/interviews").json()
    assert len(iv_list_a) == 1
    assert iv_list_a[0]["notes"] == "Nota original da A"

    # TC-0321-09: Teste técnico pertence apenas a app_a; acesso via app_b retorna 404 sem alterações
    asmt_a = client.post(
        f"/api/v1/applications/{app_a_id}/assessments",
        json={"title": "Desafio Original A", "notes": "Nota desafio A"},
        headers={"X-CSRF-Token": csrf},
    ).json()

    assert client.get(f"/api/v1/applications/{app_b_id}/assessments").json() == []
    assert (
        client.patch(
            f"/api/v1/applications/{app_b_id}/assessments/{asmt_a['id']}",
            json={"feedback": "Feedback cruzado"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/applications/{app_b_id}/assessments/{asmt_a['id']}",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    asmt_list_a = client.get(f"/api/v1/applications/{app_a_id}/assessments").json()
    assert len(asmt_list_a) == 1
    assert asmt_list_a[0]["notes"] == "Nota desafio A"

    # TC-0321-10: Contato pertence apenas a app_a; acesso via app_b retorna 404 sem alterações
    ct_a = client.post(
        f"/api/v1/applications/{app_a_id}/contacts",
        json={
            "name": "Contato Original A",
            "email": "contato.a@example.com",
            "notes": "Contato apenas da A",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()

    assert client.get(f"/api/v1/applications/{app_b_id}/contacts").json() == []
    assert (
        client.patch(
            f"/api/v1/applications/{app_b_id}/contacts/{ct_a['id']}",
            json={"name": "Nome Invasivo"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/applications/{app_b_id}/contacts/{ct_a['id']}",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    ct_list_a = client.get(f"/api/v1/applications/{app_a_id}/contacts").json()
    assert len(ct_list_a) == 1
    assert ct_list_a[0]["name"] == "Contato Original A"
    assert ct_list_a[0]["notes"] == "Contato apenas da A"
