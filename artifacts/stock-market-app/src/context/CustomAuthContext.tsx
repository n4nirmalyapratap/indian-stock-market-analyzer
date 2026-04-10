import { createContext, useContext, useState, useCallback, ReactNode } from "react";

export interface CustomUser {
  id: string;
  email: string;
  name: string;
}

interface CustomAuthCtx {
  user: CustomUser | null;
  token: string | null;
  isLoaded: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

const CustomAuthContext = createContext<CustomAuthCtx | null>(null);

const TOKEN_KEY = "custom_auth_token";
const USER_KEY  = "custom_auth_user";

function readStored(): { user: CustomUser | null; token: string | null } {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const raw   = localStorage.getItem(USER_KEY);
    if (token && raw) return { token, user: JSON.parse(raw) };
  } catch {}
  return { user: null, token: null };
}

export function CustomAuthProvider({ children }: { children: ReactNode }) {
  const stored = readStored();
  const [token, setToken] = useState<string | null>(stored.token);
  const [user,  setUser]  = useState<CustomUser | null>(stored.user);

  const _persist = (t: string, u: CustomUser) => {
    localStorage.setItem(TOKEN_KEY, t);
    localStorage.setItem(USER_KEY, JSON.stringify(u));
    setToken(t);
    setUser(u);
  };

  const _clear = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  };

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
    _persist(data.token, data.user);
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const res = await fetch("/api/auth/register", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ email, password, name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Registration failed");
    _persist(data.token, data.user);
  }, []);

  const logout = useCallback(() => _clear(), []);

  return (
    <CustomAuthContext.Provider value={{ user, token, isLoaded: true, login, register, logout }}>
      {children}
    </CustomAuthContext.Provider>
  );
}

export function useCustomAuth(): CustomAuthCtx {
  const ctx = useContext(CustomAuthContext);
  if (!ctx) throw new Error("useCustomAuth must be used within CustomAuthProvider");
  return ctx;
}
