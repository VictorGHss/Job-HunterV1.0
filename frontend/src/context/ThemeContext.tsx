import React, { createContext, useContext, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";

interface ThemeContextValue {
  mode: ThemeMode;
  resolvedTheme: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
}

const STORAGE_KEY = "jh_theme_mode";

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function ThemeProvider({
  children,
  defaultMode = "system",
}: {
  children: React.ReactNode;
  defaultMode?: ThemeMode;
}) {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return defaultMode;
    const saved = window.localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    if (saved === "light" || saved === "dark" || saved === "system") {
      return saved;
    }
    return defaultMode;
  });

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() =>
    mode === "system" ? getSystemTheme() : mode
  );

  useEffect(() => {
    const root = window.document.documentElement;
    const applyTheme = (target: "light" | "dark") => {
      root.classList.remove("light", "dark");
      root.classList.add(target);
      setResolvedTheme(target);
    };

    if (mode === "system") {
      applyTheme(getSystemTheme());
      if (window.matchMedia) {
        const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        const handler = (e: MediaQueryListEvent) => {
          applyTheme(e.matches ? "dark" : "light");
        };
        mediaQuery.addEventListener("change", handler);
        return () => mediaQuery.removeEventListener("change", handler);
      }
    } else {
      applyTheme(mode);
    }
  }, [mode]);

  const setMode = (nextMode: ThemeMode) => {
    window.localStorage.setItem(STORAGE_KEY, nextMode);
    setModeState(nextMode);
  };

  return (
    <ThemeContext.Provider value={{ mode, resolvedTheme, setMode }}>
      {children}
    </ThemeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme deve ser utilizado dentro de um ThemeProvider.");
  }
  return ctx;
}
