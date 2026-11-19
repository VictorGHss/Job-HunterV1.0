# Changelog

Todas as mudanças relevantes deste projeto serão documentadas neste arquivo.

O formato baseia-se em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

---

## [0.4.4.2] - 2026-11-19 — Subfase 04.4.2: Contexto Autorizado e Grounding Estruturado

### Adicionado e Endurecido

- **Proteção Compartilhada de PII e Conteúdo Ativo (`backend/app/services/materials/ai/safety.py`):**
  - Detectores e redator fail-closed para e-mails diretos e ofuscados (`[at]`, `(at)`, ` at `, `[dot]`, ` dot `), telefones brasileiros e internacionais (incluindo DDD `19`, `20` e `+55 11 98765-4321`), URLs com e sem protocolo (`github.com/user`, `example.com`), links Markdown (inclusive multilinha), perfis sociais rotulados, CPF, CEP, padrões de endereço residencial, HTML/SVG, atributos `on*` e esquemas ativos (`javascript:`, `vbscript:`, `data:`, `mailto:`, `tel:`).
- **Contexto Factual Autorizado, Autorização e Orçamento (`backend/app/services/materials/ai/context_builder.py`, `contracts.py`):**
  - Exceção `AIContextAuthorizationError` e revalidação explícita contra o banco de dados de `application` (`application.user_id == user.id`), `opportunity` (pública `source_id IS NOT NULL` ou privada própria `created_by_user_id == user.id`) e consistência `application.opportunity_id == opportunity.id`.
  - Reutilização direta de `build_authorized_fact_bundle` (`fact_selector.py`) sobre o estado atual do banco, aceitando exclusivamente fatos com `verification_status == 'confirmed'`.
  - Redação fail-closed de PII em todos os campos de texto livre (`professional_summary`, descrições, `verified_results`, notas e campos da oportunidade), além de manter `period=None` para projetos sem data factual confirmada (sem inferir `updated_at.year`).
  - Sanitização e truncamento seguro de labels (`<= 200` caracteres) em `WorkExperience` e `Education`, e orçamento determinístico agregado (`max_facts=60`, `max_payload_bytes=24_000`) com `ContextTruncationMetadata` restrito ao backend.
- **Contratos e Schemas Estruturados Pydantic v2 (`backend/app/services/materials/ai/ai_schemas.py`):**
  - `AuthorizedAIContext`, `AuthorizedFactItem`, `SanitizedOpportunityContext`, `ContextTruncationMetadata`, `AISuggestionItem` e `AIMaterialEnhanceOutput` com `extra="forbid"`.
  - `user_id` e `truncation_metadata` marcados com `Field(exclude=True)` e método dedicado `to_provider_payload()` garantindo ausência de `user_id` em toda serialização externa.
  - Allowlist explícita de `slot_id` por `material_type` (alinhada aos cinco `structured_content` reais, bloqueando metadados como `is_approved`, `origin`, `header.email` e `pending_fields`), rejeição de `slot_id` duplicado no lote e validação de consistência de entidade.
- **Validador Conservador de Grounding All-or-Nothing (`backend/app/services/materials/ai/grounding_validator.py`):**
  - Separação absoluta de origem: requisitos da vaga (`context.opportunity`) nunca autorizam competências do candidato.
  - Vínculo estrito entre slots parametrizados e `fact_key` exata da entidade alvo, proibindo citações cruzadas, mistura projeto/emprego formal e citações irrelevantes (ex.: apenas idioma para alegação de engenharia de software).
  - Grounding numérico tipado por categoria e família semântica (`percentage`, `currency`, `duration`, `year`, `tech_version`, `vague_scale`, `entity_count`, `raw_number`), com word boundaries estritos em numerais por extenso (PT-BR e EN) e sem derivar evidência da própria sugestão.
  - Matcher dedicado de tecnologias (`extract_mentioned_technologies`) com fronteiras de token rígidas (`Java != JavaScript`), catálogo expandido (`MongoDB`, `Spark`, `PyTorch`, `SAP`, `Spring`, `Go`, `Node.js`, `Redis`, `React`, etc.) e desambiguação de palavras naturais em inglês (`go`, `rest`, `spring`, `redis`, `react`, `node`).
  - Validação de empresas inventadas/trocadas, cargos/senioridades, verbos de liderança/propriedade e afirmações qualitativas exageradas sem evidência nos fatos citados.
  - Transparência epistemológica formal explicitando os limites heurísticos e a necessidade permanente de revisão humana.
- **Manutenção Determinística de Teste 04.4.1 (`backend/tests/test_ai_foundation_phase0441.py`):**
  - Mantida a correção determinística em `test_tc441_07` passando `now_fn=lambda: t_crash` na chamada inicial de `execute_guarded_ai_call` para evitar flakiness de virada de dia UTC contra `t_crash` fixo (confirmada pela auditoria independente como legítima — achado B-02).

### Testes
- `tests/test_ai_grounding_phase0442.py`: 96 casos de teste cobrindo todas as sondas de regressão (A-01 a A-04, M-01 a M-05, 5 materiais, isolamento, privacidade e integração com `MockLLMProvider`/`DisabledLLMProvider`).
- Suíte completa do backend: **214/214 testes passando** em SQLite local e em PostgreSQL 16 (`backend-test` / `jobhunter_test`).
- Suíte do frontend: **15/15 testes passando** no Vitest e `tsc --noEmit` sem erros.

---

## [0.4.4.1] - 2026-11-18 — Subfase 04.4.1: Fundação e Infraestrutura de IA Assistida

### Adicionado

- **Configuração Centralizada e Kill Switch (`backend/app/core/config.py`, `.env.example`, `infra/compose.yaml`):**
  - `AI_ASSISTED_ENABLED=false` por padrão (`AI_PROVIDER=disabled`, `AI_MODEL=none`), sem necessidade de API key nem dependência de provider externo para inicializar, migrar ou utilizar qualquer módulo do sistema.
  - Cotas e janelas temporais explícitas em UTC (`10 req / 900s` em janela deslizante `[now - 900s, now]`; `30 req/dia/usuário`, `60.000 tokens/dia/usuário` e `100.000 tokens/dia` globais em dia civil fixo UTC `[00:00:00Z, 24:00:00Z)`), TTL de reserva (`60s`), parâmetros de circuit breaker (`3` falhas consecutivas, `120s` de cooldown) e limites de referência para a futura camada HTTP (`24.0s` total `< 25.0s`, `5.0s` connect, `20.0s` read, `256 KiB` máx.).
  - Bloqueio automático de `AI_PROVIDER=mock` em `ENVIRONMENT=production` (tanto na validação de `Settings` quanto no resolver/construtor de `MockLLMProvider`).
- **Migration Reversível e Persistência Sem Conteúdo Pessoal (`backend/alembic/versions/0011_ai_usage_ledger.py`, `backend/app/models/ai_usage.py`):**
  - Tabelas `ai_usage_ledger`, `ai_quota_scope_locks` e `ai_circuit_breakers` compatíveis com SQLite e PostgreSQL 16 (`upgrade` e `downgrade` `0010 -> 0011 -> 0010` e inicialização direta em `head`).
  - Integridade referencial consciente: `user_id` com `ON DELETE CASCADE` (alinhado à política de conta do projeto) e `material_id` / `version_id` com `ON DELETE SET NULL` (permitindo exclusão de materiais sem quebrar auditoria nem resetar cotas consumidas).
  - Restrição estrita de privacidade: nenhum campo armazena prompts, respostas, currículos, descrições de vagas, PII ou credenciais; identificadores técnicos passam por `validate_safe_technical_identifier`.
- **Pacote de Fundação de IA (`backend/app/services/materials/ai/`):**
  - `contracts.py`: protocolo agnóstico `LLMProvider`, `LLMStructuredRequest`, `LLMStructuredResponse`, `LLMTokenUsage` e exceções normalizadas sem acoplamento a fornecedores externos.
  - `providers.py`: `DisabledLLMProvider` (padrão seguro quando desabilitado) e `MockLLMProvider` (`MockScenario` para resposta válida, resposta inválida, falha de provider, timeout e omissão de tokens, estritamente bloqueado em `production`), sem nenhuma chamada de rede.
  - `_db_locks.py` e `quota_service.py`: reservas atômicas (`reserve_ai_quota`, `confirm_ai_quota_usage`, `fail_ai_quota_usage`, `release_ai_quota_reservation`, `expire_abandoned_reservations`, `get_quota_availability`) com ordenação canônica de locks por escopo (`SELECT ... FOR UPDATE` no PostgreSQL 16 e lock transacional imediato com `busy_timeout` no SQLite), isolamento estrito por `user_id`, expiração automática de reservas abandonadas e tratamento explícito para ausência de contagem de tokens (`usage_reported=false`, sem inventar valores).
  - `circuit_breaker.py` e `execution_guard.py`: circuit breaker compartilhado em SQL (`closed`, `open`, `half_open` com probe único exclusivo) e orquestrador em duas transações curtas que nunca mantém lock ou transação SQL aberta durante chamadas ao provider.
- **Documentação Canônica (`README.md`, `SECURITY.md`, `DEPLOY.md`, `.env.example`):**
  - Documentados kill switch, variáveis `AI_*`, semântica UTC das cotas, contabilização de reservas/falhas, escopo e limitações operacionais do circuit breaker SQL, providers disponíveis e itens fora de escopo nesta etapa.

### Testes
- `tests/test_ai_foundation_phase0441.py`: 10 cenários (`TC-441-01` a `TC-441-10`) cobrindo kill switch, guardas de produção, migration `0010 -> 0011 -> 0010` + startup `head`, integridade referencial `SET NULL` / `CASCADE`, ciclo completo do ledger e expiração de reservas, janelas UTC, concorrência real multi-thread (`Barrier`, mesmo usuário, múltiplos usuários, teto global e falhas concorrentes), ausência de lock SQL durante execução do provider, circuit breaker com probe concorrente em `half_open` e auditoria de privacidade/isolamento/logs.
- Suíte backend completa: **118/118 passando** em SQLite local e em PostgreSQL 16 (`backend-test` / `jobhunter_test`).

---

## [0.4.3] - 2026-11-18 — Subfase 04.3: Exportação Profissional em PDF e DOCX

### Adicionado

- **Módulo de Exportação Documental (`backend/app/services/materials/export/`):**
  - `document_templates.py`: centralização de tokens visuais, margens A4, tipografia, paletas, rótulos bilíngues (`pt-BR` / `en`) e dois templates intercambiáveis sem persistência adicional (`classic_ats` padrão e `modern_minimal`).
  - `document_validation.py`: normalização Unicode NFC, remoção estrita de caracteres XML 1.0 inválidos, validação de URLs externas com `validate_safe_external_url(..., allow_localhost=False)`, verificação SHA-256 das fontes controladas Liberation Sans (SIL OFL 1.1), detecção explícita via tabela `cmap` de caracteres sem glifo na fonte (`[U+XXXX]` sem apagar texto ao redor), limites centralizados (`120.000` caracteres de entrada e `5 MiB` por arquivo final), validação de magic bytes (`%PDF-` / `PK\x03\x04` + abertura `docx.Document`) e sanitização allowlist de nomes de arquivo bloqueando path traversal, CRLF, NUL e nomes reservados Windows.
  - `docx_exporter.py`: geração determinística em `io.BytesIO` com `python-docx` (`>=1.1.2,<2.0.0`), sem embutir fontes binárias, relacionamentos `w:hyperlink`, `keep_with_next`, `widow_control`, `tblHeader`/`cantSplit`, metadados com datas da versão e timestamps ZIP normalizados.
  - `pdf_exporter.py`: geração determinística em memória com `ReportLab Platypus` (`reportlab>=4.2.5,<5.0.0`, `invariant=1`), registro `TTFont` da família Liberation Sans, escaping XML antes de markup controlado, anotações `/Link` válidas, paginação multipágina com `CondPageBreak`/`KeepTogether` seletivo, rodapé `Página X de Y` apenas quando há múltiplas páginas e cabeçalho/marca d'água diagonal `RASCUNHO NÃO APROVADO` / `UNAPPROVED DRAFT` em todas as páginas no modo rascunho.
  - `export_service.py`: orquestração em memória com validação estrita por `user_id`, carregamento exato do `version_id` solicitado, bloqueio obrigatório quando há pendências (`422`), exigência de aprovação quando `allow_draft=false` (`422`), modo rascunho em `allow_draft=true` apenas para versões não aprovadas sem pendências e zero persistência em disco ou PII em logs.
- **Fontes e Container (`backend/Dockerfile`, `backend/pyproject.toml`):**
  - Distribuídos os 4 arquivos TTF da família Liberation Sans (`SIL-OFL-1.1`) em `backend/app/services/materials/export/fonts/` com `LICENSE.txt` e `SHA256SUMS.txt`, complementados pela instalação limpa de `fonts-liberation2` no `backend/Dockerfile`.
  - Adicionado `pypdf>=5.1.0,<6.0.0` em `[project.optional-dependencies] dev`.
- **Rota Binária e Vínculo Histórico (`api/routes/materials.py`, `main.py`, `material_service.py`):**
  - Criado endpoint `GET /api/v1/materials/{material_id}/versions/{version_id}/download` retornando headers `Content-Disposition` (ASCII + RFC 5987 `filename*`), `X-Content-Type-Options: nosniff`, `Cache-Control: no-store, no-cache, must-revalidate, private`, `Pragma: no-cache`, e `Content-Disposition` exposto em `CORSMiddleware` (`expose_headers`).
  - `MaterialSummaryResponse` (`GET /api/v1/materials?application_id=...`) passa a informar `linked_version_id`, `linked_version_number` e `linked_version_is_approved` registrados em `application_material_links`.
- **Frontend (`frontend/src/lib/api.ts`, `DocumentPreviewCard.tsx`, `MaterialWorkspaceModal.tsx`, `ApplicationDetailModal.tsx`):**
  - Implementado `requestBlob(...)` com autenticação HttpOnly, tratamento de erro API, parsing de `Content-Disposition` e download via Blob com `URL.revokeObjectURL`.
  - Adicionado preview documental React puro nos templates `Classic ATS` e `Modern Minimalist`, botões `Baixar PDF` / `Baixar DOCX` (final ou rascunho), bloqueio visual com pendências e atalhos na aba **Materiais** da candidatura apontando estritamente para `linked_version_id`.

### Corrigido (Achados 04.2 — Etapa 0)

- **L-1 (`material_service.py`):** `_preserve_writing_options_on_regenerate` agora recupera campos comerciais preenchidos de `freelance_proposal` (`availability`, `estimated_delivery`, `budget_or_price`, `scope_clarifications`, `additional_requirements`), canal e `contact_name`/`contact_context` aplicáveis quando `writing_options` é omitido ou parcial, sem sobrescrever com defaults vazios, mantendo `user_authored` e integridade da versão anterior.
- **L-2 (`test_materials_phase042.py`):** adicionados testes dedicados comprovando preservação de perguntas e respostas manuais em `/regenerate` de `application_answers` com reavaliação de fatos atualizados do perfil.

### Testes
- `tests/test_materials_phase043.py` (8 testes cobrindo `TC-43-01` a `TC-43-16` e edge cases) + novos testes L-1 e L-2 em `test_materials_phase042.py`.
- Suíte backend completa: **108/108 passando** em PostgreSQL 16 (`backend-test`) e SQLite local.
- `frontend/src/test/App.test.tsx`: **15/15 testes passando**, `tsc --noEmit`, `eslint .` e `vite build` sem erros.

---

## [0.4.2] - 2026-11-17 — Subfase 04.2: Propostas, Cartas e Mensagens Direcionadas

### Adicionado

- **Quatro Novos Tipos de Materiais Determinísticos (`backend/app/models/material.py`):**
  - Estendido `MaterialType` com `cover_letter` (`Carta de apresentação`), `recruiter_message` (`Mensagem para recrutador`), `freelance_proposal` (`Proposta freelance`) e `application_answers` (`Respostas para perguntas de candidatura`), reutilizando a coluna `material_type` (`VARCHAR(32)`) da migration `0010_application_materials` sem necessidade de nova migração Alembic.
- **Compositores Determinísticos Bilíngues (`pt-BR` e `en`, Sem IA Externa):**
  - `writing_common.py`: utilitários determinísticos compartilhados de formatação segura, renderização de texto simples sem placeholders nem links quebrados e proteção contra injeção em dados externos da vaga.
  - `cover_letter_composer.py`: carta estruturada (`recipient_line`, `greeting`, `opening`, `relevance_highlights`, `opportunity_alignment`, `closing`) apoiada exclusivamente em fatos `confirmed`.
  - `recruiter_message_composer.py`: mensagens objetivas por canal (`linkedin`, `email`, `contact_form`) com `character_count` real, contato opcional não inventado e geração limpa sem assunto no canal LinkedIn.
  - `freelance_proposal_composer.py`: proposta técnica com evidências confirmadas e painel estruturado de `pending_fields` (`availability`, `estimated_delivery`, `budget_or_price` obrigatórios + opcionais `scope_clarifications` e `additional_requirements`).
  - `application_answers_composer.py`: resposta determinística pergunta-a-pergunta fornecida manualmente pelo usuário, diferenciando respostas fundamentadas em fatos confirmados (`answered_from_facts`), lacunas que exigem resposta humana (`needs_user_input` com `answer_text=null` para motivação, pretensão salarial, disponibilidade e requisitos sem evidência) e respostas autoradas manualmente (`user_answered` / `user_authored`, sem promover texto livre para fatos do perfil).
- **Orquestração, API e Endurecimento Server-Side (`material_service.py`, `api/routes/materials.py`, `schemas/material.py`):**
  - `GET /api/v1/materials` passa a aceitar filtro opcional `?material_type=...`.
  - `POST /api/v1/materials/pre-analyze` e `POST /api/v1/materials` aceitam `material_type` e `writing_options` (`channel`, `contact_name`, `contact_context`, `freelance_inputs`, `questions`, `initial_answers`), retornando `compatible_material_types` priorizados para o regime da vaga (`freelance_proposal` em destaque para vagas freelance) e `additional_info_needed`.
  - Respostas e versões expõem `rendered_plain_text`, `has_blocking_pending_fields` e `pending_requirements_count`.
  - Validação estrita no servidor: imutabilidade de tipo por material (`422` em payload incompatível), validação contra o `source_facts_snapshot` da versão (`422` para referências inexistentes ou inválidas), reconciliação de proveniência (`confirmed_fact` nunca forjável após edição manual) e bloqueio explícito de aprovação (`POST .../approve` retorna `422`) enquanto houver campos obrigatórios pendentes ou perguntas marcadas como `needs_user_input`.
- **Estúdio Unificado de Materiais no Frontend (`MaterialWorkspaceModal.tsx`, `MaterialTypeEditors.tsx`, `ApplicationDetailModal.tsx`):**
  - Evolução para **Estúdio de Materiais para Candidatura** com seleção dos 5 tipos de material (badges `Recomendado` vs `Sob solicitação`), campos contextuais dedicados, editores estruturados específicos (`CoverLetterEditor`, `RecruiterMessageEditor`, `FreelanceProposalEditor`, `ApplicationAnswersEditor`), contagem aproximada de caracteres em mensagens, bloqueio visual e desabilitação do botão **Aprovar versão** com pendências obrigatórias, além do botão **Novo material direcionado** e badges de tipo na aba **Materiais** dos detalhes da candidatura.
  - Exportação via Markdown e Texto Simples; geração de PDF/DOCX e integração com provedores externos de IA permanecem fora de escopo nesta fase.

### Testes
- `tests/test_materials_phase042.py`: cobertura completa dos cenários `TC-42-01` a `TC-42-29` (todos os 4 novos tipos em `pt-BR` e `en`, proibição de invenção de preço/prazo/motivação/recrutador, reconciliação e rejeição `422` de referências forjadas, imutabilidade de tipo, bloqueio e desbloqueio de aprovação em `freelance_proposal` e `application_answers`, preservação de perguntas em `/regenerate`, isolamento IDOR e filtro `GET /materials?material_type=...`).
- Suítes backend completas: **98/98 passando** em PostgreSQL 16 (`backend-test`) e SQLite local.
- `frontend/src/test/App.test.tsx`: **13/13 testes passando** (incluindo 3 novos fluxos `TC-42-30` em `390x844`, `768x1024` e desktop `1280x800`), além de `tsc --noEmit`, `eslint` e `vite build` sem erros.

---

## [0.4.1.2] - 2026-11-17 — Subfase 04.1.2: Preservação de Confirmação Intencional de Rascunhos e Detecção Real de Omissão

### Corrigido / Endurecido

- **Política de Confirmação e Detecção Real de Omissão (`profile_service.py`):**
  - Introduzido `_requested_verification_status(payload)` usando `payload.model_fields_set` para diferenciar omissão real de `verification_status` no JSON dos valores default dos schemas Pydantic das sub-entidades (`PENDING_VALIDATION` / `DRAFT`).
  - Ajustado `_apply_confirmation_policy` para implementar a matriz completa de 12 transições: registros em `draft` e `pending_validation` permitem confirmação intencional (`confirmed`, gravando `confirmed_at`) com ou sem edição simultânea; payloads sem alteração factual e com campo omitido preservam o estado atual (`draft` ou `confirmed` + `confirmed_at` exato); alterações factuais em registros `confirmed` continuam reabrindo obrigatoriamente para `pending_validation` e limpando `confirmed_at`.
  - `_persist_status_update` e `update_profile` aplicam `_PROFILE_FACTUAL_FIELDS` de forma isolada de metadados (`preferences`), preservando confirmação quando apenas `preferences` muda.
- **Feedback Fiel na Interface (`ProfilePage.tsx`):**
  - Centralizado feedback pós-atualização em `notifyStatusUpdateResult`, sincronizando estado local (`profileForm.verification_status`) e mensagens estritamente a partir do `verification_status` retornado pelo servidor em dados gerais e ações rápidas de todas as sub-entidades.

### Testes
- `tests/test_profile_confirmation_phase0411.py` (37 testes): corrigidos testes anteriores com asserções imprecisas (`notes`/`verified_results` `None -> ""`, listas multi-item e omissão real via HTTP) e adicionada a classe `TestPhase0412ConfirmationMatrixAndOmission` (6 testes cobrindo `draft -> confirmed`, preservação com omissão real em todas as 6 entidades, `preferences`, `links` dict e fluxo quick-confirm de projeto).
- `frontend/src/test/App.test.tsx` (10 testes no total, +2 para 04.1.2): confirma projeto e perfil inicialmente em `draft` e garante que o feedback da UI reflita fielmente `draft` ou `pending_validation` retornados pelo servidor.
- Suíte backend completa em SQLite: **91/91 passando**; frontend: `typecheck`, `lint`, `vitest` (10/10) e `build` passando.

---

## [0.4.1.1] - 2026-11-17 — Subfase 04.1.1: Hardening de Confirmação e Autorização de Oportunidades

### Corrigido / Endurecido

- **Invalidação de Confirmação Após Alteração Factual (`profile_service.py`):**
  - As cinco funções de atualização de sub-entidades (`update_experience`, `update_education`, `update_skill`, `update_language`, `update_project`) e `update_profile` passaram a usar a política centralizada `_apply_confirmation_policy`, que rebaixa obrigatoriamente para `pending_validation` e limpa `confirmed_at` sempre que o conteúdo factual for alterado, **independentemente** de o cliente ter reenviado `verification_status="confirmed"`.
  - Adicionado `_normalize_factual_value` para comparação semântica: `None` e `""` são equivalentes em campos opcionais; listas de tags (`technologies`, `related_skills`) são comparadas como conjuntos sem ordem.
  - Comportamento completo de acordo com os cenários A–G: auto-confirmação de edição bloqueada (A/D); preservação de confirmação quando nada mudou (B/C); reabertura e reconfirmação intencional permitidas (E/F); rascunho nunca confirmado acidentalmente por defaults de PUT (G).
- **Autorização de Oportunidades Privadas em Materiais (`material_service.py`):**
  - `_get_opportunity` substituiu `db.get(Opportunity, id)` por `SELECT ... WHERE id = ? AND (source_id IS NOT NULL OR created_by_user_id = ?)`, impedindo acesso a oportunidades privadas de terceiros.
  - Oportunidades privadas alheias retornam `404 Not Found` idêntico ao de registro inexistente, sem expor título, empresa, descrição, tecnologias ou qualquer metadado.
  - Proteção aplicada em `pre_analyze_material` e `create_material` via `_resolve_target_context`.

### Testes
- `tests/test_profile_confirmation_phase0411.py` (31 testes): cobre as seis entidades com cenários A–G, normalização `None/""` e de listas, persistência no banco e quick-confirm via API.
- `tests/test_opportunity_authorization_phase0411.py` (6 testes): TC-0411-01 a TC-0411-06 — pré-análise e criação com oportunidade privada alheia (`404`), acesso do proprietário (`200/201`), oportunidade pública acessível por qualquer usuário, ID inexistente e isolamento sem exposição indireta.
- Suíte completa: **85/85 passando** em SQLite e em PostgreSQL 16.

---

## [0.4.1] - 2026-11-17 — Subfase 04.1: Fundação de Materiais e Currículo Direcionado Determinístico

### Adicionado
- **Schema de Materiais Versionados e Rastreabilidade (`0010_application_materials`):**
  - Novas tabelas `application_materials`, `application_material_versions` e `application_material_links`, além de restrição única composta `uq_applications_user_id_id` em `applications` (`(user_id, id)`).
  - Integridade referencial multiusuário garantida diretamente no banco por FKs compostas (`fk_mat_links_user_app`, `fk_mat_links_user_mat`, `fk_mat_links_mat_ver`) e índice único parcial `uq_active_link_per_app_material` (`unlinked_at IS NULL`) compatível com PostgreSQL 16 e SQLite.
- **Seletor Estrito de Fatos Confirmados e Análise de Lacunas (`services/materials/fact_selector.py`, `resume_composer.py`):**
  - Pré-análise e geração utilizam **exclusivamente** entidades com `verification_status == 'confirmed'` (`ProfessionalProfile`, `WorkExperience`, `Education`, `Skill`, `Language`, `ProfessionalProject`).
  - Bloqueio determinístico (`422 Unprocessable Content`) quando não há conteúdo substantivo confirmado (ao menos 1 experiência, projeto, formação ou habilidade técnica — contato + idiomas isolados não liberam geração).
  - Separação estrita entre `WorkExperience` e `ProfessionalProject`, respeito integral a `eligible_as_target_role`, preservação de `EducationStatus` (`in_progress`, `completed`, `paused`, `planned`) e proficiências sem inflar níveis nem inventar métricas/anos.
  - Suporte bilíngue (`pt-BR` e `en`), opções explícitas de inclusão de contato no cabeçalho e `source_facts_snapshot` sob allowlist estrita sem e-mail/telefone/endereço completo.
- **Confirmação Seletiva em Lote e Integridade Factual no Perfil (`POST /api/v1/profile/confirm-batch`, `profile_service.py`):**
  - Confirmação atômica seletiva exclusivamente para itens `pending_validation` marcados pelo usuário (rejeita `draft`, IDs cruzados ou inexistentes com rollback integral, limite de 150 itens por requisição, `extra="forbid"`).
  - Atualização de fatos em perfil já confirmado sem envio explícito de `verification_status` degrada automaticamente para `pending_validation` e limpa `confirmed_at`.
- **Ciclo de Vida, Imutabilidade, Edição Estruturada e Concorrência (`/api/v1/materials`, `material_service.py`):**
  - Endpoints sob `/api/v1/materials` para `POST /pre-analyze`, `GET`, `POST`, `GET /{id}`, `PUT /{id}/versions/{ver_id}`, `POST /{id}/versions/{ver_id}/derive`, `POST /{id}/regenerate`, `POST /{id}/versions/{ver_id}/approve`, `GET /{id}/versions/{ver_id}/export`, `POST /link`, `POST /unlink` e `DELETE /{id}`.
  - Alocação de versões protegida por `SELECT ... FOR UPDATE` em `application_materials` + retry controlado em `IntegrityError`.
  - Versões aprovadas ou vinculadas ficam imutáveis (`409 Conflict`), exigindo derivação explícita (`/derive`); reconciliação server-side impede forjar `provenance="confirmed_fact"` em edições manuais ou misturar `project:` em `experiences`.
- **Interface Integrada (`MaterialWorkspaceModal.tsx`, `OpportunityDiscoveryPage.tsx`, `ApplicationDetailModal.tsx`, `ProfilePage.tsx`):**
  - Botão **Gerar currículo** nos cards de oportunidades, aba **Materiais** no modal de detalhes da candidatura (com criação, aprovação, exportação em Markdown/Texto e vínculo/desvínculo), e acesso no **Perfil** para revisão seletiva em lote sem pré-seleção automática.

---

## [0.3.2.1] - 2026-11-16 — Fase 03.2.1: Correção da Referência Temporal de Interações Externas

### Corrigido / Endurecido
- **Monotonicidade da Última Interação Externa (`application_process_service.py`):**
  - Corrigida `record_external_interaction` e unificada com `_maybe_record_interview_interaction` por meio de atualização condicional atômica (`_apply_monotonic_external_interaction_summary`) em `applications` restrita a `last_external_interaction_at IS NULL OR last_external_interaction_at <= interaction_at`.
  - O resumo (`last_external_interaction_at`, `last_external_interaction_type`, `last_external_interaction_note`) agora representa sempre o **maior timestamp conhecido** como unidade lógica indivisível (atualizado de forma determinística apenas para instantes `>=` ao atual, inclusive sob transações concorrentes no PostgreSQL 16), enquanto interações retroativas seguem integralmente preservadas em `application_status_history` com sua data efetiva real, sem reiniciar nem distorcer o contador de `get_stale_applications`.
- **Cobertura de Regressão e Isolamento Entre Candidaturas (`test_applications_phase032.py`):**
  - Adicionados os testes `TC-0321-01` a `TC-0321-10` cobrindo interação retroativa, interação mais recente, primeira interação, timestamp igual, impacto na detecção de estagnação, normalização UTC de timezones distintos, preservação histórica, corrida concorrente (`threading.Barrier`) e tentativa cruzada (`GET`, `PATCH`, `DELETE`) entre duas candidaturas distintas pertencentes ao mesmo usuário (`404 Not Found`).

---

## [0.3.2] - 2026-11-16 — Fase 03.2: Gestão Avançada de Processos Seletivos

### Adicionado
- **Entrevistas, Testes Técnicos, Contatos e Interação Externa (`0009_followup_interview_logs` / `0009_application_followup_and_interview_logs.py`):**
  - Novas tabelas `application_interviews`, `application_assessments` e `application_contacts` vinculadas a `applications.id` (`ON DELETE CASCADE`), além das colunas `last_external_interaction_at`, `last_external_interaction_type` e `last_external_interaction_note` em `applications`.
  - Sincronização automática de `Application.interview_at` com a próxima entrevista futura (`scheduled`), registro de `previous_scheduled_at` em reagendamentos, atualização de `last_external_interaction_at` ao concluir entrevistas e estratégia de compatibilidade/fallback exclusivo com `assessment_deadline_at` para evitar duplicações.
- **API Avançada do ATS (`applications.py`, `application_process_service.py`):**
  - Endpoints REST completos para entrevistas, desafios técnicos e contatos por candidatura (`/interviews`, `/assessments`, `/contacts`), registro explícito de interação externa (`POST /api/v1/applications/{id}/external-interaction`), agenda cronológica unificada em UTC (`GET /api/v1/applications/agenda`), detecção informativa de processos sem interação externa (`GET /api/v1/applications/stale` ignorando `updated_at` e entrevistas futuras agendadas) e gerador determinístico de follow-up em PT-BR (`GET /api/v1/applications/{id}/follow-up-template`).
  - Validação estrita de URLs anti-SSRF/XSS, sanitização de textos, exigência de offset/fuso horário explícito nas novas entradas temporais e isolamento estrito multiusuário (`404 Not Found` uniforme).
- **Interface ATS Integrada (`ApplicationsPipelinePage.tsx`, `ApplicationDetailModal.tsx`, `ApplicationAgendaView.tsx`, `ApplicationFollowUpView.tsx`):**
  - Navegação integrada no módulo **Candidaturas** entre **Pipeline** (Kanban preservado), **Agenda** (lista cronológica/visão semanal no desktop, agrupamento vertical no mobile e horários convertidos ao fuso local do navegador com alertas de vencidos e próximas 24h) e **Acompanhamento** (processos sem interação registrada + cópia rápida de follow-up).
  - Painel de detalhes da candidatura organizado em 5 abas (`Geral`, `Entrevistas`, `Testes técnicos`, `Contatos`, `Acompanhamento`).

---

## [0.3.1.1] - 2026-11-16 — Fase 03.1.1: Hardening de Concorrência do Pipeline

### Corrigido / Endurecido
- **Restrição Única Parcial no Banco (`0008_active_app_uniq`):**
  - Criado o índice único parcial `uq_active_application_per_user_opp` em `applications (user_id, opportunity_id)` com predicado `opportunity_id IS NOT NULL AND status IN ('interested', 'preparing', 'applied', 'assessment', 'interview', 'offer')`, compatível com PostgreSQL 16 e SQLite, preservando múltiplos processos encerrados, candidaturas avulsas (`opportunity_id IS NULL`) e usuários distintos.
- **Tratamento Seguro de `IntegrityError` e Rollback (`application_service.py`):**
  - Adicionados `_is_active_application_unique_violation` e `_handle_commit_integrity_error` (capturando apenas violações de `uq_active_application_per_user_opp` via código/constraint PostgreSQL `23505` ou colunas do índice SQLite), executando `rollback()` antes de consultar qualquer atributo ORM ou relançar `ApplicationDuplicateError` -> HTTP `409 Conflict`, preservando integridade de sessão e evitando mascarar outras constraints.
- **Testes de Concorrência Real e Migração (`test_applications_phase03.py`):**
  - Cobertura determinística com duas sessões independentes em threads sincronizadas por `threading.Barrier` para criação e reabertura concorrente, inspeção de predicado no PostgreSQL 16 e SQLite e teste dedicado de `upgrade`/`downgrade` `0007 -> 0008 -> 0007` com dados preservados.

---

## [0.3.1] - 2026-11-16 — Fase 03.1: Pipeline de Gestão de Candidaturas

### Adicionado
- **Modelo de Candidaturas e Histórico (`0007_applications_pipeline`):**
  - Novas tabelas `applications` e `application_status_history` isoladas por `user_id` (`ON DELETE CASCADE`), com vínculo opcional `opportunity_id` (`ON DELETE SET NULL`) e snapshots completos da vaga (`company_name`, `role_title`, `personal_summary`, `source_name`, `source_url`, `application_url`, `location_text`, `employment_type`, `work_mode`, `seniority_level`).
  - Nove etapas oficiais com rótulos em português: `interested` (`Interesse`), `preparing` (`Preparação`), `applied` (`Candidatura enviada`), `assessment` (`Teste técnico`), `interview` (`Entrevista`), `offer` (`Proposta`), além dos estados encerrados `accepted` (`Aprovado`), `rejected` (`Rejeitado`) e `withdrawn` (`Desistência`).
- **API de Candidaturas e Indicadores (`applications.py`, `application_service.py`):**
  - Endpoints autenticados e protegidos por CSRF sob `/api/v1/applications` (`GET`, `POST`, `GET /kanban`, `GET /indicators`, `GET /{id}`, `PUT/PATCH /{id}`, `PATCH /{id}/status`, `DELETE /{id}`), prevenção de duplicidade ativa (`409 Conflict`) com suporte a nova candidatura após encerramento, preservação de imutabilidade das oportunidades externas, proteção contra exclusão silenciosa de processos com histórico (`confirm_history_deletion`) e validação anti-SSRF/XSS.
- **Integração com Catálogo e Interface Kanban (`ApplicationsPipelinePage.tsx`, `OpportunityDiscoveryPage.tsx`):**
  - Ação **Acompanhar candidatura** nos cards de oportunidades (exibindo etapa em andamento ou opção de nova candidatura após encerramento, sem envio automático).
  - Seção **Candidaturas** com indicadores reais, quadro Kanban responsivo (6 colunas no desktop e pills por etapa no mobile), seção separada para encerradas, destaques de prazo futuro/vencido, formulário manual e painel detalhado com datas, próximos passos, anotações e histórico de movimentações.

---

## [0.2.6.1] - 2026-11-16 — Fase 02.6.1: Correções de Senioridade, Experiência e Independência Dimensional

### Corrigido
- **Isolamento da Experiência Profissional (`matching.py`):**
  - Prevalência absoluta de `eligible_as_target_role=False` sobre `experience_type`, exclusão estrita de experiências em suporte técnico/Help Desk e tipo `academic` no cálculo de anos relevantes para o cargo-alvo (`confirmed_target_years`), mesclagem de intervalos de datas sobrepostos sem duplicação de meses, tratamento conservador de datas incompletas (`end_date=None` e `is_current=False`) e separação entre experiência relevante na área-alvo, tempo total de trabalho e evidência prática complementar de projetos (`ProfessionalProject`) e formação (`Education`).
- **Independência Dimensional entre Senioridade e Regime (`opportunity_service.py`, `OpportunityDiscoveryPage.tsx`, `App.tsx`):**
  - As abas **Estágios** (`?seniority=internship`), **Desenvolvedor Júnior** (`?seniority=junior`) e **Freelancers** (`?employment_type=freelance`) passaram a utilizar os campos estruturados independentes em vez do campo legado `type`, permitindo que oportunidades com `seniority_level=junior` e `employment_type=freelance` apareçam em ambas as frentes enquanto vagas freelance sênior permanecem excluídas da recomendação para perfil júnior.
- **Classificador e Extrator de Experiência (`classification.py`):**
  - Reconhecimento explícito da expressão literal `"Desenvolvimento de Software"` (e equivalentes PT-BR) em `software_development`.
  - Suporte completo a quantidades singulares e faixas em português e inglês (`1 ano`, `2 anos`, `1+ ano`, `3 a 5 anos`, `3-5 anos`, `5+ years`, `1 year`) sem inferir senioridade apenas por tempo de experiência.
  - Remoção do acoplamento legado de `_EXPERIENCED_YEARS_RE` em menções desejáveis (`Diferencial: 3 anos...`), impedindo rebaixamento indevido de vagas `junior` para `other`.
  - Redução de falsos positivos de experiência obrigatória qualitativa para requisitos puramente técnicos de ferramentas (ex.: `"Experiência com Git ou Docker."`) e frases explícitas de não obrigatoriedade/menção incidental.

---

## [0.2.6] - 2026-11-15 — Fase 02.6: Compatibilidade de Senioridade, Experiência e Requisitos Profissionais

### Adicionado
- **Separação de Senioridade e Experiência (`0006_seniority_experience`):**
  - Novos enums `SeniorityLevel` (`internship`, `entry_level`, `junior`, `mid_level`, `senior`, `staff_principal`, `management`, `unknown`) e `ExperienceRequirementMode` (`not_specified`, `none_required`, `preferred`, `required`) persistidos em `opportunities` (`seniority_level`, `experience_requirement_mode`, `experience_min_years`, `experience_preferred_years`, `experience_summary`), mantendo `opportunity_type` e `employment_type` independentes (ex.: Freelance Júnior vs Freelance Sênior; Júnior PJ vs Júnior CLT).
- **Extração Determinística de Experiência e Requisitos Obrigatórios vs Desejáveis (`classification.py`):**
  - `classify_experience_requirements` analisa seções de requisitos obrigatórios, diferenciais desejáveis e declarações de isenção de experiência (`no previous experience required`, `experiência profissional anterior não é obrigatória`) sem inferir experiência por nome de tecnologia, tags isoladas, título do cargo, idade da empresa ou senioridade de colegas.
- **Matching em Seis Dimensões e Habilidades do Candidato (`matching.py`):**
  - `evaluate_opportunity_for_user` agora consome habilidades (`Skill`), experiências (`WorkExperience`), projetos (`ProfessionalProject`) e formação (`Education`) do usuário autenticado, calculando `overall_compatibility` (`compatible`, `potential`, `incompatible`) junto a `area_compatibility`, `geographic_eligibility`, `contract_compatibility`, `seniority_compatibility`, `experience_compatibility` e `technical_compatibility`.
  - Vagas `senior`, `staff_principal`, `management` ou que exijam múltiplos anos acima da trajetória atual deixam de aparecer como compatíveis para perfil de entrada/júnior; vagas com informações omissas (`unknown`/`not_specified`) ou nível intermediário recebem status explícito `potential` com notas de incerteza.
- **API, CLI e Interface (`OpportunityDiscoveryPage.tsx`):**
  - Novos filtros `?seniority=` e `?compatibility=` em `GET /api/v1/opportunities`, badges claros de nível profissional, experiência e compatibilidade (`Compatível`, `Potencialmente compatível`, `Incompatível`) e exibição separada de requisitos técnicos vs habilidades encontradas no perfil.
  - `reclassify-opportunities` atualizado para reclassificar senioridade e experiência de forma idempotente mantendo `opportunity_source_links` e `opportunity_user_states` intactos.

---

## [0.2.5] - 2026-11-15 — Fase 02.5: Confiabilidade, Rastreabilidade e Ciclo de Vida das Oportunidades

### Adicionado
- **Rastreabilidade Normalizada Entre Fontes (`0005_lifecycle_traceability` e `OpportunitySourceLink`):**
  - Nova tabela `opportunity_source_links` persistindo, para cada publicação primária ou secundária vinculada a uma oportunidade, `external_id`, `source_url`, `application_url`, `is_primary`, `source_status`, `published_at`, `deadline_at`, `location_text`, `eligible_countries`, dados salariais, `first_seen_at`, `last_seen_at`, `last_checked_at`, `missing_sync_count` e `raw_metadata`.
  - Migração Alembic reversível (`upgrade` e `downgrade`) com backfill automático das oportunidades existentes e normalização de `external_id` da Himalayas (`<company>/jobs/<slug>`).
- **Ciclo de Vida Auditável e Revalidação por Fonte:**
  - Estados suportados em `ExternalSourceStatus`: `active`, `expired`, `closed`, `removed`, `source_unavailable`, `unconfirmed` e `unknown`.
  - Aplicação automática de sinais de expiração (`expiryDate` da Himalayas) e encerramento (`state="closed"` ou labels `fechada`/`encerrada`/`Stale` nas issues do GitHub, além de revalidação individual via `check_publication_status` para issues ausentes da primeira página sem encerrar falsamente vagas que apenas mudaram de página).
  - Exclusão determinística de vagas `expired`, `closed` e `removed` nas recomendações ativas de `evaluate_opportunity_for_user`, preservando integralmente estados salvos/dispensados do usuário (`opportunity_user_states`).
- **Métricas de Sincronização e Observabilidade (`OpportunitySyncRun` e `SyncRunSummary`):**
  - Distinção estrita entre `received_count`, `valid_count`, `rejected_count`, `inserted_count`, `updated_count`, `intra_source_duplicate_count`, `cross_source_duplicate_count`, `unique_opportunities_count`, `open_opportunities_count`, `closed_or_expired_count` e `unconfirmed_count`, exibidas por fonte e em linha consolidada no CLI e em `GET /api/v1/opportunities/sources`.
- **Interface e API:**
  - Exposição de `source_links`, `last_status_check_at` e `status_uncertainty_note` em `OpportunityResponse`, filtro por fonte considerando também vínculos secundários e exibição de fontes secundárias clicáveis, data da última verificação e estado traduzido em `OpportunityDiscoveryPage.tsx`.

### Corrigido
- Corrigida colisão de `external_id` em `HimalayasConnector` quando empresas distintas utilizavam o mesmo slug final de vaga (`/jobs/software-developer`), passando a usar `<company-slug>/jobs/<job-slug>`.
- Corrigido limite de truncamento de `locationRestrictions` em `HimalayasConnector` (`max_items=250`), evitando perda de países elegíveis em listas extensas.
- Substituído o descarte silencioso de clones multi-país em `JobicyConnector` por vinculação rastreável em `opportunity_source_links` (`intra_source_duplicate_count`) com mesclagem de `eligible_countries`.
- Refinada a extração de `city` em `github_vagas.py` para remover sufixos de UF (`/PR`, `/SP`) em vagas presenciais/híbridas e endurecida a deduplicação composta (`_is_safe_composite_match`) para impedir falsos positivos baseados apenas em `(title, company_name)`.

---

## [0.2.4] - 2026-11-15 — Fase 02.4: Expansão de Fontes e Cobertura de Oportunidades

### Adicionado
- **Novos Conectores Públicos Autorizados (`jobicy`, `himalayas`, `github_backend_br`, `github_frontend_br`):**
  - `JobicyConnector` (`https://jobicy.com/api/v2/remote-jobs?count=50&industry=dev`, intervalo `3600s`) com deduplicação de clones multi-país no próprio lote e mapeamento de `jobLevel`/`jobType`.
  - `HimalayasConnector` (`https://himalayas.app/jobs/api/search?q=software+developer`, intervalo `3600s`) preservando `applicationLink` oficial, descartando vagas expiradas (`expiryDate`) e mapeando `locationRestrictions` vazias como `Worldwide`.
  - `GitHubBackendBRConnector` (`backend-br/vagas`) e `GitHubFrontendBRConnector` (`frontendbr/vagas`) consumindo a API REST oficial v3 do GitHub sob licença MIT (`3600s`), com filtro de PRs/issues `Stale`/avisos administrativos, extração de modalidade/localidade (`[Remoto]`, `[Híbrido]`) e redação automática de PII (`redact_contact_pii`).
- **Deduplicação Entre Fontes (`sync_service.py`):**
  - `_find_existing_opportunity` e `_upsert_opportunity` identificam vagas duplicadas entre fontes distintas por `application_url`, `source_url` ou par normalizado `(title, company_name)`, preservando atribuição e URLs canônicas da fonte original e registrando `also_seen_in_sources`.

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
