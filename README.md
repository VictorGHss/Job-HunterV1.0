# Job Hunter

Plataforma de descoberta, análise e preparação supervisionada de candidaturas para oportunidades profissionais na área de tecnologia (**Estágios**, **Desenvolvedor Júnior / Posições de Entrada** e **Projetos Freelance** no Brasil e no exterior).

- **Hostname planejado:** `https://jobhunter.ctrls.dev.br`
- **Fase atual:** Fase 02.5 — Confiabilidade, Rastreabilidade e Ciclo de Vida das Oportunidades
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
│   │   │   └── 0005_lifecycle_traceability.py
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── auth.py
│   │   │   │   ├── health.py
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
│   │   │   ├── opportunity.py
│   │   │   ├── profile.py
│   │   │   └── user.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── opportunity.py
│   │   │   └── profile.py
│   │   ├── services/
│   │   │   ├── opportunities/
│   │   │   │   ├── connectors/
│   │   │   │   ├── matching.py
│   │   │   │   ├── opportunity_service.py
│   │   │   │   ├── sanitization.py
│   │   │   │   └── sync_service.py
│   │   │   ├── auth_service.py
│   │   │   └── profile_service.py
│   │   ├── cli.py
│   │   └── main.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_foundation_phase01.py
│   │   └── test_opportunities_phase02.py
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
  - **Remote OK (`remote_ok`)**: feed JSON público sem chave (`https://remoteok.com/api`), atribuição visível e links diretos **sem `rel="nofollow"`** (`99` oportunidades únicas no catálogo local).
  - **Jobicy (`jobicy`)**: API v2 pública oficial (`https://jobicy.com/api/v2/remote-jobs?count=50&industry=dev`), sem chave, limite oficial `<= 1 req/h`, com unificação de clones multi-país preservando todos os links e mesclando países elegíveis (`43` oportunidades únicas + `7` vínculos secundários regionais em `opportunity_source_links`).
  - **Himalayas (`himalayas`)**: API JSON pública oficial (`https://himalayas.app/jobs/api/search?q=software+developer`), sem chave, identificadores compostos `<company>/jobs/<slug>`, preservação integral de `applicationLink` (`?utm_source=api`) e controle de ciclo de vida via `expiryDate` (`20` oportunidades únicas).
  - **GitHub Backend BR (`github_backend_br`)** e **GitHub Frontend BR (`github_frontend_br`)**: repositórios comunitários brasileiros licenciados sob **MIT** (`backend-br/vagas` e `frontendbr/vagas`, observando que a licença MIT do repositório não suprime direitos sobre conteúdo de terceiros) consumidos via API REST oficial v3 do GitHub (`per_page=30`), com filtragem de PRs/issues `Stale`/avisos administrativos, revalidação de issues encerradas/removidas e **redação automática de PII** (e-mails e telefones pessoais) no corpo da vaga (`30` + `3` oportunidades únicas + `1` vínculo compartilhado entre ambos os repositórios).
  - **Catálogo consolidado após Fase 02.5 (`195` oportunidades únicas e `203` vínculos de publicação em `opportunity_source_links`, com `53` compatíveis com o perfil):** rastreabilidade normalizada de todas as fontes primárias e secundárias (`source_url`, `application_url`, `external_id`, `source_status`, `first_seen_at`, `last_seen_at`, `last_checked_at`), deduplicação segura sem falsos positivos por mero `(title, company_name)` e métricas auditáveis de sincronização (`received_count == valid_count + rejected_count` e `valid_count == inserted_count + updated_count + intra_source_duplicate_count + cross_source_duplicate_count`).
  - **Classificação determinística tridimensional (`classification.py`)**: avalia de forma independente `opportunity_type`, `employment_type` e `professional_area` + `secondary_areas` (`software_development`, `backend`, `frontend`, `fullstack`, `data`, `artificial_intelligence`, `devops_cloud`, `api_integrations`, `infrastructure`, `technical_support`, `customer_support`, `marketing_sales`, `healthcare`, `administration`, `other`, `unknown`), bloqueando falsos positivos de tecnologias mencionadas incidentalmente em vagas de suporte, atendimento, marketing ou saúde.
  - **Matching por área e relevância (`matching.py`)**: distingue área compatível, incompatível e não identificada (`unknown`), impede recomendação de suporte técnico/atendimento/marketing como desenvolvimento, mantém `employment_type=unknown` elegível mesmo com `block_clt=true` e permite filtrar por área na API (`GET /api/v1/opportunities?area=...`) e na interface.
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
# Validação sem gravar no banco
docker exec job-hunter-backend python -m app.cli sync-opportunities --dry-run

# Sincronização padrão (respeita intervalo mínimo por fonte)
docker exec job-hunter-backend python -m app.cli sync-opportunities

# Reclassificação determinística segura em registros externos já persistidos
docker exec job-hunter-backend python -m app.cli reclassify-opportunities --source remote_ok --dry-run
docker exec job-hunter-backend python -m app.cli reclassify-opportunities --source remote_ok
```

Oportunidades brasileiras locais, estágios acadêmicos ou freelas recebidos fora dos feeds podem ser cadastrados de forma privada pelo botão **Adicionar Oportunidade** ou via **Web Share Target (PWA)** no navegador/Android, sem raspagem automática de HTML pelo servidor.

### 4.6. Encerrando o Ambiente

Para parar os containers sem perder os dados do banco:

```powershell
docker compose --env-file .env -f infra/compose.yaml down
```

---

## 5. Desenvolvimento e Execução de Testes Localmente

### Backend (Pytest + Alembic)
Execução rápida local (SQLite):
```powershell
cd backend
.\.venv\Scripts\pytest.exe
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
