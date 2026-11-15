import React, { useState } from "react";
import { Briefcase, Lock, ShieldCheck, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { api } from "@/lib/api";
import type { User } from "@/types/api";

interface LoginViewProps {
  onLoginSuccess: (user: User) => void;
}

export function LoginView({ onLoginSuccess }: LoginViewProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const session = await api.auth.login(email, password);
      onLoginSuccess(session.user);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Falha ao autenticar. Verifique suas credenciais."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-between bg-background text-foreground p-4 sm:p-6">
      <header className="w-full max-w-5xl mx-auto flex items-center justify-between py-2">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center text-primary">
            <Briefcase className="h-5 w-5" />
          </div>
          <div>
            <span className="font-bold tracking-tight text-base">
              Job Hunter
            </span>
            <span className="ml-2 rounded-md bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">
              Fase 01
            </span>
          </div>
        </div>
        <ThemeToggle />
      </header>

      <main className="w-full max-w-md mx-auto my-auto py-8">
        <Card className="border-border/80">
          <CardHeader className="space-y-2">
            <div className="inline-flex items-center gap-1.5 text-xs font-medium text-primary">
              <ShieldCheck className="h-4 w-4" />
              Acesso Autenticado & Isolado por Usuário
            </div>
            <CardTitle className="text-2xl">Entrar no Job Hunter</CardTitle>
            <CardDescription>
              Plataforma de gestão de perfil profissional, análise de vagas e
              preparação supervisionada de candidaturas.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {error && (
              <div
                role="alert"
                className="rounded-lg border border-destructive/40 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive"
              >
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="login-email">E-mail</Label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="seu@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="login-password">Senha</Label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <Button
                type="submit"
                className="w-full"
                disabled={submitting}
              >
                <Lock className="h-4 w-4" />
                {submitting ? "Autenticando..." : "Acessar Plataforma"}
              </Button>
            </form>

            <div className="rounded-lg border border-border bg-muted/50 p-3.5 text-xs text-muted-foreground space-y-1.5">
              <div className="flex items-center gap-1.5 font-medium text-foreground">
                <Terminal className="h-3.5 w-3.5 text-primary" />
                Cadastro público desabilitado nesta versão
              </div>
              <p>
                Por segurança, não há registro aberto nem credenciais padrão.
                Provisione sua conta administrativa via CLI com Argon2id:
              </p>
              <code className="block rounded bg-background/80 p-2 font-mono text-[11px] text-foreground overflow-x-auto">
                python -m app.cli create-admin --email voce@dominio.com
                --display-name "Seu Nome"
              </code>
            </div>
          </CardContent>
        </Card>
      </main>

      <footer className="w-full max-w-5xl mx-auto text-center text-xs text-muted-foreground py-2">
        Job Hunter • Hostname planejado: https://jobhunter.ctrls.dev.br
      </footer>
    </div>
  );
}
