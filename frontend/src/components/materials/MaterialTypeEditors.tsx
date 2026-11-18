import { AlertTriangle, CheckCircle2, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import type {
  ApplicationAnswerItem,
  ApplicationAnswersStructuredContent,
  CoverLetterStructuredContent,
  FreelanceProposalStructuredContent,
  MaterialBlockProvenance,
  RecruiterMessageStructuredContent,
  ResumeManualNoteItem,
  WritingEvidenceBlock,
  WritingTextBlock,
} from "@/types/api";

const PROVENANCE_BADGE: Record<
  MaterialBlockProvenance,
  { label: string; variant: "default" | "secondary" | "outline" }
> = {
  confirmed_fact: { label: "Fato confirmado", variant: "secondary" },
  manual_edit: { label: "Editado manualmente", variant: "outline" },
  user_authored: { label: "Autoral (manual)", variant: "outline" },
};

const QUESTION_KIND_LABELS: Record<string, string> = {
  technical_experience: "Experiência técnica",
  project_example: "Projeto",
  education: "Formação",
  language: "Idioma",
  motivation: "Motivação pessoal",
  compensation: "Remuneração / Pretensão",
  availability: "Disponibilidade",
  general_personal: "Pergunta aberta / pessoal",
};

function ProvenancePill({ provenance }: { provenance: MaterialBlockProvenance }) {
  const meta = PROVENANCE_BADGE[provenance] || PROVENANCE_BADGE.user_authored;
  return (
    <Badge variant={meta.variant} className="text-[10px]">
      {meta.label}
    </Badge>
  );
}

function ManualNotesCard({
  notes,
  isMutable,
  onChange,
}: {
  notes: ResumeManualNoteItem[];
  isMutable: boolean;
  onChange: (next: ResumeManualNoteItem[]) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">
            Notas Adicionais do Usuário ({notes.length})
          </CardTitle>
          {isMutable && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                onChange([
                  ...notes,
                  {
                    id: `note-${Date.now()}`,
                    title: "Observação adicional",
                    content: "Informação autoral verificada manualmente.",
                    source_fact_keys: [],
                    provenance: "user_authored",
                  },
                ])
              }
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Adicionar nota manual
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {notes.map((note, idx) => (
          <div key={note.id} className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <Input
                aria-label={`Título da nota ${idx + 1}`}
                disabled={!isMutable}
                value={note.title}
                onChange={(e) => {
                  const next = [...notes];
                  next[idx] = { ...next[idx], title: e.target.value };
                  onChange(next);
                }}
              />
              {isMutable && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={() => onChange(notes.filter((_, i) => i !== idx))}
                  aria-label="Remover nota"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
            <textarea
              rows={2}
              aria-label={`Conteúdo da nota ${idx + 1}`}
              disabled={!isMutable}
              value={note.content}
              onChange={(e) => {
                const next = [...notes];
                next[idx] = { ...next[idx], content: e.target.value };
                onChange(next);
              }}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground"
            />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function TextBlockEditor({
  id,
  title,
  block,
  rows = 3,
  isMutable,
  onChange,
}: {
  id: string;
  title: string;
  block: WritingTextBlock;
  rows?: number;
  isMutable: boolean;
  onChange: (next: WritingTextBlock) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label htmlFor={id} className="text-sm font-semibold">
            {title}
          </Label>
          <div className="flex items-center gap-1.5">
            {block.source_fact_keys.length > 0 && (
              <Badge variant="outline" className="text-[10px]">
                {block.source_fact_keys.length} fato(s) de origem
              </Badge>
            )}
            <ProvenancePill provenance={block.provenance} />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <textarea
          id={id}
          rows={rows}
          disabled={!isMutable}
          value={block.text}
          onChange={(e) =>
            onChange({
              ...block,
              text: e.target.value,
              provenance:
                block.source_fact_keys.length > 0 ? "manual_edit" : "user_authored",
            })
          }
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground"
        />
      </CardContent>
    </Card>
  );
}

function EvidenceListEditor({
  title,
  items,
  isMutable,
  onChange,
}: {
  title: string;
  items: WritingEvidenceBlock[];
  isMutable: boolean;
  onChange: (next: WritingEvidenceBlock[]) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          {title} ({items.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Nenhum bloco selecionado para esta seção.
          </p>
        ) : (
          items.map((item, idx) => (
            <div
              key={`${item.entity_id || "manual"}-${idx}`}
              className="space-y-2 rounded-lg border border-border p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="secondary" className="text-[10px]">
                    {item.entity_type === "project"
                      ? "Projeto"
                      : item.entity_type === "experience"
                        ? "Experiência"
                        : item.entity_type || "Autoral"}
                  </Badge>
                  {item.matched_requirements.slice(0, 4).map((req) => (
                    <Badge key={req} variant="outline" className="text-[10px]">
                      {req}
                    </Badge>
                  ))}
                </div>
                <ProvenancePill provenance={item.provenance} />
              </div>
              <Input
                aria-label={`Título do destaque ${idx + 1}`}
                disabled={!isMutable}
                value={item.title}
                onChange={(e) => {
                  const next = [...items];
                  next[idx] = {
                    ...next[idx],
                    title: e.target.value,
                    provenance:
                      item.source_fact_keys.length > 0
                        ? "manual_edit"
                        : "user_authored",
                  };
                  onChange(next);
                }}
              />
              <textarea
                rows={3}
                aria-label={`Texto do destaque ${idx + 1}`}
                disabled={!isMutable}
                value={item.summary_text}
                onChange={(e) => {
                  const next = [...items];
                  next[idx] = {
                    ...next[idx],
                    summary_text: e.target.value,
                    provenance:
                      item.source_fact_keys.length > 0
                        ? "manual_edit"
                        : "user_authored",
                  };
                  onChange(next);
                }}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground"
              />
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function CoverLetterEditor({
  content,
  isMutable,
  onChange,
}: {
  content: CoverLetterStructuredContent;
  isMutable: boolean;
  onChange: (next: CoverLetterStructuredContent) => void;
}) {
  return (
    <div className="space-y-4">
      <TextBlockEditor
        id="cl-recipient"
        title="Destinatário"
        rows={1}
        block={content.recipient_line}
        isMutable={isMutable}
        onChange={(recipient_line) => onChange({ ...content, recipient_line })}
      />
      <TextBlockEditor
        id="cl-greeting"
        title="Saudação"
        rows={1}
        block={content.greeting}
        isMutable={isMutable}
        onChange={(greeting) => onChange({ ...content, greeting })}
      />
      <TextBlockEditor
        id="cl-opening"
        title="Apresentação Inicial"
        rows={3}
        block={content.opening}
        isMutable={isMutable}
        onChange={(opening) => onChange({ ...content, opening })}
      />
      <EvidenceListEditor
        title="Experiências e Projetos Relevantes"
        items={content.relevance_highlights}
        isMutable={isMutable}
        onChange={(relevance_highlights) =>
          onChange({ ...content, relevance_highlights })
        }
      />
      {content.opportunity_alignment && (
        <TextBlockEditor
          id="cl-alignment"
          title="Relação com os Requisitos da Vaga"
          rows={3}
          block={content.opportunity_alignment}
          isMutable={isMutable}
          onChange={(opportunity_alignment) =>
            onChange({ ...content, opportunity_alignment })
          }
        />
      )}
      <TextBlockEditor
        id="cl-closing"
        title="Encerramento"
        rows={3}
        block={content.closing}
        isMutable={isMutable}
        onChange={(closing) => onChange({ ...content, closing })}
      />
      <ManualNotesCard
        notes={content.manual_notes}
        isMutable={isMutable}
        onChange={(manual_notes) => onChange({ ...content, manual_notes })}
      />
    </div>
  );
}

export function RecruiterMessageEditor({
  content,
  isMutable,
  onChange,
}: {
  content: RecruiterMessageStructuredContent;
  isMutable: boolean;
  onChange: (next: RecruiterMessageStructuredContent) => void;
}) {
  const approxLength =
    (content.subject?.text ? content.subject.text.length + 12 : 0) +
    content.greeting.text.length +
    content.body.text.length +
    content.sign_off.text.length +
    6;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-foreground">Canal:</span>
          <Badge variant="secondary">{content.channel}</Badge>
        </div>
        <span className="text-muted-foreground">
          Contagem aproximada: <strong>{approxLength}</strong> caracteres
        </span>
      </div>

      {content.subject && (
        <TextBlockEditor
          id="rm-subject"
          title="Assunto sugerido"
          rows={1}
          block={content.subject}
          isMutable={isMutable}
          onChange={(subject) => onChange({ ...content, subject })}
        />
      )}
      <TextBlockEditor
        id="rm-greeting"
        title="Saudação"
        rows={1}
        block={content.greeting}
        isMutable={isMutable}
        onChange={(greeting) => onChange({ ...content, greeting })}
      />
      <TextBlockEditor
        id="rm-body"
        title="Mensagem Principal"
        rows={4}
        block={content.body}
        isMutable={isMutable}
        onChange={(body) => onChange({ ...content, body })}
      />
      <TextBlockEditor
        id="rm-signoff"
        title="Assinatura e Contatos"
        rows={3}
        block={content.sign_off}
        isMutable={isMutable}
        onChange={(sign_off) => onChange({ ...content, sign_off })}
      />
      <ManualNotesCard
        notes={content.manual_notes}
        isMutable={isMutable}
        onChange={(manual_notes) => onChange({ ...content, manual_notes })}
      />
    </div>
  );
}

export function FreelanceProposalEditor({
  content,
  isMutable,
  onChange,
}: {
  content: FreelanceProposalStructuredContent;
  isMutable: boolean;
  onChange: (next: FreelanceProposalStructuredContent) => void;
}) {
  const pendingRequiredCount = content.pending_fields.filter(
    (f) => f.required && f.status === "pending"
  ).length;

  return (
    <div className="space-y-4">
      <Card
        className={
          pendingRequiredCount > 0
            ? "border-amber-500/50 bg-amber-500/5"
            : "border-emerald-500/40 bg-emerald-500/5"
        }
      >
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm">
                {pendingRequiredCount > 0 ? (
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                )}
                Informações Comerciais & Execução ({pendingRequiredCount} obrigatória(s) pendente(s))
              </CardTitle>
              <CardDescription className="text-xs">
                Estes dados nunca são inventados automaticamente. Preencha e salve o rascunho antes de aprovar a proposta.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {content.pending_fields.map((field, idx) => (
            <div
              key={field.field_id}
              className="space-y-1.5 rounded-lg border border-border bg-background p-3 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor={`fp-field-${field.field_id}`} className="font-semibold">
                  {field.label}
                </Label>
                <div className="flex items-center gap-1.5">
                  <Badge variant={field.required ? "default" : "outline"} className="text-[10px]">
                    {field.required ? "Obrigatório" : "Opcional"}
                  </Badge>
                  <Badge
                    variant={field.status === "provided" ? "secondary" : "outline"}
                    className="text-[10px]"
                  >
                    {field.status === "provided" ? "Preenchido" : "Pendente"}
                  </Badge>
                </div>
              </div>
              <p className="text-muted-foreground">{field.question}</p>
              <Input
                id={`fp-field-${field.field_id}`}
                disabled={!isMutable}
                value={field.user_value || ""}
                placeholder="Informe o valor real para incluir na proposta"
                onChange={(e) => {
                  const val = e.target.value;
                  const nextFields = [...content.pending_fields];
                  nextFields[idx] = {
                    ...nextFields[idx],
                    user_value: val ? val : null,
                    status: val.trim() ? "provided" : "pending",
                  };
                  onChange({ ...content, pending_fields: nextFields });
                }}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <TextBlockEditor
        id="fp-intro"
        title="Apresentação"
        rows={2}
        block={content.introduction}
        isMutable={isMutable}
        onChange={(introduction) => onChange({ ...content, introduction })}
      />
      <TextBlockEditor
        id="fp-understanding"
        title="Entendimento do Projeto"
        rows={3}
        block={content.project_understanding}
        isMutable={isMutable}
        onChange={(project_understanding) =>
          onChange({ ...content, project_understanding })
        }
      />
      <EvidenceListEditor
        title="Projetos e Experiências Confirmadas"
        items={content.relevant_evidence}
        isMutable={isMutable}
        onChange={(relevant_evidence) =>
          onChange({ ...content, relevant_evidence })
        }
      />
      <TextBlockEditor
        id="fp-approach"
        title="Abordagem Técnica Sugerida"
        rows={3}
        block={content.suggested_approach}
        isMutable={isMutable}
        onChange={(suggested_approach) =>
          onChange({ ...content, suggested_approach })
        }
      />
      <TextBlockEditor
        id="fp-alignment"
        title="Pontos de Alinhamento & Condições"
        rows={3}
        block={content.alignment_points}
        isMutable={isMutable}
        onChange={(alignment_points) =>
          onChange({ ...content, alignment_points })
        }
      />
      <TextBlockEditor
        id="fp-closing"
        title="Encerramento"
        rows={2}
        block={content.closing}
        isMutable={isMutable}
        onChange={(closing) => onChange({ ...content, closing })}
      />
      <ManualNotesCard
        notes={content.manual_notes}
        isMutable={isMutable}
        onChange={(manual_notes) => onChange({ ...content, manual_notes })}
      />
    </div>
  );
}

export function ApplicationAnswersEditor({
  content,
  isMutable,
  onChange,
}: {
  content: ApplicationAnswersStructuredContent;
  isMutable: boolean;
  onChange: (next: ApplicationAnswersStructuredContent) => void;
}) {
  const updateItem = (idx: number, patch: Partial<ApplicationAnswerItem>) => {
    const next = [...content.items];
    next[idx] = { ...next[idx], ...patch };
    onChange({ ...content, items: next });
  };

  return (
    <div className="space-y-4">
      {content.items.map((item, idx) => {
        const needsUser =
          item.requires_user_input ||
          item.status === "needs_user_input" ||
          !(item.answer_text && item.answer_text.trim());
        return (
          <Card
            key={item.question_id}
            className={needsUser ? "border-amber-500/40" : undefined}
          >
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="space-y-1">
                  <CardTitle className="text-sm">
                    {idx + 1}. {item.question}
                  </CardTitle>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="outline" className="text-[10px]">
                      {QUESTION_KIND_LABELS[item.question_kind] ||
                        item.question_kind}
                    </Badge>
                    <Badge
                      variant={needsUser ? "outline" : "secondary"}
                      className="text-[10px]"
                    >
                      {item.status === "answered_from_facts"
                        ? "Baseada em fatos"
                        : item.status === "user_answered"
                          ? "Respondida manualmente"
                          : "Exige resposta sua"}
                    </Badge>
                    <ProvenancePill provenance={item.provenance} />
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              {item.follow_up_prompt && needsUser && (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-amber-800 dark:text-amber-200">
                  {item.follow_up_prompt}
                </div>
              )}

              {item.evidence_notes.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {item.evidence_notes.map((ev, eIdx) => (
                    <Badge key={eIdx} variant="secondary" className="text-[10px]">
                      Evidência: {ev}
                    </Badge>
                  ))}
                </div>
              )}

              <textarea
                rows={3}
                aria-label={`Resposta para pergunta ${idx + 1}`}
                disabled={!isMutable}
                value={item.answer_text || ""}
                placeholder="Digite sua resposta pessoal ou técnica verificada..."
                onChange={(e) => {
                  const val = e.target.value;
                  const hasText = Boolean(val.trim());
                  updateItem(idx, {
                    answer_text: val || null,
                    status: hasText ? "user_answered" : "needs_user_input",
                    requires_user_input: !hasText,
                    provenance:
                      item.source_fact_keys.length > 0 && hasText
                        ? "manual_edit"
                        : "user_authored",
                  });
                }}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground"
              />
            </CardContent>
          </Card>
        );
      })}

      <ManualNotesCard
        notes={content.manual_notes}
        isMutable={isMutable}
        onChange={(manual_notes) => onChange({ ...content, manual_notes })}
      />
    </div>
  );
}
