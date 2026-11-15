import { useCallback, useEffect, useState } from "react";
import { LoginView } from "@/components/auth/LoginView";
import {
  ApplicationsSectionView,
  FreelancersSectionView,
  HomeDashboardView,
  InternshipsSectionView,
  JuniorDeveloperSectionView,
} from "@/components/dashboard/DashboardViews";
import {
  AppShell,
  type NavSection,
  type SharedTargetPayload,
} from "@/components/layout/AppShell";
import { ProfilePage } from "@/components/profile/ProfilePage";
import { ThemeProvider } from "@/context/ThemeContext";
import { api } from "@/lib/api";
import type { FullProfileBundle, User } from "@/types/api";

function detectSharedTargetFromUrl(): SharedTargetPayload | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const title = params.get("share_title") || undefined;
  const text = params.get("share_text") || undefined;
  const url = params.get("share_url") || undefined;
  if (!title && !text && !url) return null;
  return { title, text, url };
}

export function JobHunterApp() {
  const [user, setUser] = useState<User | null>(null);
  const [bundle, setBundle] = useState<FullProfileBundle | null>(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [activeSection, setActiveSection] = useState<NavSection>("inicio");
  const [sharedPayload, setSharedPayload] =
    useState<SharedTargetPayload | null>(() => detectSharedTargetFromUrl());

  const loadBundle = useCallback(async () => {
    const data = await api.profile.getBundle();
    setBundle(data);
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const session = await api.auth.me();
        if (!mounted) return;
        setUser(session.user);
        const profileData = await api.profile.getBundle();
        if (!mounted) return;
        setBundle(profileData);
      } catch {
        if (mounted) {
          setUser(null);
          setBundle(null);
        }
      } finally {
        if (mounted) {
          setLoadingAuth(false);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const handleLoginSuccess = async (loggedUser: User) => {
    setUser(loggedUser);
    await loadBundle();
  };

  const handleLogout = async () => {
    try {
      await api.auth.logout();
    } finally {
      setUser(null);
      setBundle(null);
      setActiveSection("inicio");
    }
  };

  if (loadingAuth) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
        <div className="text-center space-y-2">
          <div className="h-8 w-8 mx-auto rounded-full border-2 border-primary border-t-transparent animate-spin" />
          <p className="text-sm text-muted-foreground">
            Inicializando Job Hunter...
          </p>
        </div>
      </div>
    );
  }

  if (!user || !bundle) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <AppShell
      user={user}
      activeSection={activeSection}
      onSelectSection={setActiveSection}
      onLogout={handleLogout}
      sharedPayload={sharedPayload}
      onDismissShared={() => setSharedPayload(null)}
    >
      {activeSection === "inicio" && (
        <HomeDashboardView
          bundle={bundle}
          onNavigate={setActiveSection}
        />
      )}
      {activeSection === "estagios" && (
        <InternshipsSectionView
          bundle={bundle}
          onNavigate={setActiveSection}
        />
      )}
      {activeSection === "junior" && (
        <JuniorDeveloperSectionView
          bundle={bundle}
          onNavigate={setActiveSection}
        />
      )}
      {activeSection === "freelancers" && (
        <FreelancersSectionView
          bundle={bundle}
          onNavigate={setActiveSection}
        />
      )}
      {activeSection === "candidaturas" && (
        <ApplicationsSectionView
          bundle={bundle}
          onNavigate={setActiveSection}
        />
      )}
      {activeSection === "perfil" && (
        <ProfilePage bundle={bundle} onRefresh={loadBundle} />
      )}
    </AppShell>
  );
}

export default function App() {
  return (
    <ThemeProvider defaultMode="system">
      <JobHunterApp />
    </ThemeProvider>
  );
}
