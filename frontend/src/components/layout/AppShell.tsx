import React from "react";
import {
  Briefcase,
  Code2,
  FileCheck2,
  Globe2,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  Share2,
  UserCircle2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { cn } from "@/lib/utils";
import type { User } from "@/types/api";

export type NavSection =
  | "inicio"
  | "estagios"
  | "junior"
  | "freelancers"
  | "candidaturas"
  | "perfil";

interface NavItem {
  id: NavSection;
  label: string;
  shortLabel: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  {
    id: "inicio",
    label: "Início",
    shortLabel: "Início",
    icon: LayoutDashboard,
  },
  {
    id: "estagios",
    label: "Estágios",
    shortLabel: "Estágios",
    icon: GraduationCap,
  },
  {
    id: "junior",
    label: "Desenvolvedor Júnior",
    shortLabel: "Dev Júnior",
    icon: Code2,
  },
  {
    id: "freelancers",
    label: "Freelancers",
    shortLabel: "Freelance",
    icon: Globe2,
  },
  {
    id: "candidaturas",
    label: "Candidaturas",
    shortLabel: "Candidaturas",
    icon: FileCheck2,
  },
  {
    id: "perfil",
    label: "Perfil",
    shortLabel: "Perfil",
    icon: UserCircle2,
  },
];

export interface SharedTargetPayload {
  title?: string;
  text?: string;
  url?: string;
}

interface AppShellProps {
  user: User;
  activeSection: NavSection;
  onSelectSection: (section: NavSection) => void;
  onLogout: () => void;
  sharedPayload: SharedTargetPayload | null;
  onDismissShared: () => void;
  children: React.ReactNode;
}

export function AppShell({
  user,
  activeSection,
  onSelectSection,
  onLogout,
  sharedPayload,
  onDismissShared,
  children,
}: AppShellProps) {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground pb-20 lg:pb-0">
      {/* Topbar */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/90 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center text-primary shrink-0">
              <Briefcase className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold tracking-tight text-base">
                  Job Hunter
                </span>
                <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-semibold text-primary">
                  Fase 01
                </span>
              </div>
              <p className="text-xs text-muted-foreground hidden sm:block">
                Fundação arquitetural & Perfil profissional central
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <ThemeToggle />
            <div className="hidden md:flex flex-col items-end text-xs">
              <span className="font-medium text-foreground">
                {user.display_name}
              </span>
              <span className="text-muted-foreground">{user.email}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onLogout}
              title="Encerrar sessão com segurança"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Sair</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Main Layout */}
      <div className="flex-1 max-w-7xl w-full mx-auto flex gap-6 px-4 sm:px-6 py-6">
        {/* Desktop Sidebar */}
        <aside
          aria-label="Navegação principal"
          className="hidden lg:flex w-60 shrink-0 flex-col gap-1.5"
        >
          <div className="rounded-xl border border-border bg-card p-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectSection(item.id)}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors text-left",
                    isActive
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          <div className="rounded-xl border border-border bg-card p-4 text-xs text-muted-foreground space-y-2 mt-2">
            <p className="font-semibold text-foreground">
              Regra Fundamental de IA
            </p>
            <p>
              Nenhuma experiência, tecnologia, métrica ou competência será
              inventada. Apenas dados{" "}
              <strong className="text-foreground">Confirmados</strong> pelo
              usuário poderão integrar futuras candidaturas.
            </p>
          </div>
        </aside>

        {/* Content Area */}
        <main className="flex-1 min-w-0 space-y-6">
          {sharedPayload && (
            <div className="rounded-xl border border-primary/40 bg-primary/10 p-4 flex items-start justify-between gap-4">
              <div className="space-y-1 text-sm">
                <div className="flex items-center gap-2 font-semibold text-primary">
                  <Share2 className="h-4 w-4" />
                  Link recebido via Web Share Target (PWA)
                </div>
                {sharedPayload.title && (
                  <p>
                    <strong>Título:</strong> {sharedPayload.title}
                  </p>
                )}
                {sharedPayload.url && (
                  <p className="break-all">
                    <strong>URL:</strong> {sharedPayload.url}
                  </p>
                )}
                {sharedPayload.text && (
                  <p>
                    <strong>Texto:</strong> {sharedPayload.text}
                  </p>
                )}
                <p className="text-xs text-muted-foreground pt-1">
                  A estrutura PWA de recebimento já está pronta. A análise
                  automatizada de vagas compartilhadas será ativada na fase de
                  integração com o motor de oportunidades.
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={onDismissShared}
                aria-label="Fechar aviso de compartilhamento"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}

          {children}
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      <nav
        aria-label="Navegação móvel"
        className="lg:hidden fixed bottom-0 inset-x-0 z-30 border-t border-border bg-card/95 backdrop-blur px-2 py-1.5"
      >
        <div className="grid grid-cols-6 gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectSection(item.id)}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex flex-col items-center justify-center rounded-lg py-1.5 px-1 text-[11px] font-medium transition-colors",
                  isActive
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4 mb-0.5" />
                <span className="truncate max-w-full">{item.shortLabel}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
