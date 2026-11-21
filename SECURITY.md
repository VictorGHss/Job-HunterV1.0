# Política e Arquitetura de Segurança (SECURITY.md)

Este documento registra as decisões arquiteturais de segurança implementadas na **Fase 01** e endurecidas nas fases subsequentes do **Job Hunter**, bem como os controles ativos e limitações conhecidas.

---

## 1. Isolamento Multiusuário (`user_id` Ownership)

- **Identificadores UUID v4:** Usuários, sessões e todas as entidades profissionais (`ProfessionalProfile`, `WorkExperience`, `Education`, `Skill`, `Language`, `ProfessionalProject`) utilizam chaves primárias `UUID` não sequenciais, prevenindo ataques de enumeração previsível (IDOR por incremento).
- **Associação Obrigatória:** Todas as tabelas de domínio profissional possuem chave estrangeira `user_id` apontando para `users.id` com `ON DELETE CASCADE`.
- **Verificação Estrita em Todas as Consultas:** Toda leitura, atualização ou exclusão no `profile_service.py` filtra simultaneamente por `entity.id == target_id` e `entity.user_id == current_user.id`.
- **Resposta Uniforme `404 Not Found`:** Caso um usuário autenticado tente acessar, editar ou remover um registro cujo UUID pertença a outro usuário, o sistema retorna `404 Not Found` (sem revelar sequer se o identificador existe no banco).
- **Testes Automatizados de Isolamento:** A suíte `tests/test_foundation_phase01.py` valida explicitamente que um usuário autenticado (`Bob`) não consegue ler, modificar ou excluir nenhum dado profissional de outra usuária (`Alice`).

---

## 2. Autenticação, Hash de Senhas e Provisionamento

- **Argon2id (`argon2-cffi`):** Senhas nunca são armazenadas em texto puro ou hashes reversíveis/rápidos. Utilizamos exclusivamente `Argon2id` (`time_cost=3`, `memory_cost=65536` / 64 MiB, `parallelism=4`, `hash_len=32`, `salt_len=16`), com suporte automático a `check_needs_rehash`.
- **Mitigação de Enumeração por Tempo (Timing Attacks):** Quando uma tentativa de login informa um e-mail inexistente, o backend executa uma verificação Argon2id contra um hash dummy pré-alocado para manter o tempo de resposta uniforme e retorna a mesma mensagem genérica (`401 Credenciais inválidas ou conta indisponível`).
- **Ausência de Cadastro Público e Credenciais Padrão:**
  - Não existe endpoint público de auto-cadastro (`/register` ou `/signup`).
  - Nenhuma conta ou senha padrão é criada automaticamente na inicialização ou nas migrações.
  - O provisionamento ocorre via CLI segura (`python -m app.cli create-admin`), lendo a senha por prompt oculto (`getpass`), `stdin` ou variável de ambiente efêmera.
- **Proteção Persistente Contra Força Bruta no Login (`auth_rate_limits`):**
  - Implementada em banco de dados PostgreSQL/SQLite (sem dependência de Redis e sem estado volátil apenas em memória).
  - Avalia simultaneamente tentativas por **par `(IP de origem, conta)`** (`LOGIN_ACCOUNT_IP_MAX_ATTEMPTS=5`) e por **IP de origem** (`LOGIN_IP_MAX_ATTEMPTS=20`) dentro de janela configurável (`LOGIN_RATE_LIMIT_WINDOW_SECONDS=900`), aplicando cooldown temporário (`LOGIN_COOLDOWN_SECONDS=300` + cabeçalho `Retry-After`) sem bloqueio permanente e sem permitir DoS global de uma conta por IPs terceiros.
  - Chaves de rate limit são derivadas com HMAC-SHA256 sobre `SECRET_KEY`, sem gravar e-mails ou senhas em texto claro na tabela `auth_rate_limits`.
  - Respostas `401` e `429` mantêm mensagens genéricas que não revelam se o e-mail existe.
- **Identificação Confiável de Origem (Anti-Spoofing):**
  - `extract_trusted_client_ip` só processa `X-Forwarded-For` (da direita para a esquerda, parando no primeiro IP não pertencente a `TRUSTED_PROXY_CIDRS`) quando o peer TCP direto pertence a `TRUSTED_PROXY_CIDRS`.
  - `CF-Connecting-IP` só é aceito quando o peer é confiável **e** `TRUST_CF_CONNECTING_IP=true` foi explicitamente configurado.

---

## 3. Gestão de Sessões e Proteção CSRF

- **Cookies `HttpOnly`:** O token de sessão (`jh_session`) é transmitido exclusivamente via cookie `HttpOnly`, inacessível a scripts JavaScript (`document.cookie`), mitigando roubo de sessão via XSS.
- **Armazenamento de Sessão por Hash SHA-256:** O banco de dados (`user_sessions`) **não** armazena o token de sessão em texto puro; armazena apenas seu hash `SHA-256` (`token_hash`). Mesmo em um cenário hipotético de leitura indevida da tabela `user_sessions`, os tokens ativos não podem ser reconstruídos.
- **Revogação Imediata e Expiração:**
  - O endpoint `POST /api/v1/auth/logout` registra `revoked_at` no banco de dados e remove os cookies no navegador.
  - Sessões expiradas (`expires_at <= now`) ou vinculadas a contas não ativas (`account_status != 'active'`) são rejeitadas imediatamente.
- **Proteção CSRF (Double-Submit / Session-Bound Token):**
  - Toda sessão possui um `csrf_token` criptograficamente aleatório (256 bits).
  - Todas as requisições mutáveis (`POST`, `PUT`, `PATCH`, `DELETE`) exigem o cabeçalho `X-CSRF-Token`, validado em tempo constante (`secrets.compare_digest`) contra o token vinculado à sessão no banco.

---

## 4. Validação de Dados, Cabeçalhos e Infraestrutura

- **Validação Estrita com Pydantic v2:**
  - Normalização de e-mails e listas de strings.
  - Validação de formato de URLs (`http://` ou `https://`).
  - Validação lógica de intervalos de datas (`end_date >= start_date`).
  - Validação de níveis CEFR (`A1` a `C2`) e enums de status.
- **CORS Restrito e Validação Estrita em Produção:** Configurado explicitamente via `CORS_ORIGINS` (proibindo `*`), permitindo apenas métodos e cabeçalhos necessários (`Content-Type`, `X-CSRF-Token`, `Accept`). Em `ENVIRONMENT=production`, o backend falha no startup caso `COOKIE_SECURE` não seja `true`, `SECRET_KEY` seja fraca ou contenha placeholder, ou `CORS_ORIGINS` não use `https://`.
- **Isolamento de Dados Privados de Seed:** Nenhum dado profissional particular permanece no código compartilhado. Importações iniciais ocorrem apenas localmente via CLI (`import-profile-seed`), a partir de arquivo ignorado pelo Git (`local-seeds/profile-seed.local.json`) montado em somente leitura (`/run/local-seeds:ro`), com validação estrita (`schema_version: 1`, `extra="forbid"`), rollback transacional em erro e proibição de auto-confirmação (`verification_status="confirmed"` rejeitado na entrada).
- **Container de Produção Enxuto:** O `backend/Dockerfile` separa o estágio `base` (produção, sem `pytest` nem `tests/`) do estágio `test`.
- **Security Headers:** Respostas HTTP incluem `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` e `Referrer-Policy: strict-origin-when-cross-origin`.
- **PostgreSQL Não Exposto:** No `infra/compose.yaml`, o banco de dados opera exclusivamente na rede interna `job_hunter_net`, sem portas abertas no host.
- **Execução Não-Root:** O container do backend executa sob usuário dedicado sem privilégios (`appuser`).
- **Tratamento de Erros e Logs Limpos:** Exceções não tratadas retornam mensagem genérica `500 Erro interno do servidor` sem expor stacktraces, queries SQL, senhas ou tokens nos logs.

---

## 5. Governança de Dados para Futura Integração com IA

- **Distinção Técnica entre Rascunho e Fato Confirmado:** Todos os registros possuem `verification_status` (`draft`, `pending_validation`, `confirmed`) e carimbo `confirmed_at`.
- **Prevenção de Invenção Curricular:** As fases futuras de integração com LLMs deverão filtrar exclusivamente registros com `verification_status == 'confirmed'` ao compor currículos e propostas.

---

## 6. Limitações Conhecidas Após a Fase 01.1 e Evoluções Planejadas

1. **Restrição de Origem ao Habilitar `TRUST_CF_CONNECTING_IP`:** `TRUST_CF_CONNECTING_IP=true` só deve ser ativado quando a origem HTTP estiver isolada atrás de Cloudflare Tunnel / rede privada / firewall que bloqueie acessos externos diretos fora do proxy confiável.
2. **Gestão de Múltiplas Sessões na UI:** O banco já suporta múltiplas sessões independentes por usuário com `user_agent` e `ip_address`; uma tela dedicada para encerrar outras sessões ativas poderá ser adicionada em fases futuras.
3. **Proteção de Borda e Ataques Distribuídos:** O rate limiting atual protege por `(IP, conta)` e por `IP` no backend sem Redis; caso o serviço seja exposto publicamente em larga escala, recomenda-se combinar com Cloudflare Access (Zero Trust) e regras WAF na borda.

---

## 7. Controles de Segurança do Motor de Descoberta (Fase 02)

- **Hardening de Conectores HTTP Externos (`BaseOpportunityConnector`):**
  - Timeouts explícitos de conexão e leitura (`SYNC_HTTP_CONNECT_TIMEOUT_SECONDS=5`, `SYNC_HTTP_READ_TIMEOUT_SECONDS=15`) e `follow_redirects=False` no cliente HTTP.
  - Leitura em stream com teto rígido de bytes (`SYNC_MAX_RESPONSE_BYTES=5242880` / 5 MiB), evitando exaustão de memória por payloads anômalos.
  - Respeito obrigatório ao cabeçalho `Retry-After` em HTTP `429` e rejeição controlada de JSON malformado (`ConnectorPayloadError`).
- **Sanitização de HTML, Redação de PII e Dados Externos:**
  - Descrições vindas de APIs externas passam por parser HTML restritivo (`sanitize_external_html_text`), removendo `<script>`, `<style>` e quaisquer tags antes da persistência, sendo renderizadas no frontend exclusivamente como texto simples (nunca `dangerouslySetInnerHTML`).
  - Nos conectores de issues comunitárias (`github_backend_br` e `github_frontend_br`), e-mails e telefones pessoais presentes no texto bruto são anonimizados antes da persistência (`redact_contact_pii`), preservando apenas o link oficial da issue no GitHub para candidatura.
- **Prevenção contra SSRF e Raspagem Indevida em Links Manuais / PWA:**
  - O endpoint `POST /api/v1/opportunities/manual` e o fluxo Web Share Target nunca realizam requisições HTTP do servidor para URLs fornecidas pelo usuário.
  - `validate_safe_external_url` aceita apenas esquemas `http`/`https`, proíbe credenciais embutidas e bloqueia alvos `localhost`, `.local`, IPs privados, loopback e faixas link-local/metadata (`169.254.169.254`).
- **Isolamento de Escrita e Privacidade Multiusuário:**
  - Oportunidades coletadas de provedores públicos pertencem ao catálogo global com leitura autenticada e **escrita bloqueada** (`403 Forbidden`) para usuários via `PATCH /api/v1/opportunities/{id}`.
  - Oportunidades cadastradas manualmente pertencem estritamente a `created_by_user_id` (`404 Not Found` para qualquer outro usuário).
  - Estados individuais (`is_saved`, `is_dismissed`, `last_viewed_at`) são persistidos por usuário na tabela `opportunity_user_states`.
  - O campo `raw_metadata` das fontes externas nunca é exposto nos schemas de resposta da API.
- **Governança Explícita de Habilitação, Rastreabilidade e Ciclo de Vida (Fases 02.1 a 02.5):**
  - `SourceDefinition` declara explicitamente `enabled_by_default` e `disabled_reason`. Fontes sem conformidade confirmada para agregação multiusuário (atualmente `remotive`, aguardando esclarecimento/autorização escrita sobre os Termos de Uso gerais de março/2026) permanecem desabilitadas por padrão (`enabled=false`).
  - `ensure_default_sources` aplica bloqueios padrão de conformidade no banco sem nunca reativar automaticamente fontes desabilitadas manualmente pelo operador.
  - `sync_sources` impede qualquer requisição HTTP externa quando `source.enabled == False` ou `enabled_by_default == False`, recusando `--source <slug>` explicitamente com erro e garantindo que `--force` ignore somente o intervalo mínimo entre coletas.
  - **Rastreabilidade Normalizada e Preservação de Links (`opportunity_source_links`):** Nenhuma deduplicação apaga ou sobrescreve URLs originais de publicação ou candidatura (`applicationLink` da Himalayas com `?utm_source=api`, links diretos da Jobicy e Remote OK sem `nofollow`, e URLs de issues no GitHub). Todas as ocorrências primárias e secundárias são persistidas individualmente em `opportunity_source_links`.
  - **Direitos sobre Conteúdo de Terceiros e LGPD/PII (`github_backend_br` e `github_frontend_br`):** A licença MIT dos repositórios comunitários aplica-se à estrutura do repositório, não suprimindo direitos de terceiros nem proteção de dados pessoais; por isso, e-mails e telefones pessoais em issues abertas sofrem redação obrigatória (`redact_contact_pii`) antes da persistência e o candidato é sempre direcionado à issue oficial no GitHub.

---

## 8. Isolamento e Integridade do Pipeline de Candidaturas (Fases 03.1 a 03.2.1)

- **Propriedade Estrita (`user_id` e Isolamento Entre Candidaturas):** Candidaturas (`applications`), histórico (`application_status_history`) e registros filhos (`application_interviews`, `application_assessments`, `application_contacts`) derivam posse exclusivamente de `Application.user_id` (sem `user_id` redundante inconsistente em tabelas filhas) e vinculam toda consulta/mutação filha a `child.application_id == application_id`. Todas as operações de agenda, estagnação, entrevistas, desafios, contatos, interação externa e follow-up retornam `404 Not Found` uniforme tanto em acesso cruzado entre usuários quanto entre candidaturas diferentes do mesmo usuário.
- **Unicidade Ativa Sob Concorrência e Monotonicidade Temporal (`uq_active_application_per_user_opp`):** Restrição única parcial imposta diretamente no PostgreSQL 16 e no SQLite para `(user_id, opportunity_id)` quando `opportunity_id IS NOT NULL` e `status` está entre os estágios ativos (`interested`, `preparing`, `applied`, `assessment`, `interview`, `offer`). Violações concorrentes dessa restrição recebem `rollback()` imediato da sessão e são traduzidas exclusivamente para `ApplicationDuplicateError` / HTTP `409 Conflict` sem mascarar erros de outras constraints. Além disso, o resumo da última interação externa (`last_external_interaction_at`, `type`, `note`) é atualizado via `UPDATE` condicional atômico monotônico apenas para timestamps `>=` ao maior instante conhecido, preservando registros retroativos intactos no histórico e impedindo que edições internas (`updated_at`) reiniciem a detecção de estagnação.
- **Validação de URLs, Sanitização e Fuso Horário Explícito (Fase 03.2):** `meeting_url`, `instructions_url`, `submission_url` e `linkedin_url` passam obrigatoriamente por `validate_safe_external_url` (`http`/`https` apenas, bloqueando `javascript:`, `data:`, credenciais embutidas e alvos SSRF internos), sem requisições HTTP do backend para esses endereços. Notas, feedbacks, descrições e contatos são sanitizados via `sanitize_plain_text` / `sanitize_external_html_text`, e os novos contratos temporais exigem offset explícito (`tzinfo`) com persistência em UTC.
- **Imutabilidade do Catálogo Externo e Snapshots:** Criar, atualizar, mover ou excluir candidaturas nunca altera registros da tabela `opportunities`. A remoção de uma oportunidade privada vinculada aplica `ON DELETE SET NULL`, preservando integralmente o histórico e os snapshots do processo seletivo.
- **Proteção Contra Remoção Silenciosa e Cascata Atômica:** Candidaturas já enviadas, encerradas ou com histórico de transições recusam exclusão por padrão (`409 Conflict`), exigindo confirmação explícita (`confirm_history_deletion=true`), momento em que entrevistas, testes técnicos, contatos e históricos associados são excluídos atomicamente em cascata. Todos os follow-ups são gerados de forma determinística local, sem IA nem envios automáticos.

---

## 9. Integridade Factual, Proveniência e Segurança dos Materiais de Candidatura (Subfase 04.1)

- **Filtragem Estrita por Fatos Confirmados (`fact_selector.py`):** A pré-análise e a geração determinística de currículos (`pt-BR` e `en`) leem exclusivamente entidades com `verification_status == 'confirmed'`. Registros `pending_validation` ou `draft` são expostos apenas como avisos explícitos fora do conteúdo gerado, e a geração é bloqueada (`422`) caso não exista ao menos um bloco substantivo confirmado (experiência, projeto, formação acadêmica ou habilidade técnica).
- **Confirmação Seletiva em Lote Sem Auto-Confirmação (`POST /api/v1/profile/confirm-batch`):** Aceita exclusivamente UUIDs informados explicitamente pelo usuário com `verification_status == 'pending_validation'` (máximo de 150 itens por requisição, `extra="forbid"`, proibição de `user_id` no corpo), rejeitando atomicamente com rollback qualquer item `draft` ou pertencente a outro usuário. Na UI, nenhum checkbox inicia pré-selecionado.
- **Anti-Injection, Anti-XSS e Sanitização de Conteúdo:** Descrições e requisitos de oportunidades externas são tratados apenas como dados não confiáveis de correspondência determinística (nunca executados nem copiados como fatos confirmados). Todo conteúdo estruturado e texto exportado passa por sanitização XSS/URL (`validate_safe_external_url`, remoção de tags/scripts) e é renderizado na interface como texto React puro sem `dangerouslySetInnerHTML`.
- **Reconciliação de Proveniência Server-Side (`resume_composer.py`):** Edições manuais sobre o JSON estruturado canônico (`structured_content`) têm sua proveniência reconciliada no servidor — qualquer bloco alterado ou adicionado é rebaixado para `manual_edit` ou `user_authored`, impedindo que o cliente forje `confirmed_fact` ou misture referências `project:` dentro de `experiences`.
- **Imutabilidade, Snapshot Reduzido e Zero PII em Logs:** Versões aprovadas (`POST .../approve`) ou vinculadas a candidaturas tornam-se imutáveis (`409 Conflict`), preservando rastreabilidade histórica. O campo `source_facts_snapshot` utiliza allowlist estrita sem e-mail, telefone ou endereço completo, e nenhum conteúdo de currículo ou PII pessoal é gravado nos logs da aplicação.
- **Integridade Multiusuário no Banco (`0010_application_materials`):** Vínculos em `application_material_links` possuem FKs compostas garantindo no banco que `application`, `material` e `version` pertençam ao mesmo `user_id` e `material_id`, além de índice único parcial (`uq_active_link_per_app_material`) e retorno uniforme `404 Not Found` para tentativas IDOR.

---

## 10. Correções de Segurança — Subfase 04.1.1

- **Invalidação Obrigatória de Confirmação Após Alteração Factual (`profile_service.py`):** Qualquer PUT que altere o conteúdo factual de um registro confirmado (`WorkExperience`, `Education`, `Skill`, `Language`, `ProfessionalProject` ou `ProfessionalProfile`) degrada obrigatoriamente o status para `pending_validation` e limpa `confirmed_at`, **independentemente** do valor de `verification_status` enviado pelo cliente. Uma operação de edição não pode auto-confirmar o próprio conteúdo que acabou de modificar. A política é centralizada em `_apply_confirmation_policy` e cobre todos os cenários: (A) alteração factual + `confirmed` explícito → `pending_validation`; (B) sem alteração + `confirmed` → preserva; (C) sem alteração + status omitido → preserva; (D) alteração + `pending_validation` → `pending_validation`; (E) reabertura explícita → permitida; (F) confirmação intencional de pendente sem alteração → permitida; (G) rascunho → jamais confirmado acidentalmente via defaults de PUT.
- **Autorização de Oportunidades Privadas em Materiais (`material_service.py`):** `_get_opportunity` utiliza `SELECT` com filtro `OR(source_id IS NOT NULL, created_by_user_id == user.id)` em vez de `db.get(Opportunity, id)`, impedindo que qualquer usuário acesse título, empresa, tecnologias ou qualquer metadado de uma oportunidade privada pertencente a outra conta. Oportunidades privadas de terceiros retornam `404 Not Found` idêntico ao de registro inexistente, sem revelar sequer que a oportunidade existe. A proteção é aplicada em todos os fluxos que dependem de `_resolve_target_context`: `pre_analyze_material` e `create_material`.

---

## 11. Correções da Política de Confirmação — Subfase 04.1.2

- **Preservação de Confirmação Intencional e Detecção Real de Omissão (`profile_service.py`):** `_requested_verification_status` inspeciona `payload.model_fields_set` para distinguir omissão real de `verification_status` dos defaults dos schemas Pydantic das sub-entidades. `_apply_confirmation_policy` permite transições explícitas `draft -> confirmed` e `pending_validation -> confirmed` (gravando `confirmed_at`), preserva o status atual quando não há alteração factual e o campo é omitido, e mantém a reabertura obrigatória para `pending_validation` (limpando `confirmed_at`) sempre que um registro `confirmed` sofre alteração factual.
- **Feedback Fiel na Interface (`ProfilePage.tsx`):** Após salvar o perfil geral ou acionar ações de confirmação rápida em sub-entidades, a interface sincroniza o estado local e exibe feedback estritamente a partir do `verification_status` retornado pelo backend, nunca exibindo confirmação bem-sucedida caso o registro permaneça em `draft` ou seja reaberto para `pending_validation`.

---

## 12. Segurança, Proveniência e Aprovação na Geração de Textos (Subfase 04.2)

- **Separação Estrita Entre Dados Não Confiáveis da Vaga e Fatos Confirmados (`writing_common.py`, compositores 04.2):** Descrições e textos livres vindos de vagas externas nunca são ecoados nem interpretados como instruções de execução ou fatos do usuário; apenas tokens determinísticos de requisitos e fatos `verification_status == 'confirmed'` selecionados via `AuthorizedFactBundle` entram nos blocos fundamentados.
- **Proibição Absoluta de Invenção Comercial e Motivacional (`freelance_proposal_composer.py`, `application_answers_composer.py`, `recruiter_message_composer.py`):** Preços, orçamentos, prazos de entrega, disponibilidade, nomes de recrutadores, referências de indicação, pretensão salarial e motivações pessoais **nunca** são fabricados. Quando não informados pelo usuário, são representados apenas como campos estruturados pendentes (`pending_fields` / `requires_user_input=True`, com `answer_text=null`).
- **Imutabilidade de Tipo e Validação Contra Snapshot (`material_service.py`):** Ao atualizar ou derivar versões (`PUT .../versions/{version_id}`, `POST .../derive`), o conteúdo estruturado é validado estritamente conforme o `material_type` imutável do material pai (`422 Unprocessable Entity` em divergência estrutural), e todas as chaves `source_fact_keys` passam por verificação rigorosa contra o `source_facts_snapshot` da versão (`422` se inexistentes ou cross-entity), preservando proveniência `manual_edit` ou `user_authored` sem jamais aceitar promoção pelo cliente para `confirmed_fact` nem promover respostas manuais de candidatura para fatos do perfil.
- **Bloqueio Obrigatório de Aprovação com Pendências (`POST /api/v1/materials/{id}/versions/{version_id}/approve`):** Versões de `freelance_proposal` com qualquer campo obrigatório em `status != 'provided'` e versões de `application_answers` com qualquer pergunta em `needs_user_input` ou texto vazio têm a aprovação explicitamente rejeitada com `422 Unprocessable Entity` no servidor e botão desabilitado na UI.
- **Conformidade sem Auto-Envio e Zero PII em Logs:** Todos os materiais gerados permanecem restritos a pré-visualização, edição supervisionada, aprovação, vínculo e cópia manual em Markdown/Texto simples, mantendo envio automático, provedores externos de IA e registro de PII em logs estritamente bloqueados.

---

## 13. Segurança e Integridade na Exportação Binária em PDF e DOCX (Subfase 04.3)

- **Autorização e Imutabilidade Histórica (`export_service.py`, `api/routes/materials.py`):** A rota `GET /api/v1/materials/{material_id}/versions/{version_id}/download` exige usuário autenticado, filtra o material estritamente por `user_id` (`404 Not Found` uniforme para IDOR ou cruzamento `material_id`/`version_id` incompatível), carrega exatamente o `version_id` solicitado sem reconstruir conteúdo do perfil atual e nunca grava arquivos binários no disco ou banco (`io.BytesIO` exclusivo).
- **Política Estrita de Aprovação e Pendências (`export_service.py`):** Pendências obrigatórias (`freelance_proposal` ou `application_answers`) bloqueiam a exportação com `422 Unprocessable Entity` mesmo com `allow_draft=true`. Com `allow_draft=false` (padrão), apenas versões aprovadas são exportadas; em modo rascunho explícito (`allow_draft=true` em versão não aprovada sem pendências), todas as páginas recebem cabeçalho e marca d'água diagonal (`RASCUNHO NÃO APROVADO` / `UNAPPROVED DRAFT`) e sufixo `-rascunho` / `-draft`.
- **Anti-XSS, XML Escaping, SSRF em Links e Limites (`document_validation.py`, `pdf_exporter.py`, `docx_exporter.py`):** Textos passam por normalização Unicode NFC, limpeza de caracteres de controle XML 1.0 inválidos e escaping XML antes de tags controladas pelo ReportLab; todo link externo é validado com `validate_safe_external_url(..., allow_localhost=False)`, descartando `javascript:`, `file:`, `data:` e IPs locais/privados; limites centralizados (`120.000` chars de entrada e `5 MiB` por arquivo final) e validação de magic bytes (`%PDF-`/`%%EOF` e ZIP DOCX válido via `docx.Document`) impedem respostas corrompidas ou abuso de memória.
- **Integridade de Fontes, Nomes de Arquivo e Headers HTTP (`main.py`, `api/routes/materials.py`):** As fontes `Liberation Sans` (SIL OFL 1.1) possuem verificação de hash SHA-256; glifos não suportados no PDF são substituídos explicitamente por `[U+XXXX]` sem omitir conteúdo vizinho; nomes de arquivo usam allowlist ASCII + RFC 5987 bloqueando traversal (`../`), CRLF, NUL e nomes reservados do Windows (`CON`, `PRN`, etc.); respostas incluem `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store, no-cache, must-revalidate, private`, `Pragma: no-cache` e exposição controlada via CORS, sem registro de PII em logs.

---

## 14. Fundação e Controles de Segurança para IA Assistida (Subfase 04.4.1)

- **Kill Switch Desabilitado por Padrão e Bloqueio Anti-Mock em Produção (`core/config.py`, `services/materials/ai/providers.py`):** `AI_ASSISTED_ENABLED` nasce `false` e nenhuma API key é exigida para iniciar ou operar o sistema. Quando desabilitada, qualquer reserva ou chamada ao provider falha imediatamente com `AIDisabledError` sem efeitos colaterais nem tráfego externo. Em `ENVIRONMENT=production`, `AI_PROVIDER=mock` é rejeitado tanto na validação de startup das `Settings` quanto na instanciação/resolução de `MockLLMProvider`.
- **Isolamento Estrito por `user_id` e Verificação de Ownership (`quota_service.py`):** Consultas de disponibilidade (`get_quota_availability`), leitura de registros (`get_ledger_entry_for_user`) e transições de reserva filtram obrigatoriamente por `user_id`. Caso `material_id` ou `version_id` sejam informados na reserva, o serviço valida previamente se pertencem ao `user_id` solicitante (rejeitando referências cruzadas ou inexistentes com erro uniforme `material_not_found` / `version_not_found`, sem vazar existência de dados de terceiros).
- **Atomicidade Concorrente Sem Locks Abertos Durante I/O (`_db_locks.py`, `quota_service.py`, `execution_guard.py`):** O controle de cotas serializa reservas concorrentes por escopo (`global:daily:<YYYY-MM-DD>` e `user:<uuid>` em ordem lexicográfica canônica livre de deadlocks, usando `SELECT ... FOR UPDATE` no PostgreSQL 16 e escrita transacional com `busy_timeout` no SQLite) dentro de uma transação curta confirmada **antes** da invocação do `LLMProvider`, reabrindo uma segunda transação curta apenas para consolidar o desfecho (`completed`, `failed` ou `released`). Nenhum lock ou transação SQL permanece aberto durante chamadas de provider.
- **Privacidade Estrita no Ledger e Zero Segredos/PII em Logs (`models/ai_usage.py`, `contracts.py`):** A tabela `ai_usage_ledger` armazena exclusivamente metadados operacionais numéricos e códigos técnicos curtos (`operation_type`, `provider_name`, `model_name`, `status`, contagens de tokens, `latency_ms`, `error_code`), sem colunas de texto livre para prompts, respostas, currículos ou vagas. `validate_safe_technical_identifier` aplica allowlist estrita (`^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,63}$`) e bloqueia URLs, e-mails (`@`), espaços, quebras de linha e padrões de credenciais (`sk-`, `AIza`, `Bearer`, `api_key`, etc.), garantindo ausência de PII e segredos no banco e nos logs.
- **Circuit Breaker Compartilhado em SQL (`circuit_breaker.py`):** Persistido em `ai_circuit_breakers` para manter estado consistente entre múltiplos workers/réplicas sem depender de memória local por processo nem exigir Redis, limitando probes simultâneos em `half_open` a uma única execução concorrente.

---

## 15. Contexto Autorizado e Grounding Estruturado (Subfase 04.4.2)

- **Política Explícita de Autorização e Projeção Escalar Isolada do Identity Map (`context_builder.py`, `fact_selector.py`, `material_service.py`):** `build_authorized_ai_context` e `build_authorized_fact_bundle` nunca confiam em pré-filtros do chamador nem em instâncias ORM presentes ou adulteradas no `Session.identity_map` (NC-01), e também nunca usam `populate_existing=True` que descartaria edições legítimas pendentes na `Session` do chamador (NC-03). Todas as leituras de autorização e de fatos executam sob `db.no_autoflush` utilizando **projeções SQL escalares explícitas coluna a coluna** (`select(Model.col1, ...).mappings()`), convertidas para DTOs imutáveis (`@dataclass(frozen=True, slots=True)`), garantindo leitura fiel do estado persistido no banco (tanto em `autoflush=False` quanto em `autoflush=True`) sem hidratar, sobrescrever ou persistir objetos ORM sujos (`db.dirty`):
  - `application.user_id == user.id` verificado diretamente no SQL via `project_persisted_application_for_user`.
  - Visibilidade de `opportunity` (pública `source_id IS NOT NULL` ou privada própria `created_by_user_id == user.id`) verificada diretamente no SQL via `project_persisted_opportunity_for_user`.
  - Coerência estrita `application.opportunity_id == opportunity.id` quando ambos os objetos são fornecidos, além de validar a oportunidade associada quando apenas `application` é informada e bloquear tentativas de redirecionar uma candidatura em memória para oportunidade não autorizada.
  - Qualquer violação lança `AIContextAuthorizationError` sem retornar contexto parcial nem vazar metadados de terceiros.
- **Separação Absoluta Entre Fatos do Usuário e Requisitos da Vaga (`context_builder.py`, `fact_selector.py`, `grounding_validator.py`):** Fatos confirmados do candidato das 6 entidades de perfil (`ProfessionalProfile`, `WorkExperience`, `ProfessionalProject`, `Education`, `Skill` e `Language`) são filtrados diretamente no SQL com `user_id == user.id` e `verification_status == 'confirmed'` (impedindo qualquer promoção de status `draft`/`pending_validation` ou adulteração factual em memória) e mantidos estritamente separados de `SanitizedOpportunityContext`. **Requisitos da vaga nunca servem como evidência de competência técnica do usuário**; qualquer tecnologia mencionada em sugestão precisa estar fundamentada exclusivamente nos fatos confirmados citados pelo candidato.
- **Minimização, Redação Fail-Closed de PII, Exclusão de `user_id` e Serialização Canônica (`safety.py`, `ai_schemas.py`, `context_builder.py`):**
  - Colunas estruturadas de contato (`phone`, `professional_email`, `linkedin_url`, `github_url`, `portfolio_url`, localização) e timestamps operacionais de projetos (`updated_at`/`created_at`, mantendo `period=None`) não entram no contexto.
  - Campos de texto livre (`professional_summary`, descrições, `verified_results`, `notes` e campos da oportunidade) passam por sanitização e redação determinística de e-mails diretos/ofuscados, telefones (BR e internacionais), URLs/domínios, links Markdown, perfis sociais rotulados, CPF, CEP e padrões de endereço residencial, com política fail-closed (omissão do campo se permanecer padrão sensível detectável).
  - `user_id` e `truncation_metadata` usam `Field(exclude=True)` em `AuthorizedAIContext`, permanecendo disponíveis apenas no backend e ausentes em `model_dump()`, `model_dump_json()`, `to_provider_payload()`, `to_provider_payload_json()` e `to_provider_payload_bytes()`.
  - Labels de experiências e formações são sanitizados e limitados a 200 caracteres, e o contexto aplica orçamento determinístico com teto absoluto (`max_facts <= 60`, `1.024 <= max_payload_bytes <= 24.000` bytes UTF-8) medido sobre o payload completo serializado via `serialize_canonical_provider_payload` (`ensure_ascii=False, allow_nan=False, separators=(",", ":")`), garantindo `truncation_metadata.serialized_bytes == len(ctx.to_provider_payload_bytes()) <= max_payload_bytes <= 24.000` (NC-02 / NC-04).
- **Restrições Estritas de Slots, Duplicidades e Vínculo de Entidades (`ai_schemas.py`, `grounding_validator.py`):**
  - Allowlist explícita de `slot_id` por `material_type` alinhada aos schemas de `structured_content`, rejeitando slots arbitrários, de metadados (`is_approved`, `origin`, `provenance`, `header.email`, `pending_fields`) ou de outros tipos de material.
  - Rejeição de `slot_id` duplicado no mesmo conjunto de sugestões.
  - Em slots vinculados a entidade (`experience_highlight:<id>`, `project_highlight:<id>`, `relevance_highlight:...`, `relevant_evidence:...`), exige citação exata da entidade alvo, proíbe citações cruzadas de outras entidades (evitando vazamento de tecnologias/empresas entre projetos e experiências) e impede apresentar projetos como emprego formal.
  - Em slots narrativos gerais, rejeita evidências irrelevantes (ex.: citar apenas idioma ou formação para sustentar experiência profissional em desenvolvimento de software).
- **Validação Conservadora All-or-Nothing (`StructuredGroundingValidator`):** Qualquer falha em qualquer item invalida todo o lote (`is_valid = False`):
  - *Grounding Numérico Tipado:* classifica e valida por categoria e significado semântico (`percentage`, `currency`, `duration`, `year`, `tech_version`, `vague_scale`, `entity_count` por família semântica e números residuais), com word boundaries estritos em numerais por extenso (PT-BR e EN) e sem jamais extrair autorização da própria resposta da IA.
  - *Matcher Dedicado de Tecnologias:* fronteiras de token rígidas (`Java != JavaScript`) e desambiguação de termos comuns em inglês (`go`, `rest`, `spring`, `redis`, `react`, `node`), validando estritamente contra os fatos confirmados citados.
  - *Empresas, Cargos, Liderança e Afirmações Qualitativas:* bloqueia empresas inventadas ou trocadas, cargos/senioridades sem respaldo, verbos de liderança/gestão/propriedade não sustentados e afirmações qualitativas exageradas (custos, receita, transformação sistêmica, prêmios, patentes, certificações) ausentes dos fatos citados.
  - *Conteúdo Não Confiável na Saída (`safety.py`):* rejeita URLs com/sem protocolo, links Markdown (inclusive multilinha), e-mails diretos e ofuscados (`[at]`/`[dot]`/` at `/` dot `), telefones BR e internacionais (incluindo DDD 19 e 20), tags HTML/SVG, atributos `on*` e esquemas ativos (`javascript:`, `vbscript:`, `data:`).
- **Orquestração, Proteção de Proveniência, Concorrência TOCTOU e Sanitização de Erros HTTP (Subfase 04.4.3 — `overlay_merger.py`, `orchestrator.py`, `execution_guard.py`, `_db_locks.py`, `api/routes/materials.py`, `main.py`):**
  - *Orçamento global estrito de 24.000 bytes e segregação de entradas não confiáveis (`AUD-443-01`):* `build_authorized_ai_context` recebe reserva prioritária de até 75% (`18.000` bytes) para `candidate_confirmed_facts` e `target_opportunity_context`; em seguida, `_build_budgeted_structured_input` ajusta `reference_draft_slots_untrusted_for_facts` e `user_writing_preferences` via busca binária sobre medição real em bytes UTF-8 (`len(serialize_canonical_provider_payload(structured_input)) <= 24.000`), garantindo que rascunhos ou instruções nunca expulsem fatos confirmados e falhando antes de consumir quota caso o esqueleto mínimo exceda o orçamento.
  - *Proteção determinística de autoria, limites e pendências (`ControlledOverlayMerger`, `AUD-443-03`, `AUD-443-06`, `AUD-443-09`):* opera em modo All-or-Nothing sobre cópia profunda (`model_copy(deep=True)`), rejeitando caracteres de controle C0/C1, strings que se tornem vazias após sanitização/normalização (`&nbsp;`, espaços Unicode e caracteres invisíveis `Cf`/`\u200b`), citações cruzadas entre entidades (`cross_entity_citation`) e textos que excedam o limite do slot (`3.000`, `1.000`, `300` ou `4.000` caracteres, sem truncamento silencioso). Protege integralmente blocos `user_authored` e `pending_fields`, aplica a Política 2 para `manual_edit`, recalcula `has_unverified_manual_edits` e recalcula `character_count` em `recruiter_message` após a validação/normalização Pydantic (`model_validate`).
  - *Versionamento imutável e rejeição persistida (`0012_ai_version_rejection_state`):* toda versão `origin="ai_assisted"` nasce com `is_approved=False`, `is_rejected=False` e `is_mutable=False`. A rejeição (`POST .../reject-ai`) marca `is_rejected=True` e `rejected_at=utc_now()` sob `CheckConstraint` (`rejection_state_consistent`) sem exclusão física (`DELETE`), preservando a trilha de auditoria e o vínculo `ai_usage_ledger.version_id` e bloqueando aprovação, edição, derivação, vínculo e exportação/download de versões rejeitadas.
  - *Contrato transacional explícito `commit=False`, proteção contra TOCTOU e concorrência (`AUD-443-02`, `AUD-443-07`, `AUD-443-08`, `AUD-443-10`):* quando `commit=False`, `allow_transaction_reset=False` é propagado explicitamente a `prepare_atomic_write_transaction`, `acquire_quota_scope_locks` e `_lock_or_create_breaker_row`, impedindo qualquer `db.commit()` implícito mesmo após `db.flush()`. Na Sessão #2, `acquire_material_exclusivity_lock` adquire lock exclusivo em ordem canônica de 5 níveis (também utilizado por `delete_material` e demais mutações com `run_atomic_with_sqlite_retry`), revalida o fingerprint TOCTOU completo (incluindo todos os vínculos ativos e históricos em `application_material_links`) e comita versão, circuit breaker e ledger em **um único commit atômico** (com criação e consulta da sessão de contingência inteiramente protegidas por `try/except` para jamais mascarar a exceção primária).
  - *Sanitização estrita de erros HTTP e `slot_id` não confiáveis (`AUD-443-04`, `AUD-443-05`, `AUD-443-12`):* respostas `422` e `502` mapeiam todos os 26 códigos canônicos emitidos por `StructuredGroundingValidator` (`CANONICAL_GROUNDING_CODES`, incluindo falhas de topo `error`/`detail`) para rótulos estáticos seguros e validam qualquer `slot_id` retornado pelo provider contra o conjunto real de slots da versão de origem (substituindo identificadores desconhecidos por `"unrecognized_slot"`), sem jamais ecoar substrings ou marcadores do provider. `CORSMiddleware` expõe `Content-Disposition`, `X-AI-Error-Code` e `Retry-After`.
- **Limitações Remanescentes e Revisão Humana Obrigatória:** Regras determinísticas e heurísticas não substituem compreensão semântica completa; paráfrases sutis, nuances de contexto ou endereços/entidades fora dos padrões reconhecidos ainda podem exigir discernimento humano. Por arquitetura, nenhuma sugestão de IA será aprovada ou incorporada automaticamente sem revisão e aprovação explícita do usuário.

### 04.4.4 — AI Studio (frontend)

- O navegador nunca chama provedores de IA; toda chamada passa pelo backend autenticado com CSRF.
- Sugestões de IA exigem decisão humana explícita; edições são salvas via derivação (versão imutável nunca sofre PUT).
- Citações factuais exibidas vêm exclusivamente do snapshot persistido; erros mostram apenas mensagens seguras do backend, sem conteúdo do provider.
