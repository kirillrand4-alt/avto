"""HTTP/JSON транспорт веб-панели (BUILD-NEW, Фаза 2.1) — FastAPI поверх движка.

Тонкий слой: каждый эндпоинт — обёртка над готовым методом движка (store /
analytics / gates / sender / suppression / leaddesk) под auth-гейтом. Логику
не дублирует (правило SITE-DESIGN: UI-ONLY = тонкий эндпоинт). Транспорт может
иметь свои зависимости (fastapi); движок остаётся stdlib.

Сборка: ``make_app(deps)`` где ``deps`` — контейнер с собранными компонентами
(см. ``build_deps``). Аутентификация — Bearer-токен из ``Auth.resolve``.
DROP-фичи (правка порогов kill-switch, WYSIWYG, drag-drop) намеренно НЕ
экспонированы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from sender.auth import Auth, AuthError, Principal, ROLE_OWNER
from sender.leaddesk import LeadConflict


@dataclass
class Deps:
    """Собранные компоненты движка для эндпоинтов."""
    config: Any
    store: Any
    auth: Auth
    leaddesk: Any
    analytics: Any
    gates: Any
    sender: Any
    suppression: Any


def build_deps(config: Any, store: Any) -> "Deps":
    """Собрать компоненты движка из config+store для API (единая точка сборки)."""
    from sender.analytics import Analytics
    from sender.gates import Gates
    from sender.suppression import Suppression
    from sender.sender import Sender
    from sender.leaddesk import LeadDesk

    suppression = Suppression(store)
    gates = Gates(config, store)
    sender = Sender(config, store, suppression, gates, dry_run=True)
    return Deps(
        config=config, store=store, auth=Auth(store),
        leaddesk=LeadDesk(config, store), analytics=Analytics(store),
        gates=gates, sender=sender, suppression=suppression,
    )


# ---- request-модели ---- #

class LoginBody(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None


class StatusBody(BaseModel):
    status: str
    note: Optional[str] = None


class AssignBody(BaseModel):
    manager_id: int


def make_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="Rusprom Sender Panel", version="2.1")

    # ---- auth-зависимости ---- #
    def principal(authorization: Optional[str] = Header(default=None)) -> Principal:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        p = deps.auth.resolve(token)
        if p is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        return p

    def owner(p: Principal = Depends(principal)) -> Principal:
        if p.role != ROLE_OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        return p

    def _leads_to_json(leads: list) -> list:
        return [_lead_json(x) for x in leads]

    # ================= AUTH =================
    @app.post("/auth/login")
    def login(body: LoginBody, user_agent: Optional[str] = Header(default=None)):
        try:
            token = deps.auth.login(username=body.username, password=body.password,
                                    totp_code=body.totp_code, user_agent=user_agent)
        except AuthError:
            raise HTTPException(status_code=401, detail="invalid credentials")
        return {"token": token}

    @app.post("/auth/logout")
    def logout(authorization: Optional[str] = Header(default=None),
               p: Principal = Depends(principal)):
        if authorization and authorization.lower().startswith("bearer "):
            deps.auth.logout(authorization[7:].strip())
        return {"ok": True}

    @app.get("/me")
    def me(p: Principal = Depends(principal)):
        return {"user_id": p.user_id, "username": p.username, "role": p.role}

    # ================= LEAD-DESK (эпицентр) =================
    @app.get("/leads")
    def list_leads(status: Optional[str] = None, assigned_to: Optional[int] = None,
                   unassigned: bool = False, reply_kind: Optional[str] = None,
                   limit: int = 100, offset: int = 0,
                   p: Principal = Depends(principal)):
        leads = deps.leaddesk.queue(status=status, assigned_to=assigned_to,
                                    unassigned=unassigned, reply_kind=reply_kind,
                                    limit=limit, offset=offset)
        return {"leads": _leads_to_json(leads), "stats": deps.leaddesk.stats()}

    @app.get("/leads/{lead_id}")
    def get_lead(lead_id: int, p: Principal = Depends(principal)):
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        return {"lead": _lead_json(lead), "history": deps.leaddesk.history(lead_id)}

    @app.post("/leads/{lead_id}/take")
    def take_lead(lead_id: int, p: Principal = Depends(principal)):
        try:
            lead = deps.leaddesk.take(lead_id, user_id=p.user_id)
        except LeadConflict:
            raise HTTPException(status_code=409, detail="lead already taken")
        except AuthError:
            raise HTTPException(status_code=401, detail="not authenticated")
        except Exception as e:  # noqa: BLE001 - ValidationError и пр.
            raise HTTPException(status_code=400, detail=str(e))
        return {"lead": _lead_json(lead)}

    @app.post("/leads/{lead_id}/status")
    def set_lead_status(lead_id: int, body: StatusBody, p: Principal = Depends(principal)):
        try:
            lead = deps.leaddesk.set_status(lead_id, status=body.status,
                                            user_id=p.user_id, note=body.note)
        except LeadConflict:
            raise HTTPException(status_code=409, detail="lead modified concurrently")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e))
        return {"lead": _lead_json(lead)}

    @app.post("/leads/{lead_id}/assign")
    def assign_lead(lead_id: int, body: AssignBody, p: Principal = Depends(owner)):
        try:
            lead = deps.leaddesk.assign(lead_id, manager_id=body.manager_id,
                                        actor_user_id=p.user_id)
        except LeadConflict:
            raise HTTPException(status_code=409, detail="lead modified concurrently")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e))
        return {"lead": _lead_json(lead)}

    # ================= UI-ONLY обёртки над движком =================
    @app.get("/recipients")
    def recipients(valid_status: Optional[str] = None, provider: Optional[str] = None,
                   domain_like: Optional[str] = None, inn: Optional[str] = None,
                   segment: Optional[str] = None, suppressed: Optional[bool] = None,
                   limit: int = 100, offset: int = 0, p: Principal = Depends(principal)):
        f = _clean({"valid_status": valid_status, "provider": provider,
                    "domain_like": domain_like, "inn": inn, "segment": segment,
                    "suppressed": suppressed})
        rows = deps.store.query_recipients(f, limit=limit, offset=offset)
        return {"recipients": [_recipient_json(r) for r in rows],
                "count": deps.store.count_recipients(f)}

    @app.get("/campaigns")
    def campaigns(status: Optional[str] = None, p: Principal = Depends(principal)):
        return {"campaigns": [_campaign_json(c) for c in deps.store.list_campaigns(status=status)]}

    @app.get("/events")
    def events(event_type: Optional[str] = None, campaign_id: Optional[int] = None,
               provider: Optional[str] = None, limit: int = 100,
               p: Principal = Depends(principal)):
        rows = deps.store.list_events(event_type=event_type, campaign_id=campaign_id,
                                      provider=provider, limit=limit)
        return {"events": [_event_json(e) for e in rows]}

    @app.get("/suppression")
    def suppression(scope: Optional[str] = None, reason: Optional[str] = None,
                    limit: int = 100, p: Principal = Depends(principal)):
        rows = deps.store.iter_suppression(scope=scope, reason=reason, limit=limit)
        return {"suppression": [_supp_json(s) for s in rows],
                "stats": deps.suppression.stats()}

    @app.delete("/suppression/{sid}")
    def remove_suppression(sid: int, reason: str = "operator removal",
                           p: Principal = Depends(owner)):
        ok = deps.store.suppression_remove(sid, reason=reason, actor=p.username)
        if not ok:
            raise HTTPException(status_code=404, detail="suppression not found")
        return {"ok": True}

    @app.get("/analytics/dashboard")
    def dashboard(p: Principal = Depends(principal)):
        return deps.analytics.dashboard()

    @app.get("/analytics/rates")
    def rates(scope: str = "global", target: str = "*", days: int = 7,
              p: Principal = Depends(principal)):
        series = deps.analytics.rate_series(scope=scope, target=target, days=days)
        return {"series": [_rate_json(s) for s in series]}

    @app.get("/gates/active")
    def gates_active(p: Principal = Depends(principal)):
        return {"trips": [_gate_json(g) for g in deps.gates.active_trips()]}

    @app.get("/mailboxes/readiness")
    def mailbox_readiness(p: Principal = Depends(principal)):
        out = []
        for mb in deps.config.mailboxes():
            r = deps.sender.mailbox_readiness(mb.mailbox_id)
            out.append({"mailbox_id": r.mailbox_id, "ready": r.ready,
                        "ramp_day": r.ramp_day, "daily_limit": r.daily_limit,
                        "sent_today": r.sent_today, "paused": r.paused,
                        "reasons": list(r.reasons)})
        return {"mailboxes": out}

    @app.get("/capacity")
    def capacity(p: Principal = Depends(principal)):
        pools = {}
        try:
            pools = deps.config.provider_pools()
        except Exception:  # noqa: BLE001
            pass
        out = []
        for pool, ids in pools.items():
            snap = deps.analytics.capacity_report(pool, mailbox_ids=list(ids))
            out.append(_capacity_json(snap))
        return {"pools": out}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# ---- сериализаторы (dataclass → json-safe dict) ---- #

def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _lead_json(l):
    return {"id": l.id, "email": l.email, "company_name": l.company_name,
            "inn": l.inn, "status": l.status, "reply_kind": l.reply_kind,
            "phone": l.phone, "need": l.need, "assigned_to": l.assigned_to,
            "bitrix_lead_id": l.bitrix_lead_id, "version": l.version,
            "sla_due_at": _iso(l.sla_due_at), "created_at": _iso(l.created_at)}


def _recipient_json(r):
    return {"id": r.id, "email": r.email, "domain": r.domain, "inn": r.inn,
            "company_name": r.company_name, "segment": r.segment,
            "mx_provider": r.mx_provider, "valid_status": r.valid_status}


def _campaign_json(c):
    return {"id": c.id, "name": c.name, "status": c.status,
            "legal_entity": c.legal_entity, "created_at": _iso(c.created_at)}


def _event_json(e):
    return {"id": e.id, "event_type": e.event_type, "campaign_id": e.campaign_id,
            "provider": e.provider, "mailbox_id": e.mailbox_id,
            "event_ts": _iso(e.event_ts)}


def _supp_json(s):
    return {"id": s.id, "scope": s.scope, "value": s.value, "reason": s.reason,
            "created_at": _iso(s.created_at), "expires_at": _iso(s.expires_at)}


def _rate_json(s):
    return {"target": s.target, "sent": s.sent, "bounce": s.bounce,
            "complaint": s.complaint, "reply": s.reply,
            "bounce_rate": s.bounce_rate, "complaint_rate": s.complaint_rate,
            "reply_rate": s.reply_rate}


def _gate_json(g):
    return {"scope": g.scope, "target": g.target, "metric": g.metric,
            "value": g.value, "threshold": g.threshold, "action": g.action}


def _capacity_json(c):
    return {"pool": c.pool, "mailbox_count": c.mailbox_count,
            "daily_capacity": c.daily_capacity, "sent_today": c.sent_today,
            "remaining_today": c.remaining_today, "utilization_pct": c.utilization_pct,
            "paused_mailboxes": c.paused_mailboxes}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}
