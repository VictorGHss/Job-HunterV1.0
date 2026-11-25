from dataclasses import dataclass
import re
import unicodedata

from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
)
from app.services.opportunities.sanitization import repair_mojibake

_COMBINING_MARKS_RE = re.compile(r"[\u0300-\u036f]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_CAMEL_BOUNDARY_RE = re.compile(
    r"([a-z])((?:Contract|Salary|Hours|Location|Role|Type|Position|Schedule)\b)"
)
_GENDER_SUFFIX_RE = re.compile(r"\(\s*a\s*\)|/a(?![a-z0-9])")

UPPER_SENIORITY_LEVELS: frozenset[str] = frozenset(
    {
        SeniorityLevel.MID_LEVEL.value,
        SeniorityLevel.SENIOR.value,
        SeniorityLevel.STAFF_PRINCIPAL.value,
        SeniorityLevel.MANAGEMENT.value,
    }
)

PROFESSIONAL_AREA_LABELS_PT: dict[str, str] = {
    ProfessionalArea.SOFTWARE_DEVELOPMENT.value: "Desenvolvimento de Software",
    ProfessionalArea.BACKEND.value: "Backend",
    ProfessionalArea.FRONTEND.value: "Frontend",
    ProfessionalArea.FULLSTACK.value: "Full Stack",
    ProfessionalArea.DATA.value: "Dados e Analytics",
    ProfessionalArea.ARTIFICIAL_INTELLIGENCE.value: "Inteligência Artificial e ML",
    ProfessionalArea.DEVOPS_CLOUD.value: "DevOps, Cloud e SRE",
    ProfessionalArea.API_INTEGRATIONS.value: "APIs, Integrações e Automação",
    ProfessionalArea.INFRASTRUCTURE.value: "Infraestrutura de TI",
    ProfessionalArea.TECHNICAL_SUPPORT.value: "Suporte Técnico e Help Desk",
    ProfessionalArea.CUSTOMER_SUPPORT.value: "Atendimento e Suporte ao Cliente",
    ProfessionalArea.MARKETING_SALES.value: "Marketing e Vendas",
    ProfessionalArea.HEALTHCARE.value: "Saúde",
    ProfessionalArea.ADMINISTRATION.value: "Administração e Operações",
    ProfessionalArea.OTHER.value: "Outras Áreas",
    ProfessionalArea.UNKNOWN.value: "Área não identificada",
}

TECH_TARGET_AREAS: frozenset[str] = frozenset(
    {
        ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
        ProfessionalArea.BACKEND.value,
        ProfessionalArea.FRONTEND.value,
        ProfessionalArea.FULLSTACK.value,
        ProfessionalArea.DATA.value,
        ProfessionalArea.ARTIFICIAL_INTELLIGENCE.value,
        ProfessionalArea.DEVOPS_CLOUD.value,
        ProfessionalArea.API_INTEGRATIONS.value,
        ProfessionalArea.INFRASTRUCTURE.value,
    }
)

SENIORITY_LABELS_PT: dict[str, str] = {
    SeniorityLevel.INTERNSHIP.value: "Estágio",
    SeniorityLevel.ENTRY_LEVEL.value: "Início de carreira / Entry-level",
    SeniorityLevel.JUNIOR.value: "Júnior",
    SeniorityLevel.MID_LEVEL.value: "Pleno",
    SeniorityLevel.SENIOR.value: "Sênior",
    SeniorityLevel.STAFF_PRINCIPAL.value: "Staff / Principal",
    SeniorityLevel.MANAGEMENT.value: "Liderança / Gestão",
    SeniorityLevel.UNKNOWN.value: "Senioridade não informada",
}

EXPERIENCE_MODE_LABELS_PT: dict[str, str] = {
    ExperienceRequirementMode.NONE_REQUIRED.value: "Sem exigência de experiência prévia",
    ExperienceRequirementMode.PREFERRED.value: "Experiência desejável",
    ExperienceRequirementMode.REQUIRED.value: "Experiência obrigatória",
    ExperienceRequirementMode.NOT_SPECIFIED.value: "Experiência não especificada",
}

# Frases que mencionam senioridade ou perfil júnior de TERCEIROS (colegas, líderes, reportados),
# não os requisitos da própria vaga — removidas apenas do texto de descrição antes da heurística.
_NON_SELF_MENTION_PATTERNS = (
    re.compile(
        r"\b(?:collaborate|work|working|partner|paired?)\s+(?:closely\s+)?with\s+"
        r"(?:our\s+)?(?:product,\s+design,\s+)?(?:senior|staff|principal|lead|experienced|backend|frontend|ai)?\s*"
        r"(?:and\s+(?:ai|backend|frontend)\s+)?"
        r"(?:developers?|engineers?|designers?|bds?|leaders?|leadership|stakeholders?|colleagues?|team)\b"
    ),
    re.compile(
        r"\b(?:report|reports|reporting)\s+(?:directly\s+)?to\s+(?:the\s+|our\s+|an?\s+)?"
        r"(?:senior|sr\.?|lead|principal|head\s+of|director|vp|chief|manager|cto|ceo)\b"
    ),
    re.compile(
        r"\b(?:learn|learning|mentorship|mentored|guidance)\s+from\s+(?:a\s+|our\s+|an?\s+)?"
        r"(?:senior|staff|principal|lead|experienced)\s+(?:developer|engineer|team|leader|mentor)\b"
    ),
    re.compile(
        r"\b(?:senior\s+(?:leadership|stakeholders?|management|buyers?|clinical|voice\s+for)|"
        r"founded\s+by[^.]{0,80}\bsenior\b|keep\s+our\s+senior\s+developers)\b"
    ),
    re.compile(
        r"\b(?:coach(?:ing)?|mentor(?:ing)?|develop(?:ing)?|entwickelst|fuhrst|lead(?:ing)?|manage(?:ment)?)\s+"
        r"(?:insbesondere\s+unsere\s+|our\s+|the\s+)?(?:junior|jr\.?|entry[- ]level)\b"
    ),
    re.compile(
        r"\b(?:bachelor|master|associate|graduate)\s+degree\b|\bgraduate\s+from\s+our\b"
    ),
)

# Sinais explícitos de ESTÁGIO / PROGRAMA ACADÊMICO (fronteira de palavra; nunca "internal"/"international")
_INTERNSHIP_STRONG_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"interns?|internship|apprentice|apprenticeship|co-?op\s+intern|"
    r"estagio|estagiari[oa]s?|pasantia|pasante|"
    r"praktikum|praktikant(?:en|in)?|werkstudent(?:en|in)?|"
    r"working\s+student|student\s+assistant|student\s+job"
    r")(?![a-z0-9])"
)
_INTERNSHIP_BODY_PHRASE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:summer|winter|paid|unpaid|software|engineering|tech|marketing|finance)\s+internship|"
    r"(?:das|ein)\s+praktikum|"
    r"estagio\s+(?:em|na|no|de)|"
    r"vaga\s+de\s+estagio|"
    r"looking\s+for\s+(?:a\s+)?student\s+(?:job|assistant)|"
    r"working\s+student|werkstudent|student\s+assistant|"
    r"currently\s+(?:enrolled|pursuing)\s+(?:a\s+)?(?:bachelor|master|degree)"
    r")(?![a-z0-9])"
)

# Sinais de EXCLUSÃO/BLOQUEIO para estágio e júnior (cargos seniores, liderança, credenciais médicas plenas)
_STAFF_PRINCIPAL_RE = re.compile(
    r"(?<![a-z0-9])(?:staff|principal|distinguished\s+engineer|fellow)(?![a-z0-9])"
)
_MANAGEMENT_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"team\s+lead|tech\s+lead|technical\s+(?:product\s+)?lead|"
    r"engineering\s+lead|product\s+engineering\s+lead|bd\s+lead|cloud\s+lead|"
    r"lead\s+(?:engineer|developer|software\s+engineer|software\s+developer|designer|product|architect)|"
    r"head\s+of|director|vp|vice\s+president|chief\s+\w+\s+officer|cto|ceo|cfo|cio|"
    r"manager|gerente|coordenador(?:a)?|dean"
    r")(?![a-z0-9])"
)
_SENIOR_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:senior|sr\.?|especialista|architect)(?![a-z0-9])"
)
_MID_LEVEL_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:pleno|mid[- ]?level|mid[- ]?senior|intermediario)(?![a-z0-9])"
)
_LEADERSHIP_OR_SENIOR_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"senior|sr\.?|staff|principal|team\s+lead|tech\s+lead|technical\s+(?:product\s+)?lead|"
    r"engineering\s+lead|product\s+engineering\s+lead|bd\s+lead|cloud\s+lead|"
    r"lead\s+(?:engineer|developer|designer|product|architect)|"
    r"head\s+of|director|vp|vice\s+president|chief\s+\w+\s+officer|cto|ceo|cfo|cio|"
    r"manager|gerente|coordenador(?:a)?|director\s+of|dean|"
    r"pleno|mid[- ]?level|mid[- ]?senior|architect|especialista"
    r")(?![a-z0-9])"
)
_BOARD_CREDENTIAL_RE = re.compile(
    r"(?<![a-z0-9])(?:board[- ]?eligible|board\s+certification|md\s+or\s+do|endocrinologist|physician)(?![a-z0-9])"
)
_EXPERIENCED_YEARS_RE = re.compile(
    r"(?:at\s+least\s+|minimum\s+|preferably\s+)?(?:[3-9]|\d{2,})\s*(?:\+|[-–—]\s*\d+\+?)?\s*"
    r"(?:years?|anos?)\s+(?:of\s+|de\s+)?(?:[a-z0-9/+-]+\s+){0,4}(?:experience|experiencia|in\s+)"
)

# Sinais de JÚNIOR vs INÍCIO DE CARREIRA / ENTRADA
_JUNIOR_STRICT_RE = re.compile(
    r"(?<![a-z0-9])(?:junior|jr\.?)(?![a-z0-9])"
)
_ENTRY_LEVEL_ONLY_RE = re.compile(
    r"(?<![a-z0-9])(?:entry[- ]?level|trainee|new\s+grad|graduate|early[- ]?career|inicio\s+de\s+carreira)(?![a-z0-9])"
)
_JUNIOR_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"junior|jr\.?|entry[- ]?level|trainee|new\s+grad|graduate|early[- ]?career|inicio\s+de\s+carreira"
    r")(?![a-z0-9])"
)
_JUNIOR_BODY_PHRASE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:is\s+an?\s+|as\s+a\s+|for\s+an?\s+|motivated\s+|exceptional\s+)?"
    r"(?:junior|jr\.?)\s+(?:[a-z0-9]+\s+){0,2}"
    r"(?:developer|engineer|designer|analyst|programmer|dev|qa|tester|specialist|ui)|"
    r"(?:this\s+is\s+an?\s+|ideal\s+for\s+an?\s+)?entry[- ]?level\s+(?:opportunity|role|position|developer|engineer)|"
    r"ideal\s+for\s+an\s+early[- ]career\s+(?:developer|engineer|professional)|"
    r"(?:structured\s+)?graduate\s+(?:development\s+)?(?:programme|program|academy|scheme)|"
    r"trainee\s+(?:program|programa|em|de|tech)"
    r")(?![a-z0-9])"
)

# Sinais de FREELANCE / PROJETO AUTÔNOMO (sem confundir com "smart contract", "contracts manager", "API contract")
_FREELANCE_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:freelance|freelancer|freela|autonom[oa]|projeto\s+fechado)(?![a-z0-9])"
)
_FREELANCE_BODY_EXPLICIT_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"freelance(?:r)?(?:\s+(?:role|position|opportunity|project|developer|engineer|work))?|"
    r"independent\s+contractor(?:\s+(?:opportunity|arrangement|role|position))?|"
    r"1099\s+contract(?:or)?|"
    r"(?:trabalho|regime|profissional|contratacao)\s+autonom[oa]|"
    r"projeto\s+fechado|per[- ]?project|project[- ]?based"
    r")(?![a-z0-9])"
)

# Contrato explícito (separado da categoria opportunity_type)
_CONTRACT_FIXED_TERM_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"fixed[- ]?term|one[- ]?year\s+contract|1[- ]?year\s+contract|"
    r"temporari[oa]|temporary|prazo\s+determinado|contract:\s*fixed[- ]?term"
    r")(?![a-z0-9])"
)
_CONTRACT_CLT_RE = re.compile(
    r"(?<![a-z0-9])(?:clt|regime\s+clt|contratacao\s+clt|carteira\s+assinada)(?![a-z0-9])"
)
_CONTRACT_PJ_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"pj|pessoa\s+juridica|contratacao\s+pj|"
    r"(?:type|contratacion|mode|employment)[:\s]+(?:full[- ]?time\s+)?contractor|"
    r"remote\s+contractor\s+usd\s+full\s+time|"
    r"contractor\s+start\s+date|contractor\s+anniversary|b2b\s+contract"
    r")(?![a-z0-9])"
)
_CONTRACT_DUAL_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"permanent\s+or\s+contract|full[- ]?time\s+or\s+contract|"
    r"most\s+roles\s+are\s+contract[- ]?based[^.]{0,120}direct\s+hire|"
    r"freelancing\s*&\s*full\s+time"
    r")(?![a-z0-9])"
)

# ==============================================================================
# PADRÕES DETERMINÍSTICOS DE ÁREA PROFISSIONAL (FASE 02.3)
# ==============================================================================

_TECH_SUPPORT_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"technical\s+support|tech\s+support|it\s+support|help\s*desk|service\s+desk|"
    r"desktop\s+support|hil\s+support|suporte\s+tecnico|suporte\s+de\s+ti|"
    r"atendimento\s+de\s+ti|analista\s+de\s+suporte|tecnico\s+de\s+suporte|"
    r"tecnico\s+de\s+ti|(?:technical|it|tech|l1|l2|tier\s*[12]|application|product)\s+support\s+(?:engineer|specialist)|"
    r"support\s+engineer|technical\s+account\s+manager"
    r")(?![a-z0-9])"
)
_TECH_SUPPORT_BODY_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"atendimento\s+de\s+chamados|suporte\s+tecnico\s+n[123]|help\s*desk|"
    r"service\s+desk|escalat(?:e|ed)\s+to\s+l[23]|l[12]\s+support|"
    r"tier\s+[123]\s+support|zendesk[^.]{0,80}support\s+channels"
    r")(?![a-z0-9])"
)

_CUSTOMER_SUPPORT_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"customer\s+support|client\s+support|travel\s+support|customer\s+service|"
    r"customer\s+success|patient\s+care\s+specialist|patient\s+engagement\s+specialist|"
    r"call\s+center|atendimento\s+ao\s+cliente|suporte\s+ao\s+cliente|"
    r"travel\s+booking|booking\s+assistant|coordinating\s+reservations|"
    r"reservations?\s+coordinator"
    r")(?![a-z0-9])"
)

_HEALTHCARE_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"endocrinologist|physician|doctor|clinician|nurse|medical\s+director|"
    r"clinical\s+data\s+manager|telehealth|medico|enfermeir[oa]"
    r")(?![a-z0-9])"
)
_HEALTHCARE_BODY_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"ob-?gyn\s+residents?|abog\s+qualifying\s+examination|usmle|"
    r"board[- ]?eligible\s+endocrinologists?|patient[- ]?facing\s+hours"
    r")(?![a-z0-9])"
)

_MARKETING_SALES_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"marketing|paid\s+media|growth\s+product\s+manager|account\s+executive|"
    r"account\s+manager|business\s+development|bd\s+lead|partner\s+operations|"
    r"sales|vendas|comercial|copywriter|content\s+strategist|seo\s+specialist|"
    r"country\s+manager"
    r")(?![a-z0-9])"
)
_MARKETING_SALES_BODY_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"leads\s+the\s+education\s+sales\s+team|sales\s+experience\s+within\s+a\s+saas"
    r")(?![a-z0-9])"
)

_ADMIN_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"accountant|accounting|bookkeeper|recruiter|recruiting\s+coordinator|"
    r"people\s+operations|human\s+resources|hr\s+manager|contracts?\s+manager|"
    r"project\s+scheduler|academic\s+dean|wedding\s+coordinator|payment\s+integrity|"
    r"revenue\s+cycle\s+manager|specialist\s+global\s+qms|strategy\s*&\s*operations\s+coach|"
    r"agile\s+program\s+manager|program\s+manager|m&a\s+praktikum|"
    r"market\s+analyst|product\s+manager|product\s+lead|product\s+designer|"
    r"director\s+of\s+product\s+management|finance\s+systems\s*&\s*erp"
    r")(?![a-z0-9])"
)

_NON_DEV_OTHER_ROLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"transport\s+planner|video\s+annotation|content\s+reviewer|"
    r"mechanical\s+design\s+engineer|"
    r"helps\s+children\s+aged\s+5\s+to\s+17|teaching\s+them\s+python"
    r")(?![a-z0-9])"
)

# Sinais técnicos de engenharia / desenvolvimento / dados / IA / cloud / infra
_FULLSTACK_RE = re.compile(
    r"(?<![a-z0-9])(?:full[- ]?stack|desenvolvedor(?:/a)?\s+full\s+stack)(?![a-z0-9])"
)
_BACKEND_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"backend|back[- ]?end|technical\s+lead\s*-\s*golang|"
    r"(?:python|java|spring|golang|go|node\.?js|ruby|rust|c#|dot\s*net|php|laravel|fastapi|django)\s+"
    r"(?:software\s+)?(?:engineer|developer|dev|programmer|programador|desenvolvedor)|"
    r"(?:desenvolvedor|programador|engenheiro\s+de\s+software|developer|engineer|dev)\s+"
    r"(?:de\s+desenvolvimento\s+)?(?:backend|back[- ]?end|python|java|spring|golang|node\.?js|c#|php)"
    r")(?![a-z0-9])"
)
_FRONTEND_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"frontend|front[- ]?end|ui\s+developer|ui\s+engineer|"
    r"(?:react|vue|angular|next\.?js|javascript|typescript)\s+"
    r"(?:developer|engineer|dev|desenvolvedor|programador)|"
    r"(?:desenvolvedor|programador|developer|engineer|dev)\s+(?:frontend|front[- ]?end|react|vue|angular|ui)"
    r")(?![a-z0-9])"
)
_API_INTEGRATIONS_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"api\s+integration|integration\s+(?:engineer|developer)|"
    r"desenvolvedor\s+de\s+integrac(?:ao|oes)|"
    r"(?:api|integrations?|automac(?:ao|oes)|rpa)\s+(?:developer|engineer|specialist|desenvolvedor)|"
    r"projeto\s+freelance\s+api"
    r")(?![a-z0-9])"
)
_AI_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"ai\s+engineer|ml\s+engineer|ai\s+ml\s+engineer|machine\s+learning\s+engineer(?:ing)?|"
    r"agentic\s+ai\s+engineer|ml\s+inference\s+engineer|applied\s+ai|"
    r"artificial\s+intelligence\s+engineer|engenheiro\s+de\s+ia|ai\s+engineering|"
    r"research\s+engineer\s+privacy|software\s+engineer\s+ai\s+tooling|"
    r"build\s+ai\s+agents|ai\s+coding\s+evaluation"
    r")(?![a-z0-9])"
)
_DATA_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"data\s+engineer|data\s+analyst|data\s+scientist|analytics\s+engineer|"
    r"data\s+and\s+analytics|business\s+intelligence|bi\s+analyst|engenheiro\s+de\s+dados|"
    r"analista\s+de\s+dados|cientista\s+de\s+dados|estagio\s+engenharia\s+de\s+dados|"
    r"operations\s+expert\s+with\s+python\s+for\s+ai\s+supply\s+chain"
    r")(?![a-z0-9])"
)
_DATA_ENGINEERING_ROLE_RE = re.compile(
    r"(?<![a-z0-9])(?:data\s+engineer|engenheiro\s+de\s+dados|engenharia\s+de\s+dados|analytics\s+engineer|etl)(?![a-z0-9])"
)
_DEVOPS_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"devops|site\s+reliability|sre|cloud\s+engineer|cloud\s+solutions\s+architect|"
    r"solutions\s+architect|platform\s+and\s+integration\s+engineer|"
    r"platform\s+engineer|kubernetes\s+control\s+plane"
    r")(?![a-z0-9])"
)
_INFRA_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"infrastructure\s*&\s*security\s+engineer|software\s+engineer\s+infrastructure|"
    r"infrastructure\s+engineer|network\s+engineer|security\s+engineer|"
    r"systems?\s+administrator|sysadmin|director\s+of\s+it|analista\s+de\s+infraestrutura|"
    r"smart\s+contract\s+auditor|infosec"
    r")(?![a-z0-9])"
)
_SOFTWARE_DEV_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"software\s+engineers?|software\s+developer|software\s+development|"
    r"software\s+applications?\s+developer|software\s+engineering|"
    r"desenvolvedor(?:\s+de\s+software|\s+de\s+sistemas)?|"
    r"desenvolvimento\s+de\s+software|desenvolvimento\s+de\s+sistemas|"
    r"desenvolvimento\s+web|desenvolvimento\s+de\s+aplicacoes|"
    r"programador|engenheiro\s+de\s+software|engenharia\s+de\s+software|"
    r"tech\s+lead|engineering\s+lead|engineering\s+manager|product\s+engineering\s+lead|"
    r"head\s+of\s+technology|developer\s+relations\s+engineer|developer\s+advocate|"
    r"principal\s+engineer|staff\s+software\s+engineer|solutions\s+engineer|"
    r"implementation\s+engineer|oracle\s+fusion\s+cloud\s+lead|"
    r"embedded\s+systems|qa\s+tester|website\s*&\s*app\s+tester|quality\s+assurance\s+engineer|"
    r"internal\s+tools\s+software\s+engineer|apprentice\s+software\s+developer"
    r")(?![a-z0-9])"
)

# Sinais substantivos de stack para enriquecer áreas secundárias quando a vaga já é técnica
_BACKEND_STACK_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"backend|back[- ]?end|fastapi|django|flask|spring\s+boot|spring\s+data|"
    r"java\b|python\b|golang\b|node\.?js|ruby\s+on\s+rails|laravel| dot\s*net|"
    r"postgresql|postgres|mysql|redis|microservices|microsservicos|drizzle\s+orm|trpc"
    r")(?![a-z0-9])"
)
_FRONTEND_STACK_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"frontend|front[- ]?end|react(?:\.?js)?|vue(?:\.?js)?|nuxt(?:\.?js)?|"
    r"angular|next\.?js|tailwind\s*css|html5?|css3?|sass|ui\s+components"
    r")(?![a-z0-9])"
)
_API_STACK_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"rest(?:ful)?\s+apis?|apis?\s+rest(?:ful)?|http\s+apis?|graphql|webhooks?|"
    r"api\s+integrations?|integrac(?:ao|oes)\s+de\s+(?:apis?|sistemas)|"
    r"automac(?:ao|oes)|web\s+scraping"
    r")(?![a-z0-9])"
)
_AI_STACK_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"machine\s+learning|deep\s+learning|llm\s+apis?|llms?|pytorch|tensorflow|"
    r"vllm|sglang|tensorrt[- ]?llm|computer\s+vision|agentic\s+ai|ai\s+agents|"
    r"artificial\s+intelligence|inteligencia\s+artificial"
    r")(?![a-z0-9])"
)
_DATA_STACK_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"data\s+pipelines?|etl\b|data\s+warehouse|snowflake|bigquery|spark|airflow|"
    r"data\s+engineering|engenharia\s+de\s+dados"
    r")(?![a-z0-9])"
)
_DEVOPS_STACK_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"kubernetes|k8s|terraform|ansible|ci/cd|github\s+actions|cloudformation|eks\b"
    r")(?![a-z0-9])"
)


@dataclass(frozen=True, slots=True)
class ExperienceAssessment:
    mode: str
    min_years: int | None
    preferred_years: int | None
    summary: str | None
    mandatory_technologies: tuple[str, ...] = ()
    desirable_technologies: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    opportunity_type: str
    employment_type: str
    confidence: str
    reasons: tuple[str, ...]
    professional_area: str = ProfessionalArea.UNKNOWN.value
    secondary_areas: tuple[str, ...] = ()
    seniority_level: str = SeniorityLevel.UNKNOWN.value
    experience_requirement_mode: str = ExperienceRequirementMode.NOT_SPECIFIED.value
    experience_min_years: int | None = None
    experience_preferred_years: int | None = None
    experience_summary: str | None = None
    required_technologies: tuple[str, ...] = ()
    desirable_technologies: tuple[str, ...] = ()


def _extract_techs_from_text(norm_text: str) -> list[str]:
    found: list[str] = []
    for label, pattern in _TECH_EXTRACTION_MAP:
        if pattern.search(norm_text):
            found.append(label)
    return found


def classify_experience_requirements(
    *,
    title: str | None = None,
    description: str | None = None,
    requirements: list[str] | None = None,
) -> ExperienceAssessment:
    """
    Classifica requisitos explícitos de experiência separando obrigatoriedade,
    desejabilidade e ausência de especificação. Nunca infere anos de experiência
    apenas a partir do título do cargo ou de nomes isolados de tecnologias/tags.
    """
    del title  # Regra estrita: nunca inferir experiência pelo título do cargo
    reasons: list[str] = []
    required_years_list: list[int] = []
    preferred_years_list: list[int] = []
    has_no_experience = False
    has_qual_required = False
    has_qual_preferred = False
    mandatory_techs: list[str] = []
    desirable_techs: list[str] = []

    raw_blocks: list[tuple[str, str, str]] = []
    if requirements:
        for req in requirements:
            if req and str(req).strip():
                req_norm = normalize_classification_text(str(req))
                req_clean = _strip_non_self_context(req_norm)
                if req_clean:
                    raw_blocks.append(("required", req_norm, req_clean))

    if description:
        plain_with_lines = _HTML_TAG_RE.sub(
            " ",
            re.sub(
                r"(?i)<(?:br\s*/?|/p|/div|/li|/h[1-6]|tr)[^>]*>",
                "\n",
                _repair_mojibake(description),
            ),
        )
        section_mode = "neutral"
        for raw_line in plain_with_lines.splitlines():
            norm_line = normalize_classification_text(raw_line)
            if not norm_line:
                continue
            if _EXP_PREFERRED_HEADER_RE.match(norm_line):
                section_mode = "preferred"
            elif _EXP_REQUIRED_HEADER_RE.match(norm_line):
                section_mode = "required"
            elif _EXP_NEUTRAL_HEADER_RE.match(norm_line):
                section_mode = "neutral"

            for sent in re.split(r"(?<=[.!?;])\s+", norm_line):
                raw_sent_norm = sent.strip()
                sent_clean = _strip_non_self_context(raw_sent_norm)
                if sent_clean:
                    raw_blocks.append((section_mode, raw_sent_norm, sent_clean))

    for section_ctx, raw_sent_norm, norm_sent in raw_blocks:
        if not norm_sent:
            continue

        if _NO_EXPERIENCE_RE.search(norm_sent):
            has_no_experience = True
            reasons.append("exp:explicit_no_experience_required")
            continue

        is_preferred_line = bool(_LINE_PREFERRED_MARKER_RE.search(norm_sent))
        is_required_line = bool(_LINE_REQUIRED_MARKER_RE.search(norm_sent))

        effective_mode = section_ctx
        if is_preferred_line and not is_required_line:
            effective_mode = "preferred"
        elif is_required_line:
            effective_mode = "required"

        # Evita falsos positivos com idade da empresa ou frequência anual de benefícios
        if not _COMPANY_AGE_OR_PTO_RE.search(norm_sent):
            bachelor_alt = _DEGREE_ALT_YEARS_RE.search(norm_sent)
            if bachelor_alt:
                yrs_val = int(bachelor_alt.group(1))
                if effective_mode == "preferred":
                    preferred_years_list.append(yrs_val)
                else:
                    required_years_list.append(yrs_val)
            else:
                for match in _YEARS_CLAUSE_RE.finditer(norm_sent):
                    yrs_val = int(match.group(1))
                    trailing = match.group(2) or ""
                    # Ignora "0 years with Masters" se não houve Bachelor ou > 30 anos (idade da empresa)
                    if yrs_val > 25:
                        continue
                    has_exp_anchor = (
                        "experience" in norm_sent
                        or "experiencia" in norm_sent
                        or "hands-on" in trailing
                        or "hands on" in trailing
                        or section_ctx in {"required", "preferred"}
                    )
                    if not has_exp_anchor:
                        continue
                    if yrs_val == 0 and "master" in trailing:
                        continue
                    if effective_mode == "preferred":
                        preferred_years_list.append(yrs_val)
                    else:
                        required_years_list.append(yrs_val)

        if _QUAL_EXP_REQUIRED_RE.search(norm_sent):
            if effective_mode == "preferred":
                has_qual_preferred = True
            elif (
                effective_mode == "required"
                or is_required_line
                or "qualifications" in norm_sent
            ):
                has_qual_required = True

        # Extração de tecnologias em requisitos explícitos (sem converter listas "e.g." nem tags soltas)
        is_non_req_context = (
            "collaborate" in raw_sent_norm
            or "work closely with" in raw_sent_norm
            or "work alongside" in raw_sent_norm
            or "partner with" in raw_sent_norm
            or "helping" in raw_sent_norm
            or "empower" in raw_sent_norm
            or "incidental" in raw_sent_norm
            or "esporadico" in raw_sent_norm
            or "ocasional" in raw_sent_norm
            or "eventual interface" in raw_sent_norm
            or "nao e necessario" in raw_sent_norm
            or "nao precisa dominar" in raw_sent_norm
            or "nocoes de " in raw_sent_norm
        )
        has_tech_alternatives = bool(
            _LIST_ALT_TECH_RE.search(norm_sent)
            or re.search(
                r"\b(?:java|python|react|angular|vue|node\.?js|c\+\+|c#|golang|php|ruby|rust|typescript|javascript|aws|gcp|azure|git|docker)\s+(?:or|ou)\b",
                norm_sent,
            )
        )
        if not is_non_req_context:
            techs_in_line = _extract_techs_from_text(norm_sent)
            if techs_in_line:
                if effective_mode == "preferred":
                    for tech in techs_in_line:
                        if tech not in desirable_techs:
                            desirable_techs.append(tech)
                elif effective_mode == "required" and not has_tech_alternatives:
                    for tech in techs_in_line:
                        if tech not in mandatory_techs:
                            mandatory_techs.append(tech)

    min_req_years = max(required_years_list) if required_years_list else None
    pref_years = max(preferred_years_list) if preferred_years_list else None

    if min_req_years is not None and min_req_years > 0:
        mode = ExperienceRequirementMode.REQUIRED.value
        unit_req = "ano" if min_req_years == 1 else "anos"
        summary = f"Obrigatória: {min_req_years}+ {unit_req} de experiência"
        reasons.append(f"exp:required_{min_req_years}plus_years")
    elif has_no_experience:
        mode = ExperienceRequirementMode.NONE_REQUIRED.value
        min_req_years = 0
        summary = "Sem exigência de experiência prévia"
    elif has_qual_required:
        mode = ExperienceRequirementMode.REQUIRED.value
        summary = "Exige experiência profissional prévia (sem contagem mínima de anos)"
        reasons.append("exp:required_qualitative")
    elif pref_years is not None or has_qual_preferred:
        mode = ExperienceRequirementMode.PREFERRED.value
        if pref_years is not None:
            unit_pref = "ano" if pref_years == 1 else "anos"
            summary = f"Desejável: {pref_years}+ {unit_pref} de experiência"
        else:
            summary = "Experiência desejável / diferencial"
        reasons.append("exp:preferred_only")
    else:
        mode = ExperienceRequirementMode.NOT_SPECIFIED.value
        summary = None
        reasons.append("exp:not_specified")

    return ExperienceAssessment(
        mode=mode,
        min_years=min_req_years,
        preferred_years=pref_years,
        summary=summary,
        mandatory_technologies=tuple(mandatory_techs),
        desirable_technologies=tuple(desirable_techs),
        reasons=tuple(dict.fromkeys(reasons)),
    )


_STRUCTURED_INTERNSHIP_TOKENS = frozenset(
    {"intern", "internship", "estagio", "estagiario", "estagiaria", "apprentice", "working student"}
)
_STRUCTURED_UPPER_TOKENS = frozenset(
    {
        "pleno",
        "mid",
        "mid-level",
        "mid level",
        "mid-senior",
        "intermediate",
        "senior",
        "sr",
        "especialista",
        "staff",
        "principal",
        "lead",
        "manager",
        "director",
        "management",
        "exec",
        "executive",
    }
)
_STRUCTURED_JUNIOR_TOKENS = frozenset({"junior", "jr"})
_STRUCTURED_ENTRY_TOKENS = frozenset(
    {
        "entry",
        "entry_level",
        "entry-level",
        "entry level",
        "trainee",
        "graduate",
        "early-career",
        "early career",
    }
)


def _classify_seniority_level(
    *,
    norm_title: str,
    norm_desc: str,
    tag_set: set[str],
    meta_tokens: set[str],
    has_required_senior_years: bool = False,
) -> tuple[str, str]:
    """Classifica o nível profissional independentemente de contrato e sem presumir Senior quando omisso."""
    combined_meta = tag_set | meta_tokens
    title_has_staff = bool(_STAFF_PRINCIPAL_RE.search(norm_title))
    title_has_mgmt = bool(_MANAGEMENT_RE.search(norm_title))
    title_has_senior = bool(_SENIOR_TITLE_RE.search(norm_title))
    title_has_mid = bool(_MID_LEVEL_TITLE_RE.search(norm_title))
    title_has_junior = bool(_JUNIOR_STRICT_RE.search(norm_title))
    title_has_entry = bool(_ENTRY_LEVEL_ONLY_RE.search(norm_title))
    title_has_upper = title_has_staff or title_has_mgmt or title_has_senior or title_has_mid

    if title_has_staff:
        return (SeniorityLevel.STAFF_PRINCIPAL.value, "seniority:title_staff_or_principal")
    if title_has_mgmt:
        return (SeniorityLevel.MANAGEMENT.value, "seniority:title_management_or_lead")
    if title_has_senior:
        return (SeniorityLevel.SENIOR.value, "seniority:title_senior")
    if title_has_mid:
        return (SeniorityLevel.MID_LEVEL.value, "seniority:title_mid_level")

    if _INTERNSHIP_STRONG_RE.search(norm_title):
        return (SeniorityLevel.INTERNSHIP.value, "seniority:title_internship")
    if not title_has_upper and _INTERNSHIP_BODY_PHRASE_RE.search(norm_desc):
        return (SeniorityLevel.INTERNSHIP.value, "seniority:body_internship")
    if (
        combined_meta & {"intern", "internship", "estagio", "apprentice", "working student"}
        and not title_has_upper
        and not title_has_junior
        and not has_required_senior_years
        and not (combined_meta & _STRUCTURED_UPPER_TOKENS)
        and not _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc)
    ):
        return (SeniorityLevel.INTERNSHIP.value, "seniority:meta_internship")

    if title_has_junior:
        return (SeniorityLevel.JUNIOR.value, "seniority:title_junior")
    if title_has_entry:
        return (SeniorityLevel.ENTRY_LEVEL.value, "seniority:title_entry_level")

    # Sem marcador explícito no título: verifica auto-declaração clara na descrição ou metadados estruturados
    if _MID_LEVEL_BODY_SELF_RE.search(norm_desc):
        return (SeniorityLevel.MID_LEVEL.value, "seniority:body_mid_level")
    if _SENIOR_BODY_SELF_RE.search(norm_desc):
        return (SeniorityLevel.SENIOR.value, "seniority:body_senior")
    if re.search(
        r"(?<![a-z0-9])(?:is\s+an?\s+|as\s+a\s+|for\s+an?\s+|exceptional\s+)?"
        r"(?:junior|jr\.?)\s+(?:[a-z0-9]+\s+){0,2}"
        r"(?:developer|engineer|designer|analyst|programmer|dev|qa|tester|specialist|ui)(?![a-z0-9])",
        norm_desc,
    ):
        return (SeniorityLevel.JUNIOR.value, "seniority:body_junior")
    if _JUNIOR_BODY_PHRASE_RE.search(norm_desc):
        return (SeniorityLevel.ENTRY_LEVEL.value, "seniority:body_entry_level")

    if meta_tokens & {"staff", "principal"}:
        return (SeniorityLevel.STAFF_PRINCIPAL.value, "seniority:meta_staff_principal")
    if meta_tokens & {"management", "manager", "director", "head", "lead", "executive"}:
        return (SeniorityLevel.MANAGEMENT.value, "seniority:meta_management")
    if meta_tokens & {"senior", "sr", "especialista"}:
        return (SeniorityLevel.SENIOR.value, "seniority:meta_senior")
    if meta_tokens & {"mid", "mid-level", "mid level", "pleno", "intermediate"}:
        return (SeniorityLevel.MID_LEVEL.value, "seniority:meta_mid_level")
    if (
        combined_meta & _STRUCTURED_JUNIOR_TOKENS
        and not has_required_senior_years
        and not (combined_meta & _STRUCTURED_UPPER_TOKENS)
    ):
        return (SeniorityLevel.JUNIOR.value, "seniority:meta_or_tag_junior")
    if (
        combined_meta & _STRUCTURED_ENTRY_TOKENS
        and not has_required_senior_years
        and not (combined_meta & _STRUCTURED_UPPER_TOKENS)
    ):
        return (SeniorityLevel.ENTRY_LEVEL.value, "seniority:meta_or_tag_entry_level")

    return (SeniorityLevel.UNKNOWN.value, "seniority:unspecified_unknown")


_TECH_EXTRACTION_MAP: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Java", re.compile(r"(?<![a-z0-9])java(?![a-z0-9])")),
    ("Spring Boot", re.compile(r"(?<![a-z0-9])spring\s+boot(?![a-z0-9])")),
    ("Python", re.compile(r"(?<![a-z0-9])python(?![a-z0-9])")),
    ("FastAPI", re.compile(r"(?<![a-z0-9])fastapi(?![a-z0-9])")),
    ("Django", re.compile(r"(?<![a-z0-9])django(?![a-z0-9])")),
    ("Flask", re.compile(r"(?<![a-z0-9])flask(?![a-z0-9])")),
    ("TypeScript", re.compile(r"(?<![a-z0-9])typescript(?![a-z0-9])")),
    ("JavaScript", re.compile(r"(?<![a-z0-9])javascript(?![a-z0-9])")),
    ("React", re.compile(r"(?<![a-z0-9])react(?:\.?js)?(?![a-z0-9])")),
    ("Next.js", re.compile(r"(?<![a-z0-9])next\.?js(?![a-z0-9])")),
    ("Angular", re.compile(r"(?<![a-z0-9])angular(?![a-z0-9])")),
    ("Vue", re.compile(r"(?<![a-z0-9])(?:vue(?:\.?js)?|nuxt(?:\.?js)?)(?![a-z0-9])")),
    ("Node.js", re.compile(r"(?<![a-z0-9])node\.?js(?![a-z0-9])")),
    ("NestJS", re.compile(r"(?<![a-z0-9])nest\.?js(?![a-z0-9])")),
    ("Golang", re.compile(r"(?<![a-z0-9])golang(?![a-z0-9])")),
    ("C#", re.compile(r"(?<![a-z0-9])(?:c#|csharp|dot\s*net|\.net)(?![a-z0-9])")),
    ("C++", re.compile(r"(?<![a-z0-9])c\+\+(?![a-z0-9])")),
    ("PHP", re.compile(r"(?<![a-z0-9])(?:php|laravel)(?![a-z0-9])")),
    ("Ruby", re.compile(r"(?<![a-z0-9])(?:ruby|ruby\s+on\s+rails)(?![a-z0-9])")),
    ("Rust", re.compile(r"(?<![a-z0-9])rust(?![a-z0-9])")),
    ("PostgreSQL", re.compile(r"(?<![a-z0-9])postgres(?:ql)?(?![a-z0-9])")),
    ("MySQL", re.compile(r"(?<![a-z0-9])mysql(?![a-z0-9])")),
    ("SQL", re.compile(r"(?<![a-z0-9])sql(?![a-z0-9])")),
    ("Redis", re.compile(r"(?<![a-z0-9])redis(?![a-z0-9])")),
    ("Docker", re.compile(r"(?<![a-z0-9])docker(?![a-z0-9])")),
    ("Kubernetes", re.compile(r"(?<![a-z0-9])(?:kubernetes|k8s)(?![a-z0-9])")),
    ("AWS", re.compile(r"(?<![a-z0-9])aws(?![a-z0-9])")),
    ("GCP", re.compile(r"(?<![a-z0-9])(?:gcp|google\s+cloud)(?![a-z0-9])")),
    ("Azure", re.compile(r"(?<![a-z0-9])azure(?![a-z0-9])")),
    ("Terraform", re.compile(r"(?<![a-z0-9])terraform(?![a-z0-9])")),
    ("Kafka", re.compile(r"(?<![a-z0-9])kafka(?![a-z0-9])")),
    ("GraphQL", re.compile(r"(?<![a-z0-9])graphql(?![a-z0-9])")),
    ("APIs REST", re.compile(r"(?<![a-z0-9])(?:rest(?:ful)?\s+apis?|apis?\s+rest(?:ful)?)(?![a-z0-9])")),
    ("Salesforce", re.compile(r"(?<![a-z0-9])salesforce(?![a-z0-9])")),
    ("Flutter", re.compile(r"(?<![a-z0-9])flutter(?![a-z0-9])")),
    ("Kotlin", re.compile(r"(?<![a-z0-9])kotlin(?![a-z0-9])")),
)

_EXP_PREFERRED_HEADER_RE = re.compile(
    r"^(?:#{1,4}\s*)?(?:\*\*)?(?:"
    r"preferred(?:\s+qualifications|\s+experience|\s+skills)?|"
    r"nice\s+to\s+have|nice-to-have|"
    r"desirable|desejave(?:is|l)|diferencia(?:is|l)|"
    r"bonus(?:\s+qualifications|\s+points)?|plus|optional|"
    r"vai\s+ser\s+incrivel\s+se|seria\s+(?:incrivel|legal|um\s+plus)\s+se|"
    r"e\s+um\s+diferencial|seria\s+um\s+diferencial"
    r")\b"
)
_EXP_REQUIRED_HEADER_RE = re.compile(
    r"^(?:#{1,4}\s*)?(?:\*\*)?(?:"
    r"minimum\s+qualifications|basic\s+qualifications|"
    r"required(?:\s+qualifications|\s+experience|\s+skills)?|"
    r"mandatory(?:\s+requirements)?|"
    r"requirements|requisitos(?:\s+obrigatorios)?|"
    r"obrigatorios?|what\s+you(?:\s*'ll)?\s+bring|"
    r"who\s+you\s+are|qualifications|must\s+have"
    r")\b"
)
_EXP_NEUTRAL_HEADER_RE = re.compile(
    r"^(?:#{1,4}\s*)?(?:\*\*)?(?:\d+\.\s*)?(?:"
    r"about\s+(?:the\s+job|us)|sobre\s+a\s+empresa|"
    r"responsibilities|(?:principais\s+)?responsabilidades|"
    r"what\s+you(?:\s*'ll)?\s+do|no\s+dia\s+a\s+dia|"
    r"benefits|beneficios|como\s+se\s+candidatar|how\s+to\s+apply|compensation|"
    r"tecnologias\s+e\s+ambiente|nossa\s+empresa|contratacao|labels"
    r")\b"
)
_NO_EXPERIENCE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"no\s+(?:previous\s+|prior\s+)?(?:[a-z0-9/-]+\s+){0,4}experience\s+(?:is\s+)?required|"
    r"no\s+(?:previous\s+|prior\s+)?experience\s+(?:needed|necessary)|"
    r"without\s+(?:prior\s+|previous\s+)?experience|"
    r"(?:previous|prior)\s+experience[^.\n]{0,180}\b(?:but\s+)?not\s+required|"
    r"experiencia\s+(?:profissional\s+|pratica\s+)?(?:anterior\s+|previa\s+)?nao\s+(?:e|sao)\s+(?:obrigatori[oa]s?|necessari[oa]s?|exigid[oa]s?)|"
    r"sem\s+experiencia\s+(?:previa|necessaria|exigida|comprovada)?|"
    r"nao\s+(?:exige|requer|necessita)\s+(?:de\s+)?experiencia"
    r")(?![a-z0-9])"
)
_LINE_PREFERRED_MARKER_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"preferred|preferably|preferencialmente|nice\s+to\s+have|nice-to-have|desirable|bonus|"
    r"is\s+a\s+plus|are\s+a\s+plus|would\s+be\s+a\s+plus|would\s+be\s+an\s+advantage|"
    r"sera\s+um\s+diferencial|como\s+diferencial|diferencia(?:is|l)|desejave(?:is|l)|opcional"
    r")(?![a-z0-9])"
)
_LINE_REQUIRED_MARKER_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?<!not\s)(?<!not\sbe\s)(?<!nao\s)(?<!nao\se\s)required|"
    r"(?<!not\s)mandatory|must\s+have|minimum\s+of|at\s+least|"
    r"(?<!nao\s)(?<!nao\se\s)(?<!nao\ssao\s)obrigatori[oa]s?|exigid[oa]|imprescindivel|indispensavel|"
    r"experiencia\s+(?:comprovada|solida|minima)|minimum\s+qualifications"
    r")(?![a-z0-9])"
)
_COMPANY_AGE_OR_PTO_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:for|over|nearly|more\s+than)\s+\d+\s+years?[,\s]|"
    r"^\d+\s+years?[,\s]+[a-z0-9_-]+\s+has\b|"
    r"our\s+team\s+has\b|"
    r"\b(?:years?\s+old|years?\s+in\s+business|years?\s+ago|per\s+year|a\s+year|each\s+year|once\s+per\s+year|"
    r"weeks?\s+pto|years?[,\s]+we'?ve\s+delivered|anos?\s+de\s+(?:historia|mercado|idade))"
    r")(?![a-z0-9])"
)
_YEARS_CLAUSE_RE = re.compile(
    r"(?<![a-z0-9])(\d{1,2})\s*(?:\+|[-–—]\s*\d+\+?|(?:to|a)\s+\d+\+?)?\s*"
    r"(?:years?|anos?)\s*\+?(?:\s+(?:of|de|em|com)\s+|\s+)?([^.;\n]{0,80})"
)
_DEGREE_ALT_YEARS_RE = re.compile(
    r"\b(\d{1,2})\s+(?:years?|anos?)\s+(?:of\s+|de\s+)?(?:relevant\s+)?(?:experience|experiencia)\s+(?:with|com)\s+(?:bachelor|bs|ba|graduacao)\b"
)
_QUAL_EXP_REQUIRED_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"proven\s+(?:work\s+|professional\s+|industry\s+)?(?:track\s+record|experience)|"
    r"demonstrated\s+(?:work\s+|professional\s+|industry\s+)?experience|"
    r"(?:prior|previous)\s+(?:work|professional|industry|practical)\s+experience|"
    r"experiencia\s+(?:profissional|previa|comprovada|solida|minima)\b|"
    r"(?:alguma\s+)?experiencia\s+pratica\s+previa\b|"
    r"(?:experience|experiencia)\b[^.\n]{0,60}\b(?:is\s+required|are\s+required|is\s+mandatory|obrigatori[oa]s?|exigid[oa]s?|indispensavel|imprescindivel)"
    r")(?![a-z0-9])"
)
_LIST_ALT_TECH_RE = re.compile(
    r"(?<![a-z0-9])(?:e\.?\s*g\.?|such\s+as|como|one\s+or\s+more|um\s+ou\s+mais|entre\s+elas)(?![a-z0-9])"
)
_SENIOR_BODY_SELF_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:looking\s+for|seeking|hiring|wait(?:ing)?\s+for)\s+(?:an?\s+|someone\s+)?"
    r"(?:senior|sr\.?|experienced\s+senior)(?![a-z0-9])|"
    r"someone\s+senior\s+enough|"
    r"(?:vaga|perfil|desenvolvedor)\s+(?:para\s+)?(?:nivel\s+)?senior"
    r")(?![a-z0-9])"
)
_MID_LEVEL_BODY_SELF_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:buscamos|procuramos|vaga\s+para)\s+(?:uma?\s+pessoa\s+)?(?:desenvolvedora?|dev|engenheir[oa])(?:\s+[a-z]+){0,3}\s+pleno|"
    r"nivel\s*:?\s*pleno|"
    r"(?:is\s+an?\s+|seeking\s+an?\s+|looking\s+for\s+an?\s+)mid[- ]?level"
    r")(?![a-z0-9])"
)


def _repair_mojibake(text: str) -> str:
    """Wrapper retrocompatível para o reparo conservador centralizado em `sanitization.py`."""
    return repair_mojibake(text)


def normalize_classification_text(text: str | None) -> str:
    """Normaliza acentos, caixa e pontuação preservando fronteiras lexicais determinísticas."""
    if not text:
        return ""
    plain = _HTML_TAG_RE.sub(" ", _repair_mojibake(text))
    plain = _CAMEL_BOUNDARY_RE.sub(r"\1 \2", plain)
    decomposed = unicodedata.normalize("NFKD", plain)
    ascii_folded = _COMBINING_MARKS_RE.sub("", decomposed).lower()
    ascii_folded = _GENDER_SUFFIX_RE.sub("", ascii_folded)
    return _WHITESPACE_RE.sub(" ", ascii_folded).strip()


def _strip_non_self_context(normalized_desc: str) -> str:
    cleaned = normalized_desc
    for pattern in _NON_SELF_MENTION_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return [t for t in (normalize_classification_text(tag) for tag in tags) if t]


def _detect_employment_type(
    *,
    norm_title: str,
    norm_desc: str,
    norm_tags: list[str],
    opportunity_type: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if opportunity_type == OpportunityType.INTERNSHIP.value:
        reasons.append("contract:internship_role")
        return (EmploymentType.INTERNSHIP.value, reasons)

    if _CONTRACT_CLT_RE.search(norm_title) or _CONTRACT_CLT_RE.search(norm_desc):
        reasons.append("contract:explicit_clt")
        return (EmploymentType.CLT.value, reasons)

    if _CONTRACT_FIXED_TERM_RE.search(norm_title) or _CONTRACT_FIXED_TERM_RE.search(norm_desc):
        reasons.append("contract:fixed_term_or_temporary")
        return (EmploymentType.TEMPORARY.value, reasons)

    if _FREELANCE_TITLE_RE.search(norm_title) or _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc):
        if not _CONTRACT_DUAL_RE.search(norm_desc):
            reasons.append("contract:explicit_freelance_or_independent")
            return (EmploymentType.FREELANCE.value, reasons)

    if _CONTRACT_DUAL_RE.search(norm_desc):
        reasons.append("contract:ambiguous_multiple_options")
        return (EmploymentType.UNKNOWN.value, reasons)

    if _CONTRACT_PJ_RE.search(norm_desc) or _CONTRACT_PJ_RE.search(norm_title):
        reasons.append("contract:explicit_pj_or_dedicated_contractor")
        return (EmploymentType.PJ.value, reasons)

    if (
        "contract position" in norm_desc
        and ("paid per hour" in norm_desc or "hourly" in norm_desc)
        and "permanent" not in norm_desc
    ):
        reasons.append("contract:hourly_contract_position")
        return (EmploymentType.FREELANCE.value, reasons)

    if "pj" in norm_tags:
        reasons.append("contract:tag_pj")
        return (EmploymentType.PJ.value, reasons)
    if "clt" in norm_tags:
        reasons.append("contract:tag_clt")
        return (EmploymentType.CLT.value, reasons)
    if "freelance" in norm_tags and opportunity_type == OpportunityType.FREELANCE.value:
        reasons.append("contract:tag_freelance")
        return (EmploymentType.FREELANCE.value, reasons)

    reasons.append("contract:undisclosed_unknown")
    return (EmploymentType.UNKNOWN.value, reasons)


def classify_professional_area(
    *,
    title: str | None,
    tags: list[str] | None = None,
    description: str | None = None,
    requirements: list[str] | None = None,
) -> tuple[str, tuple[str, ...], list[str]]:
    """
    Classifica a área profissional primária e especialidades secundárias de forma
    independente de senioridade e contrato, bloqueando falsos positivos por menção
    incidental de tecnologia em vagas de suporte, atendimento, vendas ou saúde.
    """
    norm_title = normalize_classification_text(title)
    if not norm_title:
        return (ProfessionalArea.UNKNOWN.value, (), ["area:missing_title"])

    norm_desc = _strip_non_self_context(normalize_classification_text(description))
    norm_reqs = " ".join(_normalize_tags(requirements))
    norm_tags = _normalize_tags(tags)
    substantive_body = f"{norm_reqs} {norm_desc}".strip()

    reasons: list[str] = []

    # 1. Domínios não-desenvolvimento verificados prioritariamente para impedir
    # que menções incidentais a linguagens/bancos ou tags ruidosas gerem falso positivo.
    if _TECH_SUPPORT_TITLE_RE.search(norm_title):
        reasons.append("area:technical_support_or_helpdesk")
        sec: list[str] = []
        if _CUSTOMER_SUPPORT_TITLE_RE.search(norm_title) or "customer service" in substantive_body:
            sec.append(ProfessionalArea.CUSTOMER_SUPPORT.value)
        return (ProfessionalArea.TECHNICAL_SUPPORT.value, tuple(sec), reasons)

    if _CUSTOMER_SUPPORT_TITLE_RE.search(norm_title):
        reasons.append("area:customer_or_client_support")
        sec = []
        if "patient" in norm_title or "healthcare" in substantive_body:
            sec.append(ProfessionalArea.HEALTHCARE.value)
        if "scheduling" in norm_title or "reservations" in norm_title:
            sec.append(ProfessionalArea.ADMINISTRATION.value)
        return (ProfessionalArea.CUSTOMER_SUPPORT.value, tuple(sec), reasons)

    if _HEALTHCARE_TITLE_RE.search(norm_title) or _HEALTHCARE_BODY_RE.search(substantive_body):
        reasons.append("area:healthcare_or_clinical")
        sec = []
        if "data manager" in norm_title or "data management" in substantive_body:
            sec.append(ProfessionalArea.DATA.value)
        return (ProfessionalArea.HEALTHCARE.value, tuple(sec), reasons)

    if _NON_DEV_OTHER_ROLE_RE.search(norm_title) or _NON_DEV_OTHER_ROLE_RE.search(substantive_body):
        reasons.append("area:non_dev_specialized_other")
        return (ProfessionalArea.OTHER.value, (), reasons)

    if _MARKETING_SALES_TITLE_RE.search(norm_title) or _MARKETING_SALES_BODY_RE.search(substantive_body):
        reasons.append("area:marketing_sales_or_commercial")
        sec = []
        if "student assistant" in norm_title or "operations" in norm_title:
            sec.append(ProfessionalArea.ADMINISTRATION.value)
        return (ProfessionalArea.MARKETING_SALES.value, tuple(sec), reasons)

    if _ADMIN_TITLE_RE.search(norm_title):
        reasons.append("area:administration_finance_hr_or_product")
        sec = []
        if "it operations" in norm_title:
            sec.append(ProfessionalArea.INFRASTRUCTURE.value)
        if "revenue cycle" in norm_title and "home health" in substantive_body:
            sec.append(ProfessionalArea.HEALTHCARE.value)
        return (ProfessionalArea.ADMINISTRATION.value, tuple(sec), reasons)

    if (
        _TECH_SUPPORT_BODY_RE.search(substantive_body)
        and not _SOFTWARE_DEV_TITLE_RE.search(norm_title)
        and not _BACKEND_TITLE_RE.search(norm_title)
        and not _FRONTEND_TITLE_RE.search(norm_title)
    ):
        reasons.append("area:technical_support_body")
        return (ProfessionalArea.TECHNICAL_SUPPORT.value, (), reasons)

    # 2. Áreas técnicas de Engenharia, Software, Dados, IA, Cloud e Infraestrutura
    detected: list[str] = []

    def _add_area(area_code: str, reason: str | None = None) -> None:
        if area_code not in detected:
            detected.append(area_code)
        if reason and reason not in reasons:
            reasons.append(reason)

    # Sinais fortes no título determinam a área primária com máxima precisão
    if _FULLSTACK_RE.search(norm_title):
        _add_area(ProfessionalArea.FULLSTACK.value, "area:title_fullstack")
        _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)
        _add_area(ProfessionalArea.BACKEND.value)
        _add_area(ProfessionalArea.FRONTEND.value)

    if _AI_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.ARTIFICIAL_INTELLIGENCE.value, "area:title_ai_ml")
        if any(w in norm_title for w in ("engineer", "developer", "software", "engenheiro")):
            _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

    if _API_INTEGRATIONS_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.API_INTEGRATIONS.value, "area:title_api_integrations")
        _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

    if _BACKEND_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.BACKEND.value, "area:title_backend")
        _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

    if _FRONTEND_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.FRONTEND.value, "area:title_frontend")
        _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

    if _DATA_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.DATA.value, "area:title_data")
        if _DATA_ENGINEERING_ROLE_RE.search(norm_title):
            _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

    if _DEVOPS_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.DEVOPS_CLOUD.value, "area:title_devops_cloud")
        if "platform and integration" in norm_title:
            _add_area(ProfessionalArea.API_INTEGRATIONS.value)
        if "kubernetes control plane" in norm_title:
            _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

    if _INFRA_TITLE_RE.search(norm_title):
        if "software engineer infrastructure" in norm_title:
            _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value, "area:title_software_infra")
            _add_area(ProfessionalArea.INFRASTRUCTURE.value)
            _add_area(ProfessionalArea.DEVOPS_CLOUD.value)
        elif "infrastructure & security" in norm_title:
            _add_area(ProfessionalArea.DEVOPS_CLOUD.value, "area:title_infra_cloud_security")
            _add_area(ProfessionalArea.INFRASTRUCTURE.value)
        else:
            _add_area(ProfessionalArea.INFRASTRUCTURE.value, "area:title_infrastructure")

    if _SOFTWARE_DEV_TITLE_RE.search(norm_title):
        _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value, "area:title_software_development")

    # Se o título é técnico/engenharia (ou tem stack clara no corpo sem ser cargo administrativo/suporte),
    # analisa o corpo substantivo para identificar especialidades (fullstack, backend, frontend, APIs, IA, dados)
    is_tech_context = bool(detected) or bool(
        re.search(
            r"(?<![a-z0-9])(?:developer|engineer|desenvolvedor|programador|engenheiro|arquitetura|estagio\s+em\s+ti)(?![a-z0-9])",
            norm_title,
        )
    )

    if is_tech_context and substantive_body:
        primary_candidate = detected[0] if detected else None
        is_pure_devops_or_infra = primary_candidate in {
            ProfessionalArea.DEVOPS_CLOUD.value,
            ProfessionalArea.INFRASTRUCTURE.value,
        } and not _SOFTWARE_DEV_TITLE_RE.search(norm_title)
        is_data_analyst = (
            primary_candidate == ProfessionalArea.DATA.value
            and not _DATA_ENGINEERING_ROLE_RE.search(norm_title)
            and not _SOFTWARE_DEV_TITLE_RE.search(norm_title)
        )

        has_fullstack_body = bool(_FULLSTACK_RE.search(substantive_body))
        has_backend_body = bool(_BACKEND_STACK_RE.search(substantive_body))
        has_frontend_body = bool(_FRONTEND_STACK_RE.search(substantive_body))

        if not is_pure_devops_or_infra and not is_data_analyst:
            if has_fullstack_body or (
                has_backend_body
                and has_frontend_body
                and ProfessionalArea.SOFTWARE_DEVELOPMENT.value in detected
            ):
                _add_area(ProfessionalArea.FULLSTACK.value, "area:body_fullstack")
                _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)
                _add_area(ProfessionalArea.BACKEND.value)
                _add_area(ProfessionalArea.FRONTEND.value)
            else:
                if has_backend_body:
                    _add_area(ProfessionalArea.BACKEND.value, "area:body_backend_stack")
                    _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)
                if has_frontend_body:
                    _add_area(ProfessionalArea.FRONTEND.value, "area:body_frontend_stack")
                    _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

        if _API_STACK_RE.search(substantive_body) and not is_data_analyst:
            _add_area(ProfessionalArea.API_INTEGRATIONS.value, "area:body_api_integrations")
            if not is_pure_devops_or_infra:
                _add_area(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

        if _AI_STACK_RE.search(substantive_body):
            _add_area(ProfessionalArea.ARTIFICIAL_INTELLIGENCE.value, "area:body_ai_ml")

        if _DATA_STACK_RE.search(substantive_body):
            _add_area(ProfessionalArea.DATA.value, "area:body_data")

        if _DEVOPS_STACK_RE.search(substantive_body) and is_pure_devops_or_infra:
            _add_area(ProfessionalArea.DEVOPS_CLOUD.value, "area:body_devops_cloud")

    # Sinais secundários a partir de tags apenas quando a vaga já é comprovadamente de desenvolvimento
    if (
        ProfessionalArea.SOFTWARE_DEVELOPMENT.value in detected
        and len(detected) == 1
        and norm_tags
    ):
        tag_set = set(norm_tags)
        if "full stack" in tag_set or "fullstack" in tag_set:
            _add_area(ProfessionalArea.FULLSTACK.value, "area:tag_fullstack")
            _add_area(ProfessionalArea.BACKEND.value)
            _add_area(ProfessionalArea.FRONTEND.value)
        if tag_set & {"backend", "python", "java", "spring boot", "fastapi", "django", "postgres", "postgresql"}:
            _add_area(ProfessionalArea.BACKEND.value, "area:tag_backend")
        if tag_set & {"front end", "frontend", "react", "vue", "angular", "typescript"}:
            _add_area(ProfessionalArea.FRONTEND.value, "area:tag_frontend")
        if tag_set & {"api", "apis"}:
            _add_area(ProfessionalArea.API_INTEGRATIONS.value, "area:tag_api")

    if detected:
        # Se a vaga começou como software_development genérico no título (ex.: "Software Engineer")
        # mas o corpo revelou claramente que é fullstack/backend/frontend/IA, promove a especialidade
        # mais específica mantendo software_development nas secundárias, exceto quando o título é "Software Engineer" puro sem foco único.
        primary = detected[0]
        if (
            primary == ProfessionalArea.SOFTWARE_DEVELOPMENT.value
            and len(detected) > 1
            and _FULLSTACK_RE.search(substantive_body)
        ):
            primary = ProfessionalArea.FULLSTACK.value
        secondary = tuple(a for a in detected if a != primary)
        return (primary, secondary, reasons)

    reasons.append("area:unknown_insufficient_evidence")
    return (ProfessionalArea.UNKNOWN.value, (), reasons)


def classify_opportunity(
    *,
    title: str | None,
    tags: list[str] | None = None,
    area_tags: list[str] | None = None,
    description: str | None = None,
    requirements: list[str] | None = None,
    metadata_levels: list[str] | None = None,
) -> ClassificationDecision:
    """
    Classifica oportunidade (`opportunity_type`), senioridade (`seniority_level`),
    experiência (`experience_*`), regime contratual (`employment_type`) e
    área profissional (`professional_area` + `secondary_areas`) de forma determinística
    e independente entre as dimensões.
    """
    norm_title = normalize_classification_text(title)
    if not norm_title:
        return ClassificationDecision(
            opportunity_type=OpportunityType.UNKNOWN.value,
            employment_type=EmploymentType.UNKNOWN.value,
            confidence="low",
            reasons=("title:missing_or_empty",),
            professional_area=ProfessionalArea.UNKNOWN.value,
            secondary_areas=(),
            seniority_level=SeniorityLevel.UNKNOWN.value,
            experience_requirement_mode=ExperienceRequirementMode.NOT_SPECIFIED.value,
        )

    norm_tags = _normalize_tags(tags)
    tag_set = set(norm_tags)
    meta_tokens = set(_normalize_tags(metadata_levels))
    norm_desc_raw = normalize_classification_text(description)
    norm_desc = _strip_non_self_context(norm_desc_raw)

    primary_area, secondary_areas, area_reasons = classify_professional_area(
        title=title,
        tags=tags if area_tags is None else area_tags,
        description=description,
        requirements=requirements,
    )
    exp_assessment = classify_experience_requirements(
        title=title,
        description=description,
        requirements=requirements,
    )
    has_required_senior_years = (
        exp_assessment.mode == ExperienceRequirementMode.REQUIRED.value
        and exp_assessment.min_years is not None
        and exp_assessment.min_years >= 3
    )
    seniority_level, seniority_reason = _classify_seniority_level(
        norm_title=norm_title,
        norm_desc=norm_desc,
        tag_set=tag_set,
        meta_tokens=meta_tokens,
        has_required_senior_years=has_required_senior_years,
    )

    title_is_senior_or_lead = bool(
        _LEADERSHIP_OR_SENIOR_RE.search(norm_title)
        or _BOARD_CREDENTIAL_RE.search(norm_title)
    )
    desc_has_senior_req = bool(
        _BOARD_CREDENTIAL_RE.search(norm_desc)
        or has_required_senior_years
        or re.search(
            r"(?<![a-z0-9])(?:looking\s+for\s+an?\s+|hiring\s+(?:\d+-\d+\s+)?|as\s+a\s+|seeking\s+an?\s+)"
            r"(?:senior|sr\.?|staff|principal|experienced|lead)\b",
            norm_desc,
        )
    )

    reasons: list[str] = [seniority_reason, *exp_assessment.reasons]

    def _finalize(opp_type: str, confidence: str) -> ClassificationDecision:
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=opp_type,
        )
        return ClassificationDecision(
            opportunity_type=opp_type,
            employment_type=emp_type,
            confidence=confidence,
            reasons=tuple(reasons + emp_reasons + area_reasons),
            professional_area=primary_area,
            secondary_areas=secondary_areas,
            seniority_level=seniority_level,
            experience_requirement_mode=exp_assessment.mode,
            experience_min_years=exp_assessment.min_years,
            experience_preferred_years=exp_assessment.preferred_years,
            experience_summary=exp_assessment.summary,
            required_technologies=exp_assessment.mandatory_technologies,
            desirable_technologies=exp_assessment.desirable_technologies,
        )

    # 1. Estágio / Programa acadêmico (somente se não houver título superior/liderança)
    if _INTERNSHIP_STRONG_RE.search(norm_title) and not title_is_senior_or_lead:
        reasons.append("title:explicit_internship_or_student_role")
        return _finalize(OpportunityType.INTERNSHIP.value, "high")

    if not title_is_senior_or_lead and _INTERNSHIP_BODY_PHRASE_RE.search(norm_desc):
        reasons.append("description:explicit_internship_or_student_phrase")
        return _finalize(OpportunityType.INTERNSHIP.value, "medium")

    if (
        (tag_set | meta_tokens) & {"intern", "internship", "estagio", "apprentice", "working student"}
        and not title_is_senior_or_lead
        and not desc_has_senior_req
        and seniority_level == SeniorityLevel.INTERNSHIP.value
        and not ((tag_set | meta_tokens) & _STRUCTURED_UPPER_TOKENS)
        and not _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc)
    ):
        reasons.append("tags:internship_without_conflict")
        return _finalize(OpportunityType.INTERNSHIP.value, "medium")

    # 2. Se o TÍTULO diz explicitamente Júnior/Entry-Level (e não diz Freelance no título),
    # preserva a categoria Júnior mesmo que o corpo mencione contratação PJ/autônoma.
    if (
        _JUNIOR_TITLE_RE.search(norm_title)
        and not _FREELANCE_TITLE_RE.search(norm_title)
        and not title_is_senior_or_lead
        and not desc_has_senior_req
    ):
        reasons.append("title:explicit_junior_or_entry_level")
        return _finalize(OpportunityType.JUNIOR.value, "high")

    # 3. Freelance / Projeto autônomo explícito
    if _FREELANCE_TITLE_RE.search(norm_title):
        reasons.append("title:explicit_freelance")
        return _finalize(OpportunityType.FREELANCE.value, "high")

    if (
        _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc)
        and not title_is_senior_or_lead
        and not _CONTRACT_DUAL_RE.search(norm_desc)
    ):
        reasons.append("description:explicit_freelance_or_independent_contractor")
        return _finalize(OpportunityType.FREELANCE.value, "high")

    if (
        "freelance" in tag_set
        and not title_is_senior_or_lead
        and not desc_has_senior_req
        and not _CONTRACT_FIXED_TERM_RE.search(norm_desc)
    ):
        reasons.append("tags:freelance_without_conflict")
        return _finalize(OpportunityType.FREELANCE.value, "medium")

    # 3. Bloqueio explícito de senioridade/liderança antes de considerar júnior
    if title_is_senior_or_lead or seniority_level in UPPER_SENIORITY_LEVELS:
        reasons.append("title:senior_lead_manager_or_specialist_role")
        return _finalize(OpportunityType.OTHER.value, "high")

    # 4. Júnior / Entrada na área (mantendo coerência estrita com seniority_level)
    if _JUNIOR_TITLE_RE.search(norm_title) and not desc_has_senior_req:
        reasons.append("title:explicit_junior_or_entry_level")
        return _finalize(OpportunityType.JUNIOR.value, "high")

    if _JUNIOR_BODY_PHRASE_RE.search(norm_desc) and not desc_has_senior_req:
        reasons.append("description:explicit_junior_or_entry_level_phrase")
        return _finalize(OpportunityType.JUNIOR.value, "medium")

    if (
        seniority_level in {SeniorityLevel.JUNIOR.value, SeniorityLevel.ENTRY_LEVEL.value}
        and not desc_has_senior_req
    ):
        reasons.append("seniority:coherent_junior_or_entry_level")
        return _finalize(OpportunityType.JUNIOR.value, "medium")

    if (
        (tag_set | meta_tokens) & {"junior", "jr", "entry_level", "entry-level", "entry level", "trainee", "graduate"}
        and not desc_has_senior_req
        and not ((tag_set | meta_tokens) & _STRUCTURED_UPPER_TOKENS)
    ):
        reasons.append("tags:junior_without_conflict")
        return _finalize(OpportunityType.JUNIOR.value, "medium")

    # 5. Caso padrão conservador: other
    reasons.append("fallback:senior_mid_or_generic_other")
    confidence = "high" if desc_has_senior_req else "medium"
    return _finalize(OpportunityType.OTHER.value, confidence)


def reconcile_structured_classification(
    decision: ClassificationDecision,
    *,
    metadata_levels: list[str] | None = None,
    metadata_job_types: list[str] | None = None,
    metadata_labels: list[str] | None = None,
) -> tuple[str, str, str]:
    """
    Aplica reforço conservador e coerente de metadados estruturados da fonte
    (`jobLevel`, `seniority`, `jobType`, `labels`) sobre `(opportunity_type, employment_type, seniority_level)`:
    - Nunca rebaixa senioridade explícita superior (`mid_level`, `senior`, `staff_principal`, `management`).
    - Nunca deixa `opportunity_type=junior` com `seniority_level=unknown`.
    - Mantém `entry_level` como `seniority_level=entry_level` + `opportunity_type=junior`.
    - Mantém `junior` como `seniority_level=junior` + `opportunity_type=junior`.
    - Mantém `internship` coerente nos três campos.
    - Nunca usa substring genérica (ex.: `"intern"` dentro de `"internal"`).
    """
    opp_type = decision.opportunity_type
    emp_type = decision.employment_type
    sen_level = decision.seniority_level

    level_tokens = set(_normalize_tags(metadata_levels))
    job_type_tokens = set(_normalize_tags(metadata_job_types))
    label_tokens = set(_normalize_tags(metadata_labels))
    all_level_tokens = level_tokens | label_tokens
    all_struct_tokens = all_level_tokens | job_type_tokens

    has_upper_signal = (
        sen_level in UPPER_SENIORITY_LEVELS
        or bool(all_level_tokens & _STRUCTURED_UPPER_TOKENS)
    )
    has_required_senior_years = (
        decision.experience_requirement_mode == ExperienceRequirementMode.REQUIRED.value
        and decision.experience_min_years is not None
        and decision.experience_min_years >= 3
    )

    # 1. Estágio estruturado (somente quando não conflita com nível superior ou >=3 anos obrigatórios)
    if (
        not has_upper_signal
        and not has_required_senior_years
        and bool(all_struct_tokens & _STRUCTURED_INTERNSHIP_TOKENS)
    ):
        opp_type = OpportunityType.INTERNSHIP.value
        emp_type = EmploymentType.INTERNSHIP.value
        sen_level = SeniorityLevel.INTERNSHIP.value
    # 2. Júnior / Entry-level estruturado (sem conflito com nível superior ou >=3 anos obrigatórios)
    elif (
        not has_upper_signal
        and not has_required_senior_years
        and opp_type == OpportunityType.OTHER.value
        and sen_level == SeniorityLevel.UNKNOWN.value
    ):
        if bool(all_level_tokens & _STRUCTURED_JUNIOR_TOKENS):
            opp_type = OpportunityType.JUNIOR.value
            sen_level = SeniorityLevel.JUNIOR.value
        elif bool(all_level_tokens & _STRUCTURED_ENTRY_TOKENS):
            opp_type = OpportunityType.JUNIOR.value
            sen_level = SeniorityLevel.ENTRY_LEVEL.value
    # 3. Freelance via label explícito quando não há conflito
    elif (
        opp_type == OpportunityType.OTHER.value
        and bool(label_tokens & {"freela", "freelance"})
        and not has_upper_signal
    ):
        opp_type = OpportunityType.FREELANCE.value
        if emp_type == EmploymentType.UNKNOWN.value:
            emp_type = EmploymentType.FREELANCE.value

    # 4. Contratos estruturados (CLT / PJ / Freelance / Temporário)
    if "clt" in label_tokens and "pj" not in label_tokens:
        emp_type = EmploymentType.CLT.value
    elif "pj" in label_tokens and "clt" not in label_tokens:
        emp_type = EmploymentType.PJ.value
    elif emp_type == EmploymentType.UNKNOWN.value:
        if bool(all_struct_tokens & {"freelance", "freela"}):
            emp_type = EmploymentType.FREELANCE.value
        elif bool(all_struct_tokens & {"contract", "contractor"}):
            emp_type = EmploymentType.PJ.value
        elif bool(all_struct_tokens & {"temporary", "temporario", "fixed-term", "fixed term"}):
            emp_type = EmploymentType.TEMPORARY.value

    # 5. Garantia final de invariante de coerência entre seniority_level e opportunity_type
    if sen_level == SeniorityLevel.INTERNSHIP.value and opp_type != OpportunityType.INTERNSHIP.value:
        opp_type = OpportunityType.INTERNSHIP.value
        emp_type = EmploymentType.INTERNSHIP.value
    elif (
        sen_level in {SeniorityLevel.JUNIOR.value, SeniorityLevel.ENTRY_LEVEL.value}
        and opp_type == OpportunityType.OTHER.value
    ):
        opp_type = OpportunityType.JUNIOR.value
    elif opp_type == OpportunityType.JUNIOR.value and sen_level == SeniorityLevel.UNKNOWN.value:
        if bool(all_level_tokens & _STRUCTURED_ENTRY_TOKENS) and not bool(all_level_tokens & _STRUCTURED_JUNIOR_TOKENS):
            sen_level = SeniorityLevel.ENTRY_LEVEL.value
        else:
            sen_level = SeniorityLevel.JUNIOR.value
    elif sen_level in UPPER_SENIORITY_LEVELS and opp_type in {
        OpportunityType.INTERNSHIP.value,
        OpportunityType.JUNIOR.value,
    }:
        opp_type = OpportunityType.OTHER.value

    return (opp_type, emp_type, sen_level)
