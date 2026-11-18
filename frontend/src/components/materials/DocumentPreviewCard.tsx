import { AlertTriangle } from "lucide-react";

import type {
  AnyMaterialStructuredContent,
  ApplicationAnswersStructuredContent,
  CoverLetterStructuredContent,
  DocumentTemplateId,
  FreelanceProposalStructuredContent,
  MaterialTargetLanguage,
  RecruiterMessageStructuredContent,
  ResumeHeaderSection,
  ResumeManualNoteItem,
  ResumeStructuredContent,
} from "@/types/api";

function isSafeHttpUrl(url: string | null | undefined): url is string {
  if (!url) return false;
  return /^https?:\/\//i.test(url.trim());
}

function isCoverLetter(
  c: AnyMaterialStructuredContent
): c is CoverLetterStructuredContent {
  return "material_type" in c && c.material_type === "cover_letter";
}

function isRecruiterMessage(
  c: AnyMaterialStructuredContent
): c is RecruiterMessageStructuredContent {
  return "material_type" in c && c.material_type === "recruiter_message";
}

function isFreelanceProposal(
  c: AnyMaterialStructuredContent
): c is FreelanceProposalStructuredContent {
  return "material_type" in c && c.material_type === "freelance_proposal";
}

function isApplicationAnswers(
  c: AnyMaterialStructuredContent
): c is ApplicationAnswersStructuredContent {
  return "material_type" in c && c.material_type === "application_answers";
}

function getPreviewLabels(lang: MaterialTargetLanguage | string) {
  if (lang === "en") {
    return {
      draftBanner: "UNAPPROVED DRAFT",
      targetRole: "Target Role",
      summary: "Professional Summary",
      experiences: "Professional Experience",
      projects: "Projects",
      education: "Education",
      skills: "Technical Skills",
      languages: "Languages",
      manualNotes: "Additional Notes",
      relevantExperience: "Relevant Experience and Projects",
      opportunityAlignment: "Alignment with Role Requirements",
      projectUnderstanding: "Project Understanding",
      suggestedApproach: "Suggested Technical Approach",
      commercialTerms: "Commercial and Execution Terms",
      alignmentClosing: "Alignment Notes",
      recruiterTitle: "Recruiter Message",
      answersTitle: "Application Question Responses",
      subject: "Subject",
      channel: "Channel",
      technologies: "Technologies",
      verifiedResults: "Verified results",
      parameterCol: "Parameter",
      valueCol: "Confirmed Detail",
    };
  }
  return {
    draftBanner: "RASCUNHO NÃO APROVADO",
    targetRole: "Direcionamento para a Vaga",
    summary: "Resumo Profissional",
    experiences: "Experiência Profissional",
    projects: "Projetos",
    education: "Formação Acadêmica",
    skills: "Habilidades Técnicas",
    languages: "Idiomas",
    manualNotes: "Notas Adicionais",
    relevantExperience: "Experiências e Projetos Relevantes",
    opportunityAlignment: "Relação com os Requisitos da Vaga",
    projectUnderstanding: "Entendimento do Projeto",
    suggestedApproach: "Abordagem Técnica Sugerida",
    commercialTerms: "Condições Comerciais e Execução",
    alignmentClosing: "Pontos de Alinhamento",
    recruiterTitle: "Mensagem para Recrutador",
    answersTitle: "Respostas para Candidatura",
    subject: "Assunto",
    channel: "Canal",
    technologies: "Tecnologias",
    verifiedResults: "Resultados verificados",
    parameterCol: "Parâmetro",
    valueCol: "Informação Definida",
  };
}

function SectionHeading({
  title,
  template,
}: {
  title: string;
  template: DocumentTemplateId;
}) {
  const isClassic = template === "classic_ats";
  return (
    <h3
      className={`mt-4 border-b pb-1 text-xs font-bold tracking-wide ${
        isClassic
          ? "border-[#9CA3AF] uppercase text-[#111827]"
          : "border-[#CBD5E1] text-[#0F3D5E]"
      }`}
    >
      {title}
    </h3>
  );
}

function HeaderPreview({
  header,
  fallbackTitle,
  template,
}: {
  header: ResumeHeaderSection;
  fallbackTitle: string;
  template: DocumentTemplateId;
}) {
  const isClassic = template === "classic_ats";
  const contacts = [header.location_text, header.email, header.phone].filter(
    (v): v is string => Boolean(v && v.trim())
  );
  const links = header.links.filter((lk) => isSafeHttpUrl(lk.url));

  return (
    <header className="space-y-1 border-b border-slate-200 pb-3">
      <h2
        className={`text-lg font-bold leading-tight ${
          isClassic ? "text-[#111827]" : "text-[#0F3D5E]"
        }`}
      >
        {header.full_name || fallbackTitle}
      </h2>
      {header.professional_title && (
        <p className="text-xs font-medium text-[#4B5563]">
          {header.professional_title}
        </p>
      )}
      {(contacts.length > 0 || links.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[#4B5563]">
          {contacts.map((item, idx) => (
            <span key={idx}>
              {idx > 0 && " | "}
              {item}
            </span>
          ))}
          {links.map((lk, idx) => (
            <span key={lk.url}>
              {(contacts.length > 0 || idx > 0) && " | "}
              <a
                href={lk.url}
                target="_blank"
                rel="noopener noreferrer"
                className={`underline ${
                  isClassic ? "text-[#1D4ED8]" : "text-[#0F3D5E]"
                }`}
              >
                {lk.label || lk.url}
              </a>
            </span>
          ))}
        </div>
      )}
    </header>
  );
}

function ManualNotesPreview({
  notes,
  title,
  template,
}: {
  notes: ResumeManualNoteItem[];
  title: string;
  template: DocumentTemplateId;
}) {
  if (notes.length === 0) return null;
  return (
    <section>
      <SectionHeading title={title} template={template} />
      <div className="mt-2 space-y-2">
        {notes.map((n) => (
          <div key={n.id} className="space-y-0.5 text-xs">
            <div className="font-semibold text-[#111827]">{n.title}</div>
            <p className="whitespace-pre-line text-[#1F2937]">{n.content}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function DocumentPreviewCard({
  content,
  template,
  isDraft,
}: {
  content: AnyMaterialStructuredContent;
  template: DocumentTemplateId;
  isDraft: boolean;
}) {
  const labels = getPreviewLabels(content.language);
  const isClassic = template === "classic_ats";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span>
          Pré-visualização estrutural ({isClassic ? "Classic ATS" : "Modern Minimalist"})
          · A paginação exata e os metadados finais são aplicados no PDF/DOCX gerado no servidor.
        </span>
      </div>

      <article
        aria-label={`Pré-visualização documental (${template})`}
        className={`relative overflow-hidden rounded-xl border bg-white p-5 text-[#1F2937] shadow-sm sm:p-7 ${
          isClassic ? "border-slate-300 font-sans" : "border-slate-200 font-sans"
        }`}
      >
        {isDraft && (
          <div className="mb-4 flex items-center justify-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-[11px] font-bold tracking-wider text-amber-800">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>{labels.draftBanner}</span>
          </div>
        )}

        {isCoverLetter(content) ? (
          <div className="space-y-3 text-xs leading-relaxed">
            <HeaderPreview
              header={content.header}
              fallbackTitle="Carta de Apresentação"
              template={template}
            />
            <p className="text-[#4B5563]">{content.recipient_line.text}</p>
            <p className="font-medium text-[#111827]">{content.greeting.text}</p>
            <p className="whitespace-pre-line">{content.opening.text}</p>
            {content.relevance_highlights.length > 0 && (
              <section>
                <SectionHeading
                  title={labels.relevantExperience}
                  template={template}
                />
                <ul className="mt-2 list-disc space-y-1.5 pl-4">
                  {content.relevance_highlights.map((item, idx) => (
                    <li key={idx}>
                      <strong>{item.title}:</strong> {item.summary_text}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {content.opportunity_alignment && (
              <section>
                <SectionHeading
                  title={labels.opportunityAlignment}
                  template={template}
                />
                <p className="mt-2 whitespace-pre-line">
                  {content.opportunity_alignment.text}
                </p>
              </section>
            )}
            <p className="whitespace-pre-line pt-2">{content.closing.text}</p>
            <ManualNotesPreview
              notes={content.manual_notes}
              title={labels.manualNotes}
              template={template}
            />
          </div>
        ) : isRecruiterMessage(content) ? (
          <div className="space-y-3 text-xs leading-relaxed">
            <div className="border-b border-slate-200 pb-2">
              <h2
                className={`text-base font-bold ${
                  isClassic ? "text-[#111827]" : "text-[#0F3D5E]"
                }`}
              >
                {labels.recruiterTitle}
              </h2>
              <p className="text-[11px] text-[#4B5563]">
                {labels.channel}: {content.channel}
              </p>
            </div>
            {content.channel === "email" && content.subject && (
              <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                <strong>{labels.subject}:</strong> {content.subject.text}
              </div>
            )}
            <p className="font-medium">{content.greeting.text}</p>
            <p className="whitespace-pre-line">{content.body.text}</p>
            <p className="whitespace-pre-line pt-1">{content.sign_off.text}</p>
            <ManualNotesPreview
              notes={content.manual_notes}
              title={labels.manualNotes}
              template={template}
            />
          </div>
        ) : isFreelanceProposal(content) ? (
          <div className="space-y-3 text-xs leading-relaxed">
            <HeaderPreview
              header={content.header}
              fallbackTitle="Proposta Técnica Freelance"
              template={template}
            />
            <p className="whitespace-pre-line">{content.introduction.text}</p>
            <section>
              <SectionHeading
                title={labels.projectUnderstanding}
                template={template}
              />
              <p className="mt-2 whitespace-pre-line">
                {content.project_understanding.text}
              </p>
            </section>
            {content.relevant_evidence.length > 0 && (
              <section>
                <SectionHeading
                  title={labels.relevantExperience}
                  template={template}
                />
                <ul className="mt-2 list-disc space-y-1.5 pl-4">
                  {content.relevant_evidence.map((ev, idx) => (
                    <li key={idx}>
                      <strong>{ev.title}:</strong> {ev.summary_text}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <section>
              <SectionHeading
                title={labels.suggestedApproach}
                template={template}
              />
              <p className="mt-2 whitespace-pre-line">
                {content.suggested_approach.text}
              </p>
            </section>
            {content.pending_fields.some(
              (f) => f.status === "provided" && f.user_value
            ) && (
              <section>
                <SectionHeading
                  title={labels.commercialTerms}
                  template={template}
                />
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full border-collapse border border-slate-300 text-xs">
                    <thead>
                      <tr className="bg-slate-100 text-left">
                        <th className="border border-slate-300 px-2.5 py-1.5 font-semibold">
                          {labels.parameterCol}
                        </th>
                        <th className="border border-slate-300 px-2.5 py-1.5 font-semibold">
                          {labels.valueCol}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {content.pending_fields
                        .filter((f) => f.status === "provided" && f.user_value)
                        .map((f) => (
                          <tr key={f.field_id}>
                            <td className="border border-slate-300 px-2.5 py-1.5 font-medium">
                              {f.label}
                            </td>
                            <td className="border border-slate-300 px-2.5 py-1.5">
                              {f.user_value}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
            {content.alignment_points.text && (
              <section>
                <SectionHeading
                  title={labels.alignmentClosing}
                  template={template}
                />
                <p className="mt-2 whitespace-pre-line">
                  {content.alignment_points.text}
                </p>
              </section>
            )}
            <p className="whitespace-pre-line pt-2">{content.closing.text}</p>
            <ManualNotesPreview
              notes={content.manual_notes}
              title={labels.manualNotes}
              template={template}
            />
          </div>
        ) : isApplicationAnswers(content) ? (
          <div className="space-y-3 text-xs leading-relaxed">
            <h2
              className={`border-b border-slate-200 pb-2 text-base font-bold ${
                isClassic ? "text-[#111827]" : "text-[#0F3D5E]"
              }`}
            >
              {labels.answersTitle}
            </h2>
            {content.items.map((item, idx) => (
              <div
                key={item.question_id}
                className="space-y-1 border-b border-slate-100 pb-2.5 last:border-b-0"
              >
                <div className="font-semibold text-[#111827]">
                  {idx + 1}. {item.question}
                </div>
                {item.answer_text ? (
                  <p className="whitespace-pre-line text-[#1F2937]">
                    {item.answer_text}
                  </p>
                ) : (
                  <p className="italic text-amber-700">
                    {item.follow_up_prompt || "Pendente de resposta do candidato."}
                  </p>
                )}
              </div>
            ))}
            <ManualNotesPreview
              notes={content.manual_notes}
              title={labels.manualNotes}
              template={template}
            />
          </div>
        ) : (
          <ResumePreviewBody
            content={content as ResumeStructuredContent}
            template={template}
            labels={labels}
          />
        )}
      </article>
    </div>
  );
}

function ResumePreviewBody({
  content,
  template,
  labels,
}: {
  content: ResumeStructuredContent;
  template: DocumentTemplateId;
  labels: ReturnType<typeof getPreviewLabels>;
}) {
  const isClassic = template === "classic_ats";
  const skillsGrouped = content.skills.reduce<
    Record<string, ResumeStructuredContent["skills"]>
  >((acc, sk) => {
    if (!acc[sk.category]) acc[sk.category] = [];
    acc[sk.category].push(sk);
    return acc;
  }, {});

  return (
    <div className="space-y-2 text-xs leading-relaxed">
      <HeaderPreview
        header={content.header}
        fallbackTitle="Currículo Profissional"
        template={template}
      />

      {content.target_alignment && (
        <section>
          <SectionHeading title={labels.targetRole} template={template} />
          <p className="mt-1.5 font-medium">
            {content.target_alignment.target_role}
            {content.target_alignment.company_name
              ? ` — ${content.target_alignment.company_name}`
              : ""}
          </p>
          {content.target_alignment.alignment_note && (
            <p className="text-[#4B5563]">
              {content.target_alignment.alignment_note}
            </p>
          )}
        </section>
      )}

      {content.summary && (
        <section>
          <SectionHeading title={labels.summary} template={template} />
          <p className="mt-1.5 whitespace-pre-line">{content.summary.text}</p>
        </section>
      )}

      {content.experiences.length > 0 && (
        <section>
          <SectionHeading title={labels.experiences} template={template} />
          <div className="mt-2 space-y-2.5">
            {content.experiences.map((exp, idx) => (
              <div key={`${exp.entity_id || "exp"}-${idx}`} className="space-y-0.5">
                <div className="font-semibold text-[#111827]">
                  {exp.role} — {exp.company}
                </div>
                {exp.period_label && (
                  <div className="text-[11px] italic text-[#4B5563]">
                    {exp.period_label}
                  </div>
                )}
                {exp.description && (
                  <p className="whitespace-pre-line">{exp.description}</p>
                )}
                {exp.technologies.length > 0 && (
                  <p className="text-[11px] text-[#4B5563]">
                    <strong>{labels.technologies}:</strong>{" "}
                    {exp.technologies.join(", ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {content.projects.length > 0 && (
        <section>
          <SectionHeading title={labels.projects} template={template} />
          <div className="mt-2 space-y-2.5">
            {content.projects.map((proj, idx) => (
              <div key={`${proj.entity_id || "proj"}-${idx}`} className="space-y-0.5">
                <div className="font-semibold text-[#111827]">
                  {proj.name}
                  {proj.role ? ` (${proj.role})` : ""}
                </div>
                {proj.description && (
                  <p className="whitespace-pre-line">{proj.description}</p>
                )}
                {proj.verified_results && (
                  <p className="text-[11px]">
                    <strong>{labels.verifiedResults}:</strong>{" "}
                    {proj.verified_results}
                  </p>
                )}
                {proj.links.filter((lk) => isSafeHttpUrl(lk.url)).length > 0 && (
                  <div className="flex flex-wrap gap-2 text-[11px]">
                    {proj.links
                      .filter((lk) => isSafeHttpUrl(lk.url))
                      .map((lk) => (
                        <a
                          key={lk.url}
                          href={lk.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`underline ${
                            isClassic ? "text-[#1D4ED8]" : "text-[#0F3D5E]"
                          }`}
                        >
                          {lk.label || lk.url}
                        </a>
                      ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {content.education.length > 0 && (
        <section>
          <SectionHeading title={labels.education} template={template} />
          <ul className="mt-1.5 list-disc space-y-1 pl-4">
            {content.education.map((edu, idx) => (
              <li key={`${edu.entity_id || "edu"}-${idx}`}>
                <strong>{edu.course}</strong> — {edu.institution} (
                {edu.status_label})
                {edu.current_semester ? ` · ${edu.current_semester}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.skills.length > 0 && (
        <section>
          <SectionHeading title={labels.skills} template={template} />
          <ul className="mt-1.5 list-disc space-y-1 pl-4">
            {Object.entries(skillsGrouped).map(([cat, list]) => (
              <li key={cat}>
                <strong>{cat}:</strong>{" "}
                {list.map((it) => `${it.name} (${it.proficiency_label})`).join(", ")}
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.languages.length > 0 && (
        <section>
          <SectionHeading title={labels.languages} template={template} />
          <ul className="mt-1.5 list-disc space-y-1 pl-4">
            {content.languages.map((lg, idx) => (
              <li key={`${lg.entity_id || "lg"}-${idx}`}>
                <strong>{lg.language_name}:</strong> {lg.proficiency_label}
                {lg.cefr_level ? ` · ${lg.cefr_level}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      <ManualNotesPreview
        notes={content.manual_notes}
        title={labels.manualNotes}
        template={template}
      />
    </div>
  );
}
