from datetime import UTC, datetime, timedelta

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


def login_and_get_csrf(client, email: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def test_phase031_applications_crud_kanban_history_isolation_and_integrity(
    db_session, make_client
):
    sources = {s.slug: s for s in ensure_default_sources(db_session)}
    src = sources["remote_ok"]

    alice = create_user_account(
        db_session,
        email="alice.app@example.com",
        display_name="Alice Candidata",
        password="StrongPassword123!",
        is_admin=False,
    )
    bob = create_user_account(
        db_session,
        email="bob.app@example.com",
        display_name="Bob Candidato",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.flush()

    now = datetime.now(UTC)
    global_opp = Opportunity(
        source_id=src.id,
        external_id="rk-app-301",
        title="Backend Python Junior Developer",
        company_name="CloudNova Inc.",
        description="Build FastAPI microservices and Postgres integrations.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        location_text="Brasil / Worldwide",
        eligible_countries=["Worldwide"],
        technologies=["Python", "FastAPI", "PostgreSQL"],
        source_url="https://remoteok.com/remote-jobs/backend-python-301",
        application_url="https://apply.example.org/cloudnova-301",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-app-301",
    )
    bob_private_opp = Opportunity(
        source_id=None,
        created_by_user_id=bob.id,
        external_id=None,
        title="Oportunidade Privada do Bob",
        company_name="Cliente Secreto",
        description="Projeto privado apenas do Bob.",
        opportunity_type=OpportunityType.FREELANCE.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.FREELANCE.value,
        work_mode=WorkMode.REMOTE.value,
        eligible_countries=["Brasil"],
        source_url="https://cliente-bob.example.org/vaga",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-bob-priv-1",
    )
    alice_manual_opp = Opportunity(
        source_id=None,
        created_by_user_id=alice.id,
        external_id=None,
        title="Vaga Local Java Júnior",
        company_name="Alpha Tech",
        description="Atuação em Java e Spring Boot.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.HYBRID.value,
        location_text="Curitiba, PR",
        eligible_countries=["Brasil"],
        source_url="https://alphatech.example.org/vaga-java",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-alice-priv-2",
    )
    db_session.add_all([global_opp, bob_private_opp, alice_manual_opp])
    db_session.commit()

    client_alice = make_client(("10.10.0.50", 50000))
    csrf_alice = login_and_get_csrf(client_alice, "alice.app@example.com", "StrongPassword123!")

    # 1. Criação vinculada a oportunidade global preservando snapshots (não modifica oportunidade global)
    resp_create_linked = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(global_opp.id)},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert resp_create_linked.status_code == 201
    linked_app = resp_create_linked.json()
    assert linked_app["opportunity_id"] == str(global_opp.id)
    assert linked_app["role_title"] == "Backend Python Junior Developer"
    assert linked_app["company_name"] == "CloudNova Inc."
    assert linked_app["source_name"] == "Remote OK"
    assert linked_app["source_url"] == "https://remoteok.com/remote-jobs/backend-python-301"
    assert linked_app["application_url"] == "https://apply.example.org/cloudnova-301"
    assert linked_app["location_text"] == "Brasil / Worldwide"
    assert linked_app["employment_type"] == "pj"
    assert linked_app["work_mode"] == "remote"
    assert linked_app["seniority_level"] == "junior"
    assert linked_app["status"] == "interested"
    assert linked_app["status_label"] == "Interesse"
    assert linked_app["is_closed"] is False
    assert linked_app["applied_at"] is None  # nunca envia candidatura automaticamente!
    assert len(linked_app["status_history"]) == 1
    assert linked_app["status_history"][0]["from_status"] is None
    assert linked_app["status_history"][0]["to_status"] == "interested"

    # Catálogo reflete tracked_application_id apenas para Alice
    opp_list_alice = client_alice.get("/api/v1/opportunities?seniority=junior&page_size=20").json()
    global_card_alice = next(i for i in opp_list_alice["items"] if i["id"] == str(global_opp.id))
    assert global_card_alice["tracked_application_id"] == linked_app["id"]
    assert global_card_alice["tracked_application_status"] == "interested"

    # 2. Prevenção de duplicação acidental para oportunidade com candidatura ativa
    dup_resp = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(global_opp.id)},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert dup_resp.status_code == 409

    # 3. Bloqueio de SSRF / HTML malicioso e criação manual com datas e próximos passos
    bad_url_resp = client_alice.post(
        "/api/v1/applications",
        json={
            "role_title": "Dev Java Júnior",
            "source_url": "http://127.0.0.1:8080/internal",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert bad_url_resp.status_code == 422

    due_assessment = (now + timedelta(days=3)).replace(microsecond=0).isoformat()
    due_interview = (now + timedelta(days=5)).replace(microsecond=0).isoformat()
    due_return = (now + timedelta(days=8)).replace(microsecond=0).isoformat()

    resp_manual = client_alice.post(
        "/api/v1/applications",
        json={
            "role_title": "<script>alert(1)</script>Desenvolvedor Java Backend Júnior",
            "company_name": "Beta Sistemas",
            "personal_summary": "<b>Foco</b> em Spring Boot e PostgreSQL.",
            "source_url": "https://betasistemas.example.org/carreiras/java-jr",
            "employment_type": "pj",
            "work_mode": "remote",
            "seniority_level": "junior",
            "status": "preparing",
            "assessment_deadline_at": due_assessment,
            "interview_at": due_interview,
            "expected_response_at": due_return,
            "next_action": "Revisar desafios REST com Spring",
            "next_action_due_at": due_assessment,
            "notes": "Preparar exemplos reais do portfólio.",
        },
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert resp_manual.status_code == 201
    manual_app = resp_manual.json()
    assert "<script>" not in manual_app["role_title"]
    assert manual_app["status"] == "preparing"
    assert manual_app["status_label"] == "Preparação"
    assert manual_app["next_deadline_at"] is not None
    assert manual_app["next_action"] == "Revisar desafios REST com Spring"

    # 4. Movimentação pelas etapas do Kanban (avanço + recuo) + histórico preservado
    for next_st, expected_label, note in (
        ("applied", "Candidatura enviada", "Enviada pelo portal oficial."),
        ("assessment", "Teste técnico", "Recebido desafio API REST."),
        ("interview", "Entrevista", "Entrevista agendada com tech lead."),
        ("applied", "Candidatura enviada", "Recuo para revisão de etapa."),
        ("interview", "Entrevista", "Entrevista confirmada novamente."),
        ("offer", "Proposta", "Proposta PJ recebida."),
        ("accepted", "Aprovado", "Proposta aceita após análise."),
    ):
        mv = client_alice.patch(
            f"/api/v1/applications/{linked_app['id']}/status",
            json={"status": next_st, "note": note},
            headers={"X-CSRF-Token": csrf_alice},
        )
        assert mv.status_code == 200
        body = mv.json()
        assert body["status"] == next_st
        assert body["status_label"] == expected_label

    detail_linked = client_alice.get(f"/api/v1/applications/{linked_app['id']}").json()
    assert detail_linked["is_closed"] is True
    assert detail_linked["applied_at"] is not None
    assert detail_linked["closed_at"] is not None
    assert len(detail_linked["status_history"]) == 8
    assert detail_linked["status_history"][0]["to_status"] == "accepted"
    assert detail_linked["status_history"][-1]["to_status"] == "interested"

    # Oportunidade global NUNCA foi modificada pela candidatura da Alice!
    db_session.expire_all()
    opp_db = db_session.get(Opportunity, global_opp.id)
    assert opp_db.title == "Backend Python Junior Developer"
    assert opp_db.source_status == "active"

    # 5. Após encerramento (`accepted`/`rejected`/`withdrawn`), usuário PODE iniciar nova candidatura à mesma oportunidade
    reapply_resp = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(global_opp.id), "status": "interested"},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert reapply_resp.status_code == 201
    second_linked_app = reapply_resp.json()
    assert second_linked_app["id"] != linked_app["id"]

    # 6. Kanban separa ativas e encerradas + indicadores reais + busca/paginação
    # Cria mais duas candidaturas encerradas (rejected e withdrawn) para testar todos os indicadores
    rej_app = client_alice.post(
        "/api/v1/applications",
        json={"role_title": "Dev API Júnior Rejeitado", "status": "rejected"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    wdr_app = client_alice.post(
        "/api/v1/applications",
        json={"role_title": "Dev Freela Desistência", "status": "withdrawn"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()

    # Movimenta manual_app para interview para testar filtros e indicadores ativos
    client_alice.patch(
        f"/api/v1/applications/{manual_app['id']}/status",
        json={"status": "interview", "interview_at": due_interview},
        headers={"X-CSRF-Token": csrf_alice},
    )

    kanban = client_alice.get("/api/v1/applications/kanban").json()
    active_col_map = {col["status"]: col for col in kanban["columns"]}
    assert set(active_col_map.keys()) == {
        "interested",
        "preparing",
        "applied",
        "assessment",
        "interview",
        "offer",
    }
    # Encerradas NUNCA aparecem nas colunas ativas!
    active_ids_in_columns = {
        item["id"] for col in kanban["columns"] for item in col["items"]
    }
    assert linked_app["id"] not in active_ids_in_columns
    assert rej_app["id"] not in active_ids_in_columns
    assert wdr_app["id"] not in active_ids_in_columns
    assert second_linked_app["id"] in {i["id"] for i in active_col_map["interested"]["items"]}
    assert manual_app["id"] in {i["id"] for i in active_col_map["interview"]["items"]}

    closed_ids = {i["id"] for i in kanban["closed_items"]}
    assert closed_ids == {linked_app["id"], rej_app["id"], wdr_app["id"]}

    inds = kanban["indicators"]
    assert inds["total_count"] == 5
    assert inds["active_count"] + inds["closed_count"] == inds["total_count"]
    assert sum(col["count"] for col in kanban["columns"]) == inds["active_count"]
    assert inds["active_count"] == 2
    assert inds["interview_count"] == 1
    assert inds["accepted_count"] == 1
    assert inds["rejected_count"] == 1
    assert inds["withdrawn_count"] == 1
    assert inds["closed_count"] == 3
    assert inds["applied_count"] >= 2  # linked_app (accepted após applied) + manual_app (interview)

    # /indicators retorna coerência exata
    ind_direct = client_alice.get("/api/v1/applications/indicators").json()
    assert ind_direct == inds

    # Filtros de listagem e paginação
    active_only = client_alice.get("/api/v1/applications?include_closed=false&page=1&page_size=1").json()
    assert active_only["total"] == 2
    assert active_only["total_pages"] == 2
    assert len(active_only["items"]) == 1

    closed_only = client_alice.get("/api/v1/applications?closed_only=true&page_size=20").json()
    assert closed_only["total"] == 3

    # 7. Proteção de histórico na exclusão (409 sem confirmação explícita; 204 com confirmação; 204 direto em triagem simples)
    protected_del = client_alice.delete(
        f"/api/v1/applications/{linked_app['id']}",
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert protected_del.status_code == 409

    # Snapshot sobrevive atualização posterior da oportunidade vinculada
    app_manual_linked = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(alice_manual_opp.id)},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    patch_manual_opp = client_alice.patch(
        f"/api/v1/opportunities/{alice_manual_opp.id}",
        json={"title": "Título Alterado Depois", "company_name": "Empresa Alterada"},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert patch_manual_opp.status_code == 200
    snap_after = client_alice.get(f"/api/v1/applications/{app_manual_linked['id']}").json()
    assert snap_after["role_title"] == "Vaga Local Java Júnior"
    assert snap_after["company_name"] == "Alpha Tech"

    # Candidatura ainda em estado inicial 'interested' (sem progressão) pode ser excluída diretamente
    simple_del = client_alice.delete(
        f"/api/v1/applications/{app_manual_linked['id']}",
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert simple_del.status_code == 204
    assert db_session.get(Opportunity, alice_manual_opp.id) is not None

    # 8. Isolamento estrito multiusuário: Bob não pode ver, editar, mover ou excluir nada de Alice,
    #    nem Alice pode vincular candidatura à oportunidade privada do Bob.
    forbidden_link = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(bob_private_opp.id)},
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert forbidden_link.status_code == 404

    client_bob = make_client(("10.10.0.51", 50000))
    csrf_bob = login_and_get_csrf(client_bob, "bob.app@example.com", "StrongPassword123!")

    assert client_bob.get("/api/v1/applications").json()["total"] == 0
    assert client_bob.get("/api/v1/applications/kanban").json()["indicators"]["total_count"] == 0
    assert client_bob.get(f"/api/v1/applications/{manual_app['id']}").status_code == 404
    assert (
        client_bob.put(
            f"/api/v1/applications/{manual_app['id']}",
            json={"notes": "Tentativa indevida"},
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )
    assert (
        client_bob.patch(
            f"/api/v1/applications/{manual_app['id']}/status",
            json={"status": "rejected"},
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )
    assert (
        client_bob.delete(
            f"/api/v1/applications/{manual_app['id']}?confirm_history_deletion=true",
            headers={"X-CSRF-Token": csrf_bob},
        ).status_code
        == 404
    )

    # Bob também não vê tracked_application_id de Alice na vaga global!
    opp_list_bob = client_bob.get("/api/v1/opportunities?seniority=junior&page_size=20").json()
    global_card_bob = next(i for i in opp_list_bob["items"] if i["id"] == str(global_opp.id))
    assert global_card_bob["tracked_application_id"] is None

    # Alice confirma exclusão explícita da candidatura com histórico (mantendo oportunidade global intacta)
    explicit_del = client_alice.delete(
        f"/api/v1/applications/{linked_app['id']}?confirm_history_deletion=true",
        headers={"X-CSRF-Token": csrf_alice},
    )
    assert explicit_del.status_code == 204
    assert client_alice.get(f"/api/v1/applications/{linked_app['id']}").status_code == 404
    assert db_session.get(Opportunity, global_opp.id) is not None

    # TC-10: Se a oportunidade privada vinculada for removida no banco, ON DELETE SET NULL preserva a candidatura e seus snapshots!
    opp_for_delete_test = alice_manual_opp
    app_keep_snapshot = client_alice.post(
        "/api/v1/applications",
        json={"opportunity_id": str(opp_for_delete_test.id), "status": "applied"},
        headers={"X-CSRF-Token": csrf_alice},
    ).json()
    db_session.delete(db_session.get(Opportunity, opp_for_delete_test.id))
    db_session.commit()

    preserved = client_alice.get(f"/api/v1/applications/{app_keep_snapshot['id']}").json()
    assert preserved["opportunity_id"] is None
    assert preserved["role_title"] == "Título Alterado Depois"
    assert preserved["company_name"] == "Empresa Alterada"
    assert len(preserved["status_history"]) == 1
