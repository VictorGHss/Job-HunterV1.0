# Política e Arquitetura de Segurança (SECURITY.md)

Este documento registra as decisões arquiteturais de segurança implementadas na **Fase 01** e endurecidas na **Fase 01.1** do **Job Hunter**, bem como os controles ativos e limitações conhecidas.

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
