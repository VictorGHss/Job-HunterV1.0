# Guia de Implantação e Operação (DEPLOY.md)

Este documento descreve a operação do ambiente local em containers e a preparação arquitetural para exposição futura no domínio **`https://jobhunter.ctrls.dev.br`** utilizando **Cloudflare Tunnel** e **Cloudflare Access**.

> [!IMPORTANT]
> Nenhuma alteração de DNS ou configuração de túneis existentes na conta Cloudflare deve ser executada sem autorização explícita do responsável pelo projeto.

---

## 1. Arquitetura de Execução Local

O ambiente é orquestrado pelo arquivo [`infra/compose.yaml`](infra/compose.yaml) e dividido em três serviços conectados pela rede bridge interna `job_hunter_net`:

1. **`db` (`postgres:16-alpine`)**:
   - Volume persistente nomeado: `job_hunter_pgdata`.
   - **Não exposto publicamente no host** (utiliza apenas `expose: ["5432"]` para comunicação interna com o `backend`).
   - Possui healthcheck ativo com `pg_isready`.
2. **`backend` (`FastAPI + Uvicorn`)**:
   - Construído em imagem multi-stage (`target: base`), excluindo `pytest` e arquivos de teste do runtime de produção.
   - Roda sob usuário não-root (`appuser`, UID `10001`).
   - Monta `../local-seeds` em `/run/local-seeds:ro` para importação opcional de perfil via CLI administrativa.
   - Executa `alembic upgrade head` antes de iniciar o servidor ASGI.
   - Publicado apenas em loopback local: `127.0.0.1:${BACKEND_PORT:-8090}->8000/tcp`.
3. **`frontend` (`Nginx 1.27 Alpine` + Build estática Vite/React)**:
   - Serve os artefatos estáticos da SPA e o manifesto PWA (`/manifest.webmanifest`).
   - Encaminha requisições `/api/*` via proxy reverso interno para `http://backend:8000/api/`, propagando `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` e `X-Forwarded-Host`.
   - Publicado apenas em loopback local: `127.0.0.1:${FRONTEND_PORT:-5180}->80/tcp`.
4. **`backend-test` (Perfil opcional `test` para PostgreSQL 16)**:
   - Executa a suíte `pytest` usando o estágio `test` do Dockerfile contra o banco dedicado `jobhunter_test`, sem tocar no banco `jobhunter`.

### Portas Padrão (Sem Conflito com Outros Projetos Locais)
As portas padrão foram selecionadas após inspeção do ambiente para não colidir com serviços existentes (`5432`, `5433`, `15432`, `6379`, `8080`, etc.):
- `FRONTEND_PORT=5180` (`127.0.0.1:5180`)
- `BACKEND_PORT=8090` (`127.0.0.1:8090`)

---

## 2. Comandos Operacionais do Dia a Dia

### Iniciar o sistema
```powershell
docker compose --env-file .env -f infra/compose.yaml up -d
```

### Verificar estado e saúde (Healthchecks)
```powershell
docker compose --env-file .env -f infra/compose.yaml ps
curl http://127.0.0.1:8090/api/v1/health
```

### Visualizar logs sem expor segredos
```powershell
docker compose --env-file .env -f infra/compose.yaml logs -f backend frontend
```

### Parar o sistema (Zero consumo em segundo plano)
```powershell
docker compose --env-file .env -f infra/compose.yaml down
```

### Sincronização controlada de oportunidades (Fases 02 a 02.5)
A coleta pública é acionada explicitamente via CLI para respeitar os limites dos provedores e o estado de conformidade de cada fonte (`remote_ok`, `jobicy`, `himalayas`, `github_backend_br` e `github_frontend_br`: ativas com intervalo `>= 3600s`; `remotive`: temporariamente desabilitada com `enabled=false` aguardando autorização escrita):

```powershell
# Teste de conectividade, validação e métricas sem persistir no banco (apenas fontes habilitadas)
docker exec job-hunter-backend python -m app.cli sync-opportunities --source remote_ok --dry-run

# Sincronização normal de todas as fontes habilitadas (exibe métricas por fonte e consolidado)
docker exec job-hunter-backend python -m app.cli sync-opportunities

# Sincronização pontual ignorando apenas o intervalo mínimo (--force nunca ativa fonte desabilitada)
docker exec job-hunter-backend python -m app.cli sync-opportunities --source remote_ok --force
```

Na **Fase 02.5**, cada execução registra e exibe separadamente:
- `recebidas` (`received_count`), `validas` (`valid_count`) e `rejeitadas` (`rejected_count`), garantindo `received_count == valid_count + rejected_count`;
- `criadas` (`inserted_count`), `atualizadas` (`updated_count`), `dup_interna` (`intra_source_duplicate_count`) e `dup_entre_fontes` (`cross_source_duplicate_count`), garantindo que nenhum registro válido seja contabilizado em categorias incompatíveis;
- `unicas` (`unique_opportunities_count`), `abertas` (`open_opportunities_count`), `encerradas` (`closed_or_expired_count`) e `nao_confirmadas` (`unconfirmed_count`) por fonte e no total consolidado.

Regras operacionais de habilitação:
- `--force` ignora **somente** o intervalo mínimo entre execuções; nunca executa coleta de uma fonte com `enabled=false` ou `enabled_by_default=False`.
- Para habilitar uma fonte pausada no futuro após esclarecimento e aprovação escrita dos termos, atualize `enabled_by_default=True` no conector, defina `enabled=true` em `opportunity_sources` e execute `--dry-run` antes da sincronização real.
- Primeira carga real registrada com `remote_ok`: **97 oportunidades coletadas e inseridas** (0 atualizações/erros).

### Reclassificação segura e idempotente (Fases 02.2 a 02.6.1)
Para reavaliar `opportunity_type`, `seniority_level`, requisitos de experiência (`experience_requirement_mode`, `experience_min_years`, `experience_preferred_years`, `experience_summary`), `employment_type`, `professional_area` e `secondary_areas` em vagas externas já persistidas sem afetar cadastros manuais, estados do usuário, vínculo entre fontes (`opportunity_source_links`) ou histórico temporal:

```powershell
# Simulação sem persistência
docker exec job-hunter-backend python -m app.cli reclassify-opportunities --source remote_ok --dry-run

# Aplicação idempotente (recusa fontes desabilitadas como remotive)
docker exec job-hunter-backend python -m app.cli reclassify-opportunities --source remote_ok
```

As variáveis `SYNC_HTTP_CONNECT_TIMEOUT_SECONDS`, `SYNC_HTTP_READ_TIMEOUT_SECONDS`, `SYNC_MAX_RESPONSE_BYTES`, `SYNC_MAX_RETRIES` e `SYNC_USER_AGENT` no `.env` controlam timeouts, teto de payload e retentativas HTTP (`429 Retry-After` e backoff em `5xx`).

### Infraestrutura de IA Assistida e Controles Operacionais (Subfase 04.4.1)
A fundação de IA permanece **desabilitada por padrão** (`AI_ASSISTED_ENABLED=false`, `AI_PROVIDER=disabled`), sem exigir API key ou conectividade externa para subida dos containers, migrações ou uso dos módulos existentes:
- **Variáveis de cota e janelas temporais (UTC):**
  - `AI_RATE_LIMIT_WINDOW_SECONDS=900` e `AI_USER_WINDOW_MAX_REQUESTS=10`: janela deslizante em UTC (`[now - 900s, now]`).
  - `AI_USER_DAILY_MAX_REQUESTS=30`, `AI_USER_DAILY_MAX_TOKENS=60000` e `AI_GLOBAL_DAILY_MAX_TOKENS=100000`: dia civil fixo em UTC (`[00:00:00Z, 24:00:00Z)`).
  - `AI_RESERVATION_TTL_SECONDS=60`: expira automaticamente reservas abandonadas caso um worker seja interrompido entre a reserva e a consolidação, evitando bloqueio indefinido de cota.
  - `AI_HTTP_TOTAL_TIMEOUT_SECONDS=24.0` (obrigatoriamente `< 25.0` e `>= AI_HTTP_CONNECT_TIMEOUT_SECONDS`), `AI_HTTP_CONNECT_TIMEOUT_SECONDS=5.0`, `AI_HTTP_READ_TIMEOUT_SECONDS=20.0` e `AI_HTTP_MAX_RESPONSE_BYTES=262144`: parâmetros de referência validados para a futura camada HTTP.
- **Circuit breaker compartilhado e topologia multi-worker (`AI_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3`, `AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS=120`):**
  - O estado do circuit breaker (`ai_circuit_breakers`) e os locks de reserva (`ai_quota_scope_locks`) são persistidos no PostgreSQL (`db`), garantindo comportamento idêntico com 1 ou múltiplos workers/réplicas do `backend` sem necessidade de Redis.
  - **Limitações operacionais explícitas:** como o circuit breaker reside no banco SQL, indisponibilidade do próprio PostgreSQL impede a abertura/consulta do circuito (falhando de forma fechada antes de qualquer chamada externa); além disso, se o processo encerrar abruptamente durante o único probe permitido em `half_open`, um novo probe aguarda a expiração de `AI_RESERVATION_TTL_SECONDS` (`60s`).
- **Contexto Autorizado e Validação Estruturada de Grounding (Subfase 04.4.2):**
  - `build_authorized_ai_context` e `build_authorized_fact_bundle` consultam o estado persistido de `Application`, `Opportunity` e das 6 entidades de perfil (`ProfessionalProfile`, `WorkExperience`, `ProfessionalProject`, `Education`, `Skill`, `Language`) sob `db.no_autoflush` por meio de projeções SQL escalares explícitas (`.mappings()` -> DTOs imutáveis), filtrando `verification_status == 'confirmed'` e `user_id == user.id` diretamente no SQL sem depender de objetos ORM do `Session.identity_map` (NC-01) e sem descartar edições legítimas pendentes na sessão do chamador (NC-03).
  - Redige PII em campos de texto livre (com fallback fail-closed), exclui `user_id` e `truncation_metadata` da serialização externa (`to_provider_payload()`, `to_provider_payload_json()`, `to_provider_payload_bytes()`, `model_dump()`, `model_dump_json()`) e aplica orçamento determinístico com teto absoluto de até `60` fatos e `24.000` bytes UTF-8 (piso `1.024`) medido sobre os bytes canônicos exatos de `to_provider_payload_bytes()` (`serialized_bytes == len(to_provider_payload_bytes()) <= 24.000`, NC-02 / NC-04).
  - `StructuredGroundingValidator` opera em memória com política conservadora All-or-Nothing, exigindo allowlist de slots sem duplicidades, separação entre requisitos da vaga e fatos do candidato, grounding numérico categorizado e bloqueio de links/domínios, e-mails, telefones e conteúdo ativo. Revisão humana permanece obrigatória.
- **Orquestração, Versionamento Imutável e Rejeição Persistida (Subfase 04.4.3):**
  - Migration `0012_ai_version_rejection_state` adiciona `is_rejected` e `rejected_at` em `application_material_versions`, a constraint `rejection_state_consistent` e o índice composto `ix_material_versions_mat_rejected_ver` (`(material_id, is_rejected, version_number)`), aplicada automaticamente via `alembic upgrade head`.
  - Endpoints `POST /api/v1/materials/{material_id}/versions/{version_id}/ai-enhance` (`201 Created`) e `POST /api/v1/materials/{material_id}/versions/{version_id}/reject-ai` (`200 OK`) operam com orçamento global estrito de `<= 24.000` bytes UTF-8 medido sobre `serialize_canonical_provider_payload(structured_input)` (reservando prioritariamente até 75% para fatos confirmados), `ControlledOverlayMerger`, lock exclusivo em ordem canônica (`acquire_material_exclusivity_lock`), verificação de fingerprint TOCTOU (incluindo histórico completo de vínculos) e commit atômico único na Sessão #2 (`commit=False` explícito com `allow_transaction_reset=False`), com sessão de contingência protegida para reconciliação de commits ambíguos e headers `Content-Disposition`, `X-AI-Error-Code` e `Retry-After` expostos no `CORSMiddleware`.
  - Zero dependências de provedores de IA externos reais e zero tráfego de rede para terceiros (mantendo `AI_ASSISTED_ENABLED=false` e `AI_PROVIDER=disabled` por padrão).

---

## 3. Preparação para Cloudflare Tunnel (`jobhunter.ctrls.dev.br`)

Quando o responsável decidir publicar o acesso remoto via Cloudflare Tunnel:

### 3.1. Princípios de Exposição Segura
1. **Encaminhar tráfego exclusivamente para o serviço Web (`frontend`):**
   - O túnel deve apontar apenas para `http://127.0.0.1:5180` (ou `http://frontend:80` caso o `cloudflared` rode na rede `job_hunter_net`).
   - O Nginx do `frontend` já realiza o proxy reverso de `/api/*` para o `backend`, eliminando a necessidade de expor o container do backend diretamente na borda se não desejar.
2. **Nunca expor o PostgreSQL (`db`) no Tunnel:**
   - O banco de dados jamais deve receber rota pública, subdomínio TCP ou porta exposta no host.
3. **Segredos fora do Git:**
   - Tokens (`TUNNEL_TOKEN`) ou arquivos `cloudflared-credentials.json` nunca devem ser commitados no repositório (já bloqueados no `.gitignore`).
4. **Isolamento de outros túneis:**
   - Não reutilizar nem sobrescrever arquivos de configuração de containers ou túneis de outros projetos em execução na máquina.

### 3.2. Configuração Obrigatória de Segurança em Produção (`ENVIRONMENT=production`)
Ao habilitar `ENVIRONMENT=production` no `.env`, a aplicação valida automaticamente no startup (recusando iniciar caso falhe):
- `COOKIE_SECURE=true` (obrigatório em HTTPS).
- `SECRET_KEY` forte (mínimo 32 caracteres e 10 caracteres distintos, sem placeholders).
- `CORS_ORIGINS` não vazio, sem wildcard `*` e exclusivamente com esquema `https://`.
- `AI_PROVIDER` diferente de `mock` (o provider de testes `MockLLMProvider` é estritamente recusado no startup em `production`; se `AI_PROVIDER=disabled`, `resolve_llm_provider` retorna `DisabledLLMProvider`, falhando de forma segura sem impedir a subida dos demais módulos).

```ini
ENVIRONMENT=production
PLANNED_HOSTNAME=https://jobhunter.ctrls.dev.br
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
CORS_ORIGINS=https://jobhunter.ctrls.dev.br
```

### 3.3. Origem Confiável, Nginx e Cloudflare Tunnel (`TRUSTED_PROXY_CIDRS` / `TRUST_CF_CONNECTING_IP`)
Para que o rate limiting de login identifique corretamente o cliente sem aceitar spoofing de `X-Forwarded-For`:
- Em uso local atrás do Nginx do `frontend`, mantenha `TRUSTED_PROXY_CIDRS` restrito às sub-redes internas confiáveis (`127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`) e `TRUST_CF_CONNECTING_IP=false`.
- Caso o backend seja acessado por fora da rede confiável configurada, cabeçalhos `X-Forwarded-For` e `CF-Connecting-IP` são ignorados automaticamente.
- Ao publicar via Cloudflare Tunnel (`cloudflared` apontando para o Nginx/`frontend`), só habilite `TRUST_CF_CONNECTING_IP=true` se o Nginx e o backend **não aceitarem conexões HTTP diretas de redes não autenticadas fora do túnel/Cloudflare** (pois do contrário qualquer cliente que alcance a origem diretamente poderia forjar `CF-Connecting-IP`).

### 3.4. Camada Adicional Recomendada: Cloudflare Access (Zero Trust)
Mesmo com a autenticação Argon2id + Sessão HttpOnly nativa do Job Hunter, recomenda-se configurar uma **Application Policy** no **Cloudflare Zero Trust (Cloudflare Access)** para o hostname `jobhunter.ctrls.dev.br`:
- **Política:** `Allow` apenas para a lista explícita de e-mails autorizados (One-Time Pin ou provedor de identidade GitHub/Google).
- **Benefício:** Bloqueia bots, scanners e tentativas de força bruta na borda da Cloudflare antes mesmo de atingirem a máquina local.

### 04.4.4 — AI Studio (frontend)

Sem novas variáveis de ambiente. O frontend consome os endpoints ai-enhance e reject-ai da 04.4.3. Em proxies reversos/CORS, mantenha expostos os cabeçalhos X-AI-Error-Code e Retry-After (o backend já os expõe via CORSMiddleware).
