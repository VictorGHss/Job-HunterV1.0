"""
Normalização semântica determinística de tecnologias e preservação de proveniência
por provedor (DX-03.2.1).

Princípio central:
- Nunca destruir nem sobrescrever a taxonomia original do provedor; preservá-la
  integralmente em metadados próprios da fonte (`OpportunitySourceLink.raw_metadata`
  e `Opportunity.raw_metadata` da fonte primária).
- Popular `Opportunity.technologies` exclusivamente com tecnologias técnicas reais
  (ou competências técnicas curadas no contexto de repositórios GitHub BR), evitando
  cargos, setores econômicos, senioridade, modalidades, lifestyle e labels administrativas.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable, Mapping

from app.services.opportunities.sanitization import sanitize_plain_text

_COMBINING_MARKS_RE = re.compile(r"[\u0300-\u036f]")
_MULTI_SPACE_RE = re.compile(r"\s+")

# Prefixos/padrões que indicam labels puramente operacionais/financeiras no GitHub BR
_SALARY_LABEL_RE = re.compile(r"(?i)^(?:r\$\s*\d|usd\s*\d|\$\s*\d|\d+\s*k\b)")
_NON_TECH_ROLE_TITLE_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:"
    r"go[- ]to[- ]market|human\s+resources|recruiter|recruiting|marketing|"
    r"sales|business\s+development|customer\s+support|customer\s+service|"
    r"account\s+executive|account\s+director|copywriter|content\s+writer|"
    r"video\s+editor|graphic\s+designer|nurse|biologist|counselor|teacher|tutor"
    r")(?![a-z0-9])"
)
_TECH_TITLE_CONTEXT_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:"
    r"developer|engineer|programmer|desenvolvedor|programador|engenheiro|"
    r"backend|back[- ]?end|frontend|front[- ]?end|full[- ]?stack|devops|sre|"
    r"software|platform|infrastructure|systems|cloud|data\s+engineer|architect"
    r")(?![a-z0-9])"
)


def _fold_key(value: str) -> str:
    """Chave de lookup normalizada (lowercase, sem acentos, espaços simples)."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_folded = _COMBINING_MARKS_RE.sub("", decomposed).lower()
    return _MULTI_SPACE_RE.sub(" ", ascii_folded).strip()


def preserve_raw_string_list(
    raw_items: Iterable[Any] | None,
    *,
    max_items: int = 200,
    max_length: int = 120,
) -> list[str]:
    """
    Preserva integralmente uma lista de strings brutas da fonte sem alterar
    capitalização, sem substituir hífens e sem reordenar, apenas removendo
    HTML/caracteres de controle e entradas vazias.
    """
    if not raw_items:
        return []
    preserved: list[str] = []
    for raw in raw_items:
        if raw is None or isinstance(raw, bool):
            continue
        cleaned = sanitize_plain_text(str(raw), max_length=max_length)
        if not cleaned:
            continue
        preserved.append(cleaned)
        if len(preserved) >= max_items:
            break
    return preserved


def preserve_raw_industry(raw_value: Any) -> list[str] | str | None:
    """
    Preserva o valor original de `jobIndustry` (Jobicy) mantendo sua estrutura
    original (`list[str]` quando lista, `str` quando string, `None` quando ausente).
    """
    if raw_value is None or isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, list):
        return preserve_raw_string_list(raw_value)
    if isinstance(raw_value, str):
        return sanitize_plain_text(raw_value, max_length=200)
    return sanitize_plain_text(str(raw_value), max_length=200)


# ==============================================================================
# Catálogo canônico de tecnologias reais (linguagens, frameworks, bancos,
# cloud, DevOps/infra, dados/ML, mobile, QA e plataformas/produtos técnicos).
# ==============================================================================

_CANONICAL_TECH_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Linguagens de programação
    ("Python", ("python", "python3", "python 3", "py")),
    ("JavaScript", ("javascript", "js", "ecmascript", "es6", "es2015")),
    ("TypeScript", ("typescript", "ts")),
    ("Java", ("java",)),
    ("C#", ("c#", "csharp", "c-sharp", "c sharp")),
    ("C++", ("c++", "cpp", "c plus plus")),
    ("Go", ("golang",)),
    ("Rust", ("rust", "rustlang")),
    ("Ruby", ("ruby",)),
    ("PHP", ("php", "php8", "php 8")),
    ("Swift", ("swift",)),
    ("Kotlin", ("kotlin",)),
    ("Scala", ("scala",)),
    ("Elixir", ("elixir",)),
    ("Erlang", ("erlang",)),
    ("Clojure", ("clojure", "clojurescript")),
    ("Haskell", ("haskell",)),
    ("Dart", ("dart",)),
    ("Objective-C", ("objective-c", "objective c", "objc")),
    ("Perl", ("perl",)),
    ("Lua", ("lua",)),
    ("Bash", ("bash",)),
    ("Shell", ("shell", "shell script", "shell scripting", "sh")),
    ("PowerShell", ("powershell",)),
    ("Solidity", ("solidity",)),
    ("Zig", ("zig",)),
    ("OCaml", ("ocaml",)),
    ("F#", ("f#", "fsharp", "f-sharp")),
    ("Groovy", ("groovy",)),
    ("Julia", ("julia",)),
    ("Nim", ("nim",)),
    ("Crystal", ("crystal",)),
    ("COBOL", ("cobol",)),
    ("Fortran", ("fortran",)),
    ("Assembly", ("assembly", "asm")),
    ("VHDL", ("vhdl",)),
    ("Verilog", ("verilog", "systemverilog")),
    ("MATLAB", ("matlab",)),
    ("Delphi", ("delphi",)),
    ("ABAP", ("abap",)),
    ("AdvPL", ("advpl",)),
    ("Apex", ("apex",)),
    ("R", ("r language", "rstats", "r programming", "linguagem r")),
    ("RStudio", ("rstudio", "r studio")),
    ("C", ("c language", "linguagem c", "ansi c")),
    ("SQL", ("sql",)),
    ("PL/SQL", ("pl/sql", "plsql", "pl-sql")),
    ("T-SQL", ("t-sql", "tsql")),
    ("HTML", ("html", "html5")),
    ("CSS", ("css", "css3")),
    # Ecossistema .NET
    (".NET", (".net", "dotnet", "dot net", ".net core", "dotnet core", ".net framework")),
    ("ASP.NET", ("asp.net", "aspnet", "asp .net")),
    ("ASP.NET Core", ("asp.net core", "aspnet core")),
    ("Entity Framework", ("entity framework", "ef core", "entity framework core")),
    ("Blazor", ("blazor",)),
    # Frameworks e bibliotecas Frontend / Mobile
    ("React", ("react", "reactjs", "react.js", "react js")),
    ("React Native", ("react native", "react-native", "reactnative")),
    ("Next.js", ("next.js", "nextjs", "next js")),
    ("Vue", ("vue", "vuejs", "vue.js", "vue js", "vue3", "vue 3")),
    ("Nuxt.js", ("nuxt", "nuxtjs", "nuxt.js", "nuxt js")),
    ("Angular", ("angular", "angularjs", "angular.js")),
    ("Svelte", ("svelte",)),
    ("SvelteKit", ("sveltekit", "svelte kit")),
    ("Astro", ("astro",)),
    ("Remix", ("remix", "remix.run")),
    ("Gatsby", ("gatsby", "gatsbyjs")),
    ("Ember.js", ("ember", "ember.js", "emberjs")),
    ("SolidJS", ("solidjs", "solid.js")),
    ("jQuery", ("jquery",)),
    ("Redux", ("redux", "redux toolkit")),
    ("Tailwind CSS", ("tailwind", "tailwindcss", "tailwind css")),
    ("Bootstrap", ("bootstrap",)),
    ("Sass", ("sass", "scss")),
    ("Styled Components", ("styled-components", "styled components")),
    ("Material UI", ("material ui", "material-ui", "mui")),
    ("Vite", ("vite", "vitejs")),
    ("Webpack", ("webpack",)),
    ("Electron", ("electron", "electronjs")),
    ("Flutter", ("flutter",)),
    ("Ionic", ("ionic",)),
    ("Xamarin", ("xamarin",)),
    ("SwiftUI", ("swiftui",)),
    ("Jetpack Compose", ("jetpack compose",)),
    ("Android", ("android", "android sdk")),
    ("iOS", ("ios",)),
    ("WebAssembly", ("webassembly", "wasm")),
    ("Three.js", ("three.js", "threejs")),
    ("D3.js", ("d3", "d3.js", "d3js")),
    ("Storybook", ("storybook",)),
    # Frameworks Backend / Runtime
    ("Node.js", ("node.js", "nodejs", "node js", "node")),
    ("Deno", ("deno",)),
    ("Bun", ("bun",)),
    ("Express", ("express", "expressjs", "express.js")),
    ("NestJS", ("nestjs", "nest.js", "nest js")),
    ("Fastify", ("fastify",)),
    ("AdonisJS", ("adonis", "adonisjs", "adonis.js")),
    ("FastAPI", ("fastapi", "fast api")),
    ("Django", ("django", "django rest framework", "drf")),
    ("Flask", ("flask",)),
    ("Celery", ("celery",)),
    ("SQLAlchemy", ("sqlalchemy",)),
    ("Pydantic", ("pydantic",)),
    ("Spring", ("spring", "spring framework")),
    ("Spring Boot", ("spring boot", "springboot", "spring-boot")),
    ("Hibernate", ("hibernate",)),
    ("Quarkus", ("quarkus",)),
    ("Micronaut", ("micronaut",)),
    ("Laravel", ("laravel",)),
    ("Symfony", ("symfony",)),
    ("CodeIgniter", ("codeigniter",)),
    ("Ruby on Rails", ("ruby on rails", "rails", "ror")),
    ("Phoenix", ("phoenix", "phoenix framework")),
    ("Gin", ("gin", "gin-gonic")),
    ("Fiber", ("gofiber",)),
    ("Actix", ("actix", "actix-web")),
    ("Tokio", ("tokio",)),
    ("Prisma", ("prisma", "prisma orm")),
    ("Drizzle", ("drizzle", "drizzle orm")),
    ("TypeORM", ("typeorm",)),
    ("Sequelize", ("sequelize",)),
    ("Mongoose", ("mongoose",)),
    ("GraphQL", ("graphql", "apollo graphql")),
    ("gRPC", ("grpc",)),
    ("tRPC", ("trpc",)),
    ("WebSockets", ("websocket", "websockets")),
    ("OpenAPI", ("openapi", "swagger")),
    # Bancos de dados e armazenamento
    ("PostgreSQL", ("postgresql", "postgres", "psql", "pg")),
    ("MySQL", ("mysql",)),
    ("MariaDB", ("mariadb",)),
    ("SQLite", ("sqlite", "sqlite3")),
    ("Oracle", ("oracle", "oracle db", "oracle database")),
    ("SQL Server", ("sql server", "mssql", "ms sql", "microsoft sql server")),
    ("MongoDB", ("mongodb", "mongo")),
    ("Redis", ("redis",)),
    ("Elasticsearch", ("elasticsearch", "elastic search")),
    ("OpenSearch", ("opensearch",)),
    ("Cassandra", ("cassandra", "apache cassandra")),
    ("DynamoDB", ("dynamodb", "aws dynamodb")),
    ("Firebase", ("firebase",)),
    ("Firestore", ("firestore",)),
    ("Supabase", ("supabase",)),
    ("Neo4j", ("neo4j",)),
    ("ClickHouse", ("clickhouse",)),
    ("Snowflake", ("snowflake",)),
    ("BigQuery", ("bigquery", "google bigquery")),
    ("Redshift", ("redshift", "aws redshift")),
    ("Databricks", ("databricks",)),
    ("DuckDB", ("duckdb",)),
    ("InfluxDB", ("influxdb",)),
    ("CockroachDB", ("cockroachdb",)),
    ("Couchbase", ("couchbase",)),
    ("Memcached", ("memcached",)),
    ("MinIO", ("minio",)),
    ("Hasura", ("hasura",)),
    # Mensageria, Streaming e Dados / ML
    ("Kafka", ("kafka", "apache kafka")),
    ("RabbitMQ", ("rabbitmq", "rabbit mq")),
    ("NATS", ("nats",)),
    ("ActiveMQ", ("activemq",)),
    ("Spark", ("spark", "apache spark", "pyspark")),
    ("Airflow", ("airflow", "apache airflow")),
    ("dbt", ("dbt",)),
    ("Flink", ("flink", "apache flink")),
    ("Hadoop", ("hadoop",)),
    ("Pandas", ("pandas",)),
    ("NumPy", ("numpy",)),
    ("SciPy", ("scipy",)),
    ("Scikit-learn", ("scikit-learn", "sklearn", "scikit learn")),
    ("PyTorch", ("pytorch",)),
    ("TensorFlow", ("tensorflow",)),
    ("Keras", ("keras",)),
    ("LangChain", ("langchain",)),
    ("Hugging Face", ("hugging face", "huggingface")),
    ("OpenCV", ("opencv",)),
    ("vLLM", ("vllm",)),
    ("CUDA", ("cuda",)),
    ("OpenAI", ("openai", "openai api")),
    ("Anthropic", ("anthropic", "claude api")),
    ("Power BI", ("power bi", "powerbi", "power-bi")),
    ("Tableau", ("tableau",)),
    ("Looker", ("looker",)),
    ("Metabase", ("metabase",)),
    # Cloud, Containers, DevOps e Infraestrutura
    ("AWS", ("aws", "amazon web services")),
    ("GCP", ("gcp", "google cloud", "google cloud platform")),
    ("Azure", ("azure", "microsoft azure")),
    ("Cloudflare", ("cloudflare", "cloudflare workers")),
    ("DigitalOcean", ("digitalocean", "digital ocean")),
    ("Heroku", ("heroku",)),
    ("Vercel", ("vercel",)),
    ("Netlify", ("netlify",)),
    ("Docker", ("docker", "docker compose", "docker-compose")),
    ("Kubernetes", ("kubernetes", "k8s")),
    ("Helm", ("helm",)),
    ("Terraform", ("terraform",)),
    ("OpenTofu", ("opentofu",)),
    ("Ansible", ("ansible",)),
    ("Pulumi", ("pulumi",)),
    ("Packer", ("packer",)),
    ("Vagrant", ("vagrant",)),
    ("CloudFormation", ("cloudformation", "aws cloudformation")),
    ("AWS Lambda", ("aws lambda",)),
    ("ECS", ("aws ecs",)),
    ("EKS", ("aws eks", "eks")),
    ("Jenkins", ("jenkins",)),
    ("GitHub Actions", ("github actions",)),
    ("GitLab CI", ("gitlab ci", "gitlab-ci")),
    ("CircleCI", ("circleci",)),
    ("ArgoCD", ("argocd", "argo cd")),
    ("Prometheus", ("prometheus",)),
    ("Grafana", ("grafana",)),
    ("Datadog", ("datadog",)),
    ("New Relic", ("new relic", "newrelic")),
    ("Sentry", ("sentry",)),
    ("Splunk", ("splunk",)),
    ("ELK", ("elk", "elk stack")),
    ("Logstash", ("logstash",)),
    ("Kibana", ("kibana",)),
    ("OpenTelemetry", ("opentelemetry", "otel")),
    ("Nginx", ("nginx",)),
    ("Apache", ("apache", "apache http")),
    ("HAProxy", ("haproxy",)),
    ("Envoy", ("envoy",)),
    ("Istio", ("istio",)),
    ("Linux", ("linux",)),
    ("Unix", ("unix",)),
    ("Ubuntu", ("ubuntu",)),
    ("Debian", ("debian",)),
    ("Git", ("git",)),
    ("GitHub", ("github",)),
    ("GitLab", ("gitlab",)),
    ("Bitbucket", ("bitbucket",)),
    ("CI/CD", ("ci/cd", "ci cd", "cicd")),
    ("Vault", ("hashicorp vault",)),
    ("Consul", ("consul",)),
    ("HashiCorp Nomad", ("hashicorp nomad",)),
    ("OAuth", ("oauth", "oauth2", "oauth 2.0", "oidc")),
    # Testes e QA técnicos
    ("Playwright", ("playwright",)),
    ("Cypress", ("cypress",)),
    ("Selenium", ("selenium",)),
    ("Jest", ("jest",)),
    ("Vitest", ("vitest",)),
    ("Pytest", ("pytest",)),
    ("JUnit", ("junit",)),
    ("Appium", ("appium",)),
    ("Postman", ("postman",)),
    ("k6", ("k6",)),
    # Plataformas, engines e produtos técnicos
    ("Salesforce", ("salesforce", "sfdc")),
    ("SAP", ("sap", "sap hana", "s/4hana")),
    ("ServiceNow", ("servicenow",)),
    ("Workday", ("workday",)),
    ("Shopify", ("shopify",)),
    ("WordPress", ("wordpress",)),
    ("Drupal", ("drupal",)),
    ("Magento", ("magento",)),
    ("Strapi", ("strapi",)),
    ("Contentful", ("contentful",)),
    ("Stripe", ("stripe",)),
    ("Twilio", ("twilio",)),
    ("HubSpot", ("hubspot",)),
    ("Zendesk", ("zendesk",)),
    ("Jira", ("jira",)),
    ("Confluence", ("confluence",)),
    ("Figma", ("figma",)),
    ("Unity", ("unity", "unity3d")),
    ("Unreal Engine", ("unreal", "unreal engine")),
    ("Ethereum", ("ethereum",)),
    ("Web3", ("web3", "web3.js")),
    ("Protheus", ("protheus",)),
)

# Competências técnicas legítimas curadas (preservadas no contexto GitHub BR)
_CURATED_COMPETENCY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("DDD", ("ddd", "domain driven design", "domain-driven design")),
    ("SOLID", ("solid",)),
    ("Clean Architecture", ("clean architecture", "arquitetura limpa")),
    ("Clean Code", ("clean code", "codigo limpo")),
    ("TDD", ("tdd", "test driven development", "test-driven development")),
    ("BDD", ("bdd", "behavior driven development")),
    ("CQRS", ("cqrs",)),
    ("Testes automatizados", ("testes automatizados", "automated testing", "testes unitarios")),
    ("Microsserviços", ("microsservicos", "microservices", "microservicos")),
    ("Arquitetura Hexagonal", ("arquitetura hexagonal", "hexagonal architecture")),
    ("Design Patterns", ("design patterns", "padroes de projeto")),
    ("APIs REST", ("apis rest", "api rest", "rest api", "restful", "apis restful", "rest")),
    ("DevSecOps", ("devsecops",)),
    ("Observabilidade", ("observabilidade", "observability")),
    ("Mensageria", ("mensageria", "message broker")),
)

CANONICAL_TECH_ALIASES: dict[str, str] = {}
for _canonical, _aliases in _CANONICAL_TECH_GROUPS:
    CANONICAL_TECH_ALIASES[_fold_key(_canonical)] = _canonical
    for _alias in _aliases:
        CANONICAL_TECH_ALIASES[_fold_key(_alias)] = _canonical

CURATED_COMPETENCY_ALIASES: dict[str, str] = {}
for _canonical, _aliases in _CURATED_COMPETENCY_GROUPS:
    CURATED_COMPETENCY_ALIASES[_fold_key(_canonical)] = _canonical
    for _alias in _aliases:
        CURATED_COMPETENCY_ALIASES[_fold_key(_alias)] = _canonical

# Termos ambíguos curtos que exigem tratamento conservador explícito
AMBIGUOUS_SHORT_TOKENS: frozenset[str] = frozenset({"c", "r", "go", "ai"})

# Categorias, cargos, setores, senioridades, modalidades, lifestyle, vínculos e funções
# evidentemente não tecnológicas — sempre rejeitadas de `Opportunity.technologies`.
NON_TECH_EXCLUSION_TOKENS: frozenset[str] = frozenset(
    {
        # Senioridade / carreira
        "intern",
        "internship",
        "estagio",
        "estagiario",
        "estagiaria",
        "trainee",
        "entry",
        "entry level",
        "entry-level",
        "entry_level",
        "junior",
        "jr",
        "mid",
        "mid level",
        "mid-level",
        "mid-senior",
        "pleno",
        "intermediate",
        "senior",
        "sr",
        "staff",
        "principal",
        "lead",
        "tech lead",
        "team lead",
        "especialista",
        "specialist",
        "exec",
        "executive",
        "c-level",
        "director",
        "vp",
        "head",
        "manager",
        "graduate",
        "new grad",
        "fresher",
        "apprentice",
        "apprenticeship",
        "working student",
        "student",
        # Modalidade / localização / lifestyle
        "remote",
        "remoto",
        "remote work",
        "fully remote",
        "100% remote",
        "hybrid",
        "hibrido",
        "onsite",
        "on-site",
        "on site",
        "presencial",
        "alocado",
        "home office",
        "telecommute",
        "worldwide",
        "anywhere",
        "global",
        "international",
        "exterior",
        "latam",
        "emea",
        "apac",
        "europe",
        "usa",
        "us",
        "uk",
        "canada",
        "brasil",
        "brazil",
        "sp",
        "rj",
        "mg",
        "rs",
        "pr",
        "sc",
        "ba",
        "df",
        "sao paulo",
        "rio de janeiro",
        "belo horizonte",
        "curitiba",
        "porto alegre",
        "digital nomad",
        "nomad",
        "nomadic",
        "work from anywhere",
        "travel",
        "async",
        "asynchronous",
        "flexible",
        "distributed",
        "timezone",
        "visa sponsorship",
        "relocation",
        "equity",
        "english",
        "spanish",
        "portuguese",
        "german",
        "french",
        "bilingual",
        "multilingual",
        # Vínculos / contratos
        "full time",
        "full-time",
        "fulltime",
        "part time",
        "part-time",
        "parttime",
        "tempo integral",
        "meio periodo",
        "contract",
        "contractor",
        "freelance",
        "freelancer",
        "freela",
        "pj",
        "clt",
        "contrato",
        "temporary",
        "temporario",
        "fixed term",
        "fixed-term",
        "permanent",
        "b2b",
        "w2",
        "w-2",
        "1099",
        "hourly",
        "salaried",
        "paid",
        "unpaid",
        "volunteer",
        # Cargos / papéis
        "software engineer",
        "backend engineer",
        "back-end engineer",
        "frontend engineer",
        "front-end engineer",
        "fullstack engineer",
        "full stack engineer",
        "full-stack engineer",
        "software developer",
        "backend developer",
        "frontend developer",
        "fullstack developer",
        "web developer",
        "web dev",
        "dev",
        "developer",
        "engineer",
        "engineering",
        "programmer",
        "coder",
        "architect",
        "data engineer",
        "data analyst",
        "data scientist",
        "data entry",
        "data entry clerk",
        "administrative assistant",
        "virtual assistant",
        "executive assistant",
        "assistant",
        "customer support",
        "customer service",
        "customer success",
        "technical support",
        "tech support",
        "support",
        "support specialist",
        "recruiter",
        "recruiting",
        "talent acquisition",
        "account executive",
        "account manager",
        "project manager",
        "product manager",
        "program manager",
        "engineering manager",
        "founder",
        "cto",
        "ceo",
        "cfo",
        "coo",
        "designer",
        "ui designer",
        "ux designer",
        "graphic designer",
        "product designer",
        "copywriter",
        "writer",
        "content writer",
        "editor",
        "video editor",
        "analyst",
        "consultant",
        "coordinator",
        "administrator",
        "sys admin",
        "sysadmin",
        "system administrator",
        "devops engineer",
        "qa engineer",
        "tester",
        "scrum master",
        "agile coach",
        "sales representative",
        "sdr",
        "bdr",
        "business development",
        "accountant",
        "bookkeeper",
        "nurse",
        "doctor",
        "physician",
        "teacher",
        "tutor",
        "biologist",
        "lawyer",
        "counsel",
        "paralegal",
        # Setores econômicos, áreas amplas e funções genéricas
        "finance",
        "fintech",
        "education",
        "edtech",
        "healthcare",
        "health",
        "medical",
        "biotech",
        "pharma",
        "hospitality",
        "retail",
        "ecommerce",
        "e-commerce",
        "marketing",
        "digital marketing",
        "sales",
        "vendas",
        "comercial",
        "hr",
        "human resources",
        "people",
        "operations",
        "ops",
        "admin",
        "administration",
        "legal",
        "compliance",
        "accounting",
        "insurance",
        "real estate",
        "logistics",
        "supply chain",
        "manufacturing",
        "energy",
        "media",
        "entertainment",
        "gaming",
        "telecom",
        "government",
        "nonprofit",
        "non-profit",
        "software engineering",
        "software development",
        "data science",
        "data science & analytics",
        "data & analytics",
        "analytics",
        "design",
        "ux design",
        "ui design",
        "ui/ux",
        "ux",
        "ui",
        "product",
        "product management",
        "project management",
        "content",
        "content writing",
        "writing",
        "video",
        "vfx",
        "audio",
        "music",
        "art",
        "photography",
        "social media",
        "seo",
        "sem",
        "growth",
        "pr",
        "communications",
        "community",
        "events",
        "research",
        "science",
        "consulting",
        "management",
        "leadership",
        "strategy",
        "business",
        "crypto",
        "saas",
        "b2c",
        "startup",
        "enterprise",
        "non tech",
        "non-tech",
        "other",
        "general",
        "all",
        "misc",
        "tech",
        "it",
        "cloud",
        "backend",
        "back-end",
        "back end",
        "frontend",
        "front-end",
        "front end",
        "fullstack",
        "full-stack",
        "full stack",
        "mobile",
        "web",
        "data",
        "security",
        "infosec",
        "cybersecurity",
        "qa",
        "testing",
        "quality assurance",
        "infrastructure",
        "networking",
        "hardware",
        "embedded",
        "devops",
        "sre",
        "database",
        "databases",
        "api",
        "apis",
        "code",
        "coding",
        "programming",
        "system",
        "systems",
        "software",
        "training",
        "teaching",
        "coaching",
        "translation",
        "transcription",
        "localization",
    }
)

# Labels administrativas e de triagem de repositórios comunitários GitHub BR
GITHUB_ADMIN_AND_TRIAGE_LABELS: frozenset[str] = frozenset(
    {
        "link-quebrado",
        "link quebrado",
        "em-triagem",
        "em triagem",
        "duplicada",
        "duplicado",
        "duplicate",
        "pausada",
        "pausado",
        "spam",
        "invalid",
        "invalida",
        "invalido",
        "verificada",
        "verificado",
        "formato-sugerido",
        "formato sugerido",
        "stale",
        "fechada",
        "encerrada",
        "closed",
        "wontfix",
        "question",
        "help wanted",
        "bug",
        "documentation",
        "enhancement",
        "good first issue",
        "vaga-fechada",
        "vaga-pausada",
        "aguardando-aprovacao",
        "em-analise",
        "revisao",
        "off-topic",
        "expirada",
        "sem-salario",
        "salario-nao-informado",
        "a-combinar",
        "a combinar",
    }
)


def _is_ambiguous_go_allowed(
    *,
    source_context: str,
    context_title: str | None,
    has_other_confirmed_tech: bool,
) -> bool:
    """
    Decide conservadoramente se a tag isolada `"go"` representa a linguagem Go.
    Rejeita quando o título sugere papel não técnico (ex.: Go-to-Market, Marketing, RH)
    ou quando não há contexto técnico suficiente em feeds ruidosos.
    """
    title_clean = context_title or ""
    if title_clean and _NON_TECH_ROLE_TITLE_RE.search(title_clean):
        return False
    if source_context == "github_curated":
        return True
    if has_other_confirmed_tech:
        return True
    if title_clean and _TECH_TITLE_CONTEXT_RE.search(title_clean):
        return True
    return False


def canonicalize_technology_token(
    raw_token: str,
    *,
    source_context: str = "generic",
    context_title: str | None = None,
    has_other_confirmed_tech: bool = False,
) -> list[str]:
    """
    Avalia um único token candidato e retorna uma lista de 0, 1 ou 2 nomes canônicos
    (ex.: `"C/C++"` -> `["C", "C++"]`, `"python"` -> `["Python"]`, `"exec"` -> `[]`).

    Modos de `source_context`:
    - `"remote_ok"` / `"generic"` / `"strict"`: aceita somente tecnologias
      efetivamente reconhecidas no catálogo canônico (evitando vazamento de tags
      heterogêneas).
    - `"github_curated"`: rejeita labels administrativas, meta-labels e categorias
      não tecnológicas, canonicaliza aliases conhecidos e preserva tecnologias de
      nicho e competências técnicas curadas pelo repositório.
    - `"himalayas"` / `"jobicy"`: provedores cujos campos de taxonomia são categorias
      ou setores econômicos (rejeita por padrão para evitar contaminação).
    """
    cleaned = sanitize_plain_text(raw_token, max_length=100)
    if not cleaned:
        return []

    key = _fold_key(cleaned)
    if not key:
        return []

    if source_context in {"himalayas", "jobicy"}:
        # Categorias/setores desses provedores não devem ser promovidos como tecnologias
        return []

    # Caso composto explícito C/C++ (preserva identidade inequívoca de C e C++)
    if key in {"c/c++", "c / c++", "c and c++", "c & c++"}:
        return ["C", "C++"]

    if key in GITHUB_ADMIN_AND_TRIAGE_LABELS:
        return []

    if key in NON_TECH_EXCLUSION_TOKENS:
        return []

    if _SALARY_LABEL_RE.match(cleaned):
        return []

    # Termos curtos ambíguos tratados explicitamente
    if key in AMBIGUOUS_SHORT_TOKENS:
        if key == "go" and _is_ambiguous_go_allowed(
            source_context=source_context,
            context_title=context_title,
            has_other_confirmed_tech=has_other_confirmed_tech,
        ):
            return ["Go"]
        # "c", "r" e "ai" isolados sem contexto inequívoco não viram tecnologias
        return []

    if key in CANONICAL_TECH_ALIASES:
        return [CANONICAL_TECH_ALIASES[key]]

    if source_context == "github_curated":
        if key in CURATED_COMPETENCY_ALIASES:
            return [CURATED_COMPETENCY_ALIASES[key]]
        # Preserva tecnologias de nicho e competências técnicas curadas no repositório,
        # bloqueando tokens de 1 caractere que não sejam conhecidos.
        if len(key) <= 1:
            return []
        return [cleaned]

    # Em feeds heterogêneos (ex.: Remote OK), termos não reconhecidos permanecem
    # preservados nos metadados da fonte e não contaminam `Opportunity.technologies`.
    return []


def normalize_technologies(
    raw_items: Iterable[Any] | None,
    *,
    source_context: str = "generic",
    context_title: str | None = None,
    max_items: int = 30,
) -> list[str]:
    """
    Normaliza uma coleção de tags/labels para `Opportunity.technologies` com:
    - normalização de espaços e capitalização;
    - canonicalização de aliases conhecidos;
    - deduplicação case-insensitive;
    - rejeição de categorias, cargos, setores, senioridade, modalidades e lifestyle;
    - preservação determinística da ordem.
    """
    if not raw_items:
        return []

    cleaned_items: list[str] = []
    for raw in raw_items:
        if raw is None or isinstance(raw, bool):
            continue
        cleaned = sanitize_plain_text(str(raw), max_length=100)
        if cleaned:
            cleaned_items.append(cleaned)

    if not cleaned_items:
        return []

    # Detecta previamente se há outra tecnologia inequívoca para desambiguar `"go"`
    has_other_confirmed_tech = any(
        _fold_key(item) in CANONICAL_TECH_ALIASES
        and _fold_key(item) not in AMBIGUOUS_SHORT_TOKENS
        for item in cleaned_items
    )

    result: list[str] = []
    seen_lower: set[str] = set()

    for item in cleaned_items:
        resolved = canonicalize_technology_token(
            item,
            source_context=source_context,
            context_title=context_title,
            has_other_confirmed_tech=has_other_confirmed_tech,
        )
        for tech in resolved:
            dedup_key = _fold_key(tech)
            if dedup_key in seen_lower:
                continue
            seen_lower.add(dedup_key)
            result.append(tech)
            if len(result) >= max_items:
                return result

    return result


# ==============================================================================
# Extração conservadora de tecnologias a partir do TÍTULO (ex.: GitHub Frontend BR)
# ==============================================================================

# Tecnologias que podem ser extraídas do título com fronteira segura e alta precisão
_TITLE_EXPLICIT_PATTERNS_SPEC: tuple[tuple[str, str], ...] = (
    # Compostos e com símbolos primeiro (evita matches parciais como React dentro de React Native)
    ("React Native", r"react[\s-]+native"),
    ("ASP.NET Core", r"asp\.net\s+core"),
    ("ASP.NET", r"asp\.net"),
    (".NET", r"(?:\.net(?:\s+core|\s+framework)?|dotnet)"),
    ("C++", r"c\+\+"),
    ("C#", r"(?:c#|csharp)"),
    ("Objective-C", r"objective[\s-]+c"),
    ("Ruby on Rails", r"ruby\s+on\s+rails"),
    ("Spring Boot", r"spring[\s-]+boot"),
    ("Tailwind CSS", r"tailwind(?:\s*css)?"),
    ("Styled Components", r"styled[\s-]+components"),
    ("Material UI", r"material[\s-]+ui"),
    ("Jetpack Compose", r"jetpack\s+compose"),
    ("Node.js", r"node(?:\.js|js)"),
    ("Next.js", r"next(?:\.js|js)"),
    ("Nuxt.js", r"nuxt(?:\.js|js)"),
    ("Vue", r"vue(?:\.js|js)?"),
    ("React", r"react(?:\.js|js)?"),
    ("NestJS", r"nest(?:\.js|js)"),
    ("AdonisJS", r"adonis(?:\.js|js)"),
    ("SvelteKit", r"sveltekit"),
    ("Svelte", r"svelte"),
    ("Angular", r"angular(?:js|\.js)?"),
    ("TypeScript", r"typescript"),
    ("JavaScript", r"javascript"),
    ("Python", r"python"),
    ("FastAPI", r"fastapi"),
    ("Django", r"django"),
    ("Flask", r"flask"),
    ("Java", r"java"),
    ("Kotlin", r"kotlin"),
    ("SwiftUI", r"swiftui"),
    ("Swift", r"swift"),
    ("Flutter", r"flutter"),
    ("Dart", r"dart"),
    ("PHP", r"php"),
    ("Laravel", r"laravel"),
    ("Symfony", r"symfony"),
    ("Ruby", r"ruby"),
    ("Elixir", r"elixir"),
    ("Rust", r"rust"),
    ("Scala", r"scala"),
    ("Golang", r"golang"),
    ("PostgreSQL", r"postgres(?:ql)?"),
    ("MySQL", r"mysql"),
    ("MongoDB", r"mongodb"),
    ("Redis", r"redis"),
    ("SQL Server", r"(?:sql\s+server|mssql)"),
    ("GraphQL", r"graphql"),
    ("Docker", r"docker"),
    ("Kubernetes", r"(?:kubernetes|k8s)"),
    ("Terraform", r"terraform"),
    ("Kafka", r"kafka"),
    ("RabbitMQ", r"rabbitmq"),
    ("Snowflake", r"snowflake"),
    ("AWS", r"aws"),
    ("GCP", r"(?:gcp|google\s+cloud)"),
    ("Azure", r"azure"),
    ("Playwright", r"playwright"),
    ("Cypress", r"cypress"),
    ("Storybook", r"storybook"),
    ("WordPress", r"wordpress"),
    ("Shopify", r"shopify"),
    ("Salesforce", r"salesforce"),
    ("HTML", r"html5?"),
    ("CSS", r"css3?"),
    ("Sass", r"(?:sass|scss)"),
    ("Redux", r"redux"),
    ("Vite", r"vite"),
    ("Webpack", r"webpack"),
    ("Electron", r"electron"),
    ("PyTorch", r"pytorch"),
    ("TensorFlow", r"tensorflow"),
)

# Padrão estrito para "Go" em títulos técnicos (jamais confunde com "Go-to-Market" / "Ready to go")
_TITLE_EXPLICIT_GO_RE = re.compile(
    r"(?i)(?:"
    r"(?<![a-z0-9-])(?P<go1>go)(?=\s+(?:developer|engineer|dev|backend|back-end|programmer|desenvolvedor|programador)\b)|"
    r"\b(?:developer|engineer|desenvolvedor|programador|backend|back-end)\s+(?P<go2>go)(?![a-z0-9-])|"
    r"[•|/,+]\s*(?P<go3>go)(?=\s*(?:[•|/,+]|$))|"
    r"(?<![a-z0-9-])(?P<go4>go)(?=\s*[•|/,+]\s*(?:python|node|react|rust|java|typescript|docker|kubernetes|aws)\b)"
    r")"
)

_COMPILED_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        "Go" if label == "Golang" else label,
        re.compile(rf"(?i)(?<![a-z0-9+#])(?:{expr})(?![a-z0-9+#])"),
    )
    for label, expr in _TITLE_EXPLICIT_PATTERNS_SPEC
)


def extract_technologies_from_title(title: str | None) -> list[str]:
    """
    Extrai conservadoramente tecnologias explicitamente nomeadas no TÍTULO da vaga.
    - Nunca varre descrições.
    - Consome spans maiores primeiro (ex.: `React Native` não duplica `React`).
    - Não converte cargos (`Developer`, `Engineer`), áreas (`UX Design`, `Full-stack`)
      ou termos ambíguos (`C`, `R`, `AI`, `"Go-to-Market"`) em tecnologias.
    """
    cleaned_title = sanitize_plain_text(title, max_length=300)
    if not cleaned_title:
        return []

    occupied: list[tuple[int, int]] = []
    hits: list[tuple[int, str]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(not (end <= s or start >= e) for s, e in occupied)

    for canonical, pattern in _COMPILED_TITLE_PATTERNS:
        for match in pattern.finditer(cleaned_title):
            start, end = match.span()
            if _overlaps(start, end):
                continue
            # Evita "Java" dentro de "JavaScript" caso algum separador incomum ocorra
            if canonical == "Java" and cleaned_title[end : end + 6].lower().startswith("script"):
                continue
            occupied.append((start, end))
            hits.append((start, canonical))

    # Verificação contextual estrita para "Go" no título (bloqueia "Go-to-Market", etc.)
    if not _NON_TECH_ROLE_TITLE_RE.search(cleaned_title):
        for match in _TITLE_EXPLICIT_GO_RE.finditer(cleaned_title):
            span = next(
                (match.span(grp) for grp in ("go1", "go2", "go3", "go4") if match.group(grp) is not None),
                None,
            )
            if span is None:
                continue
            start, end = span
            if _overlaps(start, end):
                continue
            occupied.append((start, end))
            hits.append((start, "Go"))

    hits.sort(key=lambda item: item[0])

    result: list[str] = []
    seen: set[str] = set()
    for _, tech in hits:
        key = _fold_key(tech)
        if key not in seen:
            seen.add(key)
            result.append(tech)
    return result


# ==============================================================================
# Mesclagem cross-source segura de tecnologias
# ==============================================================================


def _source_slug_to_context(source_slug: str | None) -> str:
    slug = (source_slug or "").strip().lower()
    if slug == "remote_ok":
        return "remote_ok"
    if slug in {"github_backend_br", "github_frontend_br"}:
        return "github_curated"
    if slug in {"himalayas", "jobicy"}:
        return slug
    return "generic"


def merge_normalized_technologies(
    existing_technologies: Iterable[str] | None,
    incoming_technologies: Iterable[str] | None,
    *,
    incoming_source_slug: str | None = None,
    context_title: str | None = None,
    max_items: int = 40,
) -> list[str]:
    """
    Mescla tecnologias de uma fonte secundária sobre uma oportunidade existente:
    - Preserva os itens já armazenados em `existing_technologies` (sem limpeza
      retroativa destrutiva de registros legados).
    - Filtra e canonicaliza estritamente `incoming_technologies` segundo o contexto
      da fonte secundária, evitando entrada de categorias, cargos ou setores.
    - Deduplica case-insensitive e por equivalência canônica.
    - Preserva a ordem determinística.
    """
    merged: list[str] = []
    seen_keys: set[str] = set()

    for item in existing_technologies or []:
        if not item or not str(item).strip():
            continue
        raw_str = str(item).strip()
        folded = _fold_key(raw_str)
        if not folded or folded in seen_keys:
            continue
        seen_keys.add(folded)
        if folded in CANONICAL_TECH_ALIASES:
            seen_keys.add(_fold_key(CANONICAL_TECH_ALIASES[folded]))
        elif folded in CURATED_COMPETENCY_ALIASES:
            seen_keys.add(_fold_key(CURATED_COMPETENCY_ALIASES[folded]))
        merged.append(raw_str)

    incoming_ctx = _source_slug_to_context(incoming_source_slug)
    normalized_incoming = normalize_technologies(
        incoming_technologies,
        source_context=incoming_ctx,
        context_title=context_title,
        max_items=max_items,
    )

    for tech in normalized_incoming:
        key = _fold_key(tech)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(tech)
        if len(merged) >= max_items:
            break

    return merged


def deduplicate_technologies_preserving_order(
    items: Iterable[str] | None,
    *,
    max_items: int = 40,
) -> list[str]:
    """
    Deduplica tecnologias de forma case-insensitive e por equivalência canônica,
    preservando integralmente a ordem determinística de entrada.
    """
    result: list[str] = []
    seen_keys: set[str] = set()
    for item in items or []:
        if not item or not str(item).strip():
            continue
        cleaned = str(item).strip()
        folded = _fold_key(cleaned)
        if not folded or folded in seen_keys:
            continue
        canonical_key: str | None = None
        if folded in CANONICAL_TECH_ALIASES:
            canonical_key = _fold_key(CANONICAL_TECH_ALIASES[folded])
        elif folded in CURATED_COMPETENCY_ALIASES:
            canonical_key = _fold_key(CURATED_COMPETENCY_ALIASES[folded])
        if canonical_key and canonical_key in seen_keys:
            continue
        seen_keys.add(folded)
        if canonical_key:
            seen_keys.add(canonical_key)
        result.append(cleaned)
        if len(result) >= max_items:
            break
    return result


def extract_link_technologies_from_metadata(
    source_slug: str | None,
    raw_metadata: Mapping[str, Any] | None,
    *,
    context_title: str | None = None,
) -> tuple[list[str], bool]:
    """
    Recompõe deterministicamente as tecnologias de um `OpportunitySourceLink`
    a partir do seu `raw_metadata` específico de provedor.

    Retorna `(technologies, provenance_reconstructible)`:
    - `provenance_reconstructible=True`: a taxonomia original da fonte está
      presente no vínculo e permite recomposição exata.
    - `provenance_reconstructible=False`: vínculo legado sem metadados originais
      suficientes; chamadores devem aplicar política de preservação conservadora.
    """
    slug = (source_slug or "").strip().lower()
    meta = raw_metadata if isinstance(raw_metadata, Mapping) else {}

    if slug == "remote_ok":
        raw_tags = meta.get("raw_tags")
        if isinstance(raw_tags, list):
            return (
                normalize_technologies(
                    raw_tags,
                    source_context="remote_ok",
                    context_title=context_title,
                ),
                True,
            )
        return ([], False)

    if slug == "himalayas":
        if isinstance(meta.get("categories"), list):
            return ([], True)
        return ([], False)

    if slug == "jobicy":
        if "job_industry" in meta:
            return ([], True)
        return ([], False)

    if slug == "github_backend_br":
        raw_labels = meta.get("labels")
        if isinstance(raw_labels, list):
            return (
                normalize_technologies(
                    raw_labels,
                    source_context="github_curated",
                    context_title=context_title,
                ),
                True,
            )
        return ([], False)

    if slug == "github_frontend_br":
        raw_labels = meta.get("labels")
        if isinstance(raw_labels, list):
            label_techs = normalize_technologies(
                raw_labels,
                source_context="github_curated",
                context_title=context_title,
            )
            title_techs = extract_technologies_from_title(context_title)
            return (
                deduplicate_technologies_preserving_order(label_techs + title_techs),
                True,
            )
        return ([], False)

    return ([], False)


# ==============================================================================
# Extração unificada de sinais de classificação da fonte primária (B-02)
# ==============================================================================


@dataclass(frozen=True, slots=True)
class PrimaryClassificationSignals:
    """
    Sinais extraídos exclusivamente dos metadados da fonte primária, separados por
    dimensão semântica para evitar que setores econômicos (`job_industry`) sejam
    alimentados no classificador de senioridade.
    """

    area_tags: tuple[str, ...]
    seniority_tags: tuple[str, ...]
    meta_levels: tuple[str, ...]
    raw_labels: tuple[str, ...]
    raw_job_types: tuple[str, ...]


def extract_primary_classification_signals(
    primary_metadata: Mapping[str, Any] | None,
    technologies: Iterable[str] | None = None,
) -> PrimaryClassificationSignals:
    """
    Contrato único compartilhado por `reclassify_opportunities()` e pelos fallbacks
    em memória de `matching.py`:
    - `raw_tags` (Remote OK): alimenta área e senioridade (protegido por DX-03.1.3).
    - `categories` (Himalayas): alimenta área e senioridade (substituindo `-` por espaço).
    - `job_industry` (Jobicy): representa setor econômico — alimenta apenas `area_tags`,
      NUNCA `seniority_tags` nem `meta_levels`.
    - `labels` (GitHub BR): alimenta `area_tags`, `seniority_tags`, `meta_levels` e `raw_labels`.
    - `technologies`: sinal complementar e fallback conservador para registros legados
      que ainda não possuem os novos campos de proveniência.
    """
    meta = primary_metadata if isinstance(primary_metadata, Mapping) else {}

    area_tags: list[str] = []
    seen_area: set[str] = set()
    seniority_tags: list[str] = []
    seen_sen: set[str] = set()

    def _add(target: list[str], seen: set[str], value: str) -> None:
        cleaned = str(value).strip()
        if not cleaned:
            return
        low = cleaned.lower()
        if low not in seen:
            seen.add(low)
            target.append(cleaned)

    # 1. Tags originais do Remote OK (evidência primária para área e senioridade)
    raw_tags = meta.get("raw_tags")
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            s = str(tag)
            _add(area_tags, seen_area, s)
            _add(seniority_tags, seen_sen, s)

    # 2. Tecnologias declaradas (complemento técnico + fallback conservador legado)
    for tech in technologies or []:
        s = str(tech)
        _add(area_tags, seen_area, s)
        _add(seniority_tags, seen_sen, s)

    meta_levels: list[str] = []
    raw_labels: list[str] = []
    raw_job_types: list[str] = []

    # 3. Labels estruturadas do GitHub BR
    labels = meta.get("labels")
    if isinstance(labels, list):
        for lb in labels:
            s = str(lb)
            _add(area_tags, seen_area, s)
            _add(seniority_tags, seen_sen, s)
            meta_levels.append(s)
            raw_labels.append(s)

    # 4. Categorias do Himalayas (funções e sinais de senioridade)
    categories = meta.get("categories")
    if isinstance(categories, list):
        for cat in categories:
            normalized_cat = str(cat).replace("-", " ")
            _add(area_tags, seen_area, normalized_cat)
            _add(seniority_tags, seen_sen, normalized_cat)

    # 5. Setor econômico do Jobicy (`job_industry`) — apenas dimensão de área, NUNCA senioridade!
    raw_industry = meta.get("job_industry")
    if isinstance(raw_industry, list):
        for ind in raw_industry:
            _add(area_tags, seen_area, str(ind))
    elif isinstance(raw_industry, str) and raw_industry.strip():
        _add(area_tags, seen_area, raw_industry)

    # 6. Tipo de contrato / vínculo estruturado (Jobicy `job_type`, Himalayas `employment_type_raw`)
    job_types = meta.get("job_type")
    if isinstance(job_types, list):
        for jt in job_types:
            s = str(jt)
            _add(seniority_tags, seen_sen, s)
            raw_job_types.append(s)

    if meta.get("employment_type_raw"):
        emp_raw = str(meta["employment_type_raw"])
        _add(seniority_tags, seen_sen, emp_raw)
        raw_job_types.append(emp_raw)

    # 7. Nível estruturado (Jobicy `job_level`, Himalayas `seniority`)
    job_level = meta.get("job_level")
    if job_level and str(job_level).lower() not in {"any", "all"}:
        jl = str(job_level)
        _add(seniority_tags, seen_sen, jl)
        meta_levels.append(jl)

    seniorities = meta.get("seniority")
    if isinstance(seniorities, list):
        for sen in seniorities:
            s = str(sen)
            _add(seniority_tags, seen_sen, s)
            meta_levels.append(s)

    return PrimaryClassificationSignals(
        area_tags=tuple(area_tags),
        seniority_tags=tuple(seniority_tags),
        meta_levels=tuple(meta_levels),
        raw_labels=tuple(raw_labels),
        raw_job_types=tuple(raw_job_types),
    )
