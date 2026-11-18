# Job Hunter

Plataforma de descoberta, análise e preparação supervisionada de candidaturas para oportunidades profissionais na área de tecnologia (**Estágios**, **Desenvolvedor Júnior / Posições de Entrada** e **Projetos Freelance** no Brasil e no exterior).

- **Hostname planejado:** `https://jobhunter.ctrls.dev.br`
- **Fase atual:** Subfase 04.4.1 — Fundação e Infraestrutura de IA Assistida
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
│   │   │   └── 0010_application_materials.py
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
│   │   │   │   ├── matching.py
│   │   │   │   ├── opportunity_service.py
│   │   │   │   ├── sanitization.py
│   │   │   │   └── sync_service.py
│   │   │   ├── application_service.py
│   │   │   ├── auth_service.py
│   │   │   └── profile_service.py
│   │   ├── cli.py
│   │   └── main.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_applications_phase03.py
│   │   ├── test_applications_phase032.py
│   │   ├── test_foundation_phase01.py
│   │   ├── test_materials_phase041.py
│   │   ├── test_materials_phase042.py
│   │   ├── test_materials_phase043.py
│   │   ├── test_opportunities_phase02.py
│   │   ├── test_opportunity_authorization_phase0411.py
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
  - **Catálogo consolidado após Fases 02.5–02.6.1 (`195` oportunidades únicas e `203` vínculos de publicação em `opportunity_source_links`):** rastreabilidade normalizada de todas as fontes primárias e secundárias (`source_url`, `application_url`, `external_id`, `source_status`, `first_seen_at`, `last_seen_at`, `last_checked_at`), deduplicação segura sem falsos positivos por mero `(title, company_name)` e métricas auditáveis de sincronização (`received_count == valid_count + rejected_count` e `valid_count == inserted_count + updated_count + intra_source_duplicate_count + cross_source_duplicate_count`).
  - **Classificação determinística em múltiplas dimensões (`classification.py`)**: separa `opportunity_type` (campo legado para retrocompatibilidade), `seniority_level` (`internship`, `entry_level`, `junior`, `mid_level`, `senior`, `staff_principal`, `management`, `unknown`), `employment_type` (`internship`, `clt`, `pj`, `freelance`, `temporary`, `other`, `unknown`), requisitos de experiência (`experience_requirement_mode`: `none_required`, `preferred`, `required`, `not_specified`, com extração PT/EN singular/plural e faixas sem confundir requisitos puramente técnicos de ferramentas com anos profissionais nem rebaixar senioridade por menções desejáveis) e `professional_area` + `secondary_areas`, reconhecendo expressões PT-BR como `"Desenvolvimento de Software"` e bloqueando falsos positivos de suporte/atendimento/vendas.
  - **Matching multidimensional (`matching.py`) e independência de filtros:** avalia área profissional, geografia, contrato, senioridade, requisitos de experiência (isolando estritamente experiências com `eligible_as_target_role=False`, suporte de TI, intervalos sobrepostos, formação acadêmica e projetos) e habilidades técnicas do perfil (`Skill`, `WorkExperience`, `ProfessionalProject`, `Education` e preferências). As abas da UI e endpoints utilizam os campos estruturados independentes (`?seniority=internship`, `?seniority=junior`, `?employment_type=freelance` e `?compatibility=`).
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
- **Providers disponíveis e escopo atual:** implementados o protocolo agnóstico `LLMProvider`, `DisabledLLMProvider` e `MockLLMProvider` (restrito a testes e bloqueado em `ENVIRONMENT=production`). **Ainda não estão implementados nesta subfase:** providers HTTP externos (Gemini/OpenAI/Anthropic/Ollama/OpenRouter), `ContextBuilder`, `StructuredGroundingValidator`, geração/overlay de versões `ai_assisted`, endpoints de aprimoramento e interface de revisão/diff no frontend.

### 4.11. Encerrando o Ambiente

Para parar os containers sem perder os dados do banco:

```powershell
docker compose --env-file .env -f infra/compose.yaml down
```

---

## 5. Desenvolvimento e Execução de Testes Localmente

### Backend (Pytest + Alembic)
Execução rápida local (SQLite — suíte completa ou apenas Subfase 04.4.1):
```powershell
cd backend
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\pytest.exe tests\test_ai_foundation_phase0441.py -v
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
