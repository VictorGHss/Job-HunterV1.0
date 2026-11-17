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


def test_phase0311_partial_unique_index_functional_and_db_integrity(
    db_engine, db_session, make_client
):
    import pytest
    from sqlalchemy import inspect, select, text
    from sqlalchemy.exc import IntegrityError

    from app.models.application import (
        ACTIVE_APPLICATION_STATUSES,
        ACTIVE_APPLICATION_UNIQUE_INDEX_NAME,
        CLOSED_APPLICATION_STATUSES,
        Application,
        ApplicationStatus,
    )
    from app.models.user import User
    from app.services.application_service import _is_active_application_unique_violation

    # Verifica fisicamente o índice parcial no banco em execução (SQLite ou PostgreSQL 16)
    inspector = inspect(db_engine)
    indexes = {idx["name"]: idx for idx in inspector.get_indexes("applications")}
    assert ACTIVE_APPLICATION_UNIQUE_INDEX_NAME in indexes
    assert bool(indexes[ACTIVE_APPLICATION_UNIQUE_INDEX_NAME]["unique"]) is True
    assert indexes[ACTIVE_APPLICATION_UNIQUE_INDEX_NAME]["column_names"] == [
        "user_id",
        "opportunity_id",
    ]
    assert "ix_applications_user_opportunity_status" in indexes

    with db_engine.connect() as conn:
        if db_engine.dialect.name == "postgresql":
            ddl = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename = 'applications' AND indexname = :idx_name"
                ),
                {"idx_name": ACTIVE_APPLICATION_UNIQUE_INDEX_NAME},
            ).scalar_one()
        else:
            ddl = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'index' AND name = :idx_name"
                ),
                {"idx_name": ACTIVE_APPLICATION_UNIQUE_INDEX_NAME},
            ).scalar_one()

    for active_st in ACTIVE_APPLICATION_STATUSES:
        assert f"'{active_st}'" in ddl
    for closed_st in CLOSED_APPLICATION_STATUSES:
        assert f"'{closed_st}'" not in ddl

    sources = {s.slug: s for s in ensure_default_sources(db_session)}
    src = sources["remote_ok"]

    u1 = create_user_account(
        db_session,
        email="tc0311.u1@example.com",
        display_name="Usuario 1",
        password="StrongPassword123!",
        is_admin=False,
    )
    u2 = create_user_account(
        db_session,
        email="tc0311.u2@example.com",
        display_name="Usuario 2",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.flush()

    now = datetime.now(UTC)
    opp = Opportunity(
        source_id=src.id,
        external_id="rk-0311-1",
        title="Backend Engineer Junior",
        company_name="Acme Systems",
        description="APIs Python e PostgreSQL.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        professional_area=ProfessionalArea.BACKEND.value,
        eligible_countries=["Brasil"],
        source_url="https://remoteok.com/remote-jobs/0311-1",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-0311-1",
    )
    db_session.add(opp)
    db_session.commit()

    c1 = make_client(("10.10.0.61", 50000))
    csrf1 = login_and_get_csrf(c1, "tc0311.u1@example.com", "StrongPassword123!")
    c2 = make_client(("10.10.0.62", 50000))
    csrf2 = login_and_get_csrf(c2, "tc0311.u2@example.com", "StrongPassword123!")

    # TC-0311-01: Duplicidade ativa -> HTTP 409
    r1 = c1.post(
        "/api/v1/applications",
        json={"opportunity_id": str(opp.id)},
        headers={"X-CSRF-Token": csrf1},
    )
    assert r1.status_code == 201
    app1 = r1.json()
    assert c1.post(
        "/api/v1/applications",
        json={"opportunity_id": str(opp.id)},
        headers={"X-CSRF-Token": csrf1},
    ).status_code == 409

    # TC-0311-04: Outro usuário pode manter candidatura ativa para a mesma oportunidade
    r_u2 = c2.post(
        "/api/v1/applications",
        json={"opportunity_id": str(opp.id)},
        headers={"X-CSRF-Token": csrf2},
    )
    assert r_u2.status_code == 201

    # TC-0311-02 & TC-0311-03: Encerrar como rejected, criar segunda encerrada (withdrawn), depois criar nova ativa
    assert (
        c1.patch(
            f"/api/v1/applications/{app1['id']}/status",
            json={"status": "rejected", "note": "Não avançou na triagem."},
            headers={"X-CSRF-Token": csrf1},
        ).status_code
        == 200
    )
    r_closed_2 = c1.post(
        "/api/v1/applications",
        json={"opportunity_id": str(opp.id), "status": "withdrawn"},
        headers={"X-CSRF-Token": csrf1},
    )
    assert r_closed_2.status_code == 201
    app_closed_2 = r_closed_2.json()

    r_reapplied = c1.post(
        "/api/v1/applications",
        json={"opportunity_id": str(opp.id), "status": "interested"},
        headers={"X-CSRF-Token": csrf1},
    )
    assert r_reapplied.status_code == 201
    app_active_new = r_reapplied.json()
    assert app_active_new["id"] != app1["id"]

    # TC-0311-06 & TC-0311-08: Reabertura conflitante retorna 409 e preserva status e histórico originais
    reopen_conflict = c1.patch(
        f"/api/v1/applications/{app1['id']}/status",
        json={"status": "interested", "note": "Tentativa conflitante de reabertura"},
        headers={"X-CSRF-Token": csrf1},
    )
    assert reopen_conflict.status_code == 409
    unchanged_detail = c1.get(f"/api/v1/applications/{app1['id']}").json()
    assert unchanged_detail["status"] == "rejected"
    assert len(unchanged_detail["status_history"]) == 2
    assert app_closed_2["id"] != app1["id"]

    # TC-0311-05: Múltiplas candidaturas manuais avulsas (opportunity_id = NULL) permitidas
    for idx in range(3):
        avulsa = c1.post(
            "/api/v1/applications",
            json={"role_title": f"Candidatura Avulsa #{idx + 1}", "status": "interested"},
            headers={"X-CSRF-Token": csrf1},
        )
        assert avulsa.status_code == 201
        assert avulsa.json()["opportunity_id"] is None

    # TC-0311-07: Proteção direta no banco ignorando o serviço (SQLite e PostgreSQL 16)
    opp2 = Opportunity(
        source_id=src.id,
        external_id="rk-0311-2",
        title="Backend Engineer Direct DB Guard",
        description="Teste direto no banco.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        source_url="https://remoteok.com/remote-jobs/0311-2",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-0311-2",
    )
    db_session.add(opp2)
    db_session.commit()

    direct_1 = Application(
        user_id=u1.id,
        opportunity_id=opp2.id,
        role_title="Direta 1",
        status=ApplicationStatus.PREPARING.value,
    )
    db_session.add(direct_1)
    db_session.commit()

    direct_2 = Application(
        user_id=u1.id,
        opportunity_id=opp2.id,
        role_title="Direta 2",
        status=ApplicationStatus.APPLIED.value,
    )
    db_session.add(direct_2)
    with pytest.raises(IntegrityError) as exc_dup:
        db_session.commit()
    assert _is_active_application_unique_violation(exc_dup.value) is True
    db_session.rollback()

    # Sessão continua operacional após rollback e erro de outra constraint NÃO é mascarado!
    assert db_session.execute(select(User).where(User.id == u1.id)).scalar_one().id == u1.id

    other_constraint_app = Application(
        user_id=u1.id,
        opportunity_id=opp2.id,
        role_title=None,  # type: ignore[arg-type]  # viola NOT NULL
        status=ApplicationStatus.REJECTED.value,
    )
    db_session.add(other_constraint_app)
    with pytest.raises(IntegrityError) as exc_not_null:
        db_session.commit()
    assert _is_active_application_unique_violation(exc_not_null.value) is False
    db_session.rollback()


def test_phase0311_real_concurrency_creation_and_reopen(
    db_engine, db_session, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from fastapi import HTTPException
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from app.api.routes.applications import move_application_status, post_application
    from app.models.application import (
        ACTIVE_APPLICATION_STATUSES,
        Application,
        ApplicationStatus,
        ApplicationStatusHistory,
    )
    from app.models.user import User
    from app.schemas.application import ApplicationCreate, ApplicationStatusChangeRequest
    import app.services.application_service as app_svc

    user = create_user_account(
        db_session,
        email="tc0311.race@example.com",
        display_name="Race Tester",
        password="StrongPassword123!",
        is_admin=False,
    )
    db_session.flush()
    now = datetime.now(UTC)
    opp_create_race = Opportunity(
        source_id=None,
        created_by_user_id=user.id,
        title="Backend Race Test Create",
        description="Concurrency create test.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        source_url="https://example.org/race-create",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-race-create",
    )
    opp_reopen_race = Opportunity(
        source_id=None,
        created_by_user_id=user.id,
        title="Backend Race Test Reopen",
        description="Concurrency reopen test.",
        opportunity_type=OpportunityType.JUNIOR.value,
        seniority_level=SeniorityLevel.JUNIOR.value,
        employment_type=EmploymentType.PJ.value,
        work_mode=WorkMode.REMOTE.value,
        source_url="https://example.org/race-reopen",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-race-reopen",
    )
    db_session.add_all([opp_create_race, opp_reopen_race])
    db_session.commit()

    user_id = user.id
    opp_create_id = opp_create_race.id
    opp_reopen_id = opp_reopen_race.id

    SessionFactory = sessionmaker(
        bind=db_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # Cria duas candidaturas encerradas para testar TC-0311-10 (reabertura concorrente)
    closed_a_id = app_svc.create_application(
        db_session,
        user,
        ApplicationCreate(opportunity_id=opp_reopen_id, status=ApplicationStatus.REJECTED),
    ).id
    closed_b_id = app_svc.create_application(
        db_session,
        user,
        ApplicationCreate(opportunity_id=opp_reopen_id, status=ApplicationStatus.WITHDRAWN),
    ).id

    orig_find_dup = app_svc._find_active_duplicate

    # TC-0311-09: Criação concorrente determinística (Barrier força ambas as threads
    # a passarem pela consulta prévia vendo None antes do INSERT/COMMIT!)
    create_barrier = threading.Barrier(2, timeout=10)

    def _barrier_on_none_create(db, *args, **kwargs):
        res = orig_find_dup(db, *args, **kwargs)
        if res is None:
            if db_engine.dialect.name == "sqlite":
                # Libera SHARED lock de leitura do SQLite antes da barreira para evitar
                # deadlock de promoção de lock e garantir que ambas alcancem o INSERT
                db.rollback()
            create_barrier.wait()
        return res

    monkeypatch.setattr(app_svc, "_find_active_duplicate", _barrier_on_none_create)

    def _run_concurrent_create() -> tuple[int, str]:
        thread_db = SessionFactory()
        try:
            thread_user = thread_db.execute(
                select(User).where(User.id == user_id)
            ).scalar_one()
            created = post_application(
                ApplicationCreate(opportunity_id=opp_create_id),
                thread_user,
                thread_db,
            )
            return (201, str(created.id))
        except HTTPException as exc:
            return (exc.status_code, str(exc.detail))
        finally:
            thread_db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_run_concurrent_create)
        f2 = pool.submit(_run_concurrent_create)
        create_results = [f1.result(timeout=15), f2.result(timeout=15)]

    assert sorted(code for code, _ in create_results) == [201, 409]

    db_session.expire_all()
    active_created = db_session.scalars(
        select(Application).where(
            Application.user_id == user_id,
            Application.opportunity_id == opp_create_id,
            Application.status.in_(ACTIVE_APPLICATION_STATUSES),
        )
    ).all()
    assert len(active_created) == 1
    hist_count = db_session.scalar(
        select(func.count(ApplicationStatusHistory.id)).where(
            ApplicationStatusHistory.application_id == active_created[0].id
        )
    )
    assert hist_count == 1

    # TC-0311-10: Reabertura concorrente determinística
    reopen_barrier = threading.Barrier(2, timeout=10)

    def _barrier_on_none_reopen(db, *args, **kwargs):
        res = orig_find_dup(db, *args, **kwargs)
        if res is None:
            if db_engine.dialect.name == "sqlite":
                db.rollback()
            reopen_barrier.wait()
        return res

    monkeypatch.setattr(app_svc, "_find_active_duplicate", _barrier_on_none_reopen)

    def _run_concurrent_reopen(target_app_id) -> tuple[int, str]:
        thread_db = SessionFactory()
        try:
            thread_user = thread_db.execute(
                select(User).where(User.id == user_id)
            ).scalar_one()
            updated = move_application_status(
                target_app_id,
                ApplicationStatusChangeRequest(
                    status=ApplicationStatus.INTERESTED,
                    note="Reabertura concorrente",
                ),
                thread_user,
                thread_db,
            )
            return (200, updated.status)
        except HTTPException as exc:
            # Verifica na mesma sessão após o conflito que a sessão continua íntegra!
            still_exists = thread_db.execute(
                select(Application.status).where(Application.id == target_app_id)
            ).scalar_one()
            return (exc.status_code, str(still_exists))
        finally:
            thread_db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        r1 = pool.submit(_run_concurrent_reopen, closed_a_id)
        r2 = pool.submit(_run_concurrent_reopen, closed_b_id)
        reopen_results = [r1.result(timeout=15), r2.result(timeout=15)]

    assert sorted(code for code, _ in reopen_results) == [200, 409]

    # Restaura helper original para checagem final
    monkeypatch.undo()
    db_session.expire_all()
    reopen_rows = db_session.scalars(
        select(Application).where(Application.id.in_([closed_a_id, closed_b_id]))
    ).all()
    statuses_after = sorted(row.status for row in reopen_rows)
    assert len([s for s in statuses_after if s in ACTIVE_APPLICATION_STATUSES]) == 1
    assert len([s for s in statuses_after if s in ("rejected", "withdrawn")]) == 1
    # Garante que a candidatura perdedora não teve histórico corrompido
    for row in reopen_rows:
        cnt = db_session.scalar(
            select(func.count(ApplicationStatusHistory.id)).where(
                ApplicationStatusHistory.application_id == row.id
            )
        )
        assert cnt == (2 if row.status == ApplicationStatus.INTERESTED.value else 1)


def test_phase0311_migration_0008_upgrade_and_downgrade_preserves_data(tmp_path):
    from pathlib import Path
    import uuid
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, inspect, text
    from tests.conftest import resolve_test_database_url

    mig_url = resolve_test_database_url(tmp_path)
    connect_args = {"check_same_thread": False} if mig_url.startswith("sqlite") else {}
    engine = create_engine(mig_url, connect_args=connect_args, future=True)

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", mig_url)

    script_dir = ScriptDirectory.from_config(alembic_cfg)
    assert len(script_dir.get_heads()) == 1

    user_id = uuid.uuid4()
    app_id = uuid.uuid4()
    now = datetime.now(UTC)

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "0007_applications_pipeline")

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, display_name, password_hash, account_status, is_admin, created_at, updated_at) "
                "VALUES (:id, :email, :name, :pwd, 'active', :is_admin, :now, :now)"
            ),
            {
                "id": str(user_id) if engine.dialect.name == "sqlite" else user_id,
                "email": "mig0008@example.com",
                "name": "Migration Tester",
                "pwd": "hash",
                "is_admin": False,
                "now": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO applications (id, user_id, opportunity_id, role_title, employment_type, work_mode, seniority_level, status, created_at, updated_at) "
                "VALUES (:id, :uid, NULL, 'Dev Jr', 'unknown', 'unknown', 'unknown', 'interested', :now, :now)"
            ),
            {
                "id": str(app_id) if engine.dialect.name == "sqlite" else app_id,
                "uid": str(user_id) if engine.dialect.name == "sqlite" else user_id,
                "now": now,
            },
        )

    # Upgrade incremental para 0008 preserva os registros e adiciona apenas o índice único parcial
    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, "0008_active_app_uniq")

    idx_after_up = {idx["name"]: idx for idx in inspect(engine).get_indexes("applications")}
    assert "uq_active_application_per_user_opp" in idx_after_up
    assert bool(idx_after_up["uq_active_application_per_user_opp"]["unique"]) is True

    with engine.connect() as conn:
        count_up = conn.execute(text("SELECT COUNT(*) FROM applications")).scalar_one()
        assert count_up == 1

    # Downgrade 0008 -> 0007 remove somente o novo índice sem apagar candidaturas
    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "0007_applications_pipeline")

    idx_after_down = {idx["name"]: idx for idx in inspect(engine).get_indexes("applications")}
    assert "uq_active_application_per_user_opp" not in idx_after_down
    assert "ix_applications_user_opportunity_status" in idx_after_down

    with engine.connect() as conn:
        count_down = conn.execute(text("SELECT COUNT(*) FROM applications")).scalar_one()
        assert count_down == 1

    with engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, "base")
    engine.dispose()
