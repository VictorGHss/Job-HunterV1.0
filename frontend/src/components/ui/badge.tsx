import * as React from "react";
import { CheckCircle2, Clock, FileEdit } from "lucide-react";
import { cn } from "@/lib/utils";
import type { VerificationStatus } from "@/types/api";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "outline" | "success" | "warning";
}

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const variants: Record<NonNullable<BadgeProps["variant"]>, string> = {
    default: "bg-primary/15 text-primary border-primary/30",
    secondary: "bg-secondary text-secondary-foreground border-border",
    outline: "bg-transparent text-foreground border-border",
    success:
      "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
    warning:
      "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  if (status === "confirmed") {
    return (
      <Badge variant="success" title="Informação revisada e confirmada pelo usuário para uso futuro em candidaturas.">
        <CheckCircle2 className="h-3.5 w-3.5" />
        Confirmado pelo usuário
      </Badge>
    );
  }
  if (status === "pending_validation") {
    return (
      <Badge variant="warning" title="Informação aguardando revisão e confirmação explícita do usuário.">
        <Clock className="h-3.5 w-3.5" />
        Pendente de validação
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" title="Rascunho inicial — não será usado como fato em candidaturas até ser confirmado.">
      <FileEdit className="h-3.5 w-3.5" />
      Rascunho
    </Badge>
  );
}
