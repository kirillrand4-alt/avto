"""Инфо-панель оператора confirm-send (ENGINEER-TASKS-CONFIRM-SEND, Задача 2).

build_panel() собирает ЕДИНЫЙ JSON панели из готовых интеграций (ничего не
переписываем): server/lead_scoring.py (баллы/ЛПР/окно/buying_power),
server/enrich_db.py (companies/emails/signals + ОКВЭД-маппинг),
email-assistant/kb_retrieve.py (кейсы/цены/гео/триггер), kb/snyatye-verdict.json
(стоп-серии), sender store (suppression + send_log история).

Порядок блоков (линза UX): stop_flags -> scoring -> signal -> contact ->
company -> letter -> kb -> compliance -> history -> actions. CLI и веб-панель
рендерят ОДИН И ТОТ ЖЕ JSON (Задача 4 — паритет), тут представлений нет.

Честность данных (ТЗ §«чего нет»): catch-all не проверялся — поле
зарезервировано с пометкой; дельту выручки не считаем; отсутствие enrich.db
не роняет панель — блоки помечаются «нет данных».
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_SENDER = Path(__file__).resolve().parent
_ROOT = _SENDER.parent            # seo-texts/
for _p in (str(_ROOT), str(_ROOT / "server"), str(_ROOT / "email-assistant")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sender import snyatye  # noqa: E402

HOTKEYS = {"Enter": "approve", "E": "edit", "S": "skip", "X": "stoplist"}

# Роли-«роутеры»: письмо вероятно не дойдёт до ЛПР напрямую.
ROUTER_ROLES = ("приёмная", "общий")

_FIO_RE = re.compile(
    r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ович|евич|ьич|овна|евна|ична|инична)\b"
    r"|\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.")
_BANNED_RE = re.compile(
    r"лучш\w*|№\s?1\b|номер один|единственн\w*|дешевле,?\s+чем|гарантиру\w*",
    re.IGNORECASE)
_ATTR_ENTITY_RE = re.compile(r"ООО\s+[«\"]?Руспром[»\"]?")
_INN_RE = re.compile(r"ИНН\s*\d{10,12}")
_GEO_CLAIM_RE = re.compile(
    r"(\d+)\s+(?:реализованных\s+)?(?:проект\w*|внедрени\w*|внедрен\w*)",
    re.IGNORECASE)
_PRICE_RE = re.compile(
    r"\d[\d\s]{2,}(?:[.,]\d+)?\s*(?:млн\s*)?(?:руб|₽|р\.)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Чтение enrich.db (read-only; нет файла — честные пустышки)
# --------------------------------------------------------------------------- #

def load_enrich_lead(inn: str, *, db_path: Optional[str] = None,
                     email: Optional[str] = None) -> dict:
    """Компания + emails + signals по ИНН из enrich.db.

    Возврат всегда dict; ключ available=False если БД/компании нет.
    """
    import os
    path = db_path or os.environ.get("ENRICH_DB", "")
    if not path or not Path(path).exists():
        return {"available": False, "company": {}, "emails": [], "signals": []}
    cx = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    try:
        comp = cx.execute(
            "SELECT * FROM companies WHERE inn=?", (str(inn),)).fetchone()
        emails = [dict(r) for r in cx.execute(
            "SELECT email,role,person,mx_ok,source,updated_at FROM emails"
            " WHERE inn=?", (str(inn),)).fetchall()]
        # при равном накале первым идёт самый содержательный сигнал (#61):
        # короткая метка «модернизация производства» не должна заслонять
        # развёрнутую формулировку того же события из другого источника
        signals = [dict(r) for r in cx.execute(
            "SELECT source,event_type,what,sum,source_url,hotness,ts,updated_at"
            " FROM signals WHERE inn=?"
            " ORDER BY hotness DESC, LENGTH(COALESCE(what,'')) DESC, ts DESC",
            (str(inn),)).fetchall()]
    finally:
        cx.close()
    return {"available": True, "company": dict(comp) if comp else {},
            "emails": emails, "signals": signals}


# --------------------------------------------------------------------------- #
# Сборка панели
# --------------------------------------------------------------------------- #

def build_panel(
    *,
    inn: Optional[str],
    email: str,
    letter_subject: str,
    letter_body: str,
    company: Optional[dict] = None,       # строка companies enrich.db
    emails: Optional[list[dict]] = None,  # строки emails enrich.db
    signals: Optional[list[dict]] = None, # строки signals enrich.db
    base: Optional[dict] = None,          # {revenue, director} из базы обзвона
    store=None,                           # sender Store: suppression + send_log
    kb_ctx: Optional[dict] = None,        # kb_retrieve.select_for_lead(...)
    batch_domains: Optional[dict] = None, # {domain: N} текущей пачки (SHOULD)
    card: Optional[dict] = None,          # company_card.build_company_card(inn)
    signature: str = "",                  # подпись, дописываемая НА ОТПРАВКЕ:
                                          # в ней живёт юр-атрибуция ФЗ-38, и без
                                          # неё комплаенс краснел у всех писем
) -> dict:
    company = company or {}
    emails = emails or []
    signals = signals or []
    base = base or {}
    if card:
        # §3 BASE-MERGE: карточка — первоисточник; enrich-части берём из неё,
        # если вызывающий не передал их отдельно (обратная совместимость).
        enr = card.get("enrich") or {}
        company = company or (enr.get("company") or {})
        emails = emails or (enr.get("emails") or [])
        signals = signals or (enr.get("signals") or [])
        ob = card.get("obzvon") or {}
        if not base and ob:
            base = {"revenue": ob.get("revenue_rub") or ob.get("revenue"),
                    "director": ob.get("director")}

    contact = _contact_block(email, emails, company, base)
    scoring = _scoring_block(company, emails, signals, base)
    signal = _signal_block(signals)
    comp_block = _company_block(inn, company, base)
    letter = _letter_block(letter_subject, letter_body, contact, comp_block,
                           signal, kb_ctx, signature)
    kb_block = _kb_block(kb_ctx, letter_body, signals)
    compliance = _compliance_block(letter_subject, letter_body, signature)
    history = _history_block(store, inn, email)
    stop_flags = _stop_flags(company, contact, letter_body, store, inn, email,
                             history)
    company_name = ((card.get("obzvon") or {}).get("name_short")
                    if card else "") or company.get("name") or ""
    # Контакты компании плоским списком — для селекта «сменить email отправки»
    # (Фича 1). Источник: карточка (card.contacts) или enrich-emails.
    if card:
        contact_emails = (card.get("contacts") or {}).get("emails") or []
    else:
        contact_emails = [{"email": e.get("email"), "role": e.get("role", ""),
                           "person": e.get("person", ""),
                           "mx_ok": e.get("mx_ok"),
                           "source": e.get("source", "")}
                          for e in emails if e.get("email")]
    # Приоритет ролей (#69): закупки сверху, общий ящик снизу — оператор видит
    # лучший адрес первым, а не в порядке появления в базе. Именной контакт
    # выигрывает у безымянного внутри одной роли.
    contact_emails = sorted(
        contact_emails,
        key=lambda e: (_ROLE_RANK.get((e.get("role") or "").strip().lower(), 9),
                       0 if (e.get("person") or "").strip() else 1))
    panel = {
        "stop_flags": stop_flags,
        "scoring": scoring,
        "signal": signal,
        "emails": contact_emails,
        "news_events": _news_events_block(signals, company_name),
        "company_full": _company_full_block(card),
        "contact": contact,
        "company": comp_block,
        "letter": letter,
        "kb": kb_block,
        "compliance": compliance,
        "history": history,
        "reserved": {"catch_all": "не проверялось (беклог Фазы 0 валидации)"},
        "actions": {"hotkeys": dict(HOTKEYS),
                    "confirm_hold": bool(stop_flags)},
        "should": _should_block(company, emails, contact, letter_body,
                                scoring, batch_domains),
    }
    return panel


# -- блок 1: красная полоса стоп-флагов -------------------------------------- #

def _stop_flags(company, contact, body, store, inn, email, history) -> list[dict]:
    flags: list[dict] = []
    if company.get("is_competitor"):
        flags.append({"code": "competitor", "label": "КОНКУРЕНТ",
                      "severity": "red"})
    if (company.get("verified") or "") == "mismatch":
        flags.append({"code": "site_mismatch",
                      "label": "сайт НЕ этой компании (verified=mismatch)",
                      "severity": "red"})
    if contact.get("mx_ok") is False:
        flags.append({"code": "mx_dead", "label": "адрес мёртв (MX не отвечает)",
                      "severity": "red"})
    for f in snyatye.scan_text(body, include_soft=False):
        flags.append({"code": "discontinued_series",
                      "label": f"снятая серия в письме: {f['brand']} {f['series']}",
                      "severity": "red"})
    supp = _suppression_entry(store, inn, email)
    if supp is not None:
        flags.append({"code": "suppressed",
                      "label": f"адрес/ИНН в стоп-листе ({supp})",
                      "severity": "red"})
    if history.get("recent_90d"):
        last = history.get("last") or {}
        flags.append({"code": "recent_contact",
                      "label": f"контакт <90 дн ({str(last.get('ts', ''))[:10]})",
                      "severity": "red"})
    return flags


def _suppression_entry(store, inn, email) -> Optional[str]:
    if store is None:
        return None
    try:
        domain = email.rsplit("@", 1)[-1] if "@" in (email or "") else ""
        digits = "".join(ch for ch in str(inn or "") if ch.isdigit()) or None
        entry = store.suppression_lookup(
            email=(email or "").strip().lower(), domain=domain.lower(),
            inn=digits)
        return getattr(entry, "reason", None) if entry is not None else None
    except Exception:  # noqa: BLE001 - fail-safe: не смогли проверить = скажем
        return "suppression_check_failed"


# -- блок 2: скоринг-шапка ---------------------------------------------------- #

def _scoring_block(company, emails, signals, base) -> dict:
    try:
        import lead_scoring as LS
        import enrich_db as EDB
    except Exception:  # noqa: BLE001 - урезанное окружение
        return {"available": False}
    days = None
    for s in signals:
        d = LS._days_ago(s.get("ts"), s.get("updated_at"))
        if d is not None and (days is None or d < days):
            days = d
    sp = LS._signal_pts(days) if signals else 0
    rev = float(base.get("revenue") or 0)
    rp = LS._revenue_pts(rev)
    vp = LS._VERIF_PTS.get(company.get("verified") or "", 0)
    role_p = max((LS._ROLE_PTS.get(e.get("role") or "", 0) for e in emails),
                 default=0)
    score = sp + rp + vp + role_p
    _div, budget = EDB.division_for_okveds(company.get("okved") or "")
    color = "grey" if score < 40 else ("yellow" if score < 65 else "green")
    window = LS._capex_window(days)
    return {
        "available": True,
        "score": score, "color": color,
        "parts": {"signal": sp, "signal_max": 40,
                  "revenue": rp, "revenue_max": 20,
                  "verified": vp, "verified_max": 15,
                  "role": role_p, "role_max": 15},
        "buying_power": LS._buying_power(rev, budget),
        "capex_window": window,
        "capex_badge": ({"0-30": "🔥 0-30 дн", "31-90": "⏳ 31-90 дн"}
                        .get(window, "нет триггера")),
        "budget_confirmed": LS._budget_confirmed(
            [f"{s.get('event_type', '')} {s.get('what', '')}" for s in signals]),
    }


def _norm_date(raw: str) -> str:
    """Дата сигнала → YYYY-MM-DD. В снапшоте ts бывает и ISO, и RFC822 (RSS)."""
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw or "")
    if m:
        return m.group(0)
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 - непарсибельная дата → как есть, укорочено
        return (raw or "")[:16]


# -- блок 3: карточка новостного повода --------------------------------------- #

def _signal_block(signals) -> dict:
    if not signals:
        return {"present": False, "label": "повода нет — холодный заход"}

    def card(s):
        return {"event_type": s.get("event_type") or "",
                "what": (s.get("what") or "")[:80],
                "sum": s.get("sum") or "",
                "date": _norm_date(s.get("ts") or s.get("updated_at") or ""),
                "hotness": int(s.get("hotness") or 0),
                "stars": "★" * max(0, min(5, int(s.get("hotness") or 0))),
                "source_url": s.get("source_url") or ""}

    ordered = sorted(signals, key=lambda s: (-int(s.get("hotness") or 0),
                                             str(s.get("ts") or "")), reverse=False)
    return {"present": True, "top": card(ordered[0]),
            "others": [card(s) for s in ordered[1:5]]}


# -- блок 3b: ВСЕ новостные события со ссылками (§3 BASE-MERGE) --------------- #

# Только организационно-правовые формы: содержательные слова имени («Завод»,
# «Группа») из матчинга не выкидываем — лучше лишний зелёный, чем пропуск.
_ORG_STOPWORDS = frozenset({"ооо", "ао", "пао", "зао", "оао", "ип", "нко"})


def _news_events_block(signals, company_name: str) -> dict:
    """Все новостные события компании, каждое с кликабельным source_url.

    signal_match: «имя в тексте» / «НЕТ имени — проверь» (жёлтый флаг) —
    защита от чужой новости, приклеенной к компании по ошибке матчинга.
    """
    words = [w for w in re.findall(r"[А-Яа-яЁёA-Za-z0-9\-]{3,}",
                                   str(company_name or ""))
             if w.lower() not in _ORG_STOPWORDS]

    def _match(s) -> bool:
        text = " ".join(str(s.get(k) or "") for k in
                        ("what", "news_object", "sum")).lower()
        return any(w.lower() in text for w in words) if words else False

    def card(s):
        ok = _match(s)
        return {
            "event_type": s.get("event_type") or "",
            "what": s.get("what") or "",
            "news_object": s.get("news_object") or "",
            "sum": s.get("sum") or "",
            "hotness": int(s.get("hotness") or 0),
            "date": _norm_date(s.get("ts") or s.get("updated_at") or ""),
            "source_name": s.get("source") or "",
            "source_url": s.get("source_url") or "",
            "match_ok": ok,
            "signal_match": "имя в тексте" if ok else "НЕТ имени — проверь",
        }

    ordered = sorted(signals or [],
                     key=lambda s: (-int(s.get("hotness") or 0),
                                    str(s.get("ts") or "")))
    return {"count": len(ordered), "events": [card(s) for s in ordered]}


# --- расшифровка ОКВЭД -------------------------------------------------------- #

# Приоритет ролей для холодного письма (канон владельца, тот же порядок, что
# в _best_by_role серверного обогащения): ниже индекс = лучше адрес.
_ROLE_RANK = {'снабжение/закупки': 0, 'гл.инженер': 1, 'директор': 2,
              'продажи': 3, 'приёмная': 4, 'бухгалтерия': 5, 'общий': 6}

_OKVED_NAMES: Optional[dict] = None


def _okved_names() -> dict:
    """Код ОКВЭД -> название. Справочник собран из ИСХОДНОЙ выгрузки базы
    обзвона (колонка «ВсеОКВЭД» идёт с названиями), потому что индекс сжимает
    её до одних кодов — оператор видел «25.62|25.11|30.20.2» без единого слова.
    2814 кода, файл рядом с пакетом; нет файла — просто не расшифровываем."""
    global _OKVED_NAMES
    if _OKVED_NAMES is None:
        _OKVED_NAMES = {}
        import os
        for p in (os.environ.get('OKVED_NAMES', ''),
                  os.path.join(os.environ.get('SENDER_DIR', r'C:\sender'),
                               'okved-names.json'),
                  str(_ROOT / 'sender-data' / 'okved-names.json')):
            if p and Path(p).exists():
                try:
                    import json as _json
                    with open(p, encoding='utf-8') as f:
                        _OKVED_NAMES = _json.load(f)
                    break
                except Exception:  # noqa: BLE001
                    continue
    return _OKVED_NAMES


def decode_okveds(raw: object) -> list[dict]:
    """«25.62|25.11|30.20.2» -> [{code, name}]. Точного кода нет в справочнике —
    пробуем родительский («30.20.2» -> «30.20»), иначе отдаём код без названия:
    честнее показать голый код, чем выдумать расшифровку."""
    names = _okved_names()
    out: list[dict] = []
    for c in re.split(r'[|,;\s]+', str(raw or '')):
        c = c.strip()
        if not re.fullmatch(r'\d{2}(\.\d+){0,2}', c):
            continue
        name = names.get(c) or ''
        if not name and '.' in c:
            name = names.get(c.rsplit('.', 1)[0]) or ''
        out.append({'code': c, 'name': name})
    return out


# -- блок 5b: полная карточка компании (§3 BASE-MERGE, company_card) ---------- #

def _company_full_block(card) -> dict:
    """Раскрывающийся блок «вся информация»: объединённая карточка §2."""
    if not card:
        return {"available": False}
    ob = card.get("obzvon") or {}
    ecomp = (card.get("enrich") or {}).get("company") or {}
    reg = {k: ob.get(k, "") for k in
           ("name_short", "name_full", "status", "reg_date", "address",
            "region", "opf", "ust_capital", "director", "dir_inn", "founders",
            "okved_main", "okved_all_codes", "ogrn", "kpp")}
    return {
        "available": True,
        # коды с названиями: без этого оператор видел «25.62|25.11|30.20.2»
        "okved_decoded": decode_okveds(reg.get("okved_all_codes")),
        # компании вне базы обзвона идут без списка кодов — тогда название
        # берём хотя бы для основного
        "okved_main_name": next(
            (x["name"] for x in decode_okveds(
                reg.get("okved_main") or ecomp.get("okved")) if x.get("name")), ""),
        "division": card.get("division"),
        "division_source": card.get("division_source"),
        "division_guess": card.get("division_guess"),
        "obzvon_available": bool(card.get("obzvon_available")),
        "in_obzvon": bool(ob),
        "reg": reg,
        "fin": card.get("fin") or {},
        "priority": card.get("priority") or {},
        "product": card.get("product") or {},   # категории + балл + комментарий
        "contacts": card.get("contacts") or {"emails": [], "phones": []},
        "site_view": card.get("site_view") or {},
        "activity": ecomp.get("activity") or "",
        "opo": {"flag": ecomp.get("opo") or "",
                "object": ecomp.get("opo_object") or "",
                "source": ecomp.get("opo_source") or ""},
        "zakupki": {"contact": ecomp.get("zakupki_contact") or ""},
    }


# -- блок 4: контакт ----------------------------------------------------------- #

def _contact_block(email, emails, company, base) -> dict:
    email_l = (email or "").strip().lower()
    row = next((e for e in emails
                if (e.get("email") or "").lower() == email_l), {})
    role = row.get("role") or ""
    person = row.get("person") or ""
    mx = row.get("mx_ok")
    mx_ok = None if mx is None else bool(mx)

    lpr = "impersonal"
    director = (base.get("director") or "").strip()
    if director and person:
        try:
            import lead_scoring as LS
            lpr = "match" if LS._lpr_match(director, [(email_l, person)]) \
                else "mismatch"
        except Exception:  # noqa: BLE001
            lpr = "no_data"
    elif not director:
        lpr = "no_data"

    site = (company.get("site") or "").lower()
    site_domain = re.sub(r"^https?://", "", site).split("/")[0].removeprefix("www.")
    email_domain = email_l.rsplit("@", 1)[-1] if "@" in email_l else ""
    domain_mismatch = bool(site_domain and email_domain
                           and site_domain != email_domain)
    verified = company.get("verified") or ""
    return {
        "email": email_l,
        "role": role or "не определена",
        "router": role in ROUTER_ROLES,
        "person": person,
        "lpr": lpr,                      # match | mismatch | impersonal | no_data
        "mx_ok": mx_ok,                  # None = не проверялся
        "verified": verified,
        "verified_icons": _verified_icons(verified),
        "email_domain": email_domain,
        "site_domain": site_domain,
        "domain_mismatch": domain_mismatch,
        "updated_at": row.get("updated_at") or "",
        "source": row.get("source") or "",
    }


def _verified_icons(verified: str) -> str:
    marks = {"inn": "ИНН✅", "ogrn": "ОГРН✅", "phone": "тел✅",
             "provider": "пров✅", "mismatch": "❌сайт не тот"}
    return marks.get(verified, "—") if verified else "—"


# -- блок 5: компания-снипет ---------------------------------------------------- #

def _company_block(inn, company, base) -> dict:
    okved = company.get("okved") or ""
    division = company.get("division") or ""
    budget = 0
    try:
        import enrich_db as EDB
        div_calc, budget = EDB.division_for_okveds(okved)
        division = division or div_calc
    except Exception:  # noqa: BLE001
        pass
    rev = float(base.get("revenue") or 0)
    return {
        "inn": "".join(ch for ch in str(inn or "") if ch.isdigit()),
        "name": company.get("name") or "",
        "region": company.get("region") or "",
        "revenue": rev or None,
        "revenue_h": _human_money(rev),
        "okved": okved,
        "okved_budget": budget,
        "director": (base.get("director") or ""),
        "activity": company.get("activity") or "",
        "division": division,                        # kc | meyer | kc+meyer
        "division_badge": {"kc": "КЦ", "meyer": "Meyer"}.get(
            division, division or "—"),
        "why_equipment": _why_equipment(division, company),
        # на чём основан вывод о направлении: ОКВЭД (деятельность показывается
        # отдельной строкой, дублировать её здесь нельзя)
        "why_basis": (f"ОКВЭД {okved}" if okved else ""),
        "site": company.get("site") or "",
    }


def _why_equipment(division: str, company: dict) -> str:
    """Фраза-обоснование выбора направления (ОКВЭД-маппинг + activity)."""
    act = (company.get("activity") or "").strip()
    okved = (company.get("okved") or "").strip()
    base_map = {
        "kc": "сжатый воздух/пневматика в техпроцессе",
        "meyer": "сортировка и инспекция продукции (фотосепараторы/рентген)",
        "kc+meyer": "и пневматика, и сортировка продукции",
    }
    why = base_map.get(division, "")
    if not why:
        return "направление по ОКВЭД не определено — проверить вручную"
    # ТОЛЬКО причина, без пересказа деятельности: карточка показывает «чем
    # занимается» отдельной строкой, и раньше один и тот же длинный текст
    # печатался в ней дважды подряд — читать невозможно.
    return why


def _human_money(v: float) -> str:
    if not v:
        return "нет данных"
    if v >= 1e9:
        return f"{v / 1e9:.1f} млрд ₽"
    if v >= 1e6:
        return f"{v / 1e6:.0f} млн ₽"
    return f"{v:,.0f} ₽".replace(",", " ")


# -- блок 6: письмо + подсветка ------------------------------------------------- #

def _letter_block(subject, body, contact, comp, signal, kb_ctx,
                  signature: str = "") -> dict:
    highlights: list[dict] = []

    low_body = (body or "").lower()

    def add(text, kind):
        t = (text or "").strip()
        if not t or len(t) < 3:
            return
        if t.lower() in low_body:
            highlights.append({"text": t, "kind": kind})
            return
        # Русские падежи: «модернизация» из сигнала vs «модернизацию» в
        # письме — ищем по основе слова и подсвечиваем реальный фрагмент.
        stem = t.lower()[:-2] if len(t) > 7 else None
        if stem:
            m = re.search(rf"\b{re.escape(stem)}\w*", low_body)
            if m:
                highlights.append({"text": (body or "")[m.start():m.end()],
                                   "kind": kind})

    person = contact.get("person") or ""
    if person:
        add(person.split()[0], "name")
        if len(person.split()) > 1:
            add(person.split()[1], "name")
    add(comp.get("region"), "city")
    add(comp.get("name"), "company")
    if signal.get("present"):
        top = signal["top"]
        add(top.get("event_type"), "trigger")
        for w in (top.get("what") or "").split()[:4]:
            if len(w) > 5:
                add(w, "trigger")
    for m in _PRICE_RE.finditer(body or ""):
        highlights.append({"text": m.group(0).strip(), "kind": "price"})
    for c in (kb_ctx or {}).get("cases") or []:
        add(c.get("city"), "case")
    # без дублей, порядок стабильный
    seen = set()
    uniq = []
    for h in highlights:
        k = (h["text"].lower(), h["kind"])
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    # ОПЕРАТОР ДОЛЖЕН ВИДЕТЬ ВЕСЬ ТЕКСТ, КОТОРЫЙ УЙДЁТ (требование владельца).
    # Подпись с юр-атрибуцией ФЗ-38 дописывается на отправке
    # (Sender._apply_signature), в теле её нет — раньше оператор подтверждал
    # письмо, обрывающееся на «С уважением,», и не видел, чем оно закончится.
    # Отдаём и подпись отдельно, и готовый текст целиком; правится по-прежнему
    # СЫРОЕ тело, иначе подпись задвоится при отправке.
    sig = (signature or "").strip()
    tail = (body or "").rstrip()
    if sig:
        first = sig.split("\n")[0].rstrip()
        # то же правило склейки, что в Sender._apply_signature: если тело уже
        # кончается на «С уважением,», второй раз эту строку не печатаем
        if first and tail.endswith(first):
            final = tail + "\n" + "\n".join(sig.split("\n")[1:]).lstrip("\n")
        else:
            final = tail + "\n\n" + sig
    else:
        final = body or ""
    return {"subject": subject or "", "body": body or "", "highlights": uniq,
            "signature": sig, "final_body": final,
            "signature_note": ("подпись добавляется при отправке" if sig else "")}


# -- блок 7: KB-провенанс -------------------------------------------------------- #

def _kb_block(kb_ctx, body, signals) -> dict:
    kb_ctx = kb_ctx or {}
    cases = [{"id": c.get("id") or c.get("case_id") or "",
              "city": c.get("city") or "",
              "what": (c.get("what") or c.get("solution") or
                       c.get("title") or "")[:100],
              "brand": c.get("brand") or ""}
             for c in (kb_ctx.get("cases") or [])]
    geo_str = kb_ctx.get("geo") or ""
    m_fact = re.search(r"(\d+)", geo_str)
    geo_fact = int(m_fact.group(1)) if m_fact else None
    m_claim = _GEO_CLAIM_RE.search(body or "")
    geo_claimed = int(m_claim.group(1)) if m_claim else None
    overclaim = bool(geo_fact is not None and geo_claimed is not None
                     and geo_claimed > geo_fact)
    trigger = kb_ctx.get("signal_hint") or ""
    trigger_confirmed = bool(signals) if trigger else None
    return {
        "cases": cases,
        "price_band": kb_ctx.get("price_band") or "",
        "price_median": kb_ctx.get("price_median") or {},
        "budget_score": kb_ctx.get("budget_score"),
        "geo_fact": geo_fact,
        "geo_fact_str": geo_str,
        "geo_claimed": geo_claimed,
        "geo_overclaim": overclaim,          # завышение = жёлтый флаг
        "trigger_phrase": trigger,
        "trigger_confirmed": trigger_confirmed,  # «подтверждено signals: да/нет»
    }


# -- блок 8: комплаенс ФЗ-38/152 -------------------------------------------------- #

def _compliance_block(subject, body, signature: str = "") -> dict:
    """Комплаенс считаем по тексту, который РЕАЛЬНО уйдёт адресату.

    Юр-атрибуция («ООО «Руспром», ИНН …») живёт в подписи, а подпись
    дописывается на отправке (Sender._apply_signature), в теле письма её нет.
    Пока подпись сюда не передавали, блок показывал «атрибуции НЕТ» у КАЖДОГО
    письма — оператор видел красный флаг всегда и переставал его замечать,
    то есть гейт, наоборот, ослаблял контроль. Теперь подпись учитывается.
    """
    text = f"{subject}\n{body}\n{signature or ''}"
    attribution = bool(_ATTR_ENTITY_RE.search(text)
                       and (_INN_RE.search(text)
                            or "prokompressor.ru" in text.lower()))
    unsub_in_body = bool(re.search(r"отпис|не хотите получать|unsubscribe",
                                   text, re.IGNORECASE))
    fio = sorted({m.group(0) for m in _FIO_RE.finditer(text)})
    fio_n = len(fio)
    banned = sorted({m.group(0) for m in _BANNED_RE.finditer(text)})
    return {
        "attribution_ok": attribution,       # нет = красный
        "unsub_in_body": unsub_in_body,      # нет = красный (см. note)
        "unsub_note": ("механизм отписки обязателен: в теле нет — "
                       "List-Unsubscribe (RFC 8058) добавится заголовком "
                       "при отправке" if not unsub_in_body else ""),
        "fio_count": fio_n,
        "fio_scale": "0" if fio_n == 0 else ("1" if fio_n == 1
                                             else ("2" if fio_n == 2 else "3+")),
        "fio_found": fio,
        "banned_phrases": banned,            # жёлтая подсветка
        "competitors_note": "списка имён конкурентов в данных нет — "
                            "скан только по оборотам превосходства",
    }


# -- блок 10: история контактов --------------------------------------------------- #

def _history_block(store, inn, email) -> dict:
    if store is None:
        return {"items": [], "last": None, "recent_90d": False,
                "note": "send_log недоступен"}
    try:
        items = store.send_log_history(email=email, inn=inn, limit=10)
        last = store.last_contact(email=email, inn=inn)
    except Exception:  # noqa: BLE001
        return {"items": [], "last": None, "recent_90d": False,
                "note": "send_log недоступен"}
    recent = False
    if last:
        try:
            ts = datetime.fromisoformat(
                str(last.get("ts") or "").replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            recent = (datetime.now(timezone.utc) - ts).days < 90
        except ValueError:
            recent = True  # дата не парсится → консервативно красный
    replied = any(r.get("outcome") == "replied" for r in items)
    return {"items": items, "last": last, "recent_90d": recent,
            "replied_before": replied}


# -- SHOULD (Задача 2, вторая итерация) -------------------------------------------- #

def _should_block(company, emails, contact, body, scoring, batch_domains) -> dict:
    okved_all = re.findall(r"\d{2}\.\d+(?:\.\d+)?", company.get("okved") or "")
    matched = []
    try:
        import enrich_db as EDB
        for code in okved_all:
            d, _b = EDB.division_for_okveds(code)
            if d:
                matched.append(code)
    except Exception:  # noqa: BLE001
        pass

    # Deliverability-светофор: прозрачная формула — красный при mx=false или
    # verified=mismatch; жёлтый при роутер-роли/расхождении домена/фрибox;
    # иначе зелёный.
    email_l = contact.get("email") or ""
    free_provider = email_l.rsplit("@", 1)[-1] in (
        "mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru",
        "gmail.com", "rambler.ru")
    if contact.get("mx_ok") is False or (company.get("verified") == "mismatch"):
        light, why = "red", "mx мёртв или сайт не той компании"
    elif contact.get("router") or contact.get("domain_mismatch") or free_provider:
        light, why = "yellow", "роутер-роль / чужой домен / бесплатный провайдер"
    else:
        light, why = "green", "личный корп-адрес, домены сходятся"

    age_days = None
    upd = contact.get("updated_at") or ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", upd)
    if m:
        try:
            age_days = (datetime.now(timezone.utc)
                        - datetime.fromisoformat(m.group(0)).replace(
                            tzinfo=timezone.utc)).days
        except ValueError:
            age_days = None
    age_flag = ("red" if (age_days or 0) > 180
                else "yellow" if (age_days or 0) > 90 else "ok") \
        if age_days is not None else "нет данных"

    # Ценовой разрыв: максимум цены из письма vs buying_power.
    prices = []
    for mm in _PRICE_RE.finditer(body or ""):
        digits = re.sub(r"[^\d]", "", mm.group(0).split("руб")[0].split("₽")[0])
        if digits:
            val = int(digits)
            if "млн" in mm.group(0).lower():
                val *= 1_000_000
            prices.append(val)
    power = (scoring or {}).get("buying_power") or ""
    price_gap = bool(prices and power in ("micro", "small")
                     and max(prices) >= 5_000_000)

    src = (contact.get("source") or "").lower()
    if "site" in src or "сайт" in src:
        basis = "публичный адрес с сайта компании"
    elif "ег" in src or "egrul" in src:
        basis = "ЕГРЮЛ/открытый реестр"
    elif src:
        basis = f"источник: {src}"
    else:
        basis = "источник адреса не зафиксирован"

    local = email_l.split("@", 1)[0]
    return {
        "okved_all": okved_all,
        "okved_matched": matched,
        "deliverability": {"light": light, "why": why},
        "domain_concentration": (batch_domains or {}).get(
            email_l.rsplit("@", 1)[-1], 1) if email_l else None,
        "contact_age_days": age_days,
        "contact_age_flag": age_flag,
        "price_gap": price_gap,
        "prices_in_letter": prices,
        "legal_basis": basis,
        # NICE
        "generic_local_part": local in ("info", "sales", "office", "mail",
                                        "zakaz", "post", "admin"),
        "free_provider": free_provider,
        "privacy_link_in_letter": bool(
            re.search(r"политик\w+\s+(конфиденциальности|обработки)",
                      body or "", re.IGNORECASE)),
    }
