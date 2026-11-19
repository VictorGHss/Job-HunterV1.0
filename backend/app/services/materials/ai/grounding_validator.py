from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from app.services.materials.ai.ai_schemas import (
    AIMaterialEnhanceOutput,
    AuthorizedAIContext,
    AuthorizedFactItem,
    ParsedSlotTarget,
    parse_and_validate_slot_for_material,
)
from app.services.materials.ai.safety import (
    find_active_or_html_content,
    find_emails,
    find_markdown_links,
    find_phones,
    find_urls_or_domains,
)

# ---------------------------------------------------------------------------
# Normalização textual
# ---------------------------------------------------------------------------


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _normalize_for_search(text: str | None) -> str:
    if not text:
        return ""
    return _strip_accents(text).lower()


# ---------------------------------------------------------------------------
# 1. Matcher dedicado de tecnologias (sem _contains_term do matching de vagas)
#    Previne substring (Java != JavaScript) e falsos positivos em inglês (M-04).
# ---------------------------------------------------------------------------

# Tecnologias inequívocas (sempre casam por fronteira de token estrita)
_UNAMBIGUOUS_TECH_PATTERNS: dict[str, tuple[str, ...]] = {
    "python": (r"python",),
    "javascript": (r"javascript", r"js"),
    "typescript": (r"typescript", r"ts"),
    "java": (r"java",),
    "c#": (r"c#", r"csharp", r"\.net", r"dotnet", r"asp\.net"),
    "c++": (r"c\+\+", r"cpp"),
    "php": (r"php",),
    "laravel": (r"laravel",),
    "ruby": (r"ruby", r"ruby\s+on\s+rails", r"rails"),
    "kotlin": (r"kotlin",),
    "scala": (r"scala",),
    "elixir": (r"elixir",),
    "dart": (r"dart",),
    "flutter": (r"flutter",),
    "fastapi": (r"fastapi",),
    "django": (r"django",),
    "flask": (r"flask",),
    "angular": (r"angular", r"angularjs"),
    "vue": (r"vue", r"vue\.js", r"vuejs", r"nuxt", r"nuxt\.js", r"nuxtjs"),
    "svelte": (r"svelte", r"sveltekit"),
    "next.js": (r"next\.js", r"nextjs"),
    "nestjs": (r"nestjs", r"nest\.js"),
    "express": (r"express\.js", r"expressjs"),
    "react native": (r"react\s+native",),
    "graphql": (r"graphql",),
    "postgresql": (r"postgresql", r"postgres"),
    "mysql": (r"mysql",),
    "mongodb": (r"mongodb", r"mongo"),
    "redis": (r"redis",),
    "elasticsearch": (r"elasticsearch",),
    "sqlite": (r"sqlite",),
    "sql server": (r"sql\s+server", r"mssql"),
    "oracle": (r"oracle\s+db", r"oracle\s+database", r"pl/sql"),
    "dynamodb": (r"dynamodb",),
    "cassandra": (r"cassandra",),
    "sql": (r"sql",),
    "kafka": (r"kafka", r"apache\s+kafka"),
    "rabbitmq": (r"rabbitmq",),
    "pytorch": (r"pytorch",),
    "tensorflow": (r"tensorflow",),
    "scikit-learn": (r"scikit-learn", r"sklearn"),
    "pandas": (r"pandas",),
    "airflow": (r"airflow", r"apache\s+airflow"),
    "snowflake": (r"snowflake",),
    "databricks": (r"databricks",),
    "power bi": (r"power\s+bi", r"powerbi"),
    "tableau": (r"tableau",),
    "docker": (r"docker",),
    "kubernetes": (r"kubernetes", r"k8s"),
    "aws": (r"aws", r"amazon\s+web\s+services"),
    "gcp": (r"gcp", r"google\s+cloud"),
    "azure": (r"azure", r"microsoft\s+azure"),
    "terraform": (r"terraform",),
    "ansible": (r"ansible",),
    "jenkins": (r"jenkins",),
    "github actions": (r"github\s+actions",),
    "gitlab ci": (r"gitlab\s+ci",),
    "linux": (r"linux",),
    "salesforce": (r"salesforce",),
    "sap": (r"sap", r"sap\s+erp", r"sap\s+abap", r"s/4hana"),
    "nginx": (r"nginx",),
    "prometheus": (r"prometheus",),
    "grafana": (r"grafana",),
}

# Padrões dedicados para tecnologias com homônimos na língua natural (M-04)
_TECH_CONTEXT_PREFIX = (
    r"(?:with|in|using|via|on|of|experience\s+(?:with|in)|proficient\s+in|skilled\s+in|"
    r"built\s+with|written\s+in|developed\s+(?:with|in)|framework|language|linguagem|"
    r"com|em|usando|utilizando|experi[eê]ncia\s+(?:com|em)|dom[ií]nio\s+(?:de|em)|"
    r"apis?\s+(?:em|com|in|with)|micros?servi[cç]os?\s+(?:em|com)|microservices?\s+(?:in|with))"
)
_TECH_CONTEXT_SUFFIX = (
    r"(?:developer|engineer|programming|language|framework|backend|frontend|api|apis|"
    r"microservices?|micros?servi[cç]os?|ecosystem|stack|runtime|apps?|applications?|"
    r"desenvolvedor|engenheiro|linguagem|\d+(?:\.\d+)?)"
)

_TB_START = r"(?<![a-zA-Z0-9_+#])"
_TB_END = r"(?![a-zA-Z0-9_+#])(?!\.[a-zA-Z0-9])"

_AMBIGUOUS_TECH_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "go": (
        re.compile(rf"(?i){_TB_START}golang{_TB_END}"),
        re.compile(
            rf"(?i)(?:{_TECH_CONTEXT_PREFIX}\s+)go{_TB_END}(?!\s+(?:to|ahead|through|on|back|over|into|beyond|for|with|out|up|down)\b)"
        ),
        re.compile(rf"(?i){_TB_START}go\s+(?:{_TECH_CONTEXT_SUFFIX}){_TB_END}"),
        re.compile(rf"{_TB_START}Go(?:\s*[,/&]\s*[A-Z][A-Za-z0-9.+#-]+|\s+(?:e|and)\s+[A-Z][A-Za-z0-9.+#-]+)"),
        re.compile(rf"[A-Z][A-Za-z0-9.+#-]+\s*(?:[,/&]|e|and)\s+Go{_TB_END}"),
    ),
    "rest": (
        re.compile(rf"(?i){_TB_START}restful{_TB_END}"),
        re.compile(rf"(?i){_TB_START}(?:apis?\s+rest|rest\s+apis?|servi[cç]os?\s+rest|endpoints?\s+rest|arquitetura\s+rest|rest\s+services?|rest\s+endpoints?){_TB_END}"),
        re.compile(rf"{_TB_START}REST(?:\s*/\s*GraphQL|\s*[,&]\s*GraphQL){_TB_END}"),
    ),
    "spring": (
        re.compile(rf"(?i){_TB_START}spring\s*(?:boot|framework|cloud|security|mvc|data|batch){_TB_END}"),
        re.compile(
            rf"(?:{_TECH_CONTEXT_PREFIX}\s+)Spring{_TB_END}(?!\s+(?:season|break|water|cleaning|time|months?|weather)\b)"
        ),
        re.compile(rf"{_TB_START}Java\s*[/,&+]\s*Spring{_TB_END}"),
    ),
    "node.js": (
        re.compile(rf"(?i){_TB_START}(?:node\.js|nodejs|node\s+js){_TB_END}"),
        re.compile(
            rf"(?:{_TECH_CONTEXT_PREFIX}\s+)Node{_TB_END}(?!\s+(?:in|of|for|at|on|from)\b)"
        ),
        re.compile(rf"{_TB_START}Node(?:\s*[,/&]\s*(?:React|Express|TypeScript|JavaScript|NestJS|Python|Docker))"),
    ),
    "react": (
        re.compile(rf"(?i){_TB_START}(?:react\.js|reactjs){_TB_END}"),
        re.compile(
            rf"(?i)(?:{_TECH_CONTEXT_PREFIX}\s+)react{_TB_END}(?!\s+(?:to|quickly|fast|well|positively|negatively|against|with\s+empathy)\b)"
        ),
        re.compile(rf"{_TB_START}React{_TB_END}(?!\s+(?:to|quickly|fast|well|against)\b)"),
    ),
    "rust": (
        re.compile(rf"(?i)(?:{_TECH_CONTEXT_PREFIX}\s+)rust{_TB_END}"),
        re.compile(rf"(?i){_TB_START}rust\s+(?:{_TECH_CONTEXT_SUFFIX}){_TB_END}"),
        re.compile(rf"{_TB_START}Rust{_TB_END}"),
    ),
    "spark": (
        re.compile(rf"(?i){_TB_START}(?:apache\s+spark|pyspark|spark\s+sql|spark\s+streaming){_TB_END}"),
        re.compile(rf"(?i)(?:{_TECH_CONTEXT_PREFIX}\s+)spark{_TB_END}"),
        re.compile(rf"{_TB_START}Spark{_TB_END}(?!\s+(?:interest|innovation|curiosity|discussion)\b)"),
    ),
    "swift": (
        re.compile(rf"(?i){_TB_START}swiftui{_TB_END}"),
        re.compile(rf"(?i)(?:{_TECH_CONTEXT_PREFIX}\s+)swift{_TB_END}"),
        re.compile(rf"{_TB_START}Swift{_TB_END}(?!\s+(?:response|action|delivery|resolution)\b)"),
    ),
}

_COMPILED_UNAMBIGUOUS_TECH: dict[str, tuple[re.Pattern[str], ...]] = {
    tech: tuple(
        re.compile(rf"(?i){_TB_START}{pat}{_TB_END}")
        for pat in patterns
    )
    for tech, patterns in _UNAMBIGUOUS_TECH_PATTERNS.items()
}

# Mapeamento de aliases normalizados para nomes canônicos (usado também ao ler fact.technologies)
_CANONICAL_TECH_LOOKUP: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "golang": "go",
    "csharp": "c#",
    ".net": "c#",
    "dotnet": "c#",
    "asp.net": "c#",
    "cpp": "c++",
    "rails": "ruby",
    "ruby on rails": "ruby",
    "vuejs": "vue",
    "vue.js": "vue",
    "nuxt": "vue",
    "nuxt.js": "vue",
    "nuxtjs": "vue",
    "nextjs": "next.js",
    "nest.js": "nestjs",
    "expressjs": "express",
    "express.js": "express",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node.js",
    "node js": "node.js",
    "node": "node.js",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "k8s": "kubernetes",
    "amazon web services": "aws",
    "google cloud": "gcp",
    "microsoft azure": "azure",
    "apache kafka": "kafka",
    "apache spark": "spark",
    "pyspark": "spark",
    "apache airflow": "airflow",
    "sklearn": "scikit-learn",
    "powerbi": "power bi",
    "spring boot": "spring",
    "spring framework": "spring",
    "apis rest": "rest",
    "api rest": "rest",
    "rest api": "rest",
    "rest apis": "rest",
    "restful": "rest",
    "sap erp": "sap",
    "sap abap": "sap",
    "mssql": "sql server",
}


def canonicalize_tech_name(raw: str) -> str:
    norm = _normalize_for_search(raw).strip()
    return _CANONICAL_TECH_LOOKUP.get(norm, norm)


def extract_mentioned_technologies(text: str) -> set[str]:
    """Extrai tecnologias mencionadas respeitando fronteiras de token e ambiguidade em inglês."""
    if not text:
        return set()
    found: set[str] = set()
    for tech, patterns in _COMPILED_UNAMBIGUOUS_TECH.items():
        if any(p.search(text) for p in patterns):
            found.add(tech)
    for tech, patterns in _AMBIGUOUS_TECH_RULES.items():
        if any(p.search(text) for p in patterns):
            found.add(tech)
    # Se 'react native' foi detectado, remove 'react' avulso apenas se 'react' não aparecer separadamente
    if "react native" in found:
        without_rn = re.sub(r"(?i)react\s+native", " ", text)
        if not any(p.search(without_rn) for p in _AMBIGUOUS_TECH_RULES["react"]):
            found.discard("react")
    return found


def _extract_fact_technologies(fact: AuthorizedFactItem) -> set[str]:
    """Extrai exclusivamente tecnologias comprovadas em UM fato autorizado do usuário."""
    techs: set[str] = set()
    for raw_t in fact.technologies:
        if raw_t and raw_t.strip():
            techs.add(canonicalize_tech_name(raw_t))
            techs.update(extract_mentioned_technologies(raw_t))
    if fact.entity_type == "skill" and fact.label:
        techs.add(canonicalize_tech_name(fact.label))
        techs.update(extract_mentioned_technologies(fact.label))
    for field_text in (fact.label, fact.summary, fact.description, fact.verified_results):
        if field_text:
            techs.update(extract_mentioned_technologies(field_text))
    return techs


# ---------------------------------------------------------------------------
# 2. Grounding Numérico Categorizado e Associação Semântica (A-04 / 7.1–7.4)
# ---------------------------------------------------------------------------

_SPELLED_NUMBER_VALUES: dict[str, float] = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
    "cem": 100,
    "cento": 100,
    "duzentos": 200,
    "duzentas": 200,
    "trezentos": 300,
    "trezentas": 300,
    "quatrocentos": 400,
    "quatrocentas": 400,
    "quinhentos": 500,
    "quinhentas": 500,
    "seiscentos": 600,
    "setecentos": 700,
    "oitocentos": 800,
    "novecentos": 900,
    "mil": 1_000,
    "milhao": 1_000_000,
    "milhoes": 1_000_000,
    "bilhao": 1_000_000_000,
    "bilhoes": 1_000_000_000,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}

# Numerais por extenso que NUNCA são artigos indefinidos (exclui um/uma/one isolados)
_NON_ARTICLE_SPELLED = sorted(
    (k for k in _SPELLED_NUMBER_VALUES if k not in {"um", "uma", "one"}),
    key=len,
    reverse=True,
)
_ALL_SPELLED = sorted(_SPELLED_NUMBER_VALUES.keys(), key=len, reverse=True)
_SPELLED_ALL_ALT = "|".join(_ALL_SPELLED)
_SPELLED_NON_ARTICLE_ALT = "|".join(_NON_ARTICLE_SPELLED)

_VAGUE_SCALE_WORDS = frozenset(
    {
        "dezenas",
        "centenas",
        "milhares",
        "milhoes",
        "bilhoes",
        "dozens",
        "hundreds",
        "thousands",
        "millions",
        "billions",
    }
)
_VAGUE_SCALE_RE = re.compile(
    rf"\b({'|'.join(sorted(_VAGUE_SCALE_WORDS))})\b"
)

_MULTIPLIERS: dict[str, float] = {
    "k": 1_000,
    "mil": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "milhao": 1_000_000,
    "milhoes": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "bilhao": 1_000_000_000,
    "bilhoes": 1_000_000_000,
    "billion": 1_000_000_000,
}

# Regexes de extração categorizada (executados sobre texto normalizado sem acentos)
_TECH_VERSION_CLAIM_RE = re.compile(
    r"\b(python|fastapi|django|flask|react|vue|angular|java|c#|dotnet|\.net|postgresql|postgres|"
    r"mysql|mongodb|node\.?js|php|css|html|ipv|oauth|tls|http|es|ecma|typescript|kotlin|swift|spring|redis)\s*"
    r"[/ ]?\s*(\d+(?:\.\d+){0,2})\b"
)
_MM_YYYY_RE = re.compile(r"\b(0?[1-9]|1[0-2])/((?:19|20)\d{2})\b")
_ISO_DATE_RE = re.compile(r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")

_PCT_NUM_RE = re.compile(
    rf"\b(\d+(?:[.,]\d+)?|{_SPELLED_ALL_ALT})\s*(?:%|por\s+cento|percent\b)"
)
_CURR_PREFIX_RE = re.compile(
    r"(?:r\$|us\$|u\$|\$|usd|eur|brl|gbp)\s*(\d+(?:[.,]\d+)*)(?:\s*(k|mil|milhao|milhoes|million|thousand|m|b|bilhao|bilhoes|billion)\b)?"
)
_CURR_SUFFIX_RE = re.compile(
    rf"\b(\d+(?:[.,]\d+)*|{_SPELLED_ALL_ALT})(?:\s+(k|mil|milhao|milhoes|million|thousand|bilhao|bilhoes|billion))?\s+(?:de\s+)?(reais|real|dolares|dolar|dollars|dollar|euros|euro|libras|pounds|brl|usd|eur)\b"
)
_DURATION_CLAIM_RE = re.compile(
    rf"\b(\d+(?:[.,]\d+)?|{_SPELLED_ALL_ALT})\s*(?:\+\s*)?(anos?|meses|mes|semanas?|dias?|horas?|years?|yrs?|months?|weeks?|days?|hours?)\b"
)
_YEAR_CLAIM_RE = re.compile(r"\b((?:19|20)\d{2})\b")

# Quantidade + substantivo (para preservar associação valor <-> entidade/significado)
_ENTITY_COUNT_RE = re.compile(
    rf"\b(\d+(?:[.,]\d+)*|{_SPELLED_NON_ARTICLE_ALT})(?:\s*(k|mil|milhao|milhoes|million|thousand)\b)?\s+"
    r"(?:(?:de|of|novos|novas|diferentes|distintos|distintas|principais|grandes|new|different|distinct|active|major)\s+){0,2}"
    r"([a-z]{2,30})\b"
)
_RAW_NUMBER_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\b")
_SPELLED_STANDALONE_RE = re.compile(rf"\b({_SPELLED_NON_ARTICLE_ALT})\b")

_DURATION_UNIT_MAP: dict[str, str] = {
    "ano": "year",
    "anos": "year",
    "year": "year",
    "years": "year",
    "yr": "year",
    "yrs": "year",
    "mes": "month",
    "meses": "month",
    "month": "month",
    "months": "month",
    "semana": "week",
    "semanas": "week",
    "week": "week",
    "weeks": "week",
    "dia": "day",
    "dias": "day",
    "day": "day",
    "days": "day",
    "hora": "hour",
    "horas": "hour",
    "hour": "hour",
    "hours": "hour",
}

_NOUN_SEMANTIC_FAMILIES: dict[str, str] = {
    # Equipes e pessoas
    "equipe": "team_people",
    "equipes": "team_people",
    "time": "team_people",
    "times": "team_people",
    "squad": "team_people",
    "squads": "team_people",
    "pessoa": "team_people",
    "pessoas": "team_people",
    "desenvolvedor": "team_people",
    "desenvolvedores": "team_people",
    "dev": "team_people",
    "devs": "team_people",
    "engenheiro": "team_people",
    "engenheiros": "team_people",
    "membro": "team_people",
    "membros": "team_people",
    "colaborador": "team_people",
    "colaboradores": "team_people",
    "profissional": "team_people",
    "profissionais": "team_people",
    "analista": "team_people",
    "analistas": "team_people",
    "estagiario": "team_people",
    "estagiarios": "team_people",
    "team": "team_people",
    "teams": "team_people",
    "people": "team_people",
    "person": "team_people",
    "developer": "team_people",
    "developers": "team_people",
    "engineer": "team_people",
    "engineers": "team_people",
    "member": "team_people",
    "members": "team_people",
    "employee": "team_people",
    "employees": "team_people",
    "staff": "team_people",
    # APIs e serviços
    "api": "api_service",
    "apis": "api_service",
    "endpoint": "api_service",
    "endpoints": "api_service",
    "microsservico": "api_service",
    "microsservicos": "api_service",
    "microservico": "api_service",
    "microservicos": "api_service",
    "servico": "api_service",
    "servicos": "api_service",
    "microservice": "api_service",
    "microservices": "api_service",
    "service": "api_service",
    "services": "api_service",
    # Projetos e sistemas
    "projeto": "project_system",
    "projetos": "project_system",
    "produto": "project_system",
    "produtos": "project_system",
    "sistema": "project_system",
    "sistemas": "project_system",
    "aplicacao": "project_system",
    "aplicacoes": "project_system",
    "app": "project_system",
    "apps": "project_system",
    "plataforma": "project_system",
    "plataformas": "project_system",
    "modulo": "project_system",
    "modulos": "project_system",
    "project": "project_system",
    "projects": "project_system",
    "product": "project_system",
    "products": "project_system",
    "system": "project_system",
    "systems": "project_system",
    "application": "project_system",
    "applications": "project_system",
    "platform": "project_system",
    "platforms": "project_system",
    "module": "project_system",
    "modules": "project_system",
    # Clientes e usuários
    "cliente": "client_user",
    "clientes": "client_user",
    "usuario": "client_user",
    "usuarios": "client_user",
    "empresa": "client_user",
    "empresas": "client_user",
    "conta": "client_user",
    "contas": "client_user",
    "client": "client_user",
    "clients": "client_user",
    "customer": "client_user",
    "customers": "client_user",
    "user": "client_user",
    "users": "client_user",
    "company": "client_user",
    "companies": "client_user",
    "account": "client_user",
    "accounts": "client_user",
    # Infraestrutura
    "servidor": "infra_resource",
    "servidores": "infra_resource",
    "server": "infra_resource",
    "servers": "infra_resource",
    "container": "infra_resource",
    "containers": "infra_resource",
    "cluster": "infra_resource",
    "clusters": "infra_resource",
    "banco": "infra_resource",
    "bancos": "infra_resource",
    "database": "infra_resource",
    "databases": "infra_resource",
    "pipeline": "infra_resource",
    "pipelines": "infra_resource",
    # Volumes / testes / chamados
    "requisicao": "volume_metric",
    "requisicoes": "volume_metric",
    "request": "volume_metric",
    "requests": "volume_metric",
    "transacao": "volume_metric",
    "transacoes": "volume_metric",
    "transaction": "volume_metric",
    "transactions": "volume_metric",
    "chamado": "volume_metric",
    "chamados": "volume_metric",
    "ticket": "volume_metric",
    "tickets": "volume_metric",
    "teste": "volume_metric",
    "testes": "volume_metric",
    "test": "volume_metric",
    "tests": "volume_metric",
}

# Substantivos que pertencem a outras categorias já tratadas separadamente
_SKIP_ENTITY_NOUNS = frozenset(
    set(_DURATION_UNIT_MAP.keys())
    | {
        "por",
        "percent",
        "reais",
        "real",
        "dolares",
        "dolar",
        "dollars",
        "dollar",
        "euros",
        "euro",
        "libras",
        "pounds",
        "brl",
        "usd",
        "eur",
    }
)


def _parse_numeric_value(raw_token: str, multiplier: str | None = None) -> str:
    token = raw_token.strip().lower()
    if token in _SPELLED_NUMBER_VALUES:
        base = _SPELLED_NUMBER_VALUES[token]
    else:
        # Trata separadores de milhar (ex.: 300.000 ou 50,000) vs decimais (ex.: 3.13 ou 2,5)
        if re.match(r"^\d{1,3}(?:\.\d{3})+$", token):
            clean = token.replace(".", "")
        elif re.match(r"^\d{1,3}(?:,\d{3})+$", token):
            clean = token.replace(",", "")
        else:
            clean = token.replace(",", ".")
        try:
            base = float(clean)
        except ValueError:
            return token

    if multiplier:
        mult = _MULTIPLIERS.get(multiplier.strip().lower(), 1.0)
        base *= mult

    if base == int(base):
        return str(int(base))
    return f"{base:g}"


@dataclass(frozen=True, slots=True)
class QuantitativeClaim:
    category: str
    value: str
    qualifier: str
    raw_text: str


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    s, e = span
    return any(not (e <= os or s >= oe) for os, oe in occupied)


def extract_quantitative_claims(text: str) -> list[QuantitativeClaim]:
    """Extrai afirmações quantitativas tipadas por categoria e significado semântico."""
    if not text:
        return []
    norm = _normalize_for_search(text)
    claims: list[QuantitativeClaim] = []
    occupied: list[tuple[int, int]] = []

    # 1. Versões técnicas (ex.: python 3.13, react 18) — nunca viram percentual/duração/contagem
    for m in _TECH_VERSION_CLAIM_RE.finditer(norm):
        tech = canonicalize_tech_name(m.group(1))
        ver = m.group(2)
        claims.append(QuantitativeClaim("tech_version", ver, tech, m.group(0)))
        occupied.append(m.span())

    # 2. Datas MM/YYYY e YYYY-MM-DD — mês/dia nunca viram duração ou contagem
    for m in _MM_YYYY_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        claims.append(QuantitativeClaim("year", m.group(2), "date", m.group(0)))
        occupied.append(m.span())

    for m in _ISO_DATE_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        claims.append(QuantitativeClaim("year", m.group(1), "date", m.group(0)))
        occupied.append(m.span())

    # 3. Percentuais
    for m in _PCT_NUM_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        val = _parse_numeric_value(m.group(1))
        claims.append(QuantitativeClaim("percentage", val, "%", m.group(0)))
        occupied.append(m.span())

    # 4. Moedas (prefixo e sufixo/extenso)
    for m in _CURR_PREFIX_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        val = _parse_numeric_value(m.group(1), m.group(2))
        claims.append(QuantitativeClaim("currency", val, "money", m.group(0)))
        occupied.append(m.span())

    for m in _CURR_SUFFIX_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        val = _parse_numeric_value(m.group(1), m.group(2))
        claims.append(QuantitativeClaim("currency", val, "money", m.group(0)))
        occupied.append(m.span())

    # 5. Durações
    for m in _DURATION_CLAIM_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        val = _parse_numeric_value(m.group(1))
        unit = _DURATION_UNIT_MAP.get(m.group(2), m.group(2))
        claims.append(QuantitativeClaim("duration", val, unit, m.group(0)))
        occupied.append(m.span())

    # 6. Anos isolados (19xx / 20xx)
    for m in _YEAR_CLAIM_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        claims.append(QuantitativeClaim("year", m.group(1), "year", m.group(0)))
        occupied.append(m.span())

    # 7. Quantificadores vagos de escala (dezenas, centenas, milhares, dozens, hundreds...)
    for m in _VAGUE_SCALE_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        claims.append(QuantitativeClaim("vague_scale", m.group(1), "scale", m.group(0)))
        occupied.append(m.span())

    # 8. Quantidade associada a substantivo/família semântica (ex.: 5 APIs != 5 equipes)
    for m in _ENTITY_COUNT_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        noun = m.group(3)
        if noun in _SKIP_ENTITY_NOUNS:
            continue
        val = _parse_numeric_value(m.group(1), m.group(2))
        family = _NOUN_SEMANTIC_FAMILIES.get(noun, f"noun:{noun}")
        claims.append(QuantitativeClaim("entity_count", val, family, m.group(0)))
        occupied.append(m.span())

    # 9. Números puros ou numerais por extenso residuais (sempre com word boundary)
    for m in _RAW_NUMBER_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        val = _parse_numeric_value(m.group(1))
        claims.append(QuantitativeClaim("raw_number", val, "number", m.group(0)))
        occupied.append(m.span())

    for m in _SPELLED_STANDALONE_RE.finditer(norm):
        if _overlaps(m.span(), occupied):
            continue
        val = _parse_numeric_value(m.group(1))
        claims.append(QuantitativeClaim("raw_number", val, "spelled", m.group(0)))
        occupied.append(m.span())

    return claims


def _claim_supported_by_evidence(
    claim: QuantitativeClaim,
    evidence_claims: list[QuantitativeClaim],
) -> bool:
    """Verifica se uma afirmação quantitativa tem suporte na MESMA categoria e significado."""
    if claim.category == "tech_version":
        return any(
            ev.category == "tech_version"
            and ev.qualifier == claim.qualifier
            and ev.value == claim.value
            for ev in evidence_claims
        )
    if claim.category == "percentage":
        return any(
            ev.category == "percentage" and ev.value == claim.value
            for ev in evidence_claims
        )
    if claim.category == "currency":
        return any(
            ev.category == "currency" and ev.value == claim.value
            for ev in evidence_claims
        )
    if claim.category == "duration":
        return any(
            ev.category == "duration"
            and ev.value == claim.value
            and ev.qualifier == claim.qualifier
            for ev in evidence_claims
        )
    if claim.category == "year":
        return any(
            ev.category == "year" and ev.value == claim.value
            for ev in evidence_claims
        )
    if claim.category == "vague_scale":
        return any(
            ev.category == "vague_scale" and ev.value == claim.value
            for ev in evidence_claims
        )
    if claim.category == "entity_count":
        # Exige mesma quantidade E mesma família semântica (5 APIs != 5 equipes)
        return any(
            ev.category == "entity_count"
            and ev.value == claim.value
            and ev.qualifier == claim.qualifier
            for ev in evidence_claims
        )
    if claim.category == "raw_number":
        # Número residual só é aceito se existir como raw_number ou entity_count com mesmo valor
        # (nunca derivado de mês de data, versão técnica, percentual ou moeda)
        return any(
            ev.category in {"raw_number", "entity_count"} and ev.value == claim.value
            for ev in evidence_claims
        )
    return False


# ---------------------------------------------------------------------------
# 3. Empresas, Cargos, Liderança e Afirmações Qualitativas (A-04 / 7.6–7.8)
# ---------------------------------------------------------------------------

_WELL_KNOWN_COMPANIES: tuple[str, ...] = (
    "google",
    "alphabet",
    "meta",
    "facebook",
    "amazon",
    "microsoft",
    "apple",
    "netflix",
    "uber",
    "airbnb",
    "spotify",
    "stripe",
    "shopify",
    "ibm",
    "intel",
    "nvidia",
    "tesla",
    "nubank",
    "mercado livre",
    "mercadolivre",
    "ifood",
    "itau",
    "bradesco",
    "santander",
    "banco do brasil",
    "stone",
    "pagseguro",
    "picpay",
    "totvs",
    "accenture",
    "deloitte",
    "pwc",
    "kpmg",
    "mckinsey",
    "thoughtworks",
    "globant",
    "zup",
    "quintoandar",
    "creditas",
    "rappi",
    "vtex",
    "hotmart",
    "magalu",
    "magazine luiza",
    "ambev",
    "petrobras",
    "embraer",
)

_COMPILED_WELL_KNOWN_COMPANIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rf"(?i)(?<![a-z0-9_]){re.escape(name)}(?![a-z0-9_])"))
    for name in _WELL_KNOWN_COMPANIES
)

# Extração contextual de empresas/empregadores com letra maiúscula
_EMPLOYER_CONTEXT_PT_RE = re.compile(
    r"\b(?:[Tt]rabalhou|[Tt]rabalhei|[Aa]tuou|[Aa]tuei|[Aa]tuação|[Aa]tuacao|[Ee]xperiência|[Ee]xperiencia|"
    r"[Nn]a\s+empresa|[Pp]ela\s+empresa|[Pp]ara\s+a\s+empresa|[Nn]a|[Nn]o|[Pp]ela|[Pp]elo)\s+"
    r"([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.-]+(?:\s+(?:[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.-]+|Ltda\.?|S\.?A\.?|Inc\.?|Corp\.?|LLC|Ltd\.?|Labs?|Tech|Digital|Systems|Solu[cç][oõ]es|Brasil|Group|Studio|Consulting|Software)){0,3})"
)
_EMPLOYER_CONTEXT_EN_RE = re.compile(
    r"\b(?:[Ww]orked\s+at|[Ww]orking\s+at|[Ee]mployed\s+at|[Ee]xperience\s+at|[Rr]ole\s+at|[Pp]osition\s+at|"
    r"[Jj]oined|[Aa]t\s+company|[Ff]or\s+company|[Aa]t)\s+"
    r"([A-Z][A-Za-z0-9&.-]+(?:\s+(?:[A-Z][A-Za-z0-9&.-]+|Inc\.?|Corp\.?|LLC|Ltd\.?|Labs?|Tech|Systems|Group|Software)){0,3})"
)
_CORPORATE_SUFFIX_RE = re.compile(
    r"\b([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&.-]+){0,3}\s+(?:Ltda\.?|S\.?A\.?|Inc\.?|Corp\.?|LLC|Ltd\.?))"
)

# Palavras capitalizadas comuns que NÃO são nomes de empresas após "na/no/at"
_NON_COMPANY_PROPER_WORDS = frozenset(
    {
        "brasil",
        "brazil",
        "portugal",
        "estados unidos",
        "usa",
        "europa",
        "sao paulo",
        "rio de janeiro",
        "backend",
        "frontend",
        "fullstack",
        "devops",
        "cloud",
        "mobile",
        "web",
        "dados",
        "data",
        "ti",
        "it",
        "api",
        "apis",
        "rest",
        "restful",
        "graphql",
        "sql",
        "nosql",
        "ci/cd",
        "janeiro",
        "fevereiro",
        "marco",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "portugues",
        "ingles",
        "espanhol",
        "english",
        "portuguese",
        "spanish",
    }
)

# Cargos e senioridades que exigem comprovação expressa nos fatos citados (A-04 / 7.7)
_SENIORITY_AND_ROLE_TITLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ceo", ("ceo", "chief executive officer")),
    ("cto", ("cto", "chief technology officer")),
    ("cio", ("cio", "chief information officer")),
    ("cpo", ("cpo", "chief product officer")),
    ("cfo", ("cfo", "chief financial officer")),
    ("coo", ("coo", "chief operating officer")),
    ("fundador", ("fundador", "cofundador", "co-fundador", "founder", "cofounder", "co-founder")),
    ("diretor", ("diretor", "diretora", "director", "vp", "vice president", "vice-presidente")),
    ("head", ("head of", "head de")),
    ("tech lead", ("tech lead", "team lead", "lider tecnico", "lider de equipe")),
    ("gerente", ("gerente", "engineering manager", "tech manager", "manager")),
    ("coordenador", ("coordenador", "coordenadora", "coordinator")),
    ("supervisor", ("supervisor", "supervisora")),
    ("arquiteto", ("arquiteto", "arquiteta", "architect", "solutions architect", "software architect")),
    ("staff/principal", ("staff engineer", "principal engineer", "distinguished engineer")),
    ("senior", ("senior", "sr.")),
)

# Verbos de liderança, gestão e responsabilidade estratégica (PT-BR e EN)
_LEADERSHIP_VERB_GROUPS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "lideranca",
        (r"liderou", r"liderei", r"liderando", r"led", r"leading\s+(?:the\s+|a\s+)?(?:team|teams|engineering|project|projects|initiative)"),
        ("lider", "lead", "led", "lideranc"),
    ),
    (
        "coordenacao",
        (r"coordenou", r"coordenei", r"coordenando", r"coordinated", r"coordinating"),
        ("coorden", "coordinat"),
    ),
    (
        "gestao",
        (r"gerenciou", r"gerenciei", r"gerenciando", r"managed", r"managing\s+(?:the\s+|a\s+)?(?:team|teams|people|engineers|developers|department|budget|project)"),
        ("gerenc", "gestor", "gestao", "manag"),
    ),
    (
        "arquitetura_estrategica",
        (r"arquitetou", r"arquitetei", r"arquitetando", r"architected", r"architecting", r"definiu\s+a\s+arquitetura", r"defini\s+a\s+arquitetura"),
        ("arquitet", "architect"),
    ),
    (
        "supervisao",
        (r"supervisionou", r"supervisionei", r"supervisionando", r"supervised", r"supervising", r"oversaw"),
        ("supervis", "oversaw", "oversee"),
    ),
    (
        "fundacao",
        (r"fundou", r"fundei", r"cofundou", r"founded", r"co-founded"),
        ("fund", "found"),
    ),
    (
        "direcao_conducao",
        (r"dirigiu", r"dirigi", r"conduziu", r"conduzi", r"comandou", r"chefiou", r"directed", r"spearheaded", r"headed", r"owned\s+(?:the\s+)?(?:architecture|roadmap|strategy|platform|product|engineering|team)"),
        ("dirig", "diretor", "conduz", "comand", "chef", "direct", "spearhead", "head", "owned", "owner"),
    ),
)

# Afirmações qualitativas exageradas que exigem comprovação explícita no fato (A-04 / 7.8)
_QUALITATIVE_EXAGGERATION_RULES: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    (
        "financial_or_cost_claim",
        re.compile(
            r"\b(?:reduziu\s+custos?|reducao\s+de\s+custos?|economia\s+de\s+custos?|economizou|"
            r"aumentou\s+(?:a\s+)?receita|aumento\s+de\s+receita|gerou\s+receita|aumentou\s+vendas|"
            r"lucratividade|faturamento|reduced?\s+costs?|cost\s+reduction|cost\s+savings?|"
            r"saved\s+costs?|increased?\s+revenue|revenue\s+growth|boosted?\s+sales|profitability)\b"
        ),
        ("custo", "econom", "receita", "venda", "lucr", "fatur", "cost", "sav", "revenue", "sales", "profit", "roi"),
    ),
    (
        "systemic_transformation_or_efficiency_claim",
        re.compile(
            r"\b(?:transformacao\s+sistemica|transformacao\s+digital|eficiencia\s+operacional|"
            r"impacto\s+estrategico|escala\s+global|alta\s+disponibilidade|missao\s+critica|"
            r"revolucionou|reestruturou\s+completamente|otimizou\s+drasticamente|reduziu\s+drasticamente|"
            r"aumentou\s+significativamente|systemic\s+transformation|digital\s+transformation|"
            r"operational\s+efficiency|strategic\s+impact|global\s+scale|high\s+availability|"
            r"mission[- ]critical|enterprise[- ]wide|revolutionized|overhauled|drastically\s+reduced|"
            r"significantly\s+increased)\b"
        ),
        (
            "transformacao",
            "eficiencia",
            "operacional",
            "estrategic",
            "global",
            "disponibilidade",
            "critica",
            "transformation",
            "efficiency",
            "operational",
            "strategic",
            "availability",
            "critical",
        ),
    ),
    (
        "awards_patents_certifications_claim",
        re.compile(
            r"\b(?:premiado|premiacao|premio|patente|patentes|patent|melhor\s+do\s+ano|"
            r"1[oº°]\s+lugar|primeiro\s+lugar|first\s+place|awarded|award\b|"
            r"aws\s+certified|certificado\s+(?:aws|azure|gcp|kubernetes|oracle|sap)|"
            r"certificacao\s+oficial|published\s+paper|publicacao\s+cientifica)\b"
        ),
        ("premio", "premiad", "premiac", "patente", "patent", "award", "lugar", "first place", "certific", "publicac", "paper"),
    ),
)

# Sinais de que o texto faz afirmação de experiência/engenharia técnica (para checagem de relevância A-03 / 6.4)
_TECHNICAL_EXPERIENCE_CLAIM_RE = re.compile(
    r"\b(?:desenvolvedor|desenvolvimento|software|engenharia|engenheiro|programacao|programador|"
    r"experiencia\s+profissional|micros?servicos?|apis?|sistemas?|backend|frontend|fullstack|"
    r"arquitetura|devops|developer|software\s+engineering|engineer|programming|professional\s+experience|"
    r"microservices?|systems?|architecture)\b"
)

# Sinais de que um slot de projeto tenta apresentar o projeto como emprego formal
_FORMAL_EMPLOYMENT_CLAIM_RE = re.compile(
    r"\b(?:emprego\s+formal|contratado\s+clt|regime\s+clt|funcionario\s+da\s+empresa|"
    r"full[- ]time\s+employee\s+at|employed\s+full[- ]time\s+at)\b"
)

# Slots em que a menção ao nome da empresa alvo (opportunity.company_name) como destinatária é aceitável
_OPPORTUNITY_ADDRESSEE_SLOTS = frozenset(
    {
        "target_alignment",
        "opening",
        "opportunity_alignment",
        "closing",
        "subject",
        "body",
        "sign_off",
        "introduction",
        "project_understanding",
        "alignment_points",
    }
)


class GroundingValidationResult(BaseModel):
    """Resultado detalhado da validação estruturada de grounding."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    flagged_items: list[dict[str, Any]] = Field(default_factory=list)
    epistemological_disclaimer: str = (
        "A validação de grounding é estrutural, determinística, heurística e conservadora. "
        "Ela verifica se slots, chaves citadas, tecnologias, empresas, cargos, verbos de liderança, "
        "métricas tipadas e restrições de segurança possuem suporte nos fatos confirmados citados, "
        "mas não constitui um oráculo semântico perfeito. Paráfrases sutis ou distorções de contexto "
        "sem marcadores detectáveis ainda exigem revisão e aprovação humana obrigatória."
    )


def _fact_corpus_text(fact: AuthorizedFactItem) -> str:
    parts = [
        fact.label,
        fact.summary,
        fact.description,
        fact.role_or_title,
        fact.company_or_institution,
        fact.period,
        fact.verified_results,
        fact.proficiency,
        " ".join(fact.technologies),
    ]
    return " ".join(str(p) for p in parts if p)


def _extract_candidate_companies_from_text(
    text: str,
    all_profile_companies: set[str],
    cited_fact_labels: set[str],
    mentioned_techs: set[str],
) -> list[tuple[str, bool]]:
    """Extrai possíveis menções a empresas no texto.

    Retorna lista de tuplas ``(nome_normalizado, is_employer_claim)``.
    """
    norm_text = _normalize_for_search(text)
    found: list[tuple[str, bool]] = []
    seen: set[str] = set()

    # 1. Grandes empresas conhecidas (com word boundary estrito)
    for company_name, rx in _COMPILED_WELL_KNOWN_COMPANIES:
        if rx.search(norm_text):
            # Evita confundir "Amazon Web Services" (tecnologia AWS) se o texto disser literalmente "Amazon Web Services"
            if company_name == "amazon" and re.search(r"(?i)\bamazon\s+web\s+services\b", text):
                continue
            if company_name not in seen:
                seen.add(company_name)
                found.append((company_name, True))

    # 2. Outras empresas existentes no perfil do usuário (ex.: troca de Acme por Beta)
    for comp in all_profile_companies:
        comp_norm = _normalize_for_search(comp).strip()
        if len(comp_norm) < 2:
            continue
        if re.search(rf"(?<![a-z0-9_]){re.escape(comp_norm)}(?![a-z0-9_])", norm_text):
            if comp_norm not in seen:
                seen.add(comp_norm)
                found.append((comp_norm, True))

    # 3. Extração contextual de nomes próprios após preposições de empregador ou sufixo societário
    for rx in (_EMPLOYER_CONTEXT_PT_RE, _EMPLOYER_CONTEXT_EN_RE, _CORPORATE_SUFFIX_RE):
        for m in rx.finditer(text):
            raw_cand = m.group(1).strip(" .,;:")
            cand_norm = _normalize_for_search(raw_cand)
            if not cand_norm or len(cand_norm) < 2:
                continue
            if cand_norm in _NON_COMPANY_PROPER_WORDS:
                continue
            # Ignora nomes que são tecnologias puras (ex.: "em Python", "with FastAPI", "no PostgreSQL")
            cand_techs = extract_mentioned_technologies(raw_cand)
            if cand_techs and canonicalize_tech_name(raw_cand) in cand_techs:
                continue
            # Ignora nomes que correspondem exatamente ao nome de um projeto citado
            if cand_norm in cited_fact_labels:
                continue
            # Ignora se todos os tokens forem palavras técnicas/comuns
            tokens = cand_norm.split()
            if all(t in _NON_COMPANY_PROPER_WORDS or t in mentioned_techs for t in tokens):
                continue
            if cand_norm not in seen:
                seen.add(cand_norm)
                found.append((cand_norm, True))

    return found


class StructuredGroundingValidator:
    """Validador rigoroso e conservador de grounding para sugestões geradas por IA.

    Princípios:
    - Separação absoluta de origem: requisitos da vaga (`context.opportunity`) NUNCA autorizam
      competências técnicas do candidato.
    - Allowlist estrita de slots por `material_type`, sem duplicidades e com vínculo exato de entidade.
    - All-or-Nothing: qualquer falha em qualquer sugestão invalida todo o lote.
    - Grounding numérico por categoria e associação semântica (nunca derivando evidência da própria sugestão).
    - Validação de empresas, cargos, verbos de liderança e afirmações qualitativas exageradas.
    - Proibição de URLs/domínios, links Markdown (inclusive multilinha), e-mails comuns/ofuscados,
      telefones (BR e internacionais), HTML, SVG e conteúdo ativo.
    """

    def validate(
        self,
        context: AuthorizedAIContext,
        output: AIMaterialEnhanceOutput,
    ) -> GroundingValidationResult:
        rejection_reasons: list[str] = []
        flagged_items: list[dict[str, Any]] = []

        # 1. Correspondência estrita de material_type e target_language
        if output.material_type != context.material_type:
            reason = (
                f"Tipo de material do output ('{output.material_type}') "
                f"diverge do contexto autorizado ('{context.material_type}')."
            )
            rejection_reasons.append(reason)
            return GroundingValidationResult(
                is_valid=False,
                rejection_reasons=rejection_reasons,
                flagged_items=[{"error": "material_type_mismatch", "detail": reason}],
            )

        if output.target_language != context.target_language:
            reason = (
                f"Idioma do output ('{output.target_language}') "
                f"diverge do contexto autorizado ('{context.target_language}')."
            )
            rejection_reasons.append(reason)
            return GroundingValidationResult(
                is_valid=False,
                rejection_reasons=rejection_reasons,
                flagged_items=[{"error": "language_mismatch", "detail": reason}],
            )

        all_authorized_keys = context.all_fact_keys()
        all_profile_companies = context.all_confirmed_companies()
        opp_company_norm = (
            _normalize_for_search(context.opportunity.company_name).strip()
            if context.opportunity and context.opportunity.company_name
            else None
        )

        seen_slots: set[str] = set()

        for idx, item in enumerate(output.suggestions):
            item_flags: list[str] = []

            # 2.1 Validação de slot contra allowlist + unicidade (defesa em profundidade)
            parsed_slot: ParsedSlotTarget | None = None
            try:
                parsed_slot = parse_and_validate_slot_for_material(
                    context.material_type,
                    item.slot_id,
                )
            except ValueError as exc:
                item_flags.append(f"invalid_slot: {exc}")

            if item.slot_id in seen_slots:
                item_flags.append(
                    f"duplicate_slot: Slot '{item.slot_id}' aparece duplicado no lote."
                )
            seen_slots.add(item.slot_id)

            # 2.2 Verificação de chaves citadas no contexto autorizado do usuário
            if not item.cited_fact_keys:
                item_flags.append("cited_fact_keys_empty: Sugestão não cita nenhuma chave de fato.")

            cited_facts: list[AuthorizedFactItem] = []
            for key in item.cited_fact_keys:
                if key not in all_authorized_keys:
                    item_flags.append(
                        f"unauthorized_fact_key: Chave '{key}' não existe no contexto autorizado do usuário."
                    )
                else:
                    fact = context.get_fact(key)
                    if fact is not None:
                        cited_facts.append(fact)

            # 2.3 Vínculo estrito entre slot, entidade alvo e citações (A-03 / 6.3 e 6.4)
            if parsed_slot is not None and parsed_slot.slot_kind == "entity_bound":
                req_key = parsed_slot.required_fact_key
                if req_key not in item.cited_fact_keys:
                    item_flags.append(
                        f"entity_binding_mismatch: Slot '{item.slot_id}' exige citação exata da entidade '{req_key}'."
                    )
                # Proíbe mistura ontológica ou contrabando de fatos de outras entidades no slot específico
                for cited in cited_facts:
                    if cited.fact_key != req_key:
                        item_flags.append(
                            f"cross_entity_citation: Slot específico '{item.slot_id}' não pode citar "
                            f"entidade divergente '{cited.fact_key}'."
                        )

            text = item.suggested_text
            text_norm = _normalize_for_search(text)

            # 2.4 Proibição de mistura projeto -> emprego formal
            if parsed_slot is not None and parsed_slot.target_entity_type == "project":
                if _FORMAL_EMPLOYMENT_CLAIM_RE.search(text_norm):
                    item_flags.append(
                        "ontological_mismatch: Slot de projeto não pode apresentar projeto como emprego formal."
                    )

            # 2.5 Segurança de saída: URLs/domínios, Markdown multilinha, e-mails, telefones, HTML/ativo (M-05)
            if find_markdown_links(text) or find_urls_or_domains(text):
                item_flags.append(
                    "forbidden_link: Texto contém URL, domínio ou link Markdown não autorizado."
                )
            if find_emails(text):
                item_flags.append(
                    "forbidden_contact: Texto contém endereço de e-mail (direto ou ofuscado)."
                )
            if find_phones(text):
                item_flags.append(
                    "forbidden_contact: Texto contém número de telefone."
                )
            if find_active_or_html_content(text):
                item_flags.append(
                    "forbidden_html_script: Texto contém HTML, SVG, atributo de evento ou esquema ativo."
                )

            # Se não há fatos citados válidos, registra erro e segue para próximo item
            if not cited_facts:
                if item_flags:
                    rejection_reasons.extend([f"[{item.slot_id}] {f}" for f in item_flags])
                    flagged_items.append(
                        {"slot_id": item.slot_id, "suggestion_index": idx, "flags": item_flags}
                    )
                continue

            # 2.6 Relevância das citações para o conteúdo afirmado (A-03 / 6.4)
            cited_entity_types = {f.entity_type for f in cited_facts}
            mentioned_techs = extract_mentioned_technologies(text)

            if cited_entity_types <= {"language"}:
                if mentioned_techs or _TECHNICAL_EXPERIENCE_CLAIM_RE.search(text_norm):
                    item_flags.append(
                        "irrelevant_citation: Fatos apenas de idioma não fundamentam afirmações de "
                        "experiência técnica ou desenvolvimento de software."
                    )
            elif cited_entity_types <= {"language", "education"}:
                if re.search(
                    r"\b(?:experiencia\s+profissional|trabalhou\s+como|trabalhei\s+como|"
                    r"atuou\s+como|atuei\s+como|professional\s+experience|worked\s+as)\b",
                    text_norm,
                ):
                    item_flags.append(
                        "irrelevant_citation: Fatos apenas de formação/idioma não fundamentam "
                        "afirmações de experiência profissional formal."
                    )

            # Construção do corpus exclusivamente dos fatos citados (SEM requisitos da oportunidade!)
            # Em slots entity_bound, restringe estritamente ao fato alvo da entidade (evita vazamento cross-entity)
            if parsed_slot is not None and parsed_slot.slot_kind == "entity_bound":
                evidence_facts = [
                    f for f in cited_facts if f.fact_key == parsed_slot.required_fact_key
                ]
            else:
                evidence_facts = list(cited_facts)

            corpus_raw = " ".join(_fact_corpus_text(f) for f in evidence_facts)
            corpus_norm = _normalize_for_search(corpus_raw)

            # 2.7 Validação de tecnologias: APENAS fatos confirmados citados (NUNCA context.opportunity!) (A-01, A-04, M-04)
            allowed_techs_from_cited: set[str] = set()
            for f in evidence_facts:
                allowed_techs_from_cited.update(_extract_fact_technologies(f))

            for tech in sorted(mentioned_techs):
                if tech not in allowed_techs_from_cited:
                    item_flags.append(
                        f"unconfirmed_technology: Tecnologia '{tech}' não está fundamentada "
                        f"nos fatos confirmados citados para o slot '{item.slot_id}'."
                    )

            # 2.8 Grounding numérico categorizado e com associação semântica (A-04 / 7.1–7.4)
            # NUNCA deriva evidência do próprio suggested_text!
            evidence_quant_claims = extract_quantitative_claims(corpus_raw)
            suggested_quant_claims = extract_quantitative_claims(text)

            for claim in suggested_quant_claims:
                if not _claim_supported_by_evidence(claim, evidence_quant_claims):
                    flag_code = {
                        "percentage": "ungrounded_metric",
                        "currency": "ungrounded_currency",
                        "duration": "ungrounded_duration",
                        "year": "ungrounded_year",
                        "tech_version": "ungrounded_tech_version",
                        "vague_scale": "ungrounded_scale",
                        "entity_count": "ungrounded_quantity_context",
                        "raw_number": "ungrounded_number",
                    }.get(claim.category, "ungrounded_number")
                    item_flags.append(
                        f"{flag_code}: Afirmação quantitativa '{claim.raw_text}' "
                        f"(categoria={claim.category}, qualificador={claim.qualifier}) "
                        f"não fundamentada na mesma categoria nos fatos citados."
                    )

            # 2.9 Validação de empresas (A-04 / 7.6)
            cited_companies_norm = {
                _normalize_for_search(f.company_or_institution).strip()
                for f in evidence_facts
                if f.company_or_institution
            }
            cited_labels_norm = {
                _normalize_for_search(f.label).strip()
                for f in evidence_facts
                if f.label
            }
            candidate_companies = _extract_candidate_companies_from_text(
                text,
                all_profile_companies,
                cited_labels_norm,
                mentioned_techs,
            )
            for comp_norm, _is_employer in candidate_companies:
                # Verifica correspondência exata ou por token completo com empresas dos fatos citados
                in_cited_company = any(
                    comp_norm == cc
                    or re.search(rf"(?<![a-z0-9_]){re.escape(comp_norm)}(?![a-z0-9_])", cc)
                    or re.search(rf"(?<![a-z0-9_]){re.escape(cc)}(?![a-z0-9_])", comp_norm)
                    for cc in cited_companies_norm
                    if cc
                )
                if in_cited_company:
                    continue
                # Em slots que se dirigem à vaga alvo, permite mencionar a empresa da vaga
                # APENAS quando não há verbo de emprego passado ("trabalhou na", "worked at")
                if (
                    opp_company_norm
                    and comp_norm == opp_company_norm
                    and parsed_slot is not None
                    and parsed_slot.slot_id in _OPPORTUNITY_ADDRESSEE_SLOTS
                    and not re.search(
                        rf"(?i)\b(?:trabalhou|trabalhei|atuou|atuei|worked|employed|experiencia\s+na|experience\s+at)\b[^.;\n]{{0,60}}\b(?:na|no|at|for)\s+{re.escape(comp_norm)}\b",
                        text_norm,
                    )
                ):
                    continue
                item_flags.append(
                    f"unconfirmed_company: Empresa/organização '{comp_norm}' não fundamentada "
                    f"nos fatos citados para o slot '{item.slot_id}'."
                )

            # 2.10 Cargos, senioridade e responsabilidade / liderança (A-04 / 7.7)
            for role_group, role_terms in _SENIORITY_AND_ROLE_TITLES:
                matched_term = next(
                    (
                        term
                        for term in role_terms
                        if re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text_norm)
                    ),
                    None,
                )
                if matched_term is not None:
                    has_evidence = any(
                        re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", corpus_norm)
                        for term in role_terms
                    )
                    if not has_evidence:
                        item_flags.append(
                            f"unsubstantiated_role_promotion: Cargo/senioridade '{matched_term}' "
                            f"({role_group}) atribuído sem comprovação nos fatos citados."
                        )

            # Promoção implícita de Júnior/Estagiário para Pleno/Mid-level
            if re.search(r"\b(?:pleno|mid[- ]level)\b", text_norm):
                if not re.search(r"\b(?:pleno|mid[- ]level|senior)\b", corpus_norm):
                    # Em slots voltados à vaga alvo, permite "vaga de Pleno" mas não "como Pleno / Desenvolvedor Pleno"
                    if not re.search(r"\b(?:vaga|oportunidade|posicao|role|position)\s+(?:de\s+|for\s+)?(?:[\w\s]{0,25})?(?:pleno|mid[- ]level)\b", text_norm):
                        item_flags.append(
                            "unsubstantiated_role_promotion: Senioridade 'pleno/mid-level' "
                            "atribuída sem confirmação nos fatos citados."
                        )

            for verb_group, verb_patterns, evidence_roots in _LEADERSHIP_VERB_GROUPS:
                matched_verb = next(
                    (
                        m.group(0)
                        for pat in verb_patterns
                        if (m := re.search(rf"\b{pat}\b", text_norm)) is not None
                    ),
                    None,
                )
                if matched_verb is not None:
                    has_root_evidence = any(
                        re.search(rf"\b{re.escape(root)}", corpus_norm)
                        for root in evidence_roots
                    )
                    if not has_root_evidence:
                        item_flags.append(
                            f"unsubstantiated_leadership_claim: Verbo/responsabilidade '{matched_verb}' "
                            f"({verb_group}) não comprovado nos fatos citados."
                        )

            # 2.11 Afirmações qualitativas exageradas (A-04 / 7.8)
            for claim_code, claim_re, required_roots in _QUALITATIVE_EXAGGERATION_RULES:
                m = claim_re.search(text_norm)
                if m is not None:
                    has_root = any(
                        re.search(rf"\b{re.escape(root)}", corpus_norm)
                        for root in required_roots
                    )
                    if not has_root:
                        item_flags.append(
                            f"unsubstantiated_claim: Afirmação qualitativa '{m.group(0)}' "
                            f"({claim_code}) sem evidência equivalente nos fatos citados."
                        )

            if item_flags:
                rejection_reasons.extend([f"[{item.slot_id}] {flag}" for flag in item_flags])
                flagged_items.append(
                    {
                        "slot_id": item.slot_id,
                        "suggestion_index": idx,
                        "flags": item_flags,
                    }
                )

        is_valid = len(rejection_reasons) == 0 and len(flagged_items) == 0
        return GroundingValidationResult(
            is_valid=is_valid,
            rejection_reasons=rejection_reasons,
            flagged_items=flagged_items,
        )
