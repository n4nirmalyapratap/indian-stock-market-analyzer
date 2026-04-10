import { createContext, useContext, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
  toggleWithRipple: (x: number, y: number) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  setTheme: () => {},
  toggle: () => {},
  toggleWithRipple: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      return (localStorage.getItem("app-theme") as Theme) ?? "dark";
    } catch {
      return "dark";
    }
  });

  const themeRef = useRef(theme);
  themeRef.current = theme;

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    try { localStorage.setItem("app-theme", theme); } catch {}
  }, [theme]);

  function setTheme(t: Theme) { setThemeState(t); }

  function toggle() { setThemeState(t => t === "dark" ? "light" : "dark"); }

  function toggleWithRipple(x: number, y: number) {
    const next: Theme = themeRef.current === "dark" ? "light" : "dark";
    const root = document.documentElement;

    root.style.setProperty("--ripple-x", `${x}px`);
    root.style.setProperty("--ripple-y", `${y}px`);

    if (!("startViewTransition" in document)) {
      toggle();
      return;
    }

    (document as Document & { startViewTransition: (cb: () => void) => unknown })
      .startViewTransition(() => {
        flushSync(() => {
          setThemeState(next);
        });
      });
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle, toggleWithRipple }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() { return useContext(ThemeContext); }
