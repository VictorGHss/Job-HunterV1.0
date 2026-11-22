# Job Hunter

Plataforma de descoberta, análise e preparação supervisionada de candidaturas para oportunidades profissionais na área de tecnologia (**Estágios**, **Desenvolvedor Júnior / Posições de Entrada** e **Projetos Freelance** no Brasil e no exterior).

- **Hostname planejado:** `https://jobhunter.ctrls.dev.br`
- **Fase atual:** Subfase 04.4.5 — Hardening e Integração Final (MVP 1.0 consolidado)
- **Arquitetura:** Monólito modular multiusuário desde a origem

---

## 1. Objetivo do Projeto

O **Job Hunter** centraliza e governa o perfil profissional do usuário como **fonte única de verdade** para alimentar futuros motores de descoberta de vagas, avaliação de compatibilidade via IA, adaptação de currículos e elaboração de propostas.

### Princípios Fundamentais
1. **Multiusuário desde o início:** Todas as entidades profissionais pertencem estritamente a um usuário (`user_id`), com isolamento verificável em todos os endpoints.
2. **Proibição absoluta de alucinação de fatos:** A IA nunca poderá inventar experiências, tecnologias, métricas, resultados, cursos ou qualificações.
3. **Validação humana obrigatória:** Cada entidade do perfil possui estado explícito (`draft`, `pending_validation`, `confirmed`). Somente dados marcados pelo usuário como **`confirmed`** poderão ser usados como fatos em documentos finais.
4. **Aprovação explícita:** Nenhuma candidatura ou teste seletivo será executado sem revisão e autorização humana.

---

## 2. Stack Tecnológica

### Backend
- **Python 3.12+**
- **FastAPI** + **Pydantic v2** (`pydantic-settings`)
- **SQLAlchemy 2.0** (ORM tipado com `Mapped` / `mapped_column`)
- **Alembic** (migrações versionadas obrigatórias)
- **PostgreSQL 16** (armazenamento relacional + `JSONB` para preferências estruturadas)
- **Argon2id** (`argon2-cffi`) para hash seguro de senhas

### Frontend
- **React 18** + **TypeScript** + **Vite**
- **Tailwind CSS** + componentes no padrão **shadcn/ui**
- **Identidade visual adaptativa:** Modo Claro (lavanda suave + roxo), Modo Escuro (preto/grafite + roxo, sem excesso de cartões brancos) e Modo Automático conforme sistema, com persistência em `localStorage`
- **PWA & Web Share Target:** Manifesto e Service Worker preparados para compartilhamento futuro de vagas a partir do Android

### Infraestrutura
- **Docker Compose** (`infra/compose.yaml`) com PostgreSQL isolado em rede interna, Backend FastAPI e Frontend Nginx (SPA + proxy reverso `/api/`)

---

## 3. Estrutura de Diretórios

```text
job-hunter/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   │   ├── 0001_initial_foundation.py
│   │   │   ├── 0002_auth_rate_limiting.py
│   │   │   ├── 0003_opportunity_discovery.py
│   │   │   ├── 0004_professional_areas.py
│   │   │   ├── 0005_lifecycle_traceability.py
│   │   │   ├── 0006_seniority_experience_matching.py
│   │   │   ├── 0007_applications_pipeline.py
│   │   │   ├── 0008_active_app_uniq.py
│   │   │   ├── 0009_application_followup_and_interview_logs.py
│   │   │   ├── 0010_application_materials.py
│   │   │   ├── 0011_ai_usage_ledger.py
│   │   │   └── 0012_ai_version_rejection_state.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── applications.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── health.py
│   │   │   │   ├── materials.py
│   │   │   │   ├── opportunities.py
│   │   │   │   └── profile.py
│   │   │   └── deps.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   ├── ai_usage.py
│   │   │   ├── application.py
│   │   │   ├── material.py
│   │   │   ├── opportunity.py
│   │   │   ├── profile.py
│   │   │   └── user.py
│   │   ├── schemas/
│   │   │   ├── application.py
│   │   │   ├── auth.py
│   │   │   ├── material.py
│   │   │   ├── opportunity.py
│   │   │   └── profile.py
│   │   ├── services/
│   │   │   ├── materials/
│   │   │   │   ├── ai/
│   │   │   │   │   ├── _db_locks.py
│   │   │   │   │   ├── ai_schemas.py
│   │   │   │   │   ├── circuit_breaker.py
│   │   │   │   │   ├── context_builder.py
│   │   │   │   │   ├── contracts.py
│   │   │   │   │   ├── execution_guard.py
│   │   │   │   │   ├── grounding_validator.py
│   │   │   │   │   ├── orchestrator.py
│   │   │   │   │   ├── overlay_merger.py
│   │   │   │   │   ├── providers.py
│   │   │   │   │   ├── quota_service.py
│   │   │   │   │   └── safety.py
│   │   │   │   ├── export/
│   │   │   │   │   ├── fonts/
│   │   │   │   │   ├── document_templates.py
│   │   │   │   │   ├── document_validation.py
│   │   │   │   │   ├── docx_exporter.py
│   │   │   │   │   ├── export_service.py
│   │   │   │   │   └── pdf_exporter.py
│   │   │   │   ├── application_answers_composer.py
│   │   │   │   ├── cover_letter_composer.py
│   │   │   │   ├── fact_selector.py
│   │   │   │   ├── freelance_proposal_composer.py
│   │   │   │   ├── material_service.py
│   │   │   │   ├── recruiter_message_composer.py
│   │   │   │   ├── resume_composer.py
│   │   │   │   └── writing_common.py
│   │   │   ├── opportunities/
│   │   │   │   ├── connectors/
│   │   │   │   ├── classification.py
│   │   │   │   ├── matching.py
│   │   │   │   ├── opportunity_service.py
│   │   │   │   ├── sanitization.py
│   │   │   │   └── sync_service.py
│   │   │   ├── application_process_service.py
│   │   │   ├── application_service.py
│   │   │   ├── auth_service.py
│   │   │   └── profile_service.py
│   │   ├── cli.py
│   │   └── main.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_ai_foundation_phase0441.py
│   │   ├── test_ai_grounding_phase0442.py
│   │   ├── test_ai_orchestration_phase0443.py
│   │   ├── test_applications_phase03.py
│   │   ├── test_applications_phase032.py
│   │   ├── test_foundation_phase01.py
│   │   ├── test_integration_hardening_phase0445.py
│   │   ├── test_materials_phase041.py
│   │   ├── test_materials_phase042.py
│   │   ├── test_materials_phase043.py
│   │   ├── test_opportunities_phase02.py
│   │   ├── test_opportunity_authorization_phase0411.py
│   │   ├── test_opportunity_coverage_dx02.py
│   │   └── test_profile_confirmation_phase0411.py
│   ├── alembic.ini
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── public/
│   │   ├── icon.svg
│   │   ├── manifest.webmanifest
│   │   └── sw.js
│   ├── src/
│   │   ├── components/
│   │   │   ├── applications/
│   │   │   ├── auth/
│   │   │   ├── dashboard/
│   │   │   ├── layout/
│   │   │   ├── materials/
│   │   │   │   ├── aiStudioUtils.ts
│   │   │   │   ├── DocumentPreviewCard.tsx
│   │   │   │   ├── MaterialAIStudioPanel.tsx
│   │   │   │   ├── MaterialTypeEditors.tsx
│   │   │   │   └── MaterialWorkspaceModal.tsx
│   │   │   ├── opportunities/
│   │   │   ├── profile/
│   │   │   └── ui/
│   │   ├── context/
│   │   ├── lib/
│   │   ├── test/
│   │   ├── types/
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── vite.config.ts
├── infra/
│   └── compose.yaml
├── local-seeds/
│   └── profile-seed.example.json   # Exemplo genérico; *.local.json fica no .gitignore
├── .env.example
├── .gitignore
├── README.md
├── DEPLOY.md
├── SECURITY.md
└── CHANGELOG.md
```

---

## 4. Como Iniciar e Encerrar o Ambiente

### 4.1. Preparação do `.env`
Na raiz do projeto, copie o arquivo `.env.example` para `.env` e defina senhas e chaves fortes:

```powershell
Copy-Item .env.example .env
```

Gere valores seguros para `POSTGRES_PASSWORD` e `SECRET_KEY` no arquivo `.env`:

```powershell
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24)); print('SECRET_KEY=' + secrets.token_urlsafe(48))"
```

### 4.2. Subindo com Docker Compose (Recomendado)

```powershell
docker compose --env-file .env -f infra/compose.yaml up -d --build
```

As migrações Alembic (`alembic upgrade head`) são executadas automaticamente na inicialização do container `backend`.

- **Aplicação Web (Frontend + Proxy API):** `http://localhost:5180`
- **API Backend Direta / OpenAPI Docs:** `http://localhost:8090/api/docs`
- **Health Check:** `http://localhost:8090/api/v1/health`

### 4.3. Provisionando o Primeiro Administrador (Sem Credenciais Padrão)
Não existe cadastro público aberto nem senha padrão. Novos usuários sempre iniciam com perfil e preferências neutras/genéricas. Para criar sua conta administrativa:

```powershell
docker exec -it job-hunter-backend python -m app.cli create-admin --email seu@email.com --display-name "Admin"
```

O comando solicitará a senha de forma oculta no terminal e gravará o hash **Argon2id** no PostgreSQL.

### 4.4. Importação Local e Privada de Perfil (CLI Administrativo)
Dados profissionais particulares não ficam no código-fonte compartilhado. Para preencher o rascunho inicial de uma conta via arquivo local privado (ignorado pelo Git):

1. Copie `local-seeds/profile-seed.example.json` para `local-seeds/profile-seed.local.json` e preencha seus dados reais (este arquivo é montado em somente leitura em `/run/local-seeds` no container `backend`).
2. Execute a importação informando explicitamente `--email` ou `--user-id`:

```powershell
docker exec -it job-hunter-backend python -m app.cli import-profile-seed --email seu@email.com --file /run/local-seeds/profile-seed.local.json
```

A importação é transacional e idempotente: valida o JSON estritamente (`schema_version: 1`), nunca auto-confirma registros (`draft`/`pending_validation`), preserva campos já preenchidos, preferências personalizadas e estados `confirmed`, evita duplicatas em reexecuções e realiza rollback automático em caso de erro.

### 4.5. Sincronização de Oportunidades Públicas e Cadastro Manual
A Fase 02 implementa conectores modulares para feeds públicos com termos verificados e compatíveis, além de captura manual privada e recebimento de links via Web Share Target (PWA):

- **Fontes ativas e habilitadas (`enabled=true`, intervalo mínimo `3600s`):**
  - **Remote OK (`remote_ok`)**: feed JSON público sem chave filtrado por tags de tecnologia (`https://remoteok.com/api?tag=...`, cobrindo um conjunto configurável e limitado de tags técnicas com deduplicação local por ID, sem alterar as regras globais de classificação), atribuição visível e links diretos **sem `rel="nofollow"`**.
  - **Jobicy (`jobicy`)**: API pública oficial (`https://jobicy.com/api/jobs?count=100&industry=...`), sem chave, paginação por cursor (`nextCursor` / `hasMore`) com teto de páginas configurável, pausa mínima de `1s` entre requisições, consultas segmentadas (`engineering`, `data-science`) com deduplicação local, revalidação de encerramento via `/api/jobs/status?ids=...` (sem marcar como encerrada apenas por sair da janela de 7 dias) e unificação de clones multi-país preservando todos os links em `opportunity_source_links`.
  - **Himalayas (`himalayas`)**: API JSON pública oficial priorizando o catálogo completo paginado por cursor (`https://himalayas.app/jobs/api?limit=20`) complementado por buscas segmentadas controladas (`https://himalayas.app/jobs/api/search`) cobrindo termos técnicos e de início de carreira, suporte opcional a `HIMALAYAS_API_KEY` (header `Authorization: Bearer`), deduplicação por `guid`, preservação integral de `applicationLink`, aproveitamento conservador de `timezoneRestrictions` (sem equiparar fuso horário a autorização legal de país) e controle de ciclo de vida via `expiryDate`.
  - **GitHub Backend BR (`github_backend_br`)** e **GitHub Frontend BR (`github_frontend_br`)**: repositórios comunitários brasileiros licenciados sob **MIT** (`backend-br/vagas` e `frontendbr/vagas`, observando que a licença MIT do repositório não suprime direitos sobre conteúdo de terceiros) consumidos via API REST oficial v3 do GitHub com `per_page=100`, paginação real via cabeçalho `Link` (`rel="next"`, validado estritamente contra `https://api.github.com`), suporte opcional a `GITHUB_TOKEN` (PAT somente leitura de repositórios públicos via `Authorization: Bearer`), filtragem de PRs/issues `Stale`/avisos administrativos, revalidação de issues encerradas/removidas, parsing de múltiplas cidades e **redação automática de PII** (e-mails e telefones pessoais) no corpo da vaga.
  - **Rastreabilidade, integridade e cobertura (`DX-02.1` / `DX-02.2`):** todas as ocorrências primárias e secundárias permanecem registradas em `opportunity_source_links`, o reparo conservador e idempotente de mojibake é aplicado na sanitização textual (`sanitize_plain_text` / `sanitize_external_html_text`), a expiração por `deadline_at` é avaliada em tempo real em UTC sem escrita colateral em rotas GET, e tanto as rotas `GET /api/v1/opportunities*` quanto `sync-opportunities --dry-run` são estritamente somente leitura.
  - **Classificação determinística em múltiplas dimensões (`classification.py`)**: separa `opportunity_type`, `seniority_level` (`internship`, `entry_level`, `junior`, `mid_level`, `senior`, `staff_principal`, `management`, `unknown`), `employment_type` (`internship`, `clt`, `pj`, `freelance`, `temporary`, `other`, `unknown`), requisitos de experiência (`experience_requirement_mode`: `none_required`, `preferred`, `required`, `not_specified`) e `professional_area` + `secondary_areas`, garantindo coerência entre `opportunity_type` e `seniority_level` (preservando `entry_level` sem rebaixar sinais superiores).
  - **Matching multidimensional (`matching.py`) e independência de filtros:** avalia área profissional, geografia (incluindo múltiplas cidades alternativas em vagas presenciais/híbridas sem fuzzy matching genérico), contrato, senioridade, requisitos de experiência e habilidades técnicas do perfil. A API `GET /api/v1/opportunities` aceita múltiplos valores de `seniority` (`?seniority=junior&seniority=entry_level` mantendo retrocompatibilidade com valor único); a aba **Desenvolvedor Júnior & Posições de Entrada** exibe `junior` + `entry_level` preservando cada classificação original, e a visão separada **Outras potencialmente compatíveis** apresenta vagas elegíveis com `seniority_level=unknown` e `overall_compatibility=potential` com aviso explícito de senioridade não informada.
- **Fonte pausada temporariamente por conformidade:**
  - **Remotive (`remotive`)**: conector implementado e preservado no código (`https://remotive.com/api/remote-jobs?category=software-dev`, intervalo `21600s`), porém marcado com **`enabled_by_default=False`** (`enabled=false` no banco) até esclarecimento e autorização escrita sobre restrições nos Termos de Uso gerais de março de 2026 para agregação multiusuário. A execução de `sync-opportunities` (mesmo com `--force` ou `--source remotive`) recusa consultas HTTP contra fontes desabilitadas.
- **Fontes auditadas e rejeitadas / pendentes na Fase 02.4:**
  - **Arbeitnow**: termos (Seção 11) reservam revogação arbitrária e restringem redistribuição/exibição pública sem licença explícita; vagas majoritariamente presenciais na Alemanha.
  - **Adzuna**: exige cadastro de `app_id`/`app_key` e proíbe uso comercial/SaaS no tier gratuito sem contrato comercial.
  - **Jooble**: exige aprovação de `api_key` vinculada a domínio e veta armazenamento em banco fora de busca ao vivo.
  - **The Muse**: requer registro de chave para limites de produção e foca em vagas presenciais/híbridas nos EUA.
  - **Gupy**: API oficial (`api.gupy.io`) exige token Bearer corporativo por empresa recrutadora.
  - **Workana**: desabilitada por restrição do perfil do usuário (`workana_enabled=false`) e política anti-scraping.

**Como habilitar uma fonte futuramente (após validação dos termos / autorização escrita):**
1. Alterar `enabled_by_default=True` no `SourceDefinition` do conector correspondente e remover ou atualizar `disabled_reason`.
2. Garantir `enabled = true` para o respectivo `slug` na tabela `opportunity_sources` (o sistema não reativa automaticamente registros mantidos desabilitados manualmente no banco).
3. Validar com `python -m app.cli sync-opportunities --source <slug> --dry-run` antes da carga real.

Para sincronizar as fontes públicas via CLI:

```powershell
# Inicialização explícita e idempotente das fontes padrão (também executada no startup da API)
docker exec job-hunter-backend python -m app.cli init-sources

# Validação estritamente sem escrita no banco (requer fontes previamente inicializadas)
docker exec job-hunter-backend python -m app.cli sync-opportunities --dry-run

# Sincronização padrão (respeita intervalo mínimo por fonte)
docker exec job-hunter-backend python -m app.cli sync-opportunities

# Reclassificação determinística segura em registros externos já persistidos
docker exec job-hunter-backend python -m app.cli reclassify-opportunities --source remote_ok --dry-run
docker exec job-hunter-backend python -m app.cli reclassify-opportunities --source remote_ok
```

Oportunidades brasileiras locais, estágios acadêmicos ou freelas recebidos fora dos feeds podem ser cadastrados de forma privada pelo botão **Adicionar Oportunidade** ou via **Web Share Target (PWA)** no navegador/Android, sem raspagem automática de HTML pelo servidor.

### 4.6. Pipeline e Gestão Avançada de Processos Seletivos (Fases 03.1 a 03.2)
A partir de qualquer vaga do catálogo (**Acompanhar candidatura**) ou diretamente na seção **Candidaturas** (que reúne **Pipeline**, **Agenda** e **Acompanhamento**):
- **Etapas Kanban (PT-BR):** `Interesse` (`interested`), `Preparação` (`preparing`), `Candidatura enviada` (`applied`), `Teste técnico` (`assessment`), `Entrevista` (`interview`) e `Proposta` (`offer`), mantendo os desfechos encerrados (`Aprovado`, `Rejeitado`, `Desistência`) em seção separada sem poluir o quadro ativo (com navegação em abas no mobile).
- **Snapshots e Histórico Imutável:** preserva empresa, cargo, fonte, localidade, links, regime, modalidade e senioridade no momento do vínculo (`ON DELETE SET NULL` caso a oportunidade privada original seja removida), além de gravar atomicamente toda transição em `application_status_history`.
- **Prevenção de Duplicação e Reaplicação (`0008_active_app_uniq`):** além da verificação prévia na camada de serviço, um índice único parcial no banco (`uq_active_application_per_user_opp` em PostgreSQL 16 e SQLite sobre `(user_id, opportunity_id)` para `opportunity_id IS NOT NULL` e status ativos) impede race conditions concorrentes, realizando `rollback()` limpo e retornando `409 Conflict`, enquanto preserva candidaturas avulsas (`opportunity_id = NULL`) e permite nova tentativa após encerramento.
- **Entrevistas, Testes Técnicos e Contatos (`0009_followup_interview_logs`):** múltiplas rodadas em `application_interviews` (com reagendamento preservando `previous_scheduled_at` e sincronização contínua de `Application.interview_at` para a próxima entrevista futura), múltiplos desafios em `application_assessments` (com links separados de instruções/entrega, prazo, feedback e sincronização/fallback exclusivo com `assessment_deadline_at` sem duplicação na agenda) e múltiplos contatos em `application_contacts` (`/api/v1/applications/{id}/interviews`, `/assessments`, `/contacts`).
- **Agenda Unificada, Estagnação e Follow-up Determinístico:** `GET /api/v1/applications/agenda?days=30` consolida eventos em ordem cronológica real UTC (convertidos para o fuso local no navegador, com alertas de 24h e vencidos, visão semanal/cronológica no desktop e lista vertical no mobile); `GET /api/v1/applications/stale?stale_days=7` detecta processos em `applied` (> 10 dias por padrão) ou `interview` (> 7 dias por padrão) sem interação externa registrada (`last_external_interaction_at` atualizado somente via `POST /api/v1/applications/{id}/external-interaction` ou conclusão real de entrevista, **nunca** por `updated_at`, representando estritamente o **maior timestamp conhecido** — interações retroativas seguem preservadas no histórico sem fazer o resumo retroceder no tempo); e `GET /api/v1/applications/{id}/follow-up-template` gera mensagem determinística em PT-BR pronta para cópia manual, sem IA nem envios automáticos.

### 4.7. Materiais e Currículo Direcionado Determinístico (Subfase 04.1)
Nos cards de oportunidades (**Gerar currículo**), na aba **Materiais** dos detalhes de candidatura ou pelo **Estúdio de Currículo** no Perfil:
- **Pré-análise transparente:** identifica fatos confirmados relevantes para a vaga, separa itens `pending_validation` (elegíveis para confirmação em lote seletiva via `POST /api/v1/profile/confirm-batch` sem pré-seleção) de itens `draft`, lista requisitos sem evidência confirmada e bloqueia geração caso não haja conteúdo substantivo confirmado.
- **Política de confirmação factual obrigatória (Subfases 04.1.1 e 04.1.2):** qualquer edição que altere o conteúdo factual de um registro confirmado revoga automaticamente a confirmação (`pending_validation`, `confirmed_at = None`), mesmo que o cliente reenvie `verification_status="confirmed"`. A confirmação pertence ao conteúdo revisado, não ao valor de status carregado anteriormente pelo formulário. Já registros em `draft` ou `pending_validation` aceitam confirmação intencional (`confirmed`) explicitamente solicitada pelo usuário (com ou sem edição simultânea), enquanto requisições sem alteração factual que omitam `verification_status` no payload preservam o estado atual via `model_fields_set`. Oportunidades privadas de terceiros retornam `404 Not Found` sem expor nenhum dado em pré-análise ou geração de materiais.
- **Geração determinística e fidelidade estrita (`pt-BR` e `en`):** compõe currículo estruturado (`structured_content` JSONB) sem IA externa, preservando separação entre `WorkExperience` e `ProfessionalProject`, `eligible_as_target_role`, status acadêmico (`in_progress`, `completed`, `paused`, `planned`), proficiências exatas e opções explícitas de inclusão de contatos.
- **Versionamento, aprovação, exportação e vínculo:** permite editar seções do rascunho mais recente com reconciliação server-side de proveniência (`confirmed_fact`, `manual_edit`, `user_authored`), aprovar versões tornando-as imutáveis, derivar novas versões (`/derive`) ou regenerar do perfil (`/regenerate`), exportar em Markdown/Texto simples e vincular versões aprovadas a candidaturas preservando histórico completo em `application_material_links`.

### 4.8. Propostas, Cartas e Mensagens Direcionadas (Subfase 04.2)
O estúdio foi ampliado para o **Estúdio de Materiais para Candidatura** (acessível pelos cards de vagas, pela aba **Materiais** nos detalhes da candidatura via **Novo material direcionado** e pelo Perfil), mantendo funcionamento **100% determinístico e sem provedores externos de IA**:
- **Cinco tipos de material em fluxo único:** `resume` (`Currículo Direcionado`), `cover_letter` (`Carta de Apresentação`), `recruiter_message` (`Mensagem para Recrutador` por `linkedin`, `email` ou `contact_form` com contagem aproximada de caracteres), `freelance_proposal` (`Proposta Freelance`) e `application_answers` (`Respostas para Perguntas de Candidatura`).
- **Compatibilidade e solicitação explícita:** a pré-análise (`POST /api/v1/materials/pre-analyze`) prioriza os formatos mais adequados ao regime da vaga (`Recomendado` vs `Sob solicitação`, destacando `freelance_proposal` para oportunidades freelance), sem impedir seleção explícita pelo usuário.
- **Lacunas e bloqueio seguro de aprovação:** em `freelance_proposal`, disponibilidade, prazo estimado e orçamento nunca são inventados e bloqueiam `POST .../approve` (`422`) enquanto não preenchidos e salvos; em `application_answers`, perguntas factuais usam exclusivamente evidências confirmadas (`confirmed_fact`), enquanto perguntas sobre motivação, pretensão salarial, disponibilidade ou tecnologias sem evidência retornam `needs_user_input` (`answer_text = null`) exigindo resposta humana (`user_authored`) antes de liberar aprovação (sem promover respostas ad-hoc para fatos do perfil).
- **Fora de escopo nas subfases de texto:** integração com APIs de LLM externas e envio automático de mensagens ou candidaturas permanecem fora de escopo.

### 4.9. Exportação Profissional em PDF e DOCX (Subfase 04.3)
Todos os cinco tipos de materiais (`resume`, `cover_letter`, `recruiter_message`, `freelance_proposal`, `application_answers`) contam com geração binária **100% em memória** (zero armazenamento em disco/banco e zero serviços externos como Chromium/Pandoc), operando tanto no Windows quanto em container Linux (Debian 13 + `fonts-liberation2`):
- **Bibliotecas e fontes controladas:** PDF gerado com `ReportLab Platypus` (`reportlab>=4.2.5,<5.0.0`, `invariant=1`) e DOCX com `python-docx` (`>=1.1.2,<2.0.0`), utilizando fontes TrueType controladas da família **Liberation Sans** (`SIL Open Font License 1.1`, com verificação SHA-256 em `backend/app/services/materials/export/fonts/`). Em ambiente de testes utiliza `pypdf` (`>=5.1.0,<6.0.0`).
- **Templates por exportação (`classic_ats` e `modern_minimal`):** layouts de coluna única com extração linear favorável a ATS, suporte bilíngue (`pt-BR` e `en`), Unicode NFC completo, hiperlinks externos clicáveis seguros (`validate_safe_external_url`), tabelas com repetição de cabeçalho e controle de paginação multipágina (`Página X de Y` apenas quando há mais de 1 página).
- **Rota binária, headers e rascunhos:** `GET /api/v1/materials/{material_id}/versions/{version_id}/download?format=pdf|docx&template=classic_ats|modern_minimal&allow_draft=false|true` exporta estritamente o `version_id` solicitado com `Content-Disposition` sanitizado, `X-Content-Type-Options: nosniff` e `Cache-Control: no-store`. Versões com pendências obrigatórias são sempre bloqueadas (`422`), e versões não aprovadas só podem ser baixadas com `allow_draft=true`, exibindo `RASCUNHO NÃO APROVADO` / `UNAPPROVED DRAFT` em todas as páginas.
- **Limites e UX:** limites de `120.000` caracteres de entrada e `5 MiB` por arquivo final; no frontend, a aba **Pré-visualização & Exportação** traz seletor de template, preview documental e downloads Blob com `URL.revokeObjectURL`, além de atalhos **PDF**/**DOCX** na aba **Materiais** da candidatura apontando estritamente para `linked_version_id` (versão histórica vinculada em `application_material_links`).

### 4.10. Fundação e Infraestrutura de IA Assistida (Subfase 04.4.1)
Prepara a base de backend para futuro aprimoramento opcional de materiais com IA, mantendo toda a geração, edição, aprovação, versionamento e exportação determinística funcionando sem qualquer alteração de comportamento:
- **Kill switch e inicialização sem API key:** `AI_ASSISTED_ENABLED=false` e `AI_PROVIDER=disabled` por padrão. Nenhuma chave de API ou SDK externo é exigido para iniciar, testar ou operar o sistema; quando desabilitada, qualquer chamada falha de forma previsível (`AIDisabledError`) antes de alocar recursos.
- **Cotas configuráveis e semântica temporal explícita (UTC):** todas as janelas operam exclusivamente em UTC — `10` requisições por usuário em janela deslizante de `900s` (`[now - 900s, now]`), `30` requisições/dia por usuário, `60.000` tokens/dia por usuário e `100.000` tokens/dia globais em dia civil fixo UTC (`[00:00:00Z, 24:00:00Z)`), além de limites de referência para a futura camada HTTP (`< 25s` total / `24.0s` padrão, `5.0s` connect, `20.0s` read, `256 KiB` máx.).
- **Reserva atômica em duas transações curtas (`0011_ai_usage_ledger`):** reservas são gravadas em `ai_usage_ledger` sob lock explícito por escopo (`ai_quota_scope_locks`, adquirido em ordem canônica) **antes** da chamada ao provider, encerrando a transação antes de qualquer I/O externo e reabrindo uma segunda transação curta para confirmar (`completed`) ou registrar falha (`failed`). Reservas canceladas antes da chamada (`released`) ou abandonadas após `AI_RESERVATION_TTL_SECONDS` (`60s` -> `expired`) liberam cota; tentativas que iniciaram execução (`completed` e `failed`) permanecem auditáveis e contam no limite de requisições. Quando um provider não reporta consumo (`usage_reported=false`), os campos de tokens permanecem `NULL` (contribuindo `0` tokens reais sem inventar estimativas).
- **Circuit breaker compartilhado em SQL (`ai_circuit_breakers`):** estados `closed`, `open` e `half_open` persistidos no banco (`3` falhas consecutivas abrem por `120s`, probe único exclusivo em `half_open`), mantendo proteção consistente entre múltiplos workers/réplicas sem introduzir Redis.
- **Providers disponíveis na fundação:** implementados o protocolo agnóstico `LLMProvider`, `DisabledLLMProvider` e `MockLLMProvider` (restrito a testes e bloqueado em `ENVIRONMENT=production`). As camadas de contexto autorizado e validação estruturada de grounding foram entregues na Subfase 04.4.2 abaixo; **permanecem fora de escopo até as etapas seguintes:** providers HTTP externos (Gemini/OpenAI/Anthropic/Ollama/OpenRouter), geração/overlay de versões `ai_assisted`, endpoints de aprimoramento e interface de revisão/diff no frontend.

### 4.11. Contexto Autorizado e Grounding Estruturado (Subfase 04.4.2)
Constrói a camada de autorização factual, minimização de privacidade e validação conservadora que alimenta e audita sugestões estruturadas de IA antes de qualquer revisão humana:
- **Autorização Explícita e Projeção Escalar Isolada do Identity Map (`context_builder.py`, `fact_selector.py`):** antes de montar qualquer contexto, revalida no banco (sob `db.no_autoflush` via projeções SQL escalares `.mappings()`) a posse de `application` (`application.user_id == user.id`), a visibilidade canônica de `opportunity` (pública `source_id IS NOT NULL` ou privada própria `created_by_user_id == user.id`) e a coerência estrita `application.opportunity_id == opportunity.id` quando ambas são fornecidas, falhando com `AIContextAuthorizationError` em qualquer divergência sem consultar nem sobrescrever objetos ORM do `Session.identity_map` (NC-01 / NC-03).
- **Seleção Factual Canônica via Projeções Escalares e Separação de Origem:** `build_authorized_fact_bundle` projeta diretamente do banco (`select(Model.col1, ...).mappings()`) as 6 entidades de perfil (`ProfessionalProfile`, `WorkExperience`, `ProfessionalProject`, `Education`, `Skill`, `Language`) filtrando `user_id == user.id` e `verification_status == 'confirmed'` em SQL e materializando DTOs imutáveis, impedindo contaminação por atributos adulterados ou promoções de status em memória e preservando edições legítimas pendentes na sessão. Mantém separação explícita entre fatos confirmados do candidato (`candidate_confirmed_facts`) e requisitos externos da vaga (`target_opportunity_context`). **Requisitos da vaga nunca autorizam competências técnicas do candidato.**
- **Minimização, Redação Fail-Closed de PII, Serialização Canônica e Orçamento Determinístico (`safety.py`, `ai_schemas.py`, `context_builder.py`):** além de omitir colunas de contato do perfil, redige PII em campos de texto livre (e-mails diretos/ofuscados, telefones BR/internacionais, URLs/domínios, CPF, CEP e padrões de endereço residencial, omitindo o campo fail-closed caso reste padrão sensível). `user_id` e `truncation_metadata` permanecem exclusivamente no backend (`exclude=True`) e nunca aparecem em `to_provider_payload()`, `to_provider_payload_json()`, `to_provider_payload_bytes()`, `model_dump()` ou `model_dump_json()`. Projetos sem data factual confirmada mantêm `period=None` (nunca inferindo `updated_at.year`). O contexto aplica limites determinísticos (`max_facts <= 60`, `1.024 <= max_payload_bytes <= 24.000` bytes UTF-8) medidos sobre os bytes canônicos exatos de `to_provider_payload_bytes()` (`serialized_bytes == len(to_provider_payload_bytes()) <= 24.000`, NC-02 / NC-04) e sanitização/limite de 200 caracteres em labels sem falhar em perfis extensos.
- **Contratos Estruturados Pydantic v2 com Allowlist de Slots (`ai_schemas.py`):** modelos `extra="forbid"` cobrindo os cinco materiais (`resume`, `cover_letter`, `recruiter_message`, `freelance_proposal`, `application_answers`), com allowlist explícita de `slot_id` por `material_type` (excluindo metadados como `is_approved`, `origin`, `header.email` e `pending_fields`), proibição de `slot_id` duplicado no mesmo lote, vínculo exato entre slot parametrizado e `fact_key` da entidade alvo, e verificação de relevância da evidência citada.
- **Validador Conservador All-or-Nothing (`StructuredGroundingValidator`):** qualquer violação em qualquer sugestão invalida todo o lote (`is_valid = False`):
  - *Métricas Tipadas por Categoria e Significado:* separa percentuais, moedas, durações, anos/datas, versões técnicas e contagens associadas a famílias semânticas (`5 APIs` não autoriza `5 equipes`; `Python 3.13` não autoriza `3.13%`; mês `06` não autoriza `6 anos`; `25%` não autoriza `R$ 25`), com word boundaries estritos em numerais por extenso (PT-BR e EN) e sem nunca derivar autorização da própria resposta da IA.
  - *Tecnologias, Empresas, Cargos e Liderança:* matcher dedicado de tecnologias com fronteiras de token (`Java != JavaScript`) e proteção contra falsos positivos em inglês (`go`, `rest`, `spring`, `redis`, `react`, `node`), validando exclusivamente contra fatos confirmados citados (sem vazamento cross-entity nem autorização pela vaga); bloqueia empresas inventadas/trocadas, promoção de cargos/senioridade, verbos de liderança não sustentados e afirmações qualitativas exageradas (ex.: redução de custos ou transformação sistêmica sem evidência).
  - *Segurança de Saída:* rejeita URLs com/sem protocolo, links Markdown (inclusive multilinha), e-mails diretos e ofuscados (`[at]`/`[dot]`/` at `/` dot `), telefones BR/internacionais (incluindo DDD 19/20), HTML, SVG, atributos `on*` e esquemas ativos (`javascript:`, `vbscript:`, `data:`).
  - *Limitações Epistemológicas e Revisão Humana Obrigatória:* o validador é estrutural, heurístico e conservador — não realiza compreensão semântica absoluta; paráfrases sutis ou distorções de contexto sem marcadores detectáveis continuam exigindo revisão e aprovação humana obrigatória.

### 4.12. Orquestração e Versionamento da IA Assistida (Subfase 04.4.3)
Integra a fundação de cotas/circuit breaker (04.4.1) e o contexto autorizado/grounding (04.4.2) ao ciclo de vida real dos cinco materiais de candidatura:
- **Versionamento Imutável e Estado Persistido de Rejeição (`0012_ai_version_rejection_state`, `models/material.py`):**
  - Versões geradas pela IA recebem `origin="ai_assisted"`, `parent_version_id=source_version.id`, `is_approved=False`, `is_rejected=False` e `is_mutable=False` (toda sugestão de IA nasce imutável, exigindo aprovação humana, derivação `/derive` para edição manual ou rejeição explícita `/reject-ai`).
  - Migration `0012_ai_version_rejection_state` adiciona `is_rejected` (`Boolean`, default `false`) e `rejected_at` (`DateTime(timezone=True)`), com `CheckConstraint` `rejection_state_consistent` (`(NOT is_rejected AND rejected_at IS NULL) OR (is_rejected AND rejected_at IS NOT NULL AND NOT is_approved)`) e índice composto `ix_material_versions_mat_rejected_ver`.
  - **Proibição de exclusão física em rejeição:** `POST /api/v1/materials/{material_id}/versions/{version_id}/reject-ai` marca `is_rejected=True` e `rejected_at=utc_now()` sem executar `DELETE`, preservando integralmente o registro histórico em `application_material_versions` e o vínculo em `ai_usage_ledger.version_id`. Versões ativas (`not is_rejected`) permanecem ordenadas no topo de `versions` (`versions[0]` é sempre a versão ativa mais recente, restaurando `is_mutable=True` para o rascunho anterior), enquanto números de versão seguem estritamente monotônicos (`v1 -> v2 (rejeitada) -> v3`).
- **`ControlledOverlayMerger` Determinístico e Política 2 para `manual_edit` (`overlay_merger.py`):**
  - Opera sobre cópia profunda (`model_copy(deep=True)`) nos cinco materiais (`resume`, `cover_letter`, `recruiter_message`, `freelance_proposal`, `application_answers`), preservando `BlockProvenance` estritamente em `Literal["confirmed_fact", "manual_edit", "user_authored"]` (compatível com o frontend sem quebrar `PROVENANCE_META`).
  - Protege de forma absoluta blocos `user_authored`, `pending_fields` e metadados estruturais (`header`, `education`, `skills`, `languages`, `manual_notes`); recalcula `has_unverified_manual_edits` após o overlay e recalcula `character_count` em `recruiter_message` **depois** da normalização Pydantic v2 (`model_validate`), garantindo igualdade exata com o texto renderizado.
  - Rejeita caracteres de controle proibidos, textos vazios pós-sanitização (`&nbsp;`, espaços Unicode/zero-width), citações cruzadas entre entidades (`cross_entity_citation`) e sugestões que excedam o limite real do slot (`3.000` em `summary`, `1.000` em `target_alignment`, `300` em `subject`, `4.000` nos demais) com `AIOverlayConflictError`, sem truncamento silencioso e sem jamais ecoar `slot_id` não reconhecido na versão de origem.
  - **Política 2 para `manual_edit`:** em modo automático (`target_slot_ids=None`), blocos `manual_edit` são preservados; em modo explícito (`target_slot_ids=[...]`), blocos `manual_edit` listados são elegíveis (exceto em `application_answers`, onde apenas itens `answered_from_facts` com `provenance="confirmed_fact"` são elegíveis).
- **Orçamento Global de 24.000 Bytes, Contrato `commit=False`, Persistência Atômica e Proteção TOCTOU (`orchestrator.py`, `execution_guard.py`, `_db_locks.py`):**
  - Orçamento global estrito medido sobre a serialização canônica completa de `LLMStructuredRequest.structured_input` (`len(serialize_canonical_provider_payload(structured_input)) <= 24.000` bytes UTF-8): reserva prioritariamente até 75% (`18.000` bytes) para `candidate_confirmed_facts` e `target_opportunity_context`, ajustando dinamicamente `reference_draft_slots_untrusted_for_facts` e `user_writing_preferences` por busca binária em bytes UTF-8 para que rascunhos ou instruções nunca expulsem fatos confirmados.
  - Em Sessão #2 pós-provider, adquire lock exclusivo (`acquire_material_exclusivity_lock`: `UPDATE` imediato no SQLite e `SELECT ... FOR UPDATE` no PostgreSQL 16 em ordem canônica de 5 níveis, também aplicado em `delete_material` e nas demais mutações com `run_atomic_with_sqlite_retry`), compara impressão digital completa (fingerprint TOCTOU cobrindo conteúdo, status, versão ativa máxima e **todos os vínculos ativos e históricos** em `application_material_links`) e executa persistência da nova versão, atualização do circuit breaker e confirmação do ledger (`version_id=new_version.id`) com `commit=False` explícito (`allow_transaction_reset=False`, nunca comitando implicitamente após `flush()`) em **um único commit atômico** (com sessão curta de contingência protegida desde `session_factory()` para reconciliar commits ambíguos sem mascarar a exceção primária).
- **Endpoints FastAPI, CORS e Sanitização de Erros (`api/routes/materials.py`, `main.py`):**
  - `POST /api/v1/materials/{material_id}/versions/{version_id}/ai-enhance` (`201 Created`) e `POST /api/v1/materials/{material_id}/versions/{version_id}/reject-ai` (`200 OK`), protegidos por autenticação HttpOnly, CSRF e isolamento por `user_id` (`404` uniforme).
  - Respostas de erro (`422` grounding/overlay, `409` TOCTOU/estado, `429` quota com `Retry-After`, `502` malformed/provider error, `503` disabled/circuit open com `Retry-After`, `504` timeout) retornam códigos estáticos sanitizados (`X-AI-Error-Code`, exposto junto com `Retry-After` e `Content-Disposition` no `CORSMiddleware`) e `detail: str` alinhado aos 26 códigos canônicos de `StructuredGroundingValidator`, sem jamais ecoar trechos brutos ou `slot_id` não reconhecido da saída do provider.
- **Fora de escopo nesta subfase:** provedores HTTP externos reais (Gemini, OpenAI, Anthropic, Ollama, OpenRouter) e interface visual da IA no frontend (Subfase 04.4.4).

### 4.13. Encerrando o Ambiente

Para parar os containers sem perder os dados do banco:

```powershell
docker compose --env-file .env -f infra/compose.yaml down
```

---

## 5. Desenvolvimento e Execução de Testes Localmente

### Backend (Pytest + Alembic)
Execução rápida local (SQLite — suíte completa ou Subfases 04.4.1 / 04.4.2 / 04.4.3):
```powershell
cd backend
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\pytest.exe tests\test_ai_foundation_phase0441.py tests\test_ai_grounding_phase0442.py tests\test_ai_orchestration_phase0443.py -v
```

Validação completa contra **PostgreSQL 16 real** via Docker Compose (usando banco isolado `jobhunter_test`):
```powershell
docker exec job-hunter-db psql -U jobhunter_user -d jobhunter -c "CREATE DATABASE jobhunter_test OWNER jobhunter_user;"
docker compose --env-file .env -f infra/compose.yaml --profile test run --rm --build backend-test
```
*(Também é possível definir `TEST_DATABASE_URL` apontando para um banco PostgreSQL dedicado cujo nome contenha `test`.)*

### Frontend (TypeScript + ESLint + Vitest + Build)
```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

---

## 6. Documentação Complementar

- [DEPLOY.md](DEPLOY.md): Instruções detalhadas de execução local, portas e preparação para publicação segura via Cloudflare Tunnel (`https://jobhunter.ctrls.dev.br`).
- [SECURITY.md](SECURITY.md): Arquitetura de segurança, isolamento multiusuário (`user_id`), Argon2id, sessões HttpOnly, proteção CSRF e controles aplicados.
- [CHANGELOG.md](CHANGELOG.md): Histórico de entregas do projeto.

### Subfase 04.4.4 — AI Studio (frontend)

O modal de materiais possui a aba **AI Studio & Comparação**: solicitar aprimoramento por IA (todos os 5 tipos), comparar estruturadamente a sugestão com a versão de origem, ver proveniência e fatos citados, e decidir (aprovar, editar como versão derivada ou rejeitar). Sugestões nunca são aprovadas automaticamente. A UI depende de `AI_ASSISTED_ENABLED` e do provider configurados no backend; erros são exibidos com base em `X-AI-Error-Code`/`Retry-After`.

