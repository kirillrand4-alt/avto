// Auth-контекст: хранит токен (localStorage) + профиль, ставит источник токена
// для клиента, даёт login/logout и ProtectedRoute с ролевым гейтом.

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, setTokenGetter, ApiError } from "../api/client";
import type { Principal, Role } from "../api/types";

const TOKEN_KEY = "sender_token";

interface AuthState {
  principal: Principal | null;
  loading: boolean;
  login: (username: string, password: string, totp?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);

  // источник токена для api-клиента — всегда актуальный
  useEffect(() => {
    setTokenGetter(() => token);
  }, [token]);

  // при наличии токена — подтянуть профиль (/me); протухший токен -> сброс
  useEffect(() => {
    let alive = true;
    if (!token) {
      setPrincipal(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .me()
      .then((p) => {
        if (alive) setPrincipal(p);
      })
      .catch((e) => {
        if (alive && e instanceof ApiError && e.status === 401) {
          localStorage.removeItem(TOKEN_KEY);
          setToken(null);
          setPrincipal(null);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  async function login(username: string, password: string, totp?: string) {
    const { token: t } = await api.login(username, password, totp);
    localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      /* сессия могла уже истечь — чистим локально в любом случае */
    }
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setPrincipal(null);
  }

  return (
    <AuthCtx.Provider value={{ principal, loading, login, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth вне AuthProvider");
  return ctx;
}

/** Гейт: не залогинен -> /login; роль ниже требуемой -> редирект по роли. */
export function ProtectedRoute({
  children,
  role,
}: {
  children: ReactNode;
  role?: Role;
}) {
  const { principal, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="center muted">Загрузка…</div>;
  if (!principal) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (role && principal.role !== role) {
    // продажнику недоступные экраны — редирект на его ленту
    return <Navigate to={principal.role === "manager" ? "/leads" : "/"} replace />;
  }
  return <>{children}</>;
}
