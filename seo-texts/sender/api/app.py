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

from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Dict, Optional

import logging
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from sender.auth import Auth, AuthError, Principal, ROLE_OWNER
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


class RecipientBody(BaseModel):
    email: str


class SendLimitsBody(BaseModel):
    """Ручной потолок дневной отправки: общий и/или по каждому ящику."""
    all: Optional[int] = None
    per_mailbox: Dict[str, Optional[int]] = {}


class AutoresponderBody(BaseModel):
    enabled: bool


class PauseBody(BaseModel):
    """Пауза ящика или всей отправки. Причина обязательна: через неделю никто
    не вспомнит, почему ящик стоит."""
    paused: bool
    reason: Optional[str] = None


class MailboxBody(BaseModel):
    """Ящик отправки, выбранный оператором в карточке подтверждения."""

    mailbox_id: str


class ConfirmDecisionBody(BaseModel):
    """Решение оператора confirm-send (Задачи 1/4)."""
    action: str                       # approve | edit | skip | stoplist
    subject: Optional[str] = None     # edit
    body: Optional[str] = None        # edit
    reason: Optional[str] = None      # skip/stoplist
    # второе, личное подтверждение оператора на письме с заслонами: письмо
    # уходит вопреки им, обход пишется в аудит (решение владельца 26.07)
    force: bool = False


class OutOfBaseBody(BaseModel):
    """Тумблер «слать по email вне базы»."""
    allow: bool


class LeadReplyBody(BaseModel):
    """Ответ оператора из карточки лида (#62): текст в очередь подтверждений."""
    subject: Optional[str] = None
    body: str


class QuotaScheduleBody(BaseModel):
    """Расписание дневной квоты AI-генерации: карта дата -> сколько писем.
    Не одно число: владелец задаёт темп как «3 сегодня, 3 завтра, 5 послезавтра».
    Приходит ПАТЧЕМ (только изменённые дни), 0 = день снят."""
    campaign_id: int
    schedule: Dict[str, int]


class QuotaRunBody(BaseModel):
    """«Сгенерировать сейчас» — по остатку квоты на сегодня.
    count (#71): сгенерировать ещё N писем СВЕРХ сделанных сегодня —
    владелец поднял дневной лимит и добивает очередь под него."""
    campaign_id: int
    count: Optional[int] = None


class WindowBody(BaseModel):
    """Окно авто-отправки, задаётся владельцем из панели."""
    days: list[int]           # ISO 1=Пн..7=Вс
    start: str                # "09:00"
    end: str                  # "11:00"
    tz: Optional[str] = None  # напр. "Asia/Novosibirsk"


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
        rows = _leads_to_json(leads)
        # Фича 2: бейдж «Отправляли» в ленте лидов (батч send_log, не N+1).
        flags = deps.store.sent_flags(
            inns=[r.get("inn") for r in rows],
            emails=[r.get("email") for r in rows])
        for r in rows:
            digits = "".join(c for c in str(r.get("inn") or "") if c.isdigit())
            em = str(r.get("email") or "").strip().lower()
            r["sent"] = flags.get(digits) or flags.get(em) or {
                "ever": False, "last_ts": None, "replied": False,
                "within_90d": False}
        return {"leads": rows, "stats": deps.leaddesk.stats()}

    @app.get("/leads/{lead_id}")
    def get_lead(lead_id: int, p: Principal = Depends(principal)):
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        return {"lead": _lead_json(lead), "history": deps.leaddesk.history(lead_id)}

    @app.get("/leads/{lead_id}/dialog")
    def lead_dialog(lead_id: int, p: Principal = Depends(principal)):
        """Лента диалога лида. #64: показываем ВСЮ переписку с компанией
        (по ИНН, все адреса и ящики), а не один тред получателя — при
        нескольких контактах одной компании оператор видел куски.

        27.07 (владелец): плоский список выглядел ОДНИМ тредом, которым не
        является — в нём письма к разным адресам с разными темами, а in_reply_to
        и thread_id пустые. Теперь дополнительно отдаём `threads` — настоящие
        почтовые ветки, склеенные по In-Reply-To/References, thread_id и, как
        фолбэк, по нормализованной теме и адресу собеседника. Поле `thread`
        оставлено прежним, чтобы не ломать существующих потребителей.
        """
        from sender.store import group_dialog_threads
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        inn = getattr(lead, "inn", None)
        if inn:
            thread = deps.store.dialog_thread_company(inn)
            if thread:
                return {"thread": thread, "threads": group_dialog_threads(thread),
                        "scope": "company"}
        rid = getattr(lead, "recipient_id", None)
        if rid is None:
            return {"thread": [], "threads": []}
        flat = deps.store.dialog_thread(rid)
        return {"thread": flat, "threads": group_dialog_threads(flat),
                "scope": "recipient"}

    @app.get("/leads/{lead_id}/reply-draft")
    def lead_reply_draft(lead_id: int, p: Principal = Depends(principal)):
        """#62: есть ли у лида черновик ответа в очереди подтверждений."""
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        row = deps.store.confirm_find_reply_pending(
            email=getattr(lead, "email", "") or "",
            thread_id=getattr(lead, "thread_id", "") or "")
        return {"draft": row}

    @app.post("/leads/{lead_id}/reply")
    def lead_reply(lead_id: int, body: LeadReplyBody,
                   p: Principal = Depends(principal)):
        """#62: ответ из карточки лида. Текст оператора кладётся ЧЕРНОВИКОМ в
        очередь подтверждений (kind='reply', тред сохраняется) — уходит после
        нажатия «Отправить» там же, тем же путём, что все ответы."""
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        text = (body.body or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="пустой текст ответа")
        subject = (body.subject or "").strip() or "Ваш запрос"
        panel = {"kind": "reply",
                 "incoming": {"from": getattr(lead, "email", ""),
                              "classified": getattr(lead, "reply_kind", "") or "",
                              "snippet": (getattr(lead, "need", "") or "")[:4000]},
                 "review": {"decision": "OPERATOR",
                            "note": "текст написан оператором в карточке лида"}}
        res = deps.confirm.submit_reply(
            reply_to=getattr(lead, "email", "") or "",
            subject=subject, body=text,
            in_reply_to=getattr(lead, "reply_to_msgid", None),
            thread_id=getattr(lead, "thread_id", None),
            recipient_id=getattr(lead, "recipient_id", None),
            inn=getattr(lead, "inn", None), panel=panel)
        if res.status == "skipped":
            raise HTTPException(status_code=409,
                                detail=f"заслон: {res.reason or 'skipped'}")
        return {"ok": True, "review_id": res.review_id, "created": res.created}

    @app.get("/dialog/{recipient_id}")
    def contact_dialog(recipient_id: int, p: Principal = Depends(principal)):
        return {"thread": deps.store.dialog_thread(recipient_id)}

    # ---- «Почта»: read-only IMAP-браузер по ящикам панели ---------------- #
    def _mail():
        if deps.mailbrowser is None:
            raise HTTPException(status_code=503, detail="mailbrowser недоступен")
        return deps.mailbrowser

    def _mail_guard(fn):
        from sender.mailbrowser import MailBrowserError
        try:
            return fn()
        except MailBrowserError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/mail/mailboxes")
    def mail_mailboxes(p: Principal = Depends(principal)):
        return {"mailboxes": _mail().mailboxes()}

    @app.get("/mail/{mailbox_id}/folders")
    def mail_folders(mailbox_id: str, p: Principal = Depends(principal)):
        return {"folders": _mail_guard(lambda: _mail().folders(mailbox_id))}

    @app.get("/mail/{mailbox_id}/messages")
    def mail_messages(mailbox_id: str, folder: str = "INBOX", limit: int = 50,
                      offset: int = 0, search: Optional[str] = None,
                      p: Principal = Depends(principal)):
        return _mail_guard(lambda: _mail().messages(
            mailbox_id, folder=folder, limit=limit, offset=offset, search=search))

    @app.get("/mail/{mailbox_id}/message")
    def mail_message(mailbox_id: str, folder: str, uid: str,
                     p: Principal = Depends(principal)):
        return _mail_guard(lambda: _mail().message(
            mailbox_id, folder=folder, uid=uid))

    @app.get("/mail/{mailbox_id}/thread")
    def mail_thread(mailbox_id: str, folder: str, uid: str,
                    p: Principal = Depends(principal)):
        return {"thread": _mail_guard(lambda: _mail().thread(
            mailbox_id, folder=folder, uid=uid))}

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
               provider: Optional[str] = None, limit: int = 100, offset: int = 0,
               p: Principal = Depends(principal)):
        # offset: пейджер фронта (владелец вливает всю базу — списки постраничные)
        rows = deps.store.list_events(event_type=event_type, campaign_id=campaign_id,
                                      provider=provider, limit=limit, offset=offset)
        return {"events": [_event_json(e) for e in rows]}

    @app.get("/messages/needs-data")
    def needs_data(limit: int = 100, p: Principal = Depends(principal)):
        """§3 BASE-MERGE: очередь «дозаполнить данные» — письма, которым не
        хватило обязательных полей ({news_object}/{city} и т.п.)."""
        return {"needs_data": deps.store.list_needs_data(limit=limit)}

    @app.get("/suppression")
    def suppression(scope: Optional[str] = None, reason: Optional[str] = None,
                    limit: int = 100, offset: int = 0,
                    p: Principal = Depends(principal)):
        rows = deps.store.iter_suppression(scope=scope, reason=reason, limit=limit,
                                           offset=offset)
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
                      offset: int = 0, order: str = "score",
                      division: Optional[str] = None,
                      p: Principal = Depends(principal)):
        # Фильтр направления (КЦ/Meyer) считается ЗДЕСЬ и ДО нарезки страницы.
        # Раньше он жил только на фронте: панель просила 50 писем, фильтровала
        # их у себя и показывала «11 из 50» — оператор Meyer видел огрызок
        # страницы и должен был жать «показать ещё», чтобы набрать полсотни
        # своих (владелец 28.07). Предикат тот же, что был на клиенте: письмо
        # без направления видно в обоих фильтрах, `kc+meyer` — тоже.
        напр = (division or "").strip().lower()
        if напр in ("", "все", "all"):
            напр = ""

        def _по_направлению(r) -> bool:
            if not напр:
                return True
            d = str((((r.get("panel") or {}).get("company") or {})
                     .get("division") or "")).lower()
            return (not d) or (напр in d)

        # Порядок — по скорингу (#70): «горячий — писать в первую очередь».
        # Сортировать надо ВЕСЬ pending, а не страницу: раньше pending(limit,
        # offset) резал по id ДО сортировки, и «зелёные» всплывали в каждой
        # подгруженной странице заново (владелец 27.07: «сортировка идёт не
        # среди всех 319, а только среди первых 50»). Поэтому при сортировке
        # по баллу тянем всё, сортируем глобально и режем страницу сами.
        # По той же причине полный набор нужен и при фильтре направления —
        # иначе фильтровать было бы нечего, кроме уже отрезанной страницы.
        всего: Optional[int] = None
        if order != "id" or напр:
            rows = deps.confirm.pending(campaign_id=campaign_id,
                                        limit=100000, offset=0)

            def _балл(r):
                try:
                    return float(((r.get("panel") or {}).get("scoring")
                                  or {}).get("score") or -1)
                except (TypeError, ValueError):
                    return -1.0
            if order != "id":
                # Ответы клиентов — ВСЕГДА выше исходящих (просьба владельца
                # 27.07): живой человек ждёт, это дороже любого скоринга.
                rows.sort(key=lambda r: (
                    0 if (r.get("kind") or "outbound") == "reply" else 1,
                    -_балл(r), r.get("id") or 0))
            rows = [r for r in rows if _по_направлению(r)]
            # сколько писем в очереди ПОД ФИЛЬТРОМ — иначе панель не может
            # честно посчитать «осталось N» для кнопки «показать ещё»
            всего = len(rows)
            rows = rows[offset:offset + max(0, int(limit))]
        else:
            rows = deps.confirm.pending(campaign_id=campaign_id, limit=limit,
                                        offset=offset)
        # Ветка переписки для черновиков ответов: оператор отвечает, видя ВСЮ
        # историю, а не только последнее входящее. Только для reply-строк —
        # их единицы, N+1 здесь не страшен.
        for r in rows:
            if (r.get("kind") or "") == "reply":
                try:
                    inn = r.get("inn")
                    rid_ = r.get("recipient_id")
                    thread: list = []
                    if inn and hasattr(deps.store, "dialog_thread_company"):
                        thread = deps.store.dialog_thread_company(
                            str(inn), limit=60) or []
                    # ПУСТАЯ ветка по ИНН — не повод показать оператору пусто:
                    # у получателя может не быть ИНН в базе (ответ пришёл с
                    # адреса, заведённого без реквизитов). Раньше здесь стоял
                    # elif, и ветка контакта не подшивалась вообще.
                    if not thread and rid_ and hasattr(deps.store, "dialog_thread"):
                        thread = deps.store.dialog_thread(rid_, limit=60) or []
                    r["thread"] = thread
                except Exception:  # noqa: BLE001 - показ не роняем
                    pass
        # Фича 2: батч-пометка «уже отправляли» по всей странице одним
        # запросом (не N+1) — бейдж виден в списке, не заходя в карточку.
        flags = deps.store.sent_flags(
            inns=[r.get("inn") for r in rows],
            emails=[r.get("email") for r in rows])
        for r in rows:
            digits = "".join(c for c in str(r.get("inn") or "") if c.isdigit())
            em = str(r.get("email") or "").strip().lower()
            r["sent"] = flags.get(digits) or flags.get(em) or {
                "ever": False, "last_ts": None, "replied": False,
                "within_90d": False}
        # С КАКОГО ЯЩИКА уйдёт письмо и как оно закончится — считаем на показ,
        # а не при генерации: ящик подбирается в момент отправки (пауза/лимит/
        # гейт меняются в течение дня), и подпись зависит от выбранного ящика.
        # Раньше оператор видел подпись с заглушкой «имя по ящику отправки» и
        # вторым «С уважением,» — письмо в карточке не совпадало с реальным.
        # Фильтр оператора уезжает и в подбор ящика: ящики его направления
        # показываем первыми, чтобы не листать полтора десятка чужих адресов.
        # Сигнатуру проверяем один раз — CLI и тесты зовут send_as(row) без
        # именованного аргумента, ломать их нельзя.
        try:
            import inspect as _inspect
            _sa_напр = "prefer_division" in _inspect.signature(
                deps.confirm.send_as).parameters
        except (TypeError, ValueError):
            _sa_напр = False
        for r in rows:
            try:
                sa = (deps.confirm.send_as(r, prefer_division=напр or None)
                      if _sa_напр else deps.confirm.send_as(r))
            except Exception:  # noqa: BLE001
                sa = {"mailbox_id": None, "options": [],
                      "note": "не удалось определить ящик отправки"}
            r["send_as"] = sa
            panel = r.get("panel")
            # Расшифровка ОКВЭД дописывается НА ПОКАЗ, а не при генерации:
            # письма в очереди собраны раньше, чем появился справочник, и
            # оператор видел бы «25.62|25.11|30.20.2» без единого слова.
            if isinstance(panel, dict) and isinstance(panel.get("company_full"), dict):
                cf = panel["company_full"]
                try:
                    from sender.infopanel import decode_okveds
                    if not cf.get("okved_decoded"):
                        cf["okved_decoded"] = decode_okveds(
                            (cf.get("reg") or {}).get("okved_all_codes"))
                    if not cf.get("okved_main_name"):
                        # вне базы обзвона списка кодов нет вообще — тогда
                        # расшифровываем хотя бы основной код
                        осн = decode_okveds(
                            (cf.get("reg") or {}).get("okved_main")
                            or (panel.get("company") or {}).get("okved"))
                        cf["okved_main_name"] = осн[0]["name"] if осн else ""
                except Exception:  # noqa: BLE001
                    pass
            # ЕДИНЫЙ ФОРМАТ потребности в оборудовании (владелец 27.07: «не в
            # формате базы обзвона написано какое оборудование необходимо»):
            # вне базы текст брался свободной фразой; теперь подтягиваем
            # канонический equip_by_okved из самой базы по основному ОКВЭД.
            if isinstance(panel, dict):
                comp = panel.get("company")
                cards = getattr(deps, "cards", None)
                if (isinstance(comp, dict) and not comp.get("equip_needed")
                        and cards is not None and getattr(cards, "active", False)
                        and not (panel.get("company_full") or {}).get("in_obzvon")):
                    try:
                        # основной, затем ВСЕ дополнительные (правило владельца
                        # «хоть основной, хоть доп»): у Галвента (28.25.13)
                        # основной код в базе без оборудования, целевой — в доп.
                        основной = str(comp.get("okved") or "").split()[0] \
                            if str(comp.get("okved") or "").strip() else ""
                        доп = str(((panel.get("company_full") or {})
                                   .get("reg") or {})
                                  .get("okved_all_codes") or "").split("|")
                        eq, база_код = "", ""
                        for код in [основной] + [k for k in доп if k]:
                            if not код:
                                continue
                            eq = cards.equip_for_okved(код)
                            if eq:
                                база_код = код
                                break
                        if eq:
                            comp["equip_needed"] = eq
                            comp["equip_needed_basis"] = (
                                f"по ОКВЭД {база_код} (формат базы обзвона)")
                    except Exception:  # noqa: BLE001 - показ не роняем
                        pass
            # Смена получателя (оператором или авто-проходом #69) обновляет
            # только row.email — блок «Кому пишем» оставался собранным под
            # СТАРЫЙ адрес. Пересобираем на показ из panel.emails, как подпись.
            if isinstance(panel, dict):
                cont = panel.get("contact")
                if isinstance(cont, dict) and (cont.get("email") or "").lower() \
                        != str(r.get("email") or "").strip().lower():
                    try:
                        from sender.infopanel import _contact_block
                        panel["contact"] = _contact_block(
                            str(r.get("email") or ""),
                            panel.get("emails") or [],
                            # verified живёт только в блоке контакта: в блоке
                            # company его нет, а без него пересобранная карточка
                            # теряет подтверждение сайта
                            {**(panel.get("company") or {}),
                             "verified": cont.get("verified") or ""},
                            {})
                    except Exception:  # noqa: BLE001 - показ не роняем
                        pass
            if isinstance(panel, dict) and isinstance(panel.get("letter"), dict):
                sig = _signature_for(deps, sa.get("from_name") or "",
                                     campaign_id=r.get("campaign_id"))
                body = (panel["letter"].get("body") or "").rstrip()
                first = sig.split("\n")[0].rstrip() if sig else ""
                # тот же дедуп, что в Sender._apply_signature: письмо уже
                # кончается на «С уважением,», второй раз строку не печатаем
                if sig and first and body.endswith(first):
                    sig = "\n".join(sig.split("\n")[1:]).lstrip("\n")
                panel["letter"]["signature"] = sig
                panel["letter"]["final_body"] = (body + "\n" + sig) if sig else body
        # total — размер очереди С УЧЁТОМ фильтра направления (null, если
        # фильтра не было и полный набор не считался). counts остаётся
        # глобальным: шапка показывает состояние всей очереди, а не среза.
        return {"pending": rows, "counts": deps.confirm.counts(),
                "total": всего,
                "live": bool(getattr(deps.confirm, "live", False))}

    @app.post("/confirm/{rid}/mailbox")
    def confirm_set_mailbox(rid: int, body: MailboxBody,
                            p: Principal = Depends(principal)):
        from sender.confirm import ConfirmBlockedError
        try:
            row = deps.confirm.set_mailbox(rid, body.mailbox_id,
                                           operator=p.username)
        except ConfirmBlockedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"ok": True, "review": row}

    @app.get("/confirm/golden")
    def confirm_golden(limit: int = 500, p: Principal = Depends(principal)):
        return {"pairs": deps.confirm.golden_pairs(limit=limit)}

    @app.get("/confirm/{rid}")
    def confirm_get(rid: int, p: Principal = Depends(principal)):
        row = deps.confirm.get(rid)
        if row is None:
            raise HTTPException(status_code=404, detail="review not found")
        return row

    @app.post("/confirm/{rid}/recipient")
    def confirm_set_recipient(rid: int, body: RecipientBody,
                              p: Principal = Depends(principal)):
        """Сменить адрес получателя на другой контакт компании (Фича 1)."""
        from sender.confirm import ConfirmBlockedError
        from sender.errors import ValidationError as _VErr
        try:
            row = deps.confirm.set_recipient_email(
                rid, body.email, operator=p.username, actor_user_id=p.user_id)
        except ConfirmBlockedError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except _VErr as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "review": row}

    @app.post("/confirm/{rid}/decision")
    def confirm_decision(rid: int, body: ConfirmDecisionBody,
                         p: Principal = Depends(principal)):
        from sender.confirm import ConfirmBlockedError
        from sender.errors import ValidationError as _VErr
        # Ревью #48: пока письмо перегенерируется (#71), отправлять его нельзя —
        # фоновый поток может подменить текст МЕЖДУ тем, что оператор видит на
        # экране, и моментом approve: ушло бы письмо, которое никто не читал.
        # Правку блокируем по той же причине (edit без subject/body берёт текст
        # из БД). Скип/стоп-лист безопасны — текст им не важен.
        if body.action in ("approve", "edit"):
            st = _regen_box.get(rid)
            if st and st.get("running"):
                raise HTTPException(
                    status_code=409,
                    detail="идёт перегенерация этого письма — дождитесь "
                           "результата и перечитайте текст")
        try:
            if body.action == "approve":
                done = deps.confirm.approve(rid, operator=p.username,
                                            force=bool(body.force),
                                            actor_user_id=getattr(p, "user_id", None))
            elif body.action == "edit":
                done = deps.confirm.edit(rid, subject=body.subject,
                                         body=body.body, operator=p.username,
                                         force=bool(body.force),
                                         actor_user_id=getattr(p, "user_id", None))
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
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            # Ревью №15: ошибки БОЕВОЙ отправки (SuppressedError, GateTripped,
            # SendError, TransientError, ConfigError) уходили оператору как
            # голый HTTP 500 без причины — человек видел «ошибка сервера» и не
            # понимал, ушло письмо или нет. Отдаём человеческую причину;
            # письмо при этом остаётся в очереди и его можно повторить.
            name = type(e).__name__
            human = {
                "SuppressedError": "адрес в стоп-листе (отписка или жалоба) — письмо не отправлено",
                "GateTrippedError": "сработал гейт репутации ящика — отправка приостановлена",
                "RateLimitExceeded": "исчерпан дневной лимит ящика — попробуйте позже",
                "TransientError": "временная ошибка почтового сервера — письмо осталось в очереди, повторите",
                "SendError": "почтовый сервер отклонил письмо",
                "PersonalizationGateError": "в письме остались незаполненные поля",
                "ConfigError": "ошибка конфигурации ящика",
            }.get(name)
            detail = f"{human}: {e}" if human else f"{name}: {e}"
            logger.exception("confirm_decision rid=%s action=%s", rid, body.action)
            raise HTTPException(status_code=409 if human else 500, detail=detail)
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

    # --- окно авто-отправки (владелец задаёт из панели; ручную отправку не трогает) ---
    _WINDOW_DEFAULT = {"days": [1, 2, 3, 4], "start": "09:00", "end": "11:00",
                       "tz": "Europe/Moscow"}

    # ===== Пауза ящика и общий стоп =====
    # Движок и CLI умели это с самого начала (store.set_mailbox_paused,
    # cli pause/resume), а в панели была только колонка «Пауза» на чтение:
    # остановить ящик из веба было нельзя, приходилось идти в консоль сервера.
    @app.post("/mailboxes/{mailbox_id}/pause")
    def mailbox_pause(mailbox_id: str, body: PauseBody,
                      p: Principal = Depends(owner)):
        known = {mb.mailbox_id for mb in deps.config.mailboxes()}
        if mailbox_id not in known:
            raise HTTPException(status_code=404, detail=f"нет ящика {mailbox_id}")
        if body.paused and not (body.reason or "").strip():
            raise HTTPException(status_code=422, detail="нужна причина паузы")
        deps.store.set_mailbox_paused(mailbox_id, bool(body.paused),
                                      (body.reason or "").strip() or None)
        with suppress(Exception):
            deps.store.append_audit(
                action="mailbox.pause" if body.paused else "mailbox.resume",
                actor_user_id=p.user_id, entity_type="mailbox",
                entity_id=mailbox_id, detail={"reason": body.reason})
        return {"ok": True, "mailbox_id": mailbox_id, "paused": bool(body.paused)}

    @app.post("/mailboxes/pause-all")
    def mailboxes_pause_all(body: PauseBody, p: Principal = Depends(owner)):
        """ОСТАНОВИТЬ ВСЁ одной кнопкой: при подозрении на проблему с
        репутацией счёт идёт на минуты, и щёлкать 14 ящиков по одному нельзя."""
        if body.paused and not (body.reason or "").strip():
            raise HTTPException(status_code=422, detail="нужна причина остановки")
        ids = [mb.mailbox_id for mb in deps.config.mailboxes()]
        for mid in ids:
            with suppress(Exception):
                deps.store.set_mailbox_paused(mid, bool(body.paused),
                                              (body.reason or "").strip() or None)
        with suppress(Exception):
            deps.store.append_audit(
                action="mailboxes.pause_all" if body.paused else "mailboxes.resume_all",
                actor_user_id=p.user_id, entity_type="mailbox", entity_id=None,
                detail={"reason": body.reason, "ящиков": len(ids)})
        return {"ok": True, "ящиков": len(ids), "paused": bool(body.paused)}

    # ===== Дневной лимит отправки: владелец может ПРИЖАТЬ рампу =====
    # Возвращены 26.07: ручки существовали, но потерялись при синхронизации
    # репозитория с боем. Важно: настройка работает только ВНИЗ (Sender._daily_limit),
    # поднять лимит выше рампы нельзя — иначе прогрев теряет смысл.
    @app.get("/send-limits")
    def send_limits_get(p: Principal = Depends(principal)):
        cfg = deps.store.get_setting("send_limits") or {}
        if isinstance(cfg, str):
            import json as _json
            with suppress(Exception):
                cfg = _json.loads(cfg)
        if not isinstance(cfg, dict):
            cfg = {}
        per = cfg.get("per_mailbox") or {}
        rows = []
        for mb in deps.config.mailboxes():
            r = deps.sender.mailbox_readiness(mb.mailbox_id)
            rows.append({"mailbox_id": mb.mailbox_id,
                         "from_name": getattr(mb, "from_name", "") or "",
                         "division": getattr(mb, "division", None),
                         "ramp_day": r.ramp_day,
                         "effective_limit": r.daily_limit,
                         "sent_today": r.sent_today,
                         "paused": r.paused,
                         "override": per.get(mb.mailbox_id, cfg.get("all"))})
        return {"all": cfg.get("all"), "per_mailbox": per, "mailboxes": rows}

    @app.post("/send-limits")
    def send_limits_set(body: SendLimitsBody, p: Principal = Depends(owner)):
        if body.all is not None and body.all < 0:
            raise HTTPException(status_code=422, detail="лимит не может быть отрицательным")
        known = {mb.mailbox_id for mb in deps.config.mailboxes()}
        per: Dict[str, int] = {}
        for mid, lim in (body.per_mailbox or {}).items():
            if mid not in known:
                raise HTTPException(status_code=422, detail=f"неизвестный ящик {mid}")
            if lim is None:
                continue
            if int(lim) < 0:
                raise HTTPException(status_code=422, detail=f"{mid}: лимит отрицательный")
            per[mid] = int(lim)
        deps.store.set_setting("send_limits",
                               {"all": body.all, "per_mailbox": per})
        with suppress(Exception):
            deps.store.append_audit(action="send_limits.set", actor_user_id=p.user_id,
                                    entity_type="settings", entity_id="send_limits",
                                    detail={"all": body.all, "per_mailbox": per})
        return send_limits_get(p)

    # ===== Автоответчик: тумблер, который РЕАЛЬНО выключает =====
    # Раньше включался только строкой в конфиге при СТАРТЕ службы (wiring), то
    # есть выключить его из панели было нельзя. Теперь флаг живёт в
    # panel_settings и проверяется в момент обработки входящего письма.
    @app.get("/autoresponder")
    def autoresponder_get(p: Principal = Depends(principal)):
        v = deps.store.get_setting("autoresponder_enabled", None)
        собран = deps.reply_pipeline is not None
        return {"enabled": bool(v) if v is not None else False,
                "available": собран,
                "note": ("" if собран else
                         "модуль не поднят: включите autoresponder.enabled в "
                         "конфиге и перезапустите службу")}

    @app.post("/autoresponder")
    def autoresponder_set(body: AutoresponderBody, p: Principal = Depends(owner)):
        deps.store.set_setting("autoresponder_enabled", bool(body.enabled))
        with suppress(Exception):
            deps.store.append_audit(action="autoresponder.set", actor_user_id=p.user_id,
                                    entity_type="autoresponder", entity_id=None,
                                    detail={"enabled": bool(body.enabled)})
        return autoresponder_get(p)

    @app.get("/sending-window")
    def get_sending_window(p: Principal = Depends(principal)):
        ov = deps.store.get_setting("sending_window")
        if not isinstance(ov, dict) or not ov.get("days"):
            # нет override — показываем текущее из конфига
            try:
                w = deps.config.sending_window()
                cur = {"days": list(w.days), "start": w.start, "end": w.end, "tz": w.tz}
            except Exception:  # noqa: BLE001
                cur = dict(_WINDOW_DEFAULT)
            return {"window": cur, "source": "config"}
        return {"window": ov, "source": "override"}

    @app.post("/sending-window")
    def set_sending_window(body: WindowBody, p: Principal = Depends(owner)):
        days = sorted({int(d) for d in (body.days or []) if 1 <= int(d) <= 7})
        if not days:
            raise HTTPException(status_code=422, detail="days: нужен хотя бы один день 1-7")
        import re as _re
        for t in (body.start, body.end):
            if not _re.match(r"^\d{2}:\d{2}$", t or ""):
                raise HTTPException(status_code=422, detail=f"время в формате HH:MM: {t!r}")
        if body.start >= body.end:
            raise HTTPException(status_code=422, detail="start должен быть раньше end")
        win = {"days": days, "start": body.start, "end": body.end,
               "tz": body.tz or "Europe/Moscow"}
        deps.store.set_setting("sending_window", win)
        try:
            deps.store.append_audit(action="sending_window.set", actor_user_id=p.user_id,
                                    entity_type="settings", entity_id="sending_window",
                                    detail=win)
        except Exception:  # noqa: BLE001
            pass
        return {"window": win, "source": "override"}

    @app.get("/settings/out-of-base")
    def get_out_of_base(p: Principal = Depends(principal)):
        """Тумблер «слать по email вне базы» (дефолт ВЫКЛ)."""
        try:
            v = deps.store.get_setting("allow_out_of_base", None)
        except Exception:  # noqa: BLE001
            v = None
        return {"allow_out_of_base": bool(v) if v is not None else False,
                "explicit": v is not None}

    @app.post("/settings/out-of-base")
    def set_out_of_base(body: OutOfBaseBody, p: Principal = Depends(owner)):
        """Владелец включает/выключает отправку по адресам вне базы обзвона."""
        deps.store.set_setting("allow_out_of_base", bool(body.allow))
        try:
            deps.store.append_audit(action="out_of_base.set", actor_user_id=p.user_id,
                                    entity_type="settings", entity_id="allow_out_of_base",
                                    detail={"allow": bool(body.allow)})
        except Exception:  # noqa: BLE001
            pass
        return {"allow_out_of_base": bool(body.allow)}

    # --- дневная квота AI-генерации (карточка «Дневная квота генерации») ---
    # Движок держим одним экземпляром на процесс: в нём лок «один прогон за
    # раз», иначе двойной клик по кнопке запустил бы две генерации и выбрал
    # квоту дважды. Создаём лениво — панель поднимается и без модуля генерации.
    _quota_box: dict = {}

    def _quota():
        q = _quota_box.get("q")
        if q is None:
            from sender.ai_quota import build_ai_quota
            q = build_ai_quota(deps.store, deps.config)
            _quota_box["q"] = q
        return q

    @app.get("/ai/quota")
    def get_ai_quota(campaign_id: int, days: int = 7,
                     p: Principal = Depends(principal)):
        from sender.errors import ValidationError as _VErr
        q = _quota()
        try:
            rows = q.days(campaign_id, horizon=days)
            left = q.candidates_left(campaign_id)
        except _VErr as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"campaign_id": campaign_id, "today": q.today(),
                "days": [d.as_json() for d in rows],
                "candidates_left": left,
                "run": q.run_state(campaign_id)}

    @app.post("/ai/quota")
    def set_ai_quota(body: QuotaScheduleBody, p: Principal = Depends(owner)):
        from sender.errors import ValidationError as _VErr
        q = _quota()
        try:
            sched = q.set_schedule(body.campaign_id, body.schedule or {})
        except _VErr as e:
            raise HTTPException(status_code=422, detail=str(e))
        try:
            deps.store.append_audit(action="ai_quota.set", actor_user_id=p.user_id,
                                    entity_type="campaign", entity_id=body.campaign_id,
                                    detail={"patch": body.schedule})
        except Exception:  # noqa: BLE001
            pass
        return {"campaign_id": body.campaign_id, "schedule": sched,
                "days": [d.as_json() for d in q.days(body.campaign_id)]}

    @app.post("/ai/quota/run")
    def run_ai_quota(body: QuotaRunBody, p: Principal = Depends(owner)):
        """Старт генерации по остатку квоты. Отвечаем сразу: прогон идёт в
        фоне (LLM-раунды на письмо — это минуты), UI поллит GET /ai/quota."""
        from sender.errors import ValidationError as _VErr
        q = _quota()
        try:
            state = q.start_run(body.campaign_id, actor=p.username,
                                count=body.count)
        except _VErr as e:
            raise HTTPException(status_code=422, detail=str(e))
        try:
            deps.store.append_audit(action="ai_quota.run", actor_user_id=p.user_id,
                                    entity_type="campaign", entity_id=body.campaign_id,
                                    detail={"date": state.get("date")})
        except Exception:  # noqa: BLE001
            pass
        return {"campaign_id": body.campaign_id, "run": state}

    # #71: перегенерация одного письма очереди. Поток на письмо; статус в
    # памяти процесса (рестарт панели обрывает генерацию — идемпотентно,
    # оператор просто нажмёт ещё раз). Выставлен в app.state, чтобы гейт
    # «не отправлять во время перегенерации» был проверяем тестами.
    _regen_box: dict = {}
    app.state.regen_box = _regen_box

    @app.post("/confirm/{rid}/regenerate")
    def confirm_regenerate(rid: int, p: Principal = Depends(owner)):
        import threading as _th
        st = _regen_box.get(rid)
        if st and st.get("running"):
            return {"ok": True, "running": True}
        row = deps.confirm.get(rid)
        if row is None or row.get("status") != "pending":
            raise HTTPException(status_code=409,
                                detail="письмо не в очереди (не pending)")
        state = {"running": True, "error": None, "result": None}
        _regen_box[rid] = state

        def _worker():
            try:
                q = _quota()
                out = q.regenerate_review(rid)
                if out.get("ok"):
                    state["result"] = out
                else:
                    state["error"] = (out.get("reason") or "не получилось") + \
                        ("; " + "; ".join(out.get("fails") or [])
                         if out.get("fails") else "")
            except Exception as e:  # noqa: BLE001
                state["error"] = str(e)[:300]
            finally:
                state["running"] = False

        _th.Thread(target=_worker, daemon=True).start()
        try:
            deps.store.append_audit(action="confirm.regenerate",
                                    actor_user_id=p.user_id,
                                    entity_type="confirm_review", entity_id=rid)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "running": True}

    @app.get("/confirm/{rid}/regenerate/status")
    def confirm_regenerate_status(rid: int, p: Principal = Depends(principal)):
        st = _regen_box.get(rid)
        if not st:
            return {"running": False, "known": False}
        return {"running": bool(st.get("running")), "known": True,
                "error": st.get("error"),
                "subject": (st.get("result") or {}).get("subject")}

    @app.get("/capacity")
    def capacity(p: Principal = Depends(principal)):
        pools = {}
        try:
            pools = deps.config.provider_pools()
        except Exception:  # noqa: BLE001
            pass
        # Ёмкость считаем через mailbox_readiness — ту же формулу, что экран
        # ящиков и сама отправка (рамп-день + ручной потолок). Раньше бралась
        # analytics.capacity_report -> mailbox_state.daily_limit, а это
        # ЗАСТЫВШИЙ столбец с момента посева: владелец видел «ёмкость 3 на
        # ящик» при факте «можно сегодня 5».
        out = []
        for pool, ids in pools.items():
            cap = sent = paused = counted = 0
            for mid in ids:
                try:
                    r = deps.sender.mailbox_readiness(mid)
                except Exception:  # noqa: BLE001
                    continue
                if "no_state" in (r.reasons or ()):
                    continue
                counted += 1
                cap += int(r.daily_limit)
                sent += int(r.sent_today)
                if r.paused:
                    paused += 1
            remaining = max(0, cap - sent)
            util = round(100.0 * sent / cap, 2) if cap > 0 else 0.0
            out.append({"pool": str(pool), "mailbox_count": counted,
                        "daily_capacity": cap, "sent_today": sent,
                        "remaining_today": remaining,
                        "utilization_pct": util,
                        "paused_mailboxes": paused})
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


def _signature_for(deps: Deps, manager_name: str,
                   campaign_id: Optional[int] = None) -> str:
    """Подпись ровно та, что допишет отправка (Sender._apply_signature).

    Имя менеджера берём из ВЫБРАННОГО ящика, а не подставляем заглушку:
    оператор должен видеть письмо в точности таким, каким его получит клиент.
    §8: кампания может задать своего подписанта (manager_name/manager_role в
    config_json) — тогда предпросмотр показывает его, как и отправка.
    """
    try:
        from sender.sender import Sender
        cfg = deps.config
        tmpl = (cfg.get("personalization.signature_template", None)
                if hasattr(cfg, "get") else None) or Sender._DEFAULT_SIGNATURE
        inn = ""
        camp_cfg: dict = {}
        if campaign_id is not None:
            with suppress(Exception):
                camp = deps.store.get_campaign(int(campaign_id))
                if camp is not None:
                    inn = str(getattr(camp, "legal_inn", "") or "")
                    if isinstance(getattr(camp, "config", None), dict):
                        camp_cfg = camp.config
        if not inn:
            legal_fn = getattr(cfg, "legal", None)
            if callable(legal_fn):
                with suppress(Exception):
                    inn = str(getattr(legal_fn(), "inn", "") or "")
        # from_name ящика — «Владислав Мельников, Компрессор Центр» -> имя до запятой
        name = (manager_name or "").split(",")[0].strip()
        name = str(camp_cfg.get("manager_name") or "").strip() or name
        role = (str(camp_cfg.get("manager_role") or "").strip()
                or "Менеджер по продажам")
        return tmpl.format(name=name, inn=inn, role=role)
    except Exception:  # noqa: BLE001
        return ""


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
        """StaticFiles с SPA-fallback: 404 на неизвестный путь → index.html.

        ДВА ОГРАНИЧЕНИЯ, оплаченные белым экраном 26.07.2026.

        1. Фолбэк НЕ распространяется на /assets/ и файлы с расширением. Раньше
           запрос отсутствующего бандла получал в ответ index.html с кодом 200 и
           типом text/html; браузер пытался исполнить HTML как модуль, падал на
           первом же '<' — и страница оставалась пустой БЕЗ единой ошибки в сети.
           Диагностировать это невозможно: сервер отвечает 200 на всё. Теперь
           недостающий ассет — честный 404, видно сразу и в консоли, и в логе.

        2. index.html отдаётся с no-store. Имена бандлов содержат хэш, поэтому
           сами ассеты кэшируются вечно, а вот index.html обязан быть свежим:
           закэшированный указывает на бандл, которого после выкатки уже нет.
           Владелец ловил белый экран повторно именно из-за этого — сервер был
           уже починен, а браузер брал старый index.html из кэша.
        """

        _NO_FALLBACK = ('assets/', 'static/', 'favicon', 'robots.txt')

        def _no_store(self, resp):
            resp.headers['Cache-Control'] = 'no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            return resp

        async def get_response(self, path: str, scope):  # type: ignore[override]
            try:
                resp = await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
                low = (path or '').lstrip('/').lower()
                # запрос файла (есть расширение) или явной статики — не подменяем
                if low.startswith(self._NO_FALLBACK) or '.' in low.rsplit('/', 1)[-1]:
                    raise
                return self._no_store(await super().get_response('index.html', scope))
            # Корень Starlette отдаёт как path='.' (normpath от пустого пути), а не
            # пустой строкой — без этого no-store не вешался именно на «/», то есть
            # ровно на тот запрос, ради которого всё и делается.
            if (path or '').strip('/').lower() in ('', '.', 'index.html'):
                return self._no_store(resp)
            return resp

    site = FastAPI(title="Rusprom Sender Site", version="2.3")
    site.mount("/api", make_app(deps), name="api")

    # Авто-валидатор (просьба владельца: «чтобы при заливке сама включалась и
    # проверялась»). Фоновый поток панели раз в интервал смотрит, появились ли
    # получатели со статусом unknown (импорт CSV, долив лидов, любые будущие
    # пути), и валидирует их порциями — руками ничего запускать не нужно.
    # Живёт только в site-режиме (боевой вход панели): make_app дёргают тесты,
    # и поток там плодил бы DNS-запросы на каждый TestClient.
    if bool(deps.config.get("validation.auto", True)
            if hasattr(deps.config, "get") else True):
        import threading as _th
        import time as _time

        def _auto_validate_loop():
            from sender.importer import auto_validate_once
            interval = float(deps.config.get(
                "validation.auto_interval_sec", 600) or 600)
            while True:
                try:
                    res = auto_validate_once(deps.store, deps.config)
                    if res:
                        logger.info("авто-валидация: %s", res)
                except Exception:  # noqa: BLE001 - DNS-сбой не роняет поток
                    logger.exception("авто-валидация: проход не удался")
                _time.sleep(interval)

        _th.Thread(target=_auto_validate_loop, daemon=True,
                   name="auto-validate").start()

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
