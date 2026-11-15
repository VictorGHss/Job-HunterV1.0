# Changelog

Todas as mudanças relevantes deste projeto serão documentadas neste arquivo.

O formato baseia-se em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

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
