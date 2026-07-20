// Роутер: все 23 экрана SITE-DESIGN. Живые — компоненты; бэклог — честная
// заглушка BacklogStub. Auth-гейт и ролевые редиректы через ProtectedRoute.

import { Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute } from "./context/auth";
import { Layout } from "./components/Layout";
import { BacklogStub } from "./components/ui";
import { SCREENS } from "./lib/screens";
import { Login } from "./screens/Login";
import { Dashboard } from "./screens/Dashboard";
import { Leads } from "./screens/Leads";
import { LeadCard } from "./screens/LeadCard";
import {
  Campaigns, Logs, Reputation, Suppression, Mailboxes, Capacity, MyStats, Profile,
} from "./screens/views";

const BACKLOG_PATHS = SCREENS.filter((s) => !s.live).map((s) => s.path);

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        {/* Дашборд — только owner; manager редиректится на /leads гейтом */}
        <Route path="/" element={<ProtectedRoute role="owner"><Dashboard /></ProtectedRoute>} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/leads/:id" element={<LeadCard />} />
        <Route path="/my-leads" element={<Leads mine />} />
        <Route path="/stats" element={<MyStats />} />
        <Route path="/campaigns" element={<ProtectedRoute role="owner"><Campaigns /></ProtectedRoute>} />
        <Route path="/logs" element={<ProtectedRoute role="owner"><Logs /></ProtectedRoute>} />
        <Route path="/reputation" element={<ProtectedRoute role="owner"><Reputation /></ProtectedRoute>} />
        <Route path="/suppression" element={<ProtectedRoute role="owner"><Suppression /></ProtectedRoute>} />
        <Route path="/mailboxes" element={<ProtectedRoute role="owner"><Mailboxes /></ProtectedRoute>} />
        <Route path="/capacity" element={<ProtectedRoute role="owner"><Capacity /></ProtectedRoute>} />
        <Route path="/profile" element={<Profile />} />

        {/* Бэклог: маршруты есть, данные не имитируются */}
        {BACKLOG_PATHS.map((p) => {
          const scr = SCREENS.find((s) => s.path === p)!;
          return <Route key={p} path={p}
                        element={<ProtectedRoute role="owner"><BacklogStub title={scr.title} path={p} /></ProtectedRoute>} />;
        })}
      </Route>

      <Route path="*" element={<Navigate to="/leads" replace />} />
    </Routes>
  );
}
