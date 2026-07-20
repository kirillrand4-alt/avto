import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/auth";
import { ApiError } from "../api/client";

export function Login() {
  const { login, principal } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (principal) {
    // уже залогинен — по роли
    nav(principal.role === "manager" ? "/leads" : "/", { replace: true });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await login(username.trim(), password, totp.trim() || undefined);
      // редирект решит ProtectedRoute/эффект выше после обновления principal
      nav("/", { replace: true });
    } catch (e2) {
      setErr(e2 instanceof ApiError ? "Неверный логин, пароль или код 2FA" : "Ошибка входа");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>Панель рассылки</h1>
        <p className="muted">ООО «Руспром»</p>
        <label>
          Логин
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoFocus autoComplete="username" />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" />
        </label>
        <label>
          Код 2FA <span className="muted">(если включён)</span>
          <input value={totp} onChange={(e) => setTotp(e.target.value)}
                 inputMode="numeric" placeholder="000000" />
        </label>
        {err && <div className="errorbox">{err}</div>}
        <button className="btn btn-primary" disabled={busy || !username || !password}>
          {busy ? "Вход…" : "Войти"}
        </button>
      </form>
    </div>
  );
}
