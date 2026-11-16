# Changelog

Todas as mudanças relevantes deste projeto serão documentadas neste arquivo.

O formato baseia-se em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

---

## [0.2.3] - 2026-11-15 — Fase 02.3: Classificação por Área Profissional e Relevância do Matching

### Adicionado
- **Taxonomia e Persistência de Área Profissional (`0004_professional_areas`):**
  - Novo enum `ProfessionalArea` (`software_development`, `backend`, `frontend`, `fullstack`, `data`, `artificial_intelligence`, `devops_cloud`, `api_integrations`, `infrastructure`, `technical_support`, `customer_support`, `marketing_sales`, `healthcare`, `administration`, `other`, `unknown`) e colunas `professional_area` + `secondary_areas` na tabela `opportunities` com migração incremental e downgrade funcional.
- **Classificador Determinístico Multi-Área (`classify_professional_area`):**
  - Classifica área primária e especialidades secundárias independentemente de `opportunity_type` e `employment_type`, bloqueando falsos positivos de suporte técnico, atendimento, marketing, vendas, saúde e administração mesmo quando mencionam tecnologias incidentalmente ou possuem tags ruidosas.
- **Matching por Relevância de Área (`matching.py`) e Filtro na API/Interface:**
  - `OpportunityMatchEvaluation` expandido com `area_compatibility` (`compatible`, `incompatible`, `unknown`), `matched_areas`, `matched_technologies`, `missing_priority_technologies` e `uncertainty_notes`.
  - Filtro `area` em `GET /api/v1/opportunities` (considerando área primária e secundárias) e seletor de **Área profissional** com badges legíveis em português em `OpportunityDiscoveryPage.tsx`.
  - Comando `reclassify-opportunities` atualizado para recalcular e persistir `professional_area` e `secondary_areas` de forma idempotente.

---

## [0.2.2] - 2026-11-15 — Fase 02.2: Auditoria e Refinamento da Classificação de Oportunidades

### Alterado
- **Classificador Determinístico Refinado (`classification.py` e `RemoteOKConnector`):**
  - Substituída a heurística por substring simples em `remote_ok.py` pelo módulo dedicado `app/services/opportunities/classification.py` com normalização Unicode/acentos, reparo seguro de mojibake UTF-8/Latin-1, fronteira lexical estrita e separação de peso entre título, descrição higienizada (desconsiderando senioridade de colegas/reportados) e tags ruidosas.
  - Eliminados falsos positivos de `"intern"` em `internal`/`international`, de `"contract"` em `Contracts Manager` / `smart contract` e de tags ruidosas (`Telehealth Endocrinologist` com tag `internship`; `Team Lead Account Executive` com tag `junior`).
  - Recuperados falsos negativos identificados apenas na descrição/título acadêmico (`Jr. UI Developer`, `entry-level` em `Travel Support Specialist`, `Independent Contractor` em `AI Content Reviewer`, `part-time freelance` em `APAC Python`, `Marketing Student Assistant`).
  - Separado estritamente `opportunity_type` de `employment_type` (`unknown` quando contrato não informado; `pj`, `freelance`, `temporary`, `clt` e `internship` quando houver evidência clara).
- **Reclassificação Segura e CLI (`reclassify-opportunities`):**
  - Adicionados `reclassify_opportunities` em `sync_service.py` e subcomando `python -m app.cli reclassify-opportunities [--source remote_ok --dry-run]`.
  - Atualiza exclusivamente `opportunity_type` e `employment_type` de fontes externas habilitadas de forma idempotente, recusando fontes desabilitadas (`remotive`) e preservando cadastros manuais, `opportunity_user_states`, metadados e histórico temporal.
- **Testes:**
  - Expandida a suíte `tests/test_opportunities_phase02.py` com casos de fronteira lexical, acentuação, mojibake, conflito entre tags/título/descrição, separação de contrato e idempotência/preservação da reclassificação via CLI.

---

## [0.2.1] - 2026-11-15 — Fase 02.1: Conformidade das Fontes e Primeira Sincronização Real

### Alterado
- **Governança Explícita de Fontes (`SourceDefinition` e `sync_service.py`):**
  - Adicionados campos `enabled_by_default` e `disabled_reason` em `SourceDefinition`.
  - `RemoteOKConnector` mantido ativo (`enabled_by_default=True`, intervalo `3600s`, atribuição visível e links diretos sem `nofollow`).
  - `RemotiveConnector` desabilitado temporariamente (`enabled_by_default=False`) aguardando esclarecimento e autorização escrita sobre restrições nos Termos de Uso gerais de março de 2026 para agregação multiusuário; código preservado para eventual retomada após autorização.
  - `ensure_default_sources` força `enabled=False` para fontes bloqueadas por padrão no código e preserva desabilitações manuais no banco sem reativá-las automaticamente.
  - `sync_sources` recusa `--source remotive`, bloqueia qualquer requisição HTTP a fontes desabilitadas mesmo com `--force` e registra estado fiel em `GET /api/v1/opportunities/sources`.
- **Frontend (`OpportunityDiscoveryPage.tsx`):**
  - Indicador de fontes não sincronizadas passa a considerar apenas fontes habilitadas; seletor exibe rótulo explícito `(desabilitada)` para fontes pausadas.
- **Primeira Sincronização Real:**
  - Executada exclusivamente com `remote_ok` no banco PostgreSQL local `jobhunter`: **97 oportunidades coletadas e inseridas** (`88 other`, `4 junior`, `3 freelance`, `2 internship`), sem consultar a Remotive.
- **Testes:**
  - Adicionado `test_source_compliance_remotive_disabled_and_remote_ok_active` em `tests/test_opportunities_phase02.py` cobrindo os 9 cenários de conformidade, `--force`, `--source remotive`, não reativação e isolamento de falhas.

---

## [0.2.0] - 2026-11-15 — Fase 02: Motor de Descoberta de Oportunidades v1

### Adicionado
- **Modelagem e Migração Alembic (`0003_opportunity_discovery`):**
  - Novas tabelas `opportunity_sources`, `opportunities`, `opportunity_user_states` (unicidade `(user_id, opportunity_id)`) e `opportunity_sync_runs` com compatibilidade PostgreSQL 16 (`JSONB`/`UUID`) e SQLite.
- **Conectores Reais Auditados e Pipeline de Sincronização:**
  - `RemoteOKConnector` (`https://remoteok.com/api`, intervalo mínimo 1h, atribuição obrigatória sem `nofollow` e skip de item legal) e `RemotiveConnector` (`https://remotive.com/api/remote-jobs?category=software-dev`, intervalo mínimo 6h, parsing salarial e de localização requerida).
  - Hardening HTTP em `BaseOpportunityConnector`: timeouts, teto de payload em bytes (`SYNC_MAX_RESPONSE_BYTES`), respeito a `Retry-After` em `429`, backoff e isolamento de falhas.
  - Deduplicação em 3 camadas (`(source_id, external_id)`, URL canônica sem parâmetros `utm_*`/`ref` e `content_hash`), preservação de `first_seen_at` e detecção conservadora de ausência após `3` ciclos sem resposta positiva.
  - Comando CLI `python -m app.cli sync-opportunities [--source ... --force --dry-run]`.
- **Motor Determinístico de Filtragem e Explicabilidade (`evaluate_opportunity_for_user`):**
  - Avaliação explicável sem IA generativa e sem score percentual arbitrário, respeitando `block_clt` (sem confundir estágio com CLT), `workana_enabled`, `gupy_mode`, `excluded_areas`, idioma, aderência substantiva em tecnologia/requisitos/descrição (não apenas palavra no título) e verificação geográfica (`eligible`, `excluded`, `unknown`).
- **API Autenticada e Proteções (`/api/v1/opportunities`):**
  - Listagem paginada (`page_size <= 50`) com filtros combináveis no servidor, consulta individual, cadastro manual privado (`POST /manual` com bloqueio anti-SSRF), edição restrita apenas a oportunidades privadas do próprio usuário (`403` em globais) e estados individuais (`PATCH /{id}/state`).
- **Frontend de Descoberta e Captura Manual / PWA:**
  - Telas interativas para `Estágios`, `Desenvolvedor Júnior` e `Freelancers` (`OpportunityDiscoveryPage.tsx`) com busca, filtros, paginação, explicabilidade, atribuição visível sem `nofollow`, estado salvo/dispensado e sinalização de elegibilidade geográfica incerta.
  - Modal de cadastro privado (`ManualOpportunityModal.tsx`) integrado diretamente ao banner de recebimento do PWA Web Share Target.
- **Testes:**
  - Nova suíte backend `tests/test_opportunities_phase02.py` (conectores mockados, deduplicação, 429/timeout/payload limit, matching determinístico, privacidade multiusuário, imutabilidade de fontes globais e CLI).
  - Suíte frontend `App.test.tsx` ampliada para busca, paginação, salvar/dispensar, atribuição de links, estados vazio/erro e captura PWA Web Share Target.

---

## [0.1.1] - 2026-11-15 — Fase 01.1: Hardening da Fundação, Isolamento de Dados Pessoais e Segurança

### Adicionado
- **Importação Local e Privada de Perfil (`import-profile-seed`):**
  - Comando CLI administrativo `python -m app.cli import-profile-seed` (`--email` ou `--user-id` e `--file`), transacional, com validação estrita via `ProfileSeedDocumentSchema` (`schema_version: 1`, `extra="forbid"`, proibição de `verification_status="confirmed"`), preservação de campos/preferências/confirmações existentes, deduplicação por chave natural e rollback em caso de falha.
  - Estrutura `local-seeds/` com exemplo genérico (`profile-seed.example.json`), regra `.gitignore` protegendo arquivos pessoais (`profile-seed.local.json`) e montagem somente leitura (`/run/local-seeds:ro`) no `infra/compose.yaml`.
- **Rate Limiting Persistente de Login e Proteção Anti-Spoofing (`auth_rate_limits`):**
  - Nova migração Alembic `0002_auth_rate_limiting` e modelo `AuthRateLimit` (PostgreSQL/SQLite, sem Redis), com chaves HMAC-SHA256 para janela e cooldown por `(IP, conta)` e por `IP`, cabeçalho `Retry-After` em respostas `429` e preservação contra enumeração de contas ou DoS global por conta.
  - Extração de IP confiável (`extract_trusted_client_ip`) com `TRUSTED_PROXY_CIDRS`, traversal reverso de `X-Forwarded-For` e opt-in `TRUST_CF_CONNECTING_IP`.
- **Validação Estrita de Segurança em Produção:**
  - Startup do backend valida `COOKIE_SECURE=true`, força mínima de `SECRET_KEY` (sem placeholders) e `CORS_ORIGINS` HTTPS não vazio e sem wildcard `*` quando `ENVIRONMENT=production`.
- **Infraestrutura Multi-Stage e Validação com PostgreSQL 16:**
  - `backend/Dockerfile` separado nos estágios `base` (produção sem dependências de teste) e `test`, além de serviço `backend-test` (`profiles: ["test"]`) em `infra/compose.yaml` executando `pytest` contra PostgreSQL 16 real (`jobhunter_test`).

### Alterado
- Perfis e preferências criados para novos usuários (`get_or_create_profile` e `default_career_preferences`) agora iniciam com valores totalmente genéricos e neutros.
- `frontend/nginx.conf` atualizado para propagar `X-Forwarded-Host` ao backend.
- Placeholders e textos da interface React (`DashboardViews.tsx`, `ProfilePage.tsx`) e mocks de teste (`App.test.tsx`) higienizados para remover qualquer referência pessoal específica.
- Documentação canônica (`README.md`, `DEPLOY.md`, `SECURITY.md`, `CHANGELOG.md`) atualizada com fluxo privado de seed, proxy confiável, rate limiting e testes em PostgreSQL 16.

### Removido
- Removidos todos os dados profissionais particulares do código compartilhado (`profile_service.py` e suítes de teste).
- Removido o endpoint público `POST /api/v1/profile/seed-initial`, a função `seed_initial_profile_draft()`, a flag `--seed-initial-profile` do `create-admin` e todos os botões/chamadas equivalentes no frontend.

---

## [0.1.0] - 2026-11-15 — Fase 01: Fundação Arquitetural e Perfil Profissional Central

### Adicionado
- **Arquitetura Monólito Modular (`backend/`, `frontend/`, `infra/`):**
  - Backend em Python + FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + PostgreSQL.
  - Frontend em React 18 + TypeScript + Vite + Tailwind CSS + componentes estilo `shadcn/ui`.
  - Orquestração Docker Compose (`infra/compose.yaml`) com healthchecks, volume persistente `job_hunter_pgdata` e banco PostgreSQL isolado na rede interna.
- **Multiusuário e Segurança desde a Origem:**
  - Entidades `User` e `UserSession` com identificadores UUID, hash de senha `Argon2id`, hash `SHA-256` para tokens de sessão, cookies `HttpOnly`, proteção `CSRF` (`X-CSRF-Token`) e revogação imediata no logout.
  - Comando CLI seguro (`python -m app.cli create-admin`) para provisionamento do administrador sem cadastro público e sem credenciais padrão.
  - Isolamento estrito por `user_id` em todos os endpoints do perfil profissional.
- **Perfil Profissional Central (Fonte Única de Verdade):**
  - Modelagem, migração Alembic (`0001_initial_foundation`) e CRUD completo para:
    - `ProfessionalProfile` (dados pessoais opcionais, resumo, links e preferências JSONB).
    - `WorkExperience` (experiências profissionais, tecnologias, competências e flag `eligible_as_target_role`).
    - `Education` (formação acadêmica, semestre e previsão de conclusão).
    - `Skill` (habilidades categorizadas e nível autodeclarado).
    - `Language` (idiomas e referência CEFR).
    - `ProfessionalProject` (projetos profissionais, links e resultados comprovados).
  - Mecanismo de validação de fatos (`draft`, `pending_validation`, `confirmed` + `confirmed_at`) para impedir uso de dados não validados pela futura IA.
  - Serviço e endpoint (`POST /api/v1/profile/seed-initial`) para preparar o rascunho inicial do perfil profissional e preferências da Fase 01 (substituído na Fase 01.1 pela importação local privada via CLI).
- **Interface Mobile-First, Temas e Preparação PWA:**
  - Temas Claro (lavanda suave + roxo), Escuro (preto/grafite + roxo, sem excesso de cartões brancos) e Automático (sistema), com alternância manual e persistência em `localStorage`.
  - Manifesto PWA (`manifest.webmanifest`) com suporte a `share_target` para recebimento futuro de links compartilhados pelo Android.
  - Estrutura de navegação responsiva para `Início`, `Estágios`, `Desenvolvedor Júnior`, `Freelancers`, `Candidaturas` e `Perfil`.
- **Qualidade e Testes Automatizados:**
  - Suíte Pytest no backend cobrindo inicialização, health check, migrações Alembic (`upgrade`/`downgrade`), login válido/inválido, CSRF, logout, seed inicial, validações, CRUD completo e isolamento estrito entre dois usuários.
  - Suíte Vitest + Testing Library no frontend cobrindo tela de login, alternância/persistência de temas, dashboard inicial e edição do perfil.
- **Documentação Canônica:**
  - `README.md`, `DEPLOY.md`, `SECURITY.md` e `CHANGELOG.md` em português brasileiro.
