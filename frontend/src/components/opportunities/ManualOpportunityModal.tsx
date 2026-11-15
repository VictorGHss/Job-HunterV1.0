import React, { useEffect, useState } from "react";
import { Globe, PlusCircle, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { splitCommaSeparated } from "@/lib/utils";
import type {
  EmploymentType,
  Opportunity,
  OpportunityType,
  WorkMode,
} from "@/types/api";

interface ManualOpportunityModalProps {
  isOpen: boolean;
  defaultCategory?: OpportunityType;
  initialValues?: {
    title?: string;
    source_url?: string;
    description?: string;
  } | null;
  onClose: () => void;
  onCreated: (created: Opportunity) => void;
}

function isValidHttpUrl(raw: string): boolean {
  try {
    const parsed = new URL(raw.trim());
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export const ManualOpportunityModal: React.FC<ManualOpportunityModalProps> = ({
  isOpen,
  defaultCategory = "junior",
  initialValues = null,
  onClose,
  onCreated,
}) => {
  const [title, setTitle] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [opportunityType, setOpportunityType] =
    useState<OpportunityType>(defaultCategory);
  const [employmentType, setEmploymentType] =
    useState<EmploymentType>("unknown");
  const [workMode, setWorkMode] = useState<WorkMode>("remote");
  const [locationText, setLocationText] = useState("");
  const [country, setCountry] = useState("Brasil");
  const [eligibleCountriesRaw, setEligibleCountriesRaw] = useState("Brasil");
  const [technologiesRaw, setTechnologiesRaw] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [applicationUrl, setApplicationUrl] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setTitle(initialValues?.title || "");
    setSourceUrl(initialValues?.source_url || "");
    setDescription(initialValues?.description || "");
    setCompanyName("");
    setOpportunityType(defaultCategory);
    setEmploymentType(
      defaultCategory === "internship"
        ? "internship"
        : defaultCategory === "freelance"
          ? "freelance"
          : "unknown"
    );
    setWorkMode("remote");
    setLocationText("");
    setCountry("Brasil");
    setEligibleCountriesRaw("Brasil");
    setTechnologiesRaw("");
    setApplicationUrl("");
    setErrorMessage(null);
  }, [isOpen, defaultCategory, initialValues]);

  if (!isOpen) {
    return null;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setErrorMessage(null);

    if (title.trim().length < 2) {
      setErrorMessage("Informe um título válido com pelo menos 2 caracteres.");
      return;
    }

    if (!isValidHttpUrl(sourceUrl)) {
      setErrorMessage(
        "Informe uma URL pública válida iniciando com http:// ou https://."
      );
      return;
    }

    if (applicationUrl.trim() && !isValidHttpUrl(applicationUrl)) {
      setErrorMessage(
        "A URL de candidatura precisa iniciar com http:// ou https://."
      );
      return;
    }

    setSubmitting(true);
    try {
      const created = await api.opportunities.createManual({
        title: title.trim(),
        company_name: companyName.trim() || null,
        opportunity_type: opportunityType,
        employment_type: employmentType,
        work_mode: workMode,
        location_text: locationText.trim() || null,
        country: country.trim() || null,
        eligible_countries: splitCommaSeparated(eligibleCountriesRaw),
        technologies: splitCommaSeparated(technologiesRaw),
        source_url: sourceUrl.trim(),
        application_url: applicationUrl.trim() || null,
        description: description.trim() || null,
      });
      onCreated(created);
      onClose();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Não foi possível salvar a oportunidade manual.";
      setErrorMessage(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-labelledby="manual-opportunity-title"
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2
              id="manual-opportunity-title"
              className="flex items-center gap-2 text-lg font-semibold"
            >
              <PlusCircle className="h-5 w-5 text-primary" />
              Cadastrar Oportunidade Manual / Link Capturado
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Registro privado da sua conta. Por segurança (prevenção contra SSRF e
              scraping indevido), o servidor não faz download automático da URL
              informada: confirme e complemente os dados abaixo.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Fechar modal"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="manual-title">Título da oportunidade *</Label>
              <Input
                id="manual-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ex.: Estágio Backend Python ou Freela API FastAPI"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-company">Empresa ou cliente</Label>
              <Input
                id="manual-company"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Ex.: Empresa / Cliente"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-type">Categoria alvo</Label>
              <select
                id="manual-type"
                value={opportunityType}
                onChange={(e) =>
                  setOpportunityType(e.target.value as OpportunityType)
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="internship">Estágio</option>
                <option value="junior">Desenvolvedor Júnior</option>
                <option value="freelance">Freelance / Projeto</option>
                <option value="other">Outra posição técnica</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-employment">Modalidade de contrato</Label>
              <select
                id="manual-employment"
                value={employmentType}
                onChange={(e) =>
                  setEmploymentType(e.target.value as EmploymentType)
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="internship">Estágio</option>
                <option value="pj">PJ</option>
                <option value="freelance">Freelance</option>
                <option value="clt">CLT</option>
                <option value="temporary">Temporário</option>
                <option value="other">Outro</option>
                <option value="unknown">Não informado</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-work-mode">Modelo de trabalho</Label>
              <select
                id="manual-work-mode"
                value={workMode}
                onChange={(e) => setWorkMode(e.target.value as WorkMode)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="remote">Remoto</option>
                <option value="hybrid">Híbrido</option>
                <option value="onsite">Presencial</option>
                <option value="unknown">Não informado</option>
              </select>
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="manual-source-url">URL oficial da oportunidade *</Label>
              <div className="relative">
                <Globe className="pointer-events-none absolute top-3 left-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id="manual-source-url"
                  type="url"
                  className="pl-9"
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="https://empresa.com/vagas/backend"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="manual-apply-url">
                URL direta de candidatura (opcional)
              </Label>
              <Input
                id="manual-apply-url"
                type="url"
                value={applicationUrl}
                onChange={(e) => setApplicationUrl(e.target.value)}
                placeholder="https://empresa.com/apply/123"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-location">Localidade declarada</Label>
              <Input
                id="manual-location"
                value={locationText}
                onChange={(e) => setLocationText(e.target.value)}
                placeholder="Ex.: São Paulo, SP / Remoto Brasil"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-eligible-countries">
                Países / regiões elegíveis (vírgula)
              </Label>
              <Input
                id="manual-eligible-countries"
                value={eligibleCountriesRaw}
                onChange={(e) => setEligibleCountriesRaw(e.target.value)}
                placeholder="Ex.: Brasil, Worldwide"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-country">País principal</Label>
              <Input
                id="manual-country"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="Brasil"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="manual-technologies">
                Tecnologias / stack (vírgula)
              </Label>
              <Input
                id="manual-technologies"
                value={technologiesRaw}
                onChange={(e) => setTechnologiesRaw(e.target.value)}
                placeholder="Python, FastAPI, PostgreSQL"
              />
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="manual-description">
                Descrição e requisitos principais
              </Label>
              <Textarea
                id="manual-description"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Cole aqui o resumo dos requisitos técnicos, escopo ou observações importantes."
              />
            </div>
          </div>

          {errorMessage && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShieldCheck className="h-4 w-4 text-primary" />
              Visível somente no seu usuário
            </span>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancelar
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Salvando..." : "Salvar Oportunidade Privada"}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
