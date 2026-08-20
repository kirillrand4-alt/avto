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

import json
import os
import uuid
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Dict, Optional

import logging
import re as _re_mod
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from sender.auth import Auth, AuthError, Principal, ROLE_OWNER
from sender.leaddesk import LeadConflict


# P2 №6: композиционный корень переехал в sender.wiring — здесь реэкспорт,
# чтобы исторические импорты `from sender.api.app import Deps, build_deps` жили.
from sender.wiring import Deps, build_deps  # noqa: F401

# Вердикты, после которых адрес исчезает из выбора «кому»: писать туда некуда.
# Строками, а не импортом из addr_probe: модуль пробы может быть недоступен
# (тесты API поднимают приложение без него), а список выбора должен работать.
_МЁРТВЫЕ_ВЕРДИКТЫ = ("нет ящика", "нет MX")


# ---- request-модели ---- #

class LoginBody(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None


class KopiyaBody(BaseModel):
    """Копия существующего письма на другой адрес."""
    email: str


class NovoeBody(BaseModel):
    """Письмо с нуля: ящик, адрес, тема, текст.

    Модели тела запроса объявляются НА УРОВНЕ МОДУЛЯ, а не внутри make_app:
    в файле стоит `from __future__ import annotations`, аннотации становятся
    строками, и FastAPI разрешает их по глобальным именам модуля. Класс,
    объявленный внутри функции, туда не попадает — тело запроса тогда
    считается query-параметром и запрос падает с 422 «Field required».
    """
    email: str
    subject: str
    body: str
    mailbox_id: Optional[str] = None
    inn: Optional[str] = None
    campaign_id: Optional[int] = None


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


class AddRecipientBody(BaseModel):
    """Новый контакт компании, вписанный оператором в карточке подтверждения.
    Поля `force` здесь нет и быть не должно: обход стоп-листа при ЗАВЕДЕНИИ
    адреса не предусмотрен (ФЗ-38)."""

    email: str
    note: Optional[str] = None


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
    # направление очереди, которую оператор сейчас разбирает (kc|meyer).
    # Нужно, чтобы ящик отправки совпал с тем, что показан в карточке: у
    # компании «kc+meyer» подходят оба, и без этого письмо из очереди Meyer
    # уходило с компрессорного адреса.
    division: Optional[str] = None


class OutOfBaseBody(BaseModel):
    """Тумблер «слать по email вне базы»."""
    allow: bool


class LeadReplyBody(BaseModel):
    """Ответ оператора из карточки лида (#62): текст в очередь подтверждений."""
    subject: Optional[str] = None
    body: str
    # идентификаторы файлов, загруженных ручкой POST /vlozheniya
    attachments: Optional[list[str]] = None


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
    # «по времени получателя» (владелец 06.08): часы считаются в поясе РЕГИОНА
    # РЕГИСТРАЦИИ получателя, а не в одном общем. Время письма планировщик и
    # так считает в зоне получателя; тумблер убирает встречный запрет
    # воротника, который иначе рубил бы утро Владивостока как ночь Москвы.
    by_recipient_tz: Optional[bool] = None


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


class BulkToAutoBody(BaseModel):
    """Кнопка «в автоотправку» (владелец 06.08): первые N писем очереди
    подтверждений становятся approved и уходят циклу автоотправки — тот шлёт
    их сам, по времени получателя. Нажатие кнопки = решение владельца."""
    count: int                       # 1..300
    gruppa: Optional[str] = None     # тот же фильтр, что в очереди


class AutoSendBody(BaseModel):
    enabled: bool


class SuppressionBulkInnBody(BaseModel):
    """Список ИНН для массового запрета отправки (владелец: «идёт сделка»).
    text — как вставилось (строки/запятые/колонка Excel), парсим сами."""
    text: str
    reason: Optional[str] = None


class ImportBazyBody(BaseModel):
    """Ручная загрузка обогащённой партии (владелец 11.08).

    Файл едет ТЕКСТОМ в теле, а не multipart: multipart тянет за собой
    python-multipart, которого на сервере может не оказаться, и загрузка
    падала бы не на разборе данных, а на отсутствии пакета. Фронт читает файл
    сам и присылает содержимое.
    """
    text: str
    name: Optional[str] = None
    group: Optional[str] = None
    dry_run: bool = True


def make_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="Rusprom Sender Panel", version="2.1")

    @app.middleware("http")
    async def _bez_kesha(request: Request, call_next):
        """Ответы API не кэшировать (06.08: владелец видел старый текст письма).

        Переписали концовку всех писем в базе, панель по /confirm/queue отдавала
        уже новый текст — а в браузере оставался прежний. GET без заголовков
        кэша браузер вправе переиспользовать по своей эвристике, и очередь
        подтверждений «залипала» на снимке до перезагрузки страницы. Для
        оперативных данных (очередь, карточка письма, статусы отправки) это
        прямой путь к решению по устаревшему тексту, поэтому запрещаем явно.
        Статика этим не задета: её отдаёт StaticFiles своим путём, и там
        хэшированные ассеты по-прежнему кэшируются вечно.
        """
        resp = await call_next(request)
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp

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
                   napravlenie: Optional[str] = None,
                   limit: int = 100, offset: int = 0,
                   p: Principal = Depends(principal)):
        напр = (napravlenie or "").strip().lower() or None
        if напр not in (None, "kc", "meyer"):
            raise HTTPException(status_code=422,
                                detail="napravlenie: допустимо kc или meyer")
        leads = deps.leaddesk.queue(status=status, assigned_to=assigned_to,
                                    unassigned=unassigned, reply_kind=reply_kind,
                                    napravlenie=напр,
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
        # НАШ ОТВЕТ компании — отдельно от «отправляли». Владелец 19.08:
        # «сегодня ответили одному — где вот он?». Ответ уходил, но в ленте лид
        # выглядел нетронутым, и оператор не видел, что разговор уже начат.
        with suppress(Exception):   # добавка к ленте: сбой здесь не рушит список
            отв = deps.store.poslednie_otvety(
                inns=[r.get("inn") for r in rows],
                emails=[r.get("email") for r in rows])
            for r in rows:
                digits = "".join(c for c in str(r.get("inn") or "") if c.isdigit())
                em = str(r.get("email") or "").strip().lower()
                r["otvet"] = отв.get(em) or отв.get(digits) or None
        # КОПИЯ ПО АВТООТВЕТУ — отдельным полем, а не строкой внутри
        # «Потребности» (владелец 20.08: «про копию письма убери куда нибудь в
        # понятное поле, и не понятно, на копию письма мы написали такое же
        # письмо или нет»). Статус живой: копия ставится pending и дальше живёт
        # своей жизнью, а текстовая пометка замерзала на «поставлена в очередь».
        with suppress(Exception):
            коп = deps.store.kopii_avtootveta([r.get("recipient_id") for r in rows])
            for r in rows:
                rid = r.get("recipient_id")
                сп = коп.get(int(rid)) if str(rid or "").isdigit() else None
                r["kopiya"] = сп or None
                # тот же текст убираем из «Потребности» — он там мешал читать
                # сам ответ клиента, а у старых лидов уже записан в базе
                r["need"] = _bez_pometki_kopii(r.get("need"))
        return {"leads": rows, "stats": deps.leaddesk.stats()}

    # ---- КОНТАКТЫ И ЛПР ДЛЯ КАРТОЧКИ ЛИДА ------------------------------- #
    # Владелец 19.08: «не понятно кому звонить». В карточке был только адрес,
    # с которого пришёл ответ. Здесь отдаём ВСЕХ известных людей компании и все
    # её телефоны/почты — каждый со ссылкой на страницу-первоисточник, чтобы
    # менеджер мог проверить, откуда мы это взяли, а не верить на слово.
    # Читаем enrich.db напрямую и только на чтение: генерацию писем не трогаем.
    @app.get("/leads/{lead_id}")
    def get_lead(lead_id: int, p: Principal = Depends(principal)):
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="lead not found")
        # Карточка компании — ТА ЖЕ, что была при отправке письма (владелец
        # 11.08). Не пересобираем: человек отвечает на конкретное письмо, и
        # оператор должен видеть ровно то, из чего оно выросло. Пересчёт дал бы
        # другие цифры и другой повод — разговор разошёлся бы с письмом.
        карточка = None
        with suppress(Exception):  # панель — добавка, лид важнее
            к = deps.store.panel_dlya_lida(inn=getattr(lead, "inn", None),
                                           email=getattr(lead, "email", None))
            if к:
                карточка = {"panel": к.get("panel"),
                            "otpravleno": к.get("updated_at") or к.get("created_at"),
                            "pismo_id": к.get("id"),
                            "tema": к.get("edited_subject") or к.get("subject")}
        контакты = {}
        with suppress(Exception):
            контакты = _kontakty_kompanii(getattr(lead, "inn", None))
        return {"lead": _lead_json(lead), "kontakty": контакты,
                "history": deps.leaddesk.history(lead_id),
                "kartochka": карточка}

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

    # ПУБЛИЧНАЯ страница лида. Без Depends(principal) — в этом и смысл: её
    # открывает менеджер, у которого доступа в панель нет. Защита — случайный
    # токен на 32 знака, который можно отозвать; данных в самой ссылке нет.
    @app.get("/lid/{token}", response_class=HTMLResponse)
    def lid_publichno(token: str):
        from sender import lid_ssylka as LS
        from sender import lid_stranica as LST
        lead_id = LS.lead_po_tokenu(token)
        if lead_id is None:
            # Одинаковый ответ на «нет такой ссылки» и «ссылку отозвали»:
            # иначе по разнице ответов можно перебирать токены и узнавать,
            # какие существовали.
            return HTMLResponse(
                "<!doctype html><meta charset=utf-8>"
                "<p style='font:16px system-ui;margin:12vh auto;max-width:26em;"
                "text-align:center'>Ссылка недействительна.</p>", status_code=404)
        lead = deps.leaddesk.get(lead_id)
        if lead is None:
            return HTMLResponse("<!doctype html><meta charset=utf-8>"
                                "<p>Лид удалён.</p>", status_code=404)
        л = _lead_json(lead)
        нить = []
        with suppress(Exception):
            инн = getattr(lead, "inn", None)
            нить = (deps.store.dialog_thread_company(инн) if инн
                    else deps.store.dialog_thread(getattr(lead, "recipient_id", 0)))
        контакты = {}
        with suppress(Exception):
            контакты = _kontakty_kompanii(getattr(lead, "inn", None))
        стр = LST.sobrat(л, нить, контакты, (LS.bez_podpisi, LS.bez_adresov))
        return HTMLResponse(стр, headers={
            # страницу не индексировать и не хранить в общих кэшах
            "X-Robots-Tag": "noindex, nofollow",
            "Cache-Control": "private, no-store"})

    # ---- ССЫЛКА НА ЛИД ДЛЯ ОТДЕЛА ПРОДАЖ ------------------------------- #
    # Владелец 20.08: «механизм передачи в незашифрованном виде только ссылки
    # лида — вся история переписки видна, вся информация КРОМЕ почты и подписи,
    # которая была при отправке». Отдел продаж (28 человек) в панель не ходит,
    # а звонить по ответу надо; при этом рассылочные ящики и персоны рассылки
    # наружу не показываем.
    @app.post("/leads/{lead_id}/ssylka")
    def lead_ssylka_sozdat(lead_id: int, p: Principal = Depends(principal)):
        from sender import lid_ssylka as LS
        if deps.leaddesk.get(lead_id) is None:
            raise HTTPException(status_code=404, detail="lead not found")
        r = LS.sozdat(lead_id, kto=p.username)
        with suppress(Exception):
            deps.store.append_audit(
                action="lead.ssylka", actor_user_id=p.user_id,
                entity_type="lead", entity_id=str(lead_id),
                detail={"otpechatok": LS.podpis_toksena(r["token"]),
                        "sozdana": r["sozdana"]})
        return r

    @app.delete("/leads/{lead_id}/ssylka")
    def lead_ssylka_otozvat(lead_id: int, p: Principal = Depends(principal)):
        from sender import lid_ssylka as LS
        сколько = LS.otozvat(lead_id)
        with suppress(Exception):
            deps.store.append_audit(
                action="lead.ssylka_otozvana", actor_user_id=p.user_id,
                entity_type="lead", entity_id=str(lead_id),
                detail={"pogasheno": сколько})
        return {"otozvano": сколько}

    @app.get("/leads/{lead_id}/ssylki")
    def lead_ssylki(lead_id: int, p: Principal = Depends(principal)):
        from sender import lid_ssylka as LS
        return {"ssylki": LS.spisok(lead_id)}

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

    # ---- ВЛОЖЕНИЯ (владелец 19.08: «как в настоящей почте») -------------- #
    # Файл кладём на диск сразу, а в черновик ответа попадает только ССЫЛКА:
    # держать содержимое в очереди подтверждений — раздувать базу и таскать
    # мегабайты при каждом чтении списка. Имя чистим: путь из браузера приходит
    # какой угодно, а мы его потом подставляем в имя файла письма.
    ВЛОЖЕНИЯ_КОРЕНЬ = r"C:\sender\vlozheniya"
    ПРЕДЕЛ_ФАЙЛА = 15 * 1024 * 1024          # 15 МБ: больше почта режет сама
    ПРЕДЕЛ_ПИСЬМА = 20 * 1024 * 1024

    def _chistoe_imya(имя: str) -> str:
        имя = os.path.basename(str(имя or "").replace("\\", "/"))
        имя = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", имя).strip(" .")
        return (имя or "file.bin")[:120]

    @app.post("/vlozheniya")
    def vlozhenie_upload(file: UploadFile = File(...),
                         p: Principal = Depends(principal)):
        данные = file.file.read(ПРЕДЕЛ_ФАЙЛА + 1)
        if len(данные) > ПРЕДЕЛ_ФАЙЛА:
            raise HTTPException(status_code=413,
                                detail=f"файл больше {ПРЕДЕЛ_ФАЙЛА // 2**20} МБ")
        if not данные:
            raise HTTPException(status_code=422, detail="пустой файл")
        ид = uuid.uuid4().hex
        имя = _chistoe_imya(file.filename)
        папка = os.path.join(ВЛОЖЕНИЯ_КОРЕНЬ, ид)
        os.makedirs(папка, exist_ok=True)
        путь = os.path.join(папка, имя)
        with open(путь, "wb") as f:
            f.write(данные)
            f.flush()
            os.fsync(f.fileno())
        return {"id": ид, "name": имя, "size": len(данные)}

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
        # Вложения: пришли идентификаторы загруженных файлов — превращаем их в
        # пути и кладём в панель черновика. Файла нет на диске (перезапуск,
        # чужой id) — молча не пропускаем, лучше сказать оператору сразу.
        вложения = []
        всего = 0
        for ид in (getattr(body, "attachments", None) or []):
            ид = re.sub(r"[^0-9a-f]", "", str(ид))[:32]
            папка = os.path.join(ВЛОЖЕНИЯ_КОРЕНЬ, ид) if ид else ""
            файлы = os.listdir(папка) if папка and os.path.isdir(папка) else []
            if not файлы:
                raise HTTPException(status_code=404,
                                    detail=f"вложение {ид} не найдено")
            путь = os.path.join(папка, файлы[0])
            размер = os.path.getsize(путь)
            всего += размер
            вложения.append({"id": ид, "name": файлы[0], "size": размер,
                             "path": путь})
        if всего > ПРЕДЕЛ_ПИСЬМА:
            raise HTTPException(
                status_code=413,
                detail=f"вложения весят больше {ПРЕДЕЛ_ПИСЬМА // 2**20} МБ")
        if вложения:
            panel["vlozheniya"] = вложения
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

    # Путь НЕ /recipients/import: он уже занят фоновым импортом CSV, который
    # живёт с P15 и имеет свой опрос состояния. Первая редакция встала на тот
    # же адрес и перекрыла его — FastAPI отдаёт маршрут тому, кто зарегистрирован
    # раньше, и чужая рабочая ручка молча перестала отвечать.
    @app.post("/recipients/zagruzka-partii")
    def recipients_zagruzka_partii(body: ImportBazyBody,
                                   p: Principal = Depends(owner)):
        """Разобрать партию и (по команде) залить её в базу получателей.

        Два шага одной ручкой: dry_run=true показывает, ЧТО получится, и ничего
        не пишет; dry_run=false пишет. Разделение не косметическое — оператор
        должен видеть, сколько адресов уже есть и сколько в стоп-листе, ДО
        записи, иначе загрузка вслепую пишет тем, кто просил не писать.
        """
        from sender.import_bazy import применить, разобрать, свод

        контакты, замечания = разобрать(body.text or "", body.name or "")
        итог = свод(контакты, deps.store)
        ответ = {"zamechaniya": замечания,
                 **{k: v for k, v in итог.items() if k != "kontakty"}}
        if body.dry_run:
            return ответ
        группа = (body.group or "").strip()
        if not группа:
            raise HTTPException(status_code=400,
                                detail="не сказано, в какую группу грузить")
        записано = применить(deps.store, итог["kontakty"], группа=группа,
                             источник=f"ручная загрузка: {body.name or 'файл'}")
        with suppress(Exception):
            deps.store.append_audit(
                action="recipients.zagruzka_partii", actor_user_id=p.user_id,
                entity_type="recipients", entity_id=группа,
                detail={"file": body.name, **записано})
        return {**ответ, "zapisano": записано}

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

    @app.get("/messages/sent")
    def messages_sent(q: Optional[str] = None, campaign_id: Optional[int] = None,
                      mailbox_id: Optional[str] = None, replied: bool = False,
                      napravlenie: Optional[str] = None,
                      limit: int = 100, offset: int = 0,
                      p: Principal = Depends(principal)):
        """Всё отправленное — списком (владелец 11.08).

        Общего списка отправленного в панели не было: письмо можно было
        открыть поштучно или увидеть в карточке лида. Вопрос «этому мы уже
        писали?» решался памятью оператора.
        """
        # napravlenie — «кц» или «мейер» (владелец 20.08). Значение приходит
        # латиницей (kc|meyer), пустое = оба направления.
        напр = (napravlenie or "").strip().lower() or None
        if напр not in (None, "kc", "meyer"):
            raise HTTPException(status_code=422,
                                detail="napravlenie: допустимо kc или meyer")
        итог = deps.store.otpravlennye(
            q=q, campaign_id=campaign_id, mailbox_id=mailbox_id,
            napravlenie=напр, tolko_s_otvetom=bool(replied),
            limit=max(1, min(int(limit), 500)), offset=max(0, int(offset)))
        return итог

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

    @app.post("/suppression/bulk-inn")
    def suppression_bulk_inn(body: "SuppressionBulkInnBody",
                             p: Principal = Depends(owner)):
        """Массовый запрет отправки по ИНН (владелец 06.08: «загружу компании,
        где уже идёт сделка»). Вставляется текст как есть — список, колонка из
        Excel, через запятую; отсюда вынимаются все 10/12-значные числа.
        Идемпотентно: повторная загрузка того же списка ничего не дублирует.
        Бессрочно (сделка «живая», пока владелец сам не снимет запись)."""
        import re as _re
        from sender.dtos import SuppressionIn
        причина = (body.reason or "").strip() or "deal_in_progress"
        инны, кривые = [], []
        for tok in _re.split(r"[\s,;]+", body.text or ""):
            tok = tok.strip().strip('"\'')
            if not tok:
                continue
            цифры = "".join(c for c in tok if c.isdigit())
            if len(цифры) in (10, 12) and цифры == tok:
                инны.append(цифры)
            elif цифры:
                кривые.append(tok[:24])
        инны = list(dict.fromkeys(инны))  # порядок сохраняем, дубли убираем
        if not инны and not кривые:
            raise HTTPException(status_code=422,
                                detail="в тексте не нашлось ни одного ИНН")
        добавлено = было = 0
        for инн in инны:
            _sid, created = deps.store.suppression_add(SuppressionIn(
                scope="inn", value=инн, reason=причина,
                source=f"panel_bulk:{p.username}"))
            if created:
                добавлено += 1
            else:
                было += 1
        with suppress(Exception):
            deps.store.append_audit(
                action="suppression.bulk_inn", actor_user_id=p.user_id,
                entity_type="suppression", entity_id=None,
                detail={"reason": причина, "added": добавлено,
                        "existed": было, "invalid": len(кривые)})
        return {"added": добавлено, "existed": было,
                "invalid": кривые[:50], "total_parsed": len(инны)}

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

    def _легенда() -> list:
        """Расшифровка значков проверок. Отдаётся вместе с очередью, чтобы
        фронт не хранил свой список и не разъезжался при добавлении проверки."""
        try:
            from sender.proverki import ЛЕГЕНДА
            return list(ЛЕГЕНДА)
        except Exception:  # noqa: BLE001
            return []

    @app.get("/confirm/queue")
    def confirm_queue(campaign_id: Optional[int] = None, limit: int = 50,
                      offset: int = 0, order: str = "score",
                      division: Optional[str] = None,
                      gruppa: Optional[str] = None,
                      hide_blocked: bool = False,
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

        # Раскладываем по направлению ПИСЬМА, а не компании (решение владельца
        # 28.07). Метка компании берётся из ОКВЭД и базы обзвона и с письмом
        # расходится: у АЛРОСЫ (добыча алмазов) метка «meyer», а потребность и
        # новость — компрессоры, поэтому генератор пишет компрессорное письмо.
        # По метке оно попадало в очередь Meyer, и оператор видел «направление
        # Meyer» над текстом про компрессоры, ящик и подпись — компрессорные.
        # По направлению письма всё сходится само: текст, ящик, подпись.
        # Письмо, чьё направление определить нельзя, показываем в ОБЕИХ очередях —
        # чтобы оно не пропало из работы.
        def _по_направлению(r) -> bool:
            if not напр:
                return True
            d = ""
            getter = getattr(deps.confirm, "letter_division", None)
            if callable(getter):
                try:
                    d = str(getter(r) or "")
                except Exception:  # noqa: BLE001 - показ не роняем
                    d = ""
            if not d:      # старый движок/не определилось — падаем на метку компании
                d = str((((r.get("panel") or {}).get("company") or {})
                         .get("division") or ""))
            d = d.lower()
            return (not d) or (напр in d)

        # Фильтр ГРУППЫ (владелец 05.08: «сделай фильтр очереди по группам,
        # чтобы можно было выбрать новостные, по металлам, ещё какие-то»).
        # Стоит ЗДЕСЬ по той же причине, что фильтр направления выше: на клиенте
        # он отфильтровал бы одну страницу, а счётчик «осталось N» врал бы.
        # Группа берётся из получателя (segment + extra_json.gruppy), поэтому
        # карта строится ОДИН раз на запрос, а не запросом на письмо.
        гр = (gruppa or "").strip()
        if гр.lower() in ("", "все", "all"):
            гр = ""
        карта_групп = {}
        if гр:
            try:
                карта_групп = deps.store.recipient_groups()
            except Exception:  # noqa: BLE001 - показ не роняем
                карта_групп = {}

        # Скрытие «ждущих созревания доменов» (владелец 06.08: «либо из очереди
        # они просто скрывались (корпоративные)»). Гейт молодого домена держит
        # письма получателям на СОБСТВЕННЫХ почтовых серверах: их шлюзы
        # отбивают почту с новых доменов («550 5.7.1 blocked due to security
        # reason» от НПО «Сатурн»). Показывать такое письмо оператору незачем —
        # отправить он его всё равно не сможет, а место в очереди оно занимает.
        # Считаем ТЕМ ЖЕ кодом, что и сам заслон, чтобы фильтр и запрет не
        # разъезжались.
        # Карту почтовых серверов получателей читаем ВСЕГДА, а не только под
        # галкой. Причина: 09.08 владелец снял гейт молодых доменов («галочкой
        # могу определять, когда им отправлять»), и вместе с гейтом исчез
        # единственный признак, по которому корпоративного получателя было
        # видно: blocked_hidden обнулился, галка перестала фильтровать что-либо,
        # а mx_provider в строке письма не отдавался вовсе. Получилось бы хуже,
        # чем до снятия: и заслона нет, и различить нельзя. Признак живёт
        # отдельно от заслона.
        карта_mx: dict = {}
        ящики_все: list = []
        try:
            from sender.gates import young_domain_all_blocked  # noqa: F401
            карта_mx = deps.store.recipient_mx_map()
            ящики_все = [m.mailbox_id for m in deps.config.mailboxes()]
        except Exception:  # noqa: BLE001 - показ очереди не роняем
            карта_mx = {}

        # Свой почтовый сервер = не публичный провайдер. Именно такие шлюзы
        # режут письма с молодых доменов, и именно их владелец хочет видеть
        # и решать по ним отдельно.
        СВОЙ_СЕРВЕР = ("other", "unknown")

        def _mx_письма(r) -> Optional[str]:
            if not карта_mx:
                return None
            rid_ = r.get("recipient_id")
            mx = (карта_mx.get("по_id") or {}).get(int(rid_)) if rid_ else None
            if mx is None:
                em = str(r.get("email") or "").strip().lower()
                mx = (карта_mx.get("по_почте") or {}).get(em)
            return mx

        _причины_блока: dict = {}

        def _ждёт_созревания(r) -> Optional[str]:
            """Причина, по которой письмо сейчас не отправить, или None.

            Пока гейт молодых доменов включён — его причина с датой. Когда он
            снят, причины нет: письмо отправляемо, и галка прячет такие письма
            уже не как «запрещённые», а как «на свой сервер» (см. _свой_сервер).
            """
            if not карта_mx:
                return None
            try:
                from sender.gates import young_domain_all_blocked
                return young_domain_all_blocked(deps.config, ящики_все,
                                                _mx_письма(r))
            except Exception:  # noqa: BLE001
                return None

        def _свой_сервер(r) -> bool:
            return str(_mx_письма(r) or "").strip().lower() in СВОЙ_СЕРВЕР

        def _проставить_проверки(письма_) -> None:
            """Значки пройденных проверок каждому письму (владелец 11.08).

            Проверок шесть и они жили порознь: проба в своей таблице, стоп-лист
            в своей, гейт адресата в третьей, ловушки в коде, тип сервера в
            карточке. Оператор видел только адрес. Собираем всё в одну строку
            значков; карты читаются ОДНИМ запросом на таблицу, а не по разу на
            письмо — писем сотни.
            """
            try:
                from sender.lovushki import вид_ловушки
                from sender.proverki import (ЛЕГЕНДА, провайдер_по_mx,
                                             проверки_письма, собрать_карты)
            except Exception:  # noqa: BLE001 - показ очереди важнее значков
                return
            # Запасные адреса кладём в строку ДО сбора карт: карты читаются
            # одним запросом на таблицу, и адреса надо знать заранее.
            for r in письма_:
                п = r.get("panel") if isinstance(r.get("panel"), dict) else {}
                r["_pochty"] = [str(c.get("email")).strip().lower()
                                for c in (п.get("emails") or [])
                                if isinstance(c, dict) and c.get("email")]
            карты = собрать_карты(deps.store, письма_)

            def _проверить(почта, r, свой_провайдер=None):
                домен = почта.split("@")[-1] if "@" in почта else ""
                стоп = (карты["stop"].get(почта) or карты["stop"].get(домен)
                        or карты["stop"].get(str(r.get("inn") or "")))
                return проверки_письма(
                    email=почта, inn=r.get("inn"),
                    mx_provider=свой_провайдер,
                    вердикт_пробы=карты["proba"].get(почта),
                    в_стоп_листе=стоп,
                    вердикт_гейта=карты["gejt"].get(str(r.get("inn") or "")),
                    ловушка=вид_ловушки(
                        почта, отбивался=почта in карты["bounce"],
                        живой_по_пробе=карты["proba"].get(почта) == "есть"))

            for r in письма_:
                if (r.get("kind") or "outbound") == "reply":
                    r.pop("_pochty", None)
                    continue
                почта = str(r.get("email") or "").strip().lower()
                r["proverki"] = _проверить(почта, r, r.get("mx_provider"))
                # Каждый адрес выпадающего списка со своим набором значков:
                # оператор переключает письмо между ними, и знать про адрес
                # надо ДО переключения. Провайдер у запасных берётся из MX,
                # который вернула проба, — в карточке получателя его нет.
                прочие = {}
                for а in (r.get("_pochty") or []):
                    if а and а != почта:
                        прочие[а] = _проверить(
                            а, r, провайдер_по_mx(карты["mx"].get(а)) or None)
                r["proverki_adresov"] = прочие
                # Заведомо недоставимые адреса убираем из выбора совсем
                # (владелец 12.08: «нам главное не сжечь свои почты, убирай их
                # нафиг»). Фильтр живой: он смотрит вердикт пробы при каждой
                # выдаче очереди, поэтому адрес исчезает из списка сам, как
                # только вердикт пришёл, и возвращается, если тот изменился.
                # Текущий адрес письма не трогаем: его судьбу решает заслон
                # подтверждения, а молча убрать письмо из очереди хуже, чем
                # показать оператору проблему.
                п = r.get("panel") if isinstance(r.get("panel"), dict) else None
                if isinstance(п, dict) and isinstance(п.get("emails"), list):
                    живые, убрано = [], 0
                    for c in п["emails"]:
                        а = str((c or {}).get("email") or "").strip().lower()
                        if а and а != почта and \
                                карты["proba"].get(а) in _МЁРТВЫЕ_ВЕРДИКТЫ:
                            убрано += 1
                            прочие.pop(а, None)
                            continue
                        живые.append(c)
                    if убрано:
                        п["emails"] = живые
                        п["emails_skryto_mertvyh"] = убрано
                r.pop("_pochty", None)

        def _по_группе(r) -> bool:
            if not гр:
                return True
            rid = r.get("recipient_id")
            наб = (карта_групп.get("по_id") or {}).get(int(rid)) if rid else None
            if наб is None:
                em = str(r.get("email") or "").strip().lower()
                наб = (карта_групп.get("по_почте") or {}).get(em)
            if наб is None:
                d = "".join(c for c in str(r.get("inn") or "") if c.isdigit())
                наб = (карта_групп.get("по_инн") or {}).get(d)
            # Письмо, чью группу определить нельзя, НЕ показываем в выбранной
            # группе: иначе «металлообработка» покажет всё подряд, и фильтр
            # перестанет отвечать на вопрос оператора.
            return bool(наб) and гр in наб

        # Порядок — по скорингу (#70): «горячий — писать в первую очередь».
        # Сортировать надо ВЕСЬ pending, а не страницу: раньше pending(limit,
        # offset) резал по id ДО сортировки, и «зелёные» всплывали в каждой
        # подгруженной странице заново (владелец 27.07: «сортировка идёт не
        # среди всех 319, а только среди первых 50»). Поэтому при сортировке
        # по баллу тянем всё, сортируем глобально и режем страницу сами.
        # По той же причине полный набор нужен и при фильтре направления —
        # иначе фильтровать было бы нечего, кроме уже отрезанной страницы.
        всего: Optional[int] = None
        скрыто_ждущих = 0
        ждут_до = ""
        корпоративных = 0
        if order != "id" or напр or гр or hide_blocked:
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
            rows = [r for r in rows if _по_направлению(r) and _по_группе(r)]
            # Признак «свой почтовый сервер» ставим КАЖДОМУ письму независимо
            # от галки: оператор должен видеть, кому пишет, а не догадываться.
            for r in rows:
                if (r.get("kind") or "outbound") == "reply":
                    continue
                r["mx_provider"] = _mx_письма(r)
                r["svoy_server"] = _свой_сервер(r)
                if r["svoy_server"]:
                    корпоративных += 1
            _проставить_проверки(rows)
            if hide_blocked:
                живые = []
                for r in rows:
                    # черновики ответов клиентам не прячем никогда: там пишет
                    # человек, который нам уже написал
                    if (r.get("kind") or "outbound") == "reply":
                        живые.append(r)
                        continue
                    причина = _ждёт_созревания(r)
                    if причина:
                        скрыто_ждущих += 1
                        if not ждут_до:
                            # причина заканчивается «слать можно с 2026-08-20»
                            м = _re_mod.search(r"\d{4}-\d{2}-\d{2}", str(причина))
                            ждут_до = м.group(0) if м else ""
                        continue
                    # Гейт снят — галка всё равно должна работать: прячем
                    # письма на собственные почтовые серверы. Иначе после
                    # снятия заслона галка молча перестала бы делать что-либо.
                    if r.get("svoy_server"):
                        скрыто_ждущих += 1
                        continue
                    живые.append(r)
                rows = живые
            # сколько писем в очереди ПОД ФИЛЬТРОМ — иначе панель не может
            # честно посчитать «осталось N» для кнопки «показать ещё»
            всего = len(rows)
            rows = rows[offset:offset + max(0, int(limit))]
        else:
            rows = deps.confirm.pending(campaign_id=campaign_id, limit=limit,
                                        offset=offset)
            for r in rows:
                if (r.get("kind") or "outbound") == "reply":
                    continue
                r["mx_provider"] = _mx_письма(r)
                r["svoy_server"] = _свой_сервер(r)
                if r["svoy_server"]:
                    корпоративных += 1
            _проставить_проверки(rows)
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
                                     campaign_id=r.get("campaign_id"),
                                     division=sa.get("division"))
                body = (panel["letter"].get("body") or "").rstrip()
                # РОД ОТПРАВИТЕЛЯ в предпросмотре: тот же пересчёт, что делает
                # отправка (Sender._apply_signature) — оператор должен видеть
                # «Прочитала», если письмо уйдёт с женского ящика (скрин
                # владельца 28.07). Сырое тело в БД не трогаем: правка идёт по
                # нему, а согласование идемпотентно и повторится на отправке.
                try:
                    from sender.gender_agree import agree_for_mailbox
                    body = agree_for_mailbox(body, sa.get("from_name") or "",
                                             deps.config,
                                             sa.get("mailbox_id") or "")
                    panel["letter"]["body"] = body
                except Exception:  # noqa: BLE001 - показ не роняем
                    pass
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
                # сколько писем спрятано как «ждущие созревания доменов» и до
                # какой даты: оператор должен видеть, что они не потерялись
                "blocked_hidden": скрыто_ждущих,
                "blocked_until": ждут_до,
                # Сколько писем идёт на СОБСТВЕННЫЕ почтовые серверы
                # получателей. Считается всегда, даже когда гейт снят: это
                # то, по чему владелец решает, когда таким писать.
                "corp_total": корпоративных,
                # Расшифровка значков — рядом с данными, чтобы фронт не хранил
                # свой список и не разъезжался с сервером при добавлении проверки.
                "proverki_legenda": _легенда(),
                "live": bool(getattr(deps.confirm, "live", False))}

    def _проверить_срочно(*адреса) -> None:
        """Отправить адрес, введённый человеком, на проверку немедленно.

        Отбивка 11.08 показала, чего стоит промедление: оператор подменил адрес
        письма в 05:35:08, письмо ушло в 05:35:51, Google ответил «аккаунт
        отключён». Проба не ошиблась — её не успели спросить: круг публикации
        идёт раз в десять минут, а между вводом адреса и отправкой прошло сорок
        три секунды.

        В отдельном потоке: запрос оператора не должен ждать обмена с дропом.
        Ошибка здесь не отменяет операцию — адрес всё равно уйдёт обычным
        кругом, просто позже.
        """
        import threading

        цикл = getattr(app.state, "probe_sync", None)
        годные = [str(а).strip().lower() for а in адреса
                  if а and "@" in str(а)]
        if цикл is None or not годные:
            return

        def _в_фоне() -> None:
            try:
                r = цикл.срочно(годные)
                if r.get("срочных"):
                    logger.info("срочная проба адреса: %s", r)
            except Exception:  # noqa: BLE001 - проверка не вышла, письмо живо
                logger.exception("срочная проба не удалась: %s", годные)

        threading.Thread(target=_в_фоне, name="probe-srochno",
                         daemon=True).start()

    @app.post("/confirm/{rid}/kopiya")
    def confirm_kopiya(rid: int, body: KopiyaBody,
                       p: Principal = Depends(principal)):
        """То же письмо — на другой адрес (владелец 11.08).

        Случай из жизни: автоответ назвал имя коллеги, а оператор знает общую
        почту компании; или в карточке лежит один адрес, а писать надо на
        снабжение. Раньше выход был один — править получателя у письма, теряя
        исходное. Здесь исходное остаётся, а рядом появляется копия на
        указанный адрес: тот же текст, та же кампания, статус «ждёт
        подтверждения». Ничего не отправляется.

        Строка получателя для нового адреса заводится сразу: очередь
        раскладывается ПО ГРУППЕ ПОЛУЧАТЕЛЯ, и письмо без строки не видно ни
        под одним фильтром — на этом 11.08 потерялись два письма.
        """
        адрес = (body.email or "").strip().lower()
        if "@" not in адрес or " " in адрес:
            raise HTTPException(status_code=400, detail="это не адрес почты")
        исходное = deps.store.confirm_get(int(rid))
        if not исходное:
            raise HTTPException(status_code=404, detail="письма нет")
        тема = исходное.get("edited_subject") or исходное.get("subject") or ""
        тело = исходное.get("edited_body") or исходное.get("body") or ""
        if not тело:
            raise HTTPException(status_code=409, detail="в письме пустое тело")
        новый_id = None
        with suppress(Exception):
            from sender.avtootvet import завести_получателя
            новый_id = завести_получателя(
                deps.store, адрес=адрес,
                образец_id=исходное.get("recipient_id"))
        try:
            новый, создано = deps.store.confirm_submit(
                email=адрес, subject=тема, body=тело,
                inn=исходное.get("inn"), campaign_id=исходное.get("campaign_id"),
                recipient_id=новый_id or исходное.get("recipient_id"),
                status="pending",
                reason=f"копия письма #{rid} на другой адрес (оператор "
                       f"{p.username})",
                panel={"kopiya_iz": int(rid), "operator": p.username},
                dedup_key=f"kopiya:{rid}:{адрес}")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500,
                                detail=f"копия не создалась: {str(e)[:120]}")
        _проверить_срочно(адрес)
        with suppress(Exception):
            deps.store.append_audit(
                action="confirm.kopiya", actor_user_id=p.user_id,
                entity_type="confirm_review", entity_id=str(rid),
                detail={"email": адрес, "novoe_pismo": новый})
        return {"ok": True, "id": новый, "sozdano": создано, "email": адрес,
                "recipient_id": новый_id}

    @app.post("/confirm/novoe")
    def confirm_novoe(body: NovoeBody, p: Principal = Depends(principal)):
        """Написать письмо с нуля: ящик, адрес, текст (владелец 11.08).

        «Чтобы работало просто как почта». Раньше письмо могло появиться в
        очереди только из генерации или как копия существующего — а оператор
        часто знает адрес и знает, что написать, и никакой генератор ему не
        нужен.

        Письмо ложится в ту же очередь подтверждений и той же кнопкой
        отправляется: это не обход ручного режима, а вход в него. Заслоны
        (стоп-лист, проба адреса, ловушки) работают ровно так же, потому что
        они висят на очереди, а не на способе появления письма.
        """
        адрес = (body.email or "").strip().lower()
        if "@" not in адрес or " " in адрес:
            raise HTTPException(status_code=400, detail="это не адрес почты")
        тема = (body.subject or "").strip()
        тело = (body.body or "").strip()
        if not тема or not тело:
            raise HTTPException(status_code=400,
                                detail="нужны и тема, и текст письма")
        ящик = (body.mailbox_id or "").strip()
        if ящик:
            свои = {m.mailbox_id for m in deps.config.mailboxes()}
            if ящик not in свои:
                raise HTTPException(status_code=400,
                                    detail=f"нет такого ящика: {ящик}")
        новый_id = None
        with suppress(Exception):
            from sender.avtootvet import завести_получателя
            новый_id = завести_получателя(deps.store, адрес=адрес)
        import time as _t
        try:
            rid, создано = deps.store.confirm_submit(
                email=адрес, subject=тема, body=тело, inn=body.inn,
                campaign_id=body.campaign_id, recipient_id=новый_id,
                status="pending",
                reason=f"написано вручную ({p.username})",
                panel={"ruchnoe_pismo": True, "operator": p.username},
                dedup_key=f"ruchnoe:{p.username}:{адрес}:{int(_t.time())}")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500,
                                detail=f"письмо не создалось: {str(e)[:120]}")
        if ящик:
            with suppress(Exception):
                deps.confirm.set_mailbox(int(rid), ящик, operator=p.username)
        _проверить_срочно(адрес)
        with suppress(Exception):
            deps.store.append_audit(
                action="confirm.novoe", actor_user_id=p.user_id,
                entity_type="confirm_review", entity_id=str(rid),
                detail={"email": адрес, "mailbox_id": ящик})
        return {"ok": True, "id": rid, "sozdano": создано, "email": адрес,
                "mailbox_id": ящик, "recipient_id": новый_id}

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

    @app.get("/confirm/groups")
    def confirm_groups(p: Principal = Depends(principal)):
        """Список групп для выпадашки фильтра: [(группа, сколько получателей)].

        Ручка объявлена ДО `/confirm/{rid}`: иначе FastAPI разберёт «groups» как
        {rid} и вернёт 422 вместо списка.
        """
        try:
            все = (deps.store.recipient_groups() or {}).get("все") or []
        except Exception:  # noqa: BLE001 - пустой список лучше пятисотки
            все = []
        return {"groups": [{"name": g, "recipients": n} for g, n in все]}

    @app.get("/confirm/golden")
    def confirm_golden(limit: int = 500, p: Principal = Depends(principal)):
        return {"pairs": deps.confirm.golden_pairs(limit=limit)}

    # ---- кнопка «в автоотправку» (владелец 06.08) ---- #
    # Фоновый цикл автоотправки живёт в панели (оркестратор на сервере не
    # запущен). Спит, пока auto_send_enabled=false; включает его нажатие
    # кнопки владельцем ниже (или явный POST /auto-send).
    from sender.auto_send import (AutoSendLoop, ENABLED_KEY, next_slot,
                                  recipient_tz_name, window_from)
    _auto_send = AutoSendLoop(store=deps.store, config=deps.config,
                              live_sender=getattr(deps, "live_sender", None))
    app.state.auto_send = _auto_send
    if _auto_send.sender is not None:
        _auto_send.start()

    # ---- проверка адресов без отправки писем (владелец 07.08) ---- #
    # Половину отбивок дали несуществующие ящики, и узнавали мы о них только
    # по факту отправки. Цикл спрашивает сервер получателя «примешь письмо для
    # такого-то?» и обрывает разговор: письмо не уходит. Мёртвый адрес снимает
    # письмо с очереди, все прочие ответы очередь не трогают.
    from sender.addr_probe import ENABLED_KEY as _PROBE_KEY, build_addr_probe
    _probe = build_addr_probe(deps.store, deps.config)
    app.state.addr_probe = _probe
    if _probe.enabled():
        _probe.start()

    # Связка с работником на отдельном сервере. Собственная проба панели
    # (выше) выключена сознательно: она ходила бы к чужим почтовым серверам с
    # боевого IP, а его беречь дороже. Этот же цикл выходит ТОЛЬКО на наш дроп,
    # поэтому включён по умолчанию — он и делает проверку очереди постоянной.
    from sender.probe_sync import ENABLED_KEY as _SYNC_KEY, build_probe_sync
    _sync = build_probe_sync(deps.store, _probe.probe_, deps.config)
    app.state.probe_sync = _sync
    if _sync.enabled():
        _sync.start()

    @app.get("/probe-sync")
    def probe_sync_get(p: Principal = Depends(principal)):
        return {"enabled": _sync.enabled(), "running": _sync.running(),
                "interval_sec": _sync.interval, "last": _sync.last}

    @app.post("/probe-sync")
    def probe_sync_set(body: AutoSendBody, p: Principal = Depends(owner)):
        deps.store.set_setting(_SYNC_KEY, bool(body.enabled))
        if body.enabled:
            _sync.start()
        with suppress(Exception):
            deps.store.append_audit(
                action="probe_sync.set", actor_user_id=p.user_id,
                entity_type="settings", entity_id=_SYNC_KEY,
                detail={"enabled": bool(body.enabled)})
        return probe_sync_get(p)

    @app.post("/probe-sync/run")
    def probe_sync_run(p: Principal = Depends(owner)):
        """Прогнать обмен прямо сейчас, не дожидаясь тика."""
        return {"ok": True, "result": _sync.tick()}

    @app.get("/addr-probe")
    def addr_probe_get(p: Principal = Depends(principal)):
        return {"enabled": _probe.enabled(), "running": _probe.running(),
                "helo": _probe.probe_.helo or None,
                "mail_from": _probe.probe_.mail_from or None,
                "stats": _probe.probe_.stats(), "last": _probe.last}

    @app.post("/addr-probe")
    def addr_probe_set(body: AutoSendBody, p: Principal = Depends(owner)):
        deps.store.set_setting(_PROBE_KEY, bool(body.enabled))
        if body.enabled:
            _probe.start()
        with suppress(Exception):
            deps.store.append_audit(
                action="addr_probe.set", actor_user_id=p.user_id,
                entity_type="settings", entity_id=_PROBE_KEY,
                detail={"enabled": bool(body.enabled)})
        return addr_probe_get(p)

    @app.post("/addr-probe/run")
    def addr_probe_run(p: Principal = Depends(owner)):
        """Прогнать проверку прямо сейчас, не дожидаясь тика."""
        return {"ok": True, "result": _probe.tick()}

    @app.post("/addr-probe/import")
    def addr_probe_import(p: Principal = Depends(owner)):
        """Забрать вердикты работника с отдельного сервера (через дроп).

        Ручной вызов того же приёма, что делает цикл probe_sync: он ходит сам
        раз в десять минут, но иногда результат нужен сию секунду. Логика одна
        на оба пути, поэтому расходиться им негде: мёртвый адрес снимает письмо
        и уходит в стоп-лист, прочие вердикты только пополняют кэш.
        """
        try:
            return {"ok": True, **_sync.забрать()}
        except RuntimeError as e:               # дроп не настроен
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502,
                                detail=f"результат не забрался: {str(e)[:120]}")

    @app.get("/auto-send")
    def auto_send_get(p: Principal = Depends(principal)):
        return {"enabled": _auto_send.enabled(),
                "running": _auto_send.running(),
                "live": _auto_send.sender is not None,
                "last": _auto_send.last_result}

    @app.post("/auto-send")
    def auto_send_set(body: AutoSendBody, p: Principal = Depends(owner)):
        deps.store.set_setting(ENABLED_KEY, bool(body.enabled))
        if body.enabled and _auto_send.sender is not None:
            _auto_send.start()
        with suppress(Exception):
            deps.store.append_audit(
                action="auto_send.set", actor_user_id=p.user_id,
                entity_type="settings", entity_id=ENABLED_KEY,
                detail={"enabled": bool(body.enabled)})
        return auto_send_get(p)

    @app.post("/confirm/bulk-to-auto")
    def confirm_bulk_to_auto(body: BulkToAutoBody,
                             p: Principal = Depends(owner)):
        """Первые N писем очереди → approved → цикл автоотправки.

        «Первые» — в том же порядке, что видит оператор в очереди (сначала
        балл скоринга, потом id), под тем же фильтром группы; ответы клиентам
        (kind='reply') кнопкой не шлются — их оператор пишет лично. Каждое
        письмо проходит те же заслоны, что одиночный approve (suppression /
        90 дней / гейт направлений / стоп-флаги); заблокированные ПРОПУСКАЮТСЯ
        с причиной, а не отправляются силой. Срок — ближайший слот окна в
        зоне получателя. Нажатие кнопки включает цикл автоотправки."""
        n = max(1, min(300, int(body.count or 0)))
        rows = deps.confirm.pending(limit=100_000)
        rows = [r for r in rows if (r.get("kind") or "outbound") != "reply"]
        гр = (body.gruppa or "").strip()
        if гр and гр.lower() not in ("все", "all"):
            карта = {}
            with suppress(Exception):
                карта = deps.store.recipient_groups() or {}

            def _в_группе(r) -> bool:
                rid_ = r.get("recipient_id")
                наб = (карта.get("по_id") or {}).get(int(rid_)) if rid_ else None
                if наб is None:
                    em = str(r.get("email") or "").strip().lower()
                    наб = (карта.get("по_почте") or {}).get(em)
                if наб is None:
                    d = "".join(c for c in str(r.get("inn") or "") if c.isdigit())
                    наб = (карта.get("по_инн") or {}).get(d)
                return bool(наб) and гр in наб
            rows = [r for r in rows if _в_группе(r)]

        def _балл(r):
            try:
                return float(((r.get("panel") or {}).get("scoring")
                              or {}).get("score") or -1)
            except (TypeError, ValueError):
                return -1.0
        rows.sort(key=lambda r: (-_балл(r), r.get("id") or 0))
        rows = rows[:n]

        from datetime import datetime as _dt, timezone as _tz
        from sender.dtos import MessageIn
        now = _dt.now(_tz.utc)
        win = window_from(deps.store, deps.config)
        moved, skipped = [], []

        def _skip(r, why: str) -> None:
            skipped.append({"id": r.get("id"), "email": r.get("email"),
                            "reason": why})

        for r in rows:
            rid = int(r["id"])
            st = _regen_box.get(rid)
            if st is not None and st.get("running"):
                _skip(r, "перегенерируется прямо сейчас")
                continue
            panel_r = r.get("panel") if isinstance(r.get("panel"), dict) else {}
            if ((panel_r or {}).get("actions") or {}).get("confirm_hold"):
                _skip(r, "стоп-флаг карточки: решает оператор вручную")
                continue
            blocked = None
            with suppress(Exception):
                blocked = deps.confirm._guard(inn=r.get("inn"),
                                              email=r.get("email") or "")
            if blocked:
                _skip(r, blocked)
                continue
            div_blocked = None
            with suppress(Exception):
                div_blocked = deps.confirm._division_blocked(r)
            if div_blocked:
                _skip(r, f"гейт направлений: {div_blocked}")
                continue
            # получатель: id из карточки или по адресу (нужен для tz и письма)
            rec = None
            if r.get("recipient_id"):
                rec = deps.store.get_recipient(int(r["recipient_id"]))
            if rec is None and r.get("email"):
                rec_row = deps.store.find_recipient_by_email(r["email"])
                if rec_row:
                    rec = deps.store.get_recipient(int(rec_row["id"]))
            if rec is None:
                _skip(r, "получателя нет в базе recipients")
                continue
            слот = next_slot(win, recipient_tz_name(win, rec), now)
            mid = r.get("message_id")
            try:
                if mid is None:
                    cid = r.get("campaign_id")
                    if not cid:
                        _skip(r, "карточка без кампании")
                        continue
                    steps = deps.store.get_steps(int(cid))
                    if not steps:
                        _skip(r, "у кампании нет шага-письма")
                        continue
                    mid, _created = deps.store.enqueue_message(MessageIn(
                        idempotency_key=f"confirm-auto-{rid}",
                        campaign_id=int(cid), recipient_id=int(rec.id),
                        sequence_step_id=int(steps[0].id),
                        scheduled_at=слот))
                    deps.store.confirm_set_message(rid, mid)
                else:
                    deps.store.reschedule_message(int(mid), слот)
                ok = deps.store.confirm_decide(
                    rid, status="approved", decided_by=p.username,
                    reason="bulk-to-auto")
                if not ok:
                    _skip(r, "карточка уже решена параллельно")
                    continue
            except Exception as e:  # noqa: BLE001 - одно письмо не рвёт партию
                logger.exception("bulk-to-auto rid=%s", rid)
                _skip(r, f"ошибка: {e}")
                continue
            moved.append({"id": rid, "email": r.get("email"),
                          "scheduled_at": слот.isoformat()})

        if moved:
            # нажатие кнопки = решение владельца включить автоотправку
            deps.store.set_setting(ENABLED_KEY, True)
            if _auto_send.sender is not None:
                _auto_send.start()
        with suppress(Exception):
            deps.store.append_audit(
                action="confirm.bulk_to_auto", actor_user_id=p.user_id,
                entity_type="confirm_review", entity_id=None,
                detail={"count": n, "gruppa": гр or None,
                        "moved": len(moved), "skipped": len(skipped)})
        return {"moved": len(moved), "moved_items": moved,
                "skipped": skipped,
                "auto_send": {"enabled": _auto_send.enabled(),
                              "running": _auto_send.running(),
                              "live": _auto_send.sender is not None}}

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
        _проверить_срочно(body.email)
        return {"ok": True, "review": row}

    @app.post("/confirm/{rid}/recipient/add")
    def confirm_add_recipient(rid: int, body: AddRecipientBody,
                              p: Principal = Depends(principal)):
        """Вписать НОВЫЙ контакт этой компании и сразу выбрать его получателем.

        Коды разведены намеренно: 400 — формат адреса/статус карточки/дедуп
        очереди (как у старой ручки), 409 — комплаенс-блок (стоп-лист, чужой
        ИНН), как у approve, 403 — фича выключена тумблером.
        """
        from sender.confirm import ConfirmBlockedError, ManualRecipientDisabled
        from sender.errors import ValidationError as _VErr
        try:
            res = deps.confirm.add_recipient_email(
                rid, body.email, note=body.note,
                operator=p.username, actor_user_id=p.user_id)
        except ManualRecipientDisabled as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ConfirmBlockedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except _VErr as e:
            raise HTTPException(status_code=400, detail=str(e))
        _проверить_срочно(body.email)
        return {"ok": True, **res}

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
                                            actor_user_id=getattr(p, "user_id", None),
                                            division=body.division)
            elif body.action == "edit":
                done = deps.confirm.edit(rid, subject=body.subject,
                                         body=body.body, operator=p.username,
                                         force=bool(body.force),
                                         actor_user_id=getattr(p, "user_id", None),
                                         division=body.division)
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
                "YoungDomainGateError": "домен-отправитель ещё молодой для корпоративного "
                                        "сервера получателя — письмо осталось в очереди "
                                        "(отправить сейчас можно вторым подтверждением)",
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

    @app.get("/analytics/opens")
    def recent_opens(limit: int = 30, p: Principal = Depends(principal)):
        """Кто и КАКОЕ письмо открыл (владелец 28.07). Общий счётчик на
        дашборде отвечает «сколько», этот список — «что именно»."""
        fn = getattr(deps.store, "recent_opens", None)
        if not callable(fn):      # старый движок — пустой список, не 500
            return {"opens": []}
        return {"opens": fn(limit=max(1, min(int(limit), 200)))}

    @app.delete("/analytics/opens/{eid}")
    def delete_open(eid: int, reason: str = "", p: Principal = Depends(owner)):
        """Убрать открытие из ленты (тестовые/мусорные — владелец 28.07).
        Только владелец; снимок события уходит в audit_log, так что удаление
        подотчётно и восстановимо."""
        fn = getattr(deps.store, "delete_open_event", None)
        if not callable(fn):
            raise HTTPException(status_code=404, detail="движок не умеет")
        снимок = fn(int(eid), actor_user_id=p.user_id, reason=reason)
        if снимок is None:
            raise HTTPException(status_code=404,
                                detail="событие не найдено или это не открытие")
        return {"ok": True, "deleted": снимок}

    @app.delete("/leads/{lead_id}")
    def delete_lead(lead_id: int, reason: str = "", p: Principal = Depends(owner)):
        """Убрать лид из ленты. Строка остаётся со статусом 'deleted' —
        ошибочное удаление возвращается через /leads/{id}/restore."""
        fn = getattr(deps.store, "soft_delete_lead", None)
        if not callable(fn):
            raise HTTPException(status_code=404, detail="движок не умеет")
        снимок = fn(int(lead_id), actor_user_id=p.user_id, reason=reason)
        if снимок is None:
            raise HTTPException(status_code=404, detail="лид не найден")
        try:
            deps.store.append_audit(action="lead.delete", actor_user_id=p.user_id,
                                    entity_type="lead", entity_id=lead_id,
                                    detail={"reason": reason, "snapshot": снимок})
        except Exception:  # noqa: BLE001 - журнал не роняет операцию
            pass
        return {"ok": True, "deleted": снимок}

    @app.post("/leads/{lead_id}/restore")
    def restore_lead(lead_id: int, p: Principal = Depends(owner)):
        fn = getattr(deps.store, "restore_lead", None)
        if not callable(fn):
            raise HTTPException(status_code=404, detail="движок не умеет")
        if not fn(int(lead_id), actor_user_id=p.user_id):
            raise HTTPException(status_code=404, detail="лид не найден или не удалён")
        return {"ok": True}

    @app.get("/messages/{mid}")
    def message_full(mid: int, p: Principal = Depends(principal)):
        """Отправленное письмо целиком — «провалиться» в него из списка
        открытий (владелец 28.07)."""
        fn = getattr(deps.store, "message_full", None)
        if not callable(fn):
            raise HTTPException(status_code=404, detail="движок не умеет")
        row = fn(int(mid))
        if row is None:
            raise HTTPException(status_code=404, detail="письмо не найдено")
        return row

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
                cur = {"days": list(w.days), "start": w.start, "end": w.end,
                       "tz": w.tz, "by_recipient_tz": False}
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
               "tz": body.tz or "Europe/Moscow",
               "by_recipient_tz": bool(body.by_recipient_tz)}
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
        # «Сколько ожидает отправки» (владелец 20.08): ёмкость показывала
        # только израсходованное, и было не видно, есть ли чем её занимать.
        ждёт = {}
        with suppress(Exception):    # добавка к экрану: сбой не рушит ёмкость
            ждёт = deps.store.skolko_zhdyot_otpravki()
        return {"pools": out, "ozhidaet": ждёт}

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
                   campaign_id: Optional[int] = None,
                   division: Optional[str] = None) -> str:
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
        # Бренд — по направлению ВЫБРАННОГО ящика, той же функцией, что и
        # отправка: иначе письмо Meyer показывалось бы с подписью
        # «Компрессор Центр» (владелец 28.07).
        from sender.sender import brand_for_division
        return tmpl.format(name=name, inn=inn, role=role,
                           brand=brand_for_division(cfg, division))
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

    # ПУБЛИЧНАЯ СТРАНИЦА ЛИДА — до статики. Внутри API она тоже есть, но там её
    # адрес /api/lid/… : SPA-catch-all перехватывает чистый /lid/… и отдаёт
    # пустую оболочку панели (поймано пробой 20.08 — страница пришла на 410
    # знаков вместо переписки). Продажникам нужен короткий адрес.
    @site.get("/lid/{token}", response_class=HTMLResponse)
    def site_lid(token: str):
        return stranica_lida(deps, token)

    # ВАЖНО: catch-all статикой монтируем ПОСЛЕДНИМ — иначе перехватит /api и /healthz.
    site.mount("/", _SpaStaticFiles(directory=static_dir, html=True), name="spa")
    return site


# ---- сериализаторы (dataclass → json-safe dict) ---- #

def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _v_tekst(текст):
    """Тело письма — в читаемый текст. Разбор один на панель."""
    try:
        from sender.pismo_v_tekst import v_tekst
        return v_tekst(текст)
    except Exception:                                           # noqa: BLE001
        return текст


def _svoy_tekst(текст):
    """Только то, что человек написал САМ, без цитаты нашего письма.

    Владелец 19.08: «коряво первый экран выглядит очень». В поле «Потребность»
    уезжал ВЕСЬ ответ вместе с процитированным нашим письмом на два экрана —
    менеджер листал простыню, чтобы найти одну строчку смысла. Режем той же
    меркой, что и классификатор ответов: она уже умеет находить границу цитаты.
    """
    try:
        from sender.reply_classify import bez_citaty
        свой = bez_citaty(текст or "")
        return свой if свой.strip() else (текст or "")
    except Exception:                                           # noqa: BLE001
        return текст or ""


# Служебная пометка автоответа, которую imap_watcher когда-то клеил в начало
# текста: «[автоответ] новый адрес: X — копия письма поставлена в очередь».
# У новых лидов её больше нет, а у старых она уже записана в базу, поэтому
# срезаем на чтении — переписывать сохранённые ответы клиентов не будем.
_ПОМЕТКА_КОПИИ = re.compile(
    r"^\s*(\[автоответ\]\s*)?новый адрес:[^—\n]*"
    r"(—\s*копия письма[^\n]*?(в очередь|в очереди))?\s*", re.I)
_ГОЛЫЙ_АВТООТВЕТ = re.compile(r"^\s*\[автоответ\]\s*", re.I)


def _bez_pometki_kopii(text):
    """Текст ответа без служебной пометки про новый адрес и копию."""
    t = str(text or "")
    t = _ПОМЕТКА_КОПИИ.sub("", t)
    t = _ГОЛЫЙ_АВТООТВЕТ.sub("", t)
    return t.strip() or None



# Контакты компании для карточки лида и для публичной ссылки.
# Вынесена на уровень модуля: её зовёт и API, и внешний обработчик
# /lid/… , который живёт вне make_app. От deps не зависит — читает
# enrich.db только на чтение.
def _kontakty_kompanii(inn: object) -> dict:
    цифры = "".join(c for c in str(inn or "") if c.isdigit())
    путь = os.environ.get("ENRICH_DB", r"C:\sender\enrich.db")
    пусто = {"lyudi": [], "telefony": [], "pochty": [], "istochnik": None}
    if not цифры or not os.path.exists(путь):
        return пусто
    import sqlite3 as _sq
    cx = _sq.connect(f"file:{путь}?mode=ro", uri=True)
    cx.row_factory = _sq.Row
    try:
        люди = [dict(r) for r in cx.execute(
            "SELECT person, COALESCE(post,'') post, COALESCE(role,'') role, "
            "COALESCE(phone,'') phone, COALESCE(email,'') email, "
            "COALESCE(source,'') source, COALESCE(source_url,'') source_url "
            "FROM people WHERE inn=? AND COALESCE(person,'')<>'' "
            "ORDER BY (post<>'') DESC, person", (цифры,))]
        телефоны = [dict(r) for r in cx.execute(
            "SELECT phone, COALESCE(person,'') person, COALESCE(role,'') role, "
            "COALESCE(source,'') source, COALESCE(source_url,'') source_url "
            "FROM phone_contacts WHERE inn=? AND COALESCE(phone,'')<>'' "
            "ORDER BY (role<>'') DESC", (цифры,))]
        почты = [dict(r) for r in cx.execute(
            "SELECT email, COALESCE(role,'') role, COALESCE(person,'') person, "
            "COALESCE(source,'') source, COALESCE(source_url,'') source_url, "
            "COALESCE(pometka,'') pometka FROM emails WHERE inn=? "
            "ORDER BY (role<>'') DESC, email", (цифры,))]
        комп = cx.execute(
            "SELECT COALESCE(name,'') name, COALESCE(site,'') site, "
            "COALESCE(cand_site,'') cand_site, COALESCE(region,'') region, "
            "COALESCE(okved,'') okved, COALESCE(address,'') address, "
            "COALESCE(director,'') director, COALESCE(revenue_rub,0) revenue_rub, "
            "COALESCE(activity,'') activity, COALESCE(phones,'') phones, "
            "COALESCE(verified_url,'') verified_url, "
            "COALESCE(site_meta_url,'') site_meta_url FROM companies WHERE inn=?",
            (цифры,)).fetchone()
    except Exception:  # noqa: BLE001 - карточка не должна ронять лид
        return пусто
    finally:
        cx.close()
    к = dict(комп) if комп else {}
    # ДВА ИСТОЧНИКА, А НЕ ОДИН. Замер 19.08 по просьбе владельца («здесь
    # написано телефонов не собрано, но они есть на странице»): телефоны
    # обход кладёт СПИСКОМ в companies.phones, и отдельная таблица
    # phone_contacts заполняется далеко не всегда — 8467 компаний имеют
    # номера только в списке. Та же история с людьми: имя и должность
    # часто известны из подписи адреса (emails.person + role), а строки в
    # people нет — таких 1832. Карточка обязана показывать всё, что мы
    # знаем, иначе менеджер видит «не собрано» там, где собрано.
    стр_номера = {str(x.get("phone") or "").strip() for x in телефоны}
    ссылка_компании = (к.get("verified_url") or к.get("site_meta_url") or "")
    try:
        список = json.loads(к.get("phones") or "[]")
    except Exception:  # noqa: BLE001 - в поле бывал не-json
        список = [x for x in re.split(r"[;,|]", к.get("phones") or "") if x.strip()]
    for н in (список or []):
        н = str(н).strip()
        if н and н not in стр_номера:
            стр_номера.add(н)
            телефоны.append({"phone": н, "person": "", "role": "",
                             "source": "карточка обхода",
                             "source_url": ссылка_компании})
    имена = {(str(x.get("person") or "").strip().lower()) for x in люди}
    for e in почты:
        имя = str(e.get("person") or "").strip()
        if not имя or имя.lower() in имена:
            continue
        имена.add(имя.lower())
        люди.append({"person": имя, "post": "", "role": e.get("role") or "",
                     "phone": "", "email": e.get("email") or "",
                     "source": "подпись адреса на сайте",
                     "source_url": e.get("source_url") or ""})
    return {"lyudi": люди, "telefony": телефоны, "pochty": почты,
            "kompaniya": к}



def stranica_lida(deps, token: str):
    """Публичная страница лида по ссылке. Без входа в панель — в этом её смысл.

    Живёт на уровне модуля, потому что вешается ДВАЖДЫ: внутри API (там она
    доступна как /api/lid/…) и на внешнем приложении ДО монтирования SPA —
    иначе чистый /lid/… перехватывает статика и отдаёт пустую оболочку панели.
    Продажникам нужен короткий адрес, а не /api/… .
    """
    from fastapi.responses import HTMLResponse as _H
    # модули лежат ВНУТРИ пакета sender, поэтому импорт пакетный:
    # верхнеуровневый «import lid_ssylka» их не находит — панель
    # падала на 500 сразу после рестарта (ModuleNotFoundError).
    from sender import lid_ssylka as LS
    from sender import lid_stranica as LST
    lead_id = LS.lead_po_tokenu(token)
    if lead_id is None:
        # Одинаковый ответ на «нет такой ссылки» и «ссылку отозвали»: иначе по
        # разнице ответов можно перебирать токены и узнавать, какие существовали.
        return _H("<!doctype html><meta charset=utf-8>"
                  "<p style='font:16px system-ui;margin:12vh auto;max-width:26em;"
                  "text-align:center'>Ссылка недействительна.</p>",
                  status_code=404)
    lead = deps.leaddesk.get(lead_id)
    if lead is None:
        return _H("<!doctype html><meta charset=utf-8><p>Лид удалён.</p>",
                  status_code=404)
    л = _lead_json(lead)
    нить = []
    with suppress(Exception):
        инн = getattr(lead, "inn", None)
        нить = (deps.store.dialog_thread_company(инн) if инн
                else deps.store.dialog_thread(getattr(lead, "recipient_id", 0)))
    контакты = {}
    with suppress(Exception):
        контакты = _kontakty_kompanii(getattr(lead, "inn", None))
    стр = LST.sobrat(л, нить, контакты, (LS.bez_podpisi, LS.bez_adresov))
    return _H(стр, headers={"X-Robots-Tag": "noindex, nofollow",
                            "Cache-Control": "private, no-store"})


def _lead_json(l):
    return {"id": l.id, "email": l.email, "company_name": l.company_name,
            "inn": l.inn, "status": l.status, "reply_kind": l.reply_kind,
            "phone": l.phone, "need": _v_tekst(l.need),
            # что человек написал сам — для первого экрана карточки
            "need_svoy": _v_tekst(_svoy_tekst(l.need)),
            "assigned_to": l.assigned_to,
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
