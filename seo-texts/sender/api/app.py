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

from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
    warmup: Any = None
    dns: Any = None


def build_deps(config: Any, store: Any) -> "Deps":
    """Собрать компоненты движка из config+store для API (единая точка сборки)."""
    from sender.analytics import Analytics
    from sender.gates import Gates
    from sender.suppression import Suppression
    from sender.sender import Sender
    from sender.leaddesk import LeadDesk
    from sender.warmup import Warmup
    from sender.dns import DnsHealth

    suppression = Suppression(store)
    gates = Gates(config, store)
    sender = Sender(config, store, suppression, gates, dry_run=True)
    return Deps(
        config=config, store=store, auth=Auth(store),
        leaddesk=LeadDesk(config, store), analytics=Analytics(store),
        gates=gates, sender=sender, suppression=suppression,
        warmup=Warmup(config, store, sender), dns=DnsHealth(),
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


class CampaignBody(BaseModel):
    name: str
    # Таргетинг: сегмент базы (например "кц" / "meyer"); None/пусто = вся база
    segment: Optional[str] = None
    # P1.6: фазовый порядок отправки по PxR и порог балла
    send_order: Optional[str] = None       # pilot_asc | priority_desc | None(=по id)
    min_priority_max: Optional[int] = None  # отсечь «Макс. балл по связке» ниже порога


class StepBody(BaseModel):
    step_index: int
    subject: str
    body: str
    delay_hours: int = 0
    gate: str = "all"


class CampaignStatusBody(BaseModel):
    status: str  # active|paused|draft|completed


class UserBody(BaseModel):
    username: str
    password: str
    role: str = "manager"
    enable_2fa: bool = False


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


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
        rows = [_lead_json(x) for x in leads]
        # Колонка «Открыл»: справочный open-счётчик по получателю лида
        # (прокси картинок в РФ искажают сигнал — см. OPEN-TRACKING-SPEC.md).
        opens = deps.store.open_counts(
            [l.recipient_id for l in leads if l.recipient_id])
        for row, l in zip(rows, leads):
            row["opens"] = opens.get(l.recipient_id or -1, 0)
        return rows

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

    # ---- P1.5.2: загрузка базы из панели ----
    # CSV идёт СЫРЫМ телом запроса (без multipart: не тянем python-multipart),
    # segment — query-параметр. Импорт крутится в фоне-потоке (161k строк —
    # десятки секунд), прогресс поллится по import_id. Upsert идемпотентен:
    # повторная загрузка того же файла безопасна.
    _imports: dict[str, dict] = {}

    def _run_import(import_id: str, csv_path: str, segment: Optional[str]):
        state = _imports[import_id]

        def _cb(n: int) -> None:
            state["total_rows"] = n

        try:
            from sender.importer import import_csv
            result = import_csv(deps.store, csv_path,
                                default_segment=segment or None,
                                progress_cb=_cb)
            state.update(result)
            state["done"] = True
        except Exception as e:  # noqa: BLE001 - ошибка уходит в статус, не в лог-тишину
            state["error"] = str(e)
            state["done"] = True
        finally:
            import os as _os
            try:
                _os.unlink(csv_path)
            except OSError:
                pass

    @app.post("/recipients/import")
    async def import_recipients(request: Request, segment: Optional[str] = None,
                                p: Principal = Depends(owner)):
        import tempfile
        import threading
        import uuid
        data = await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="empty csv body")
        tmp = tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, prefix="panel-import-")
        tmp.write(data)
        tmp.close()
        import_id = uuid.uuid4().hex[:12]
        _imports[import_id] = {"done": False, "error": None, "total_rows": 0,
                               "imported": 0, "skipped_invalid": 0}
        deps.store.append_audit(action="recipients.import", actor_user_id=p.user_id,
                                detail={"segment": segment, "bytes": len(data)})
        threading.Thread(target=_run_import, args=(import_id, tmp.name, segment),
                         daemon=True).start()
        return {"import_id": import_id}

    @app.get("/recipients/import/{import_id}")
    def import_status(import_id: str, p: Principal = Depends(owner)):
        state = _imports.get(import_id)
        if state is None:
            raise HTTPException(status_code=404, detail="import not found")
        return state

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

    # ================= КАМПАНИИ (owner) — экраны 3/4/5 =================
    @app.post("/campaigns")
    def create_campaign(body: CampaignBody, p: Principal = Depends(owner)):
        from sender.store import CampaignIn
        legal = deps.config.legal()
        cfg = {}
        if (body.segment or "").strip():
            cfg["segment"] = body.segment
        if body.send_order in ("pilot_asc", "priority_desc"):
            cfg["send_order"] = body.send_order
        if body.min_priority_max is not None:
            cfg["min_priority_max"] = int(body.min_priority_max)
        cid = deps.store.create_campaign(CampaignIn(
            name=body.name, legal_entity=legal.entity, legal_inn=legal.inn,
            config=cfg))
        deps.store.append_audit(action="campaign.create", actor_user_id=p.user_id,
                                entity_type="campaign", entity_id=cid,
                                detail={"name": body.name, "segment": body.segment})
        return {"campaign_id": cid}

    @app.get("/campaigns/{cid}")
    def campaign_detail(cid: int, p: Principal = Depends(owner)):
        c = deps.store.get_campaign(cid)
        if c is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        steps = deps.store.get_steps(cid)
        try:
            report = deps.analytics.campaign_report(cid)
            funnel = _campaign_report_json(report)
        except Exception:  # noqa: BLE001 - отчёт не должен ронять карточку
            funnel = None
        return {"campaign": _campaign_json(c),
                "steps": [_step_json(s) for s in steps], "funnel": funnel}

    @app.post("/campaigns/{cid}/steps")
    def add_step(cid: int, body: StepBody, p: Principal = Depends(owner)):
        from sender.store import SequenceStepIn
        if deps.store.get_campaign(cid) is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        sid = deps.store.add_step(SequenceStepIn(
            campaign_id=cid, step_index=body.step_index, delay_hours=body.delay_hours,
            subject_tmpl=body.subject, body_tmpl=body.body,
            engagement_gate=body.gate, include_legal=True))
        deps.store.append_audit(action="campaign.add_step", actor_user_id=p.user_id,
                                entity_type="campaign", entity_id=cid,
                                detail={"step_index": body.step_index})
        return {"step_id": sid}

    @app.post("/campaigns/{cid}/status")
    def campaign_status(cid: int, body: CampaignStatusBody, p: Principal = Depends(owner)):
        if deps.store.get_campaign(cid) is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        deps.store.set_campaign_status(cid, body.status)
        deps.store.append_audit(action="campaign.status", actor_user_id=p.user_id,
                                entity_type="campaign", entity_id=cid,
                                detail={"status": body.status})
        return {"ok": True, "status": body.status}

    # ================= КОМАНДА / НАСТРОЙКИ (owner) — экран 21 =================
    @app.get("/users")
    def list_users(p: Principal = Depends(owner)):
        return {"users": [_user_json(u) for u in deps.store.list_users()]}

    @app.post("/users")
    def create_user(body: UserBody, p: Principal = Depends(owner)):
        try:
            info = deps.auth.create_user(username=body.username, password=body.password,
                                         role=body.role, enable_2fa=body.enable_2fa)
        except AuthError as e:
            raise HTTPException(status_code=400, detail=str(e))
        deps.store.append_audit(action="user.create", actor_user_id=p.user_id,
                                entity_type="user", entity_id=info["user_id"],
                                detail={"username": body.username, "role": body.role})
        return info  # totp_uri включён при enable_2fa (показать owner один раз)

    @app.post("/users/{uid}/deactivate")
    def deactivate_user(uid: int, p: Principal = Depends(owner)):
        u = deps.store.get_user(uid)
        if u is None:
            raise HTTPException(status_code=404, detail="user not found")
        # офбординг: рвём сессии; переназначение взятых лидов — операторски отдельно
        deps.store.update_user(uid, is_active=False)
        deps.store.revoke_user_sessions(uid)
        deps.store.append_audit(action="user.deactivate", actor_user_id=p.user_id,
                                entity_type="user", entity_id=uid)
        return {"ok": True}

    @app.post("/users/{uid}/activate")
    def activate_user(uid: int, p: Principal = Depends(owner)):
        if deps.store.get_user(uid) is None:
            raise HTTPException(status_code=404, detail="user not found")
        deps.store.update_user(uid, is_active=True)
        deps.store.append_audit(action="user.activate", actor_user_id=p.user_id,
                                entity_type="user", entity_id=uid)
        return {"ok": True}

    @app.get("/settings")
    def settings(p: Principal = Depends(owner)):
        legal = deps.config.legal()
        g = deps.config.gates()
        return {
            "legal": {"entity": legal.entity, "inn": legal.inn,
                      "unsub_base_url": legal.unsub_base_url},
            "gates": {"domain_bounce_pct": g.domain_bounce_pct,
                      "domain_complaint_pct": g.domain_complaint_pct,
                      "mailbox_bounce_pct": g.mailbox_bounce_pct,
                      "global_complaint_pct": g.global_complaint_pct,
                      "provider_bounce_pct": getattr(g, "provider_bounce_pct", None),
                      "min_volume": g.min_volume},
            "readonly_note": "Пороги kill-switch — read-only by design (правка = код движка).",
        }

    # ================= АУДИТ (owner) — экран 23 =================
    @app.get("/audit")
    def audit(actor_user_id: Optional[int] = None, action: Optional[str] = None,
              limit: int = 200, offset: int = 0, p: Principal = Depends(owner)):
        return {"audit": deps.store.list_audit(actor_user_id=actor_user_id,
                                               action=action, limit=limit, offset=offset)}

    # ================= ДОМЕНЫ / DNS (owner) — экран 14 =================
    @app.get("/domains")
    def domains(p: Principal = Depends(owner)):
        # сводка по доменам отправляющих ящиков БЕЗ сетевого DNS (быстро)
        by_domain: dict[str, dict] = {}
        for mb in deps.config.mailboxes():
            dom = mb.mailbox_id.split("@")[-1]
            d = by_domain.setdefault(dom, {"domain": dom, "mailboxes": 0, "ready": 0})
            d["mailboxes"] += 1
            r = deps.sender.mailbox_readiness(mb.mailbox_id)
            if r.ready:
                d["ready"] += 1
        return {"domains": list(by_domain.values())}

    @app.get("/domains/{domain}/dns")
    def domain_dns(domain: str, p: Principal = Depends(owner)):
        # сетевой чек DKIM/SPF/DMARC (может быть небыстрым) — «Проверить сейчас»
        rep = deps.dns.check(domain)
        return {"dns": {"domain": rep.domain, "spf": rep.spf, "dkim": rep.dkim,
                        "dmarc": rep.dmarc, "mx_ok": rep.mx_ok,
                        "spf_record": rep.spf_record, "dmarc_policy": rep.dmarc_policy,
                        "issues": list(rep.issues)}}

    # ================= ПРОГРЕВ (owner) — экран 16 =================
    @app.get("/warmup")
    def warmup(p: Principal = Depends(principal)):
        out = []
        for mb in deps.config.mailboxes():
            st = deps.store.get_warmup_state(mb.mailbox_id)
            if st is None:
                continue
            out.append({"mailbox_id": mb.mailbox_id, "phase": st.phase,
                        "ramp_day": st.ramp_day, "warmup_target": st.warmup_target,
                        "warmup_sent_today": st.warmup_sent_today,
                        "reputation_score": st.reputation_score})
        return {"warmup": out}

    # ================= КОМПЛАЕНС / СУБЪЕКТ ПД (owner) — экраны 19/20 =================
    @app.get("/compliance")
    def compliance(p: Principal = Depends(owner)):
        return {"suppression": deps.suppression.stats()}

    @app.get("/subject/{email}")
    def subject(email: str, p: Principal = Depends(owner)):
        # право на забвение / запрос РКН: вся история по адресу. Просмотр аудируется.
        history = deps.store.consent_history(email)
        supp = deps.store.suppression_lookup(email=email, domain=email.split("@")[-1], inn=None)
        deps.store.append_audit(action="subject.view", actor_user_id=p.user_id,
                                entity_type="subject", entity_id=email)
        return {"email": email, "consent_history": history,
                "suppressed": supp is not None,
                "suppression": _supp_json(supp) if supp else None}

    # ================= ПРОФИЛЬ: смена пароля (все) — экран 22 =================
    @app.post("/profile/password")
    def change_password(body: PasswordBody, p: Principal = Depends(principal)):
        from sender.auth import verify_password
        u = deps.store.get_user(p.user_id)
        if u is None or not verify_password(body.old_password, u.password_hash):
            raise HTTPException(status_code=400, detail="неверный текущий пароль")
        deps.auth.set_password(p.user_id, body.new_password)  # рвёт остальные сессии
        deps.store.append_audit(action="profile.password_change", actor_user_id=p.user_id,
                                entity_type="user", entity_id=p.user_id)
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def make_site_app(deps: Deps, static_dir: str) -> FastAPI:
    """«Сайт» одним процессом: API под ``/api`` + собранный SPA (dist/) статикой.

    Контракт фронта (web/src/api/client.ts, ``API_BASE="/api"``): все вызовы идут
    в ``/api/*``. В dev это срезает dev-прокси Vite; здесь то же делает
    монтирование под-приложения — ``/api/leads`` → ``make_app`` → ``/leads``.
    Любой прочий GET, не совпавший с файлом в dist/, отдаёт ``index.html`` —
    так работает client-side-роутинг React Router (перезагрузка на
    ``/campaigns/5`` не даёт 404). Сам API-слой не трогаем: ``make_app`` остаётся
    корневым (тесты и e2e бьют в ``/leads`` напрямую через тот же rewrite).

    В проде за TLS обычно стоит nginx (см. RUNBOOK-DEPLOY §2), но этот режим
    самодостаточен — удобен для стейджинга/смоука без обратного прокси.
    """
    import os
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.staticfiles import StaticFiles

    if not os.path.isdir(static_dir):
        raise FileNotFoundError(
            f"static_dir не найден: {static_dir!r} — сначала соберите SPA: "
            f"cd web && npm ci && npm run build"
        )

    class _SpaStaticFiles(StaticFiles):
        """StaticFiles с SPA-fallback: 404 на неизвестный путь → index.html."""

        async def get_response(self, path: str, scope):  # type: ignore[override]
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    site = FastAPI(title="Rusprom Sender Site", version="2.3")
    site.mount("/api", make_app(deps), name="api")

    @site.get("/healthz")
    def healthz():  # корневой health для nginx/systemd/докера (SPA-fallback не мешает)
        return {"status": "ok"}

    # ВАЖНО: catch-all статикой монтируем ПОСЛЕДНИМ — иначе перехватит /api и /healthz.
    site.mount("/", _SpaStaticFiles(directory=static_dir, html=True), name="spa")
    return site


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
            "mx_provider": r.mx_provider, "valid_status": r.valid_status,
            # P1.6: баллы приоритета из базы обзвона
            "priority_max": getattr(r, "priority_max", None),
            "pxr": getattr(r, "pxr", None)}


def _campaign_json(c):
    cfg = c.config if isinstance(getattr(c, "config", None), dict) else {}
    return {"id": c.id, "name": c.name, "status": c.status,
            "legal_entity": c.legal_entity, "created_at": _iso(c.created_at),
            # таргетинг: None = вся база (сегмент из config_json кампании)
            "segment": cfg.get("segment"),
            "send_order": cfg.get("send_order"),
            "min_priority_max": cfg.get("min_priority_max")}


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


def _step_json(s):
    return {"id": s.id, "step_index": s.step_index, "delay_hours": s.delay_hours,
            "subject_tmpl": s.subject_tmpl, "engagement_gate": s.engagement_gate,
            "include_legal": s.include_legal}


def _campaign_report_json(r):
    return {"campaign_id": r.campaign_id, "sent": r.sent, "delivered": r.delivered,
            "bounced": r.bounced, "complaints": r.complaints, "replies": r.replies,
            "unsubscribes": r.unsubscribes, "bounce_rate": r.bounce_rate,
            "complaint_rate": r.complaint_rate, "reply_rate": r.reply_rate,
            # open — справочно («в РФ приблизительно»), в гейты не входит
            "opens": getattr(r, "opens", 0), "open_rate": getattr(r, "open_rate", 0.0)}


def _user_json(u):
    # НИКОГДА не отдаём password_hash / totp_secret наружу
    return {"id": u.id, "username": u.username, "email": u.email, "role": u.role,
            "is_active": u.is_active, "has_2fa": u.totp_secret is not None,
            "created_at": _iso(u.created_at)}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}
