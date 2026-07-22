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
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from sender.auth import Auth, AuthError, Principal, ROLE_OWNER
from sender.dtos import MessageIn
from sender.leaddesk import LeadConflict


# P2 №6: композиционный корень переехал в sender.wiring — здесь реэкспорт,
# чтобы исторические импорты `from sender.api.app import Deps, build_deps` жили.
from sender.wiring import Deps, build_deps  # noqa: F401


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


class ConfirmDecisionBody(BaseModel):
    """Решение оператора confirm-send (Задачи 1/4)."""
    action: str                       # approve | edit | skip | stoplist
    subject: Optional[str] = None     # edit
    body: Optional[str] = None        # edit
    reason: Optional[str] = None      # skip/stoplist


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


class ReplyBody(BaseModel):
    """Ручной ответ оператора по лиду (Задача 3, реплай-деск)."""
    text: str
    subject: Optional[str] = None
    version: int                       # оптимистичная блокировка лида


class MailboxBody(BaseModel):
    """Добавление ящика из веба (Задача 2)."""
    mailbox_id: str
    provider: str                      # yandex | mailru | google | outlook
    smtp_host: str
    smtp_port: int = 465
    imap_host: str
    imap_port: int = 993
    login: str
    password_env: str
    from_name: Optional[str] = None
    pool: Optional[str] = None
    is_warmup_node: bool = False


class AutoresponderBody(BaseModel):
    enabled: bool


class GenerateBody(BaseModel):
    """Пре-генерация писем на дневной лимит (Задача 1)."""
    campaign_id: int


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

    # ---- Задача 3: РУЧНОЙ ОТВЕТ по лиду (реплай-деск) ----
    # Оператор пишет ответ руками → уходит СРАЗУ тем же ящиком в тот же тред.
    # Отправка настоящая только вне dry_run (ХОЛД: панель собрана в dry_run —
    # письмо ассемблится и пишется в историю, но SMTP не зовётся). Комплаенс-гейт
    # (suppression + байлайн + unsub-футер) — на бэкенде, минуя UI.
    @app.post("/leads/{lead_id}/reply")
    def reply_lead(lead_id: int, body: ReplyBody, p: Principal = Depends(principal)):
        from types import SimpleNamespace
        from sender.errors import SenderError
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="пустой текст ответа")
        subject = (body.subject or "").strip() or "Re: ваш запрос"
        if len(subject) > 900:
            raise HTTPException(status_code=400, detail="слишком длинная тема")
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        # принадлежность: владелец отвечает на любой; менеджер — только на свой
        if p.role != ROLE_OWNER and lead.assigned_to != p.user_id:
            raise HTTPException(status_code=403, detail="лид не взят вами")
        if lead.version != body.version:
            raise HTTPException(status_code=409, detail="лид изменён — обновите карточку")
        # комплаенс-гейт: suppression / отписка (ФЗ-38)
        probe = SimpleNamespace(email=lead.email,
                                domain=(lead.email or "").rsplit("@", 1)[-1], inn=lead.inn)
        entry = deps.suppression.is_suppressed(probe)
        if entry is not None:
            raise HTTPException(status_code=409,
                                detail=f"адрес в suppression ({entry.reason}) — ответ заблокирован")
        # байлайн + футер отписки (комплаенс-инвариант, всегда, минуя UI)
        legal = deps.config.legal()
        footer = (f"\n\n--\n{legal.entity}"
                  + (f", ИНН {legal.inn}" if legal.inn else "")
                  + "\nЧтобы не получать письма — ответьте «отписаться».")
        full_body = text + footer
        meta = deps.store.get_lead_reply_meta(lead_id) or {}
        mailbox_id = meta.get("reply_mailbox")
        if not mailbox_id:
            mbs = deps.config.mailboxes()
            mailbox_id = mbs[0].mailbox_id if mbs else None
        if not mailbox_id:
            raise HTTPException(status_code=500, detail="нет ящика-отправителя")
        try:
            res = deps.sender.send_reply(
                mailbox_id=mailbox_id, to_email=lead.email, subject=subject,
                body=full_body, in_reply_to=meta.get("reply_to_msgid"))
        except SenderError as e:
            raise HTTPException(status_code=502, detail=f"отправка не удалась: {e}")
        deps.store.add_lead_reply_event(
            lead_id, actor_user_id=p.user_id, subject=subject, body=full_body,
            to_email=lead.email, mailbox_id=mailbox_id,
            rfc_message_id=res.rfc_message_id, dry_run=res.dry_run)
        deps.store.append_audit(action="lead.reply", actor_user_id=p.user_id,
                                entity_type="lead", entity_id=lead_id,
                                detail={"dry_run": res.dry_run, "mailbox": mailbox_id})
        return {"ok": True, "dry_run": res.dry_run,
                "sent_message_id": res.rfc_message_id,
                "lead": _lead_json(deps.leaddesk.get(lead_id)),
                "history": deps.leaddesk.history(lead_id)}

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
        from sender.errors import ValidationError as _VErr
        try:
            ok = deps.store.suppression_remove(sid, reason=reason, actor=p.username)
        except _VErr as e:
            # П1.2: отписку (ФЗ-38) снять нельзя — честный 409, а не 500/404.
            raise HTTPException(status_code=409, detail=str(e))
        if not ok:
            raise HTTPException(status_code=404, detail="suppression not found")
        return {"ok": True}

    # ================= CONFIRM-SEND (Задачи 1/2/4) =================
    # Тонкие обёртки над deps.confirm — тем же модулем ходит CLI (паритет).

    @app.get("/confirm/queue")
    def confirm_queue(campaign_id: Optional[int] = None, limit: int = 50,
                      offset: int = 0, p: Principal = Depends(principal)):
        rows = deps.confirm.pending(campaign_id=campaign_id, limit=limit,
                                    offset=offset)
        return {"pending": rows, "counts": deps.confirm.counts()}

    @app.get("/confirm/golden")
    def confirm_golden(limit: int = 500, p: Principal = Depends(principal)):
        return {"pairs": deps.confirm.golden_pairs(limit=limit)}

    @app.get("/confirm/{rid}")
    def confirm_get(rid: int, p: Principal = Depends(principal)):
        row = deps.confirm.get(rid)
        if row is None:
            raise HTTPException(status_code=404, detail="review not found")
        return row

    @app.post("/confirm/{rid}/decision")
    def confirm_decision(rid: int, body: ConfirmDecisionBody,
                         p: Principal = Depends(principal)):
        from sender.confirm import ConfirmBlockedError
        from sender.errors import ValidationError as _VErr
        try:
            if body.action == "approve":
                done = deps.confirm.approve(rid, operator=p.username)
            elif body.action == "edit":
                done = deps.confirm.edit(rid, subject=body.subject,
                                         body=body.body, operator=p.username)
            elif body.action == "skip":
                done = deps.confirm.skip(rid, reason=body.reason or "",
                                         operator=p.username)
            elif body.action == "stoplist":
                done = deps.confirm.stoplist(rid, reason=body.reason or "",
                                             operator=p.username)
            else:
                raise HTTPException(status_code=422, detail="unknown action")
        except ConfirmBlockedError as e:
            # Юр-заслон на этапе подтверждения: письмо остаётся pending.
            raise HTTPException(status_code=409, detail=str(e))
        except _VErr as e:
            raise HTTPException(status_code=422, detail=str(e))
        row = deps.confirm.get(rid)
        if row is None:
            raise HTTPException(status_code=404, detail="review not found")
        return {"ok": True, "decided": bool(done), "review": row}

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

    # ================= ЯЩИКИ ИЗ ВЕБА (Задача 2, owner) =================
    @app.post("/mailboxes")
    def add_mailbox(body: MailboxBody, p: Principal = Depends(owner)):
        import sqlite3
        mid = (body.mailbox_id or "").strip().lower()
        if "@" not in mid:
            raise HTTPException(status_code=400, detail="mailbox_id должен быть email")
        if body.provider not in ("yandex", "mailru", "google", "outlook"):
            raise HTTPException(status_code=400, detail="provider: yandex|mailru|google|outlook")
        if deps.store.mailbox_override_exists(mid) or \
                any(m.mailbox_id == mid for m in deps.config.mailboxes()):
            raise HTTPException(status_code=409, detail="ящик уже добавлен")
        row = {"mailbox_id": mid, "provider": body.provider,
               "smtp_host": body.smtp_host, "smtp_port": body.smtp_port,
               "imap_host": body.imap_host, "imap_port": body.imap_port,
               "login": body.login, "password_env": body.password_env,
               "from_name": body.from_name, "pool": body.pool,
               "is_warmup_node": body.is_warmup_node}
        try:
            deps.store.add_mailbox_override(row, created_by=p.user_id)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="ящик уже добавлен")
        deps.config.load_mailbox_overrides(deps.store)   # горячий подхват в память
        deps.store.append_audit(action="mailbox.add", actor_user_id=p.user_id,
                                entity_type="mailbox", entity_id=None,
                                detail={"mailbox_id": mid, "provider": body.provider})
        return {"ok": True, "mailbox_id": mid,
                "note": "ящик добавлен и подхвачен; пароль читается из env "
                        f"{body.password_env} на сервере"}

    # ================= АВТООТВЕТЧИК (Задача 4) — по умолчанию ВЫКЛ =================
    @app.get("/autoresponder")
    def autoresponder_get(p: Principal = Depends(principal)):
        return {"enabled": deps.store.get_flag("autoresponder_enabled", default=False)}

    @app.post("/autoresponder")
    def autoresponder_set(body: AutoresponderBody, p: Principal = Depends(owner)):
        deps.store.set_flag("autoresponder_enabled", bool(body.enabled))
        deps.store.append_audit(action="autoresponder.set", actor_user_id=p.user_id,
                                entity_type="autoresponder", entity_id=None,
                                detail={"enabled": bool(body.enabled)})
        return {"ok": True, "enabled": bool(body.enabled)}

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

    # ---- Задача 1: ПРЕ-ГЕНЕРАЦИЯ писем на дневной лимит ----
    # Объём = суммарная дневная ёмкость активных ящиков (Σ max(0, лимит−отправлено)).
    # Топ-N получателей по приоритету → рендер шаблона шага → confirm-очередь (pending).
    # Оператор открывает confirm — письма уже готовы. Фоном; прогресс поллится.
    _gen_jobs: dict[str, dict] = {}

    def _today_capacity() -> int:
        total = 0
        for mb in deps.config.mailboxes():
            try:
                r = deps.sender.mailbox_readiness(mb.mailbox_id)
                if not r.paused:
                    total += max(0, int(r.daily_limit) - int(r.sent_today))
            except Exception:  # noqa: BLE001
                pass
        return total

    def _merge(tmpl: str, rec) -> str:
        vals = {"company_name": getattr(rec, "company_name", "") or "",
                "inn": getattr(rec, "inn", "") or "",
                "email": getattr(rec, "email", "") or "",
                "region": getattr(rec, "region", "") or ""}
        out = tmpl or ""
        for k, v in vals.items():
            out = out.replace("{" + k + "}", str(v))
        return out

    def _run_generate(gid: str, cid: int, capacity: int):
        st = _gen_jobs[gid]
        try:
            steps = deps.store.get_steps(cid)
            step = steps[0] if steps else None
            if step is None:
                st.update(done=True, error="у кампании нет шагов")
                return
            camp = deps.store.get_campaign(cid)
            seg = (camp.config or {}).get("segment") if camp else None
            f = _clean({"valid_status": "valid", "segment": seg})
            recs = deps.store.query_recipients(f, limit=capacity, offset=0)
            for rec in recs:
                try:
                    subj = _merge(step.subject_tmpl, rec)
                    bodyt = _merge(step.body_tmpl, rec)
                    mid, _ = deps.store.enqueue_message(MessageIn(
                        idempotency_key=f"pregen:{cid}:{rec.id}",
                        campaign_id=cid, recipient_id=rec.id,
                        sequence_step_id=step.id,
                        scheduled_at=datetime.now(timezone.utc)),
                        status="pending_review")
                    deps.store.confirm_submit(
                        email=rec.email, subject=subj, body=bodyt, inn=rec.inn,
                        campaign_id=cid, recipient_id=rec.id, message_id=mid,
                        panel=None, status="pending")
                    st["generated"] = st.get("generated", 0) + 1
                except Exception:  # noqa: BLE001
                    st["failed"] = st.get("failed", 0) + 1
            st["done"] = True
        except Exception as e:  # noqa: BLE001
            st.update(done=True, error=str(e))

    @app.post("/campaigns/{cid}/generate")
    def generate_letters(cid: int, p: Principal = Depends(owner)):
        import threading
        import uuid
        if deps.store.get_campaign(cid) is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        capacity = _today_capacity()
        if capacity <= 0:
            return {"status": "idle", "capacity": 0,
                    "reason": "нет дневной ёмкости (ящики на лимите/паузе)"}
        gid = uuid.uuid4().hex[:12]
        _gen_jobs[gid] = {"done": False, "error": None, "capacity": capacity,
                          "generated": 0, "failed": 0}
        deps.store.append_audit(action="campaign.generate", actor_user_id=p.user_id,
                                entity_type="campaign", entity_id=cid,
                                detail={"capacity": capacity})
        threading.Thread(target=_run_generate, args=(gid, cid, capacity),
                         daemon=True).start()
        return {"status": "started", "generate_id": gid, "capacity": capacity}

    @app.get("/campaigns/{cid}/generate/{gid}")
    def generate_status(cid: int, gid: str, p: Principal = Depends(owner)):
        st = _gen_jobs.get(gid)
        if st is None:
            raise HTTPException(status_code=404, detail="generate job not found")
        return st

    @app.get("/campaigns/{cid}/capacity")
    def campaign_capacity(cid: int, p: Principal = Depends(owner)):
        return {"capacity": _today_capacity()}

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
            "autoresponder": {
                "enabled": deps.store.get_flag("autoresponder_enabled", default=False),
                "note": "ВЫКЛ по умолчанию; включать только по явной команде владельца",
            },
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
