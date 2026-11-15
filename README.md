# Job Hunter

Plataforma de descoberta, análise e preparação supervisionada de candidaturas para oportunidades profissionais na área de tecnologia (**Estágios**, **Desenvolvedor Júnior / Posições de Entrada** e **Projetos Freelance** no Brasil e no exterior).

- **Hostname planejado:** `https://jobhunter.ctrls.dev.br`
- **Fase atual:** Fase 02 — Motor de Descoberta de Oportunidades v1
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
│   │   │   └── 0003_opportunity_discovery.py
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

- **Fontes integradas e habilitadas:**
  - **Remote OK (`remote_ok`)**: feed JSON público sem chave, intervalo mínimo padrão de `3600s` (1h), com atribuição visível e links diretos **sem `rel="nofollow"`** conforme termos oficiais (`https://remoteok.com/terms`).
  - **Remotive (`remotive`)**: feed JSON público de desenvolvimento de software (`https://remotive.com/api/remote-jobs?category=software-dev`), intervalo mínimo de `21600s` (6h, máx. 4 req/dia recomendado nos termos), com crédito visível e link direto sem redistribuição em massa.
- **Fontes avaliadas e não integradas nesta etapa:**
  - **Gupy**: API oficial (`api.gupy.io`) exige token Bearer corporativo por empresa recrutadora, não sendo feed público livre.
  - **Arbeitnow**: termos gerais restringem redistribuição comercial sem autorização explícita; mantida pendente de revisão jurídica caso evolua para SaaS.
  - **Jobicy**: API v2 pública (`1 req/h`) mapeada como candidata futura complementar.
  - **Workana**: desabilitada por restrição do perfil do usuário e política anti-scraping.

Para sincronizar as fontes públicas via CLI:

```powershell
# Validação sem gravar no banco
docker exec job-hunter-backend python -m app.cli sync-opportunities --dry-run

# Sincronização padrão (respeita intervalo mínimo por fonte)
docker exec job-hunter-backend python -m app.cli sync-opportunities
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
