"""Объединённая карточка компании: база обзвона + enrich.db + скоринг (по ИНН).

ТЗ владельца (ENGINEER-TASKS-BASE-MERGE, 2026-07-24): базу обзвона (161 761
юрлицо, 36 полей, CSV с дропа) НЕ сливать физически с enrich.db — карточка
собирается на лету поверх компактного индекса и кэшируется.

Правила приоритета при конфликте (§2 ТЗ, дословно):
- направление (kc|meyer) — ТОЛЬКО из базы обзвона; enrich его не перебивает.
  ИНН не из базы → направление ПУСТОЕ (division_for_okveds из enrich можно
  показывать как «предположение», но НЕ как основание для отправки);
- контакты: enrich.db приоритетнее базы (свежее, роли/верификация);
  телефоны — ОБА набора с пометкой источника;
- выручка/ОКВЭД/директор — из базы обзвона (первоисточник);
- site из enrich только при verified in (inn, ogrn, phone, provider);
  cand_site — с пометкой «не подтверждён».

Индекс обзвона — SQLite-таблица `obzvon` (компактная: «ВсеОКВЭД» сжат до
кодов, остальное как есть). Строится стримом CSV: build_obzvon_index()
(CLI: sender/tools/build_obzvon_index.py). Пути задаются конфигом
`obzvon.index_path` / `obzvon.enrich_db` (env ENRICH_DB — фолбэк, как в
infopanel).
"""

from __future__ import annotations

import csv
import logging
import re
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# «База» из CSV → каноническое направление ящиков/кампаний
DIVISION_BY_BASE = {
    "компрессор центр": "kc",
    "meyer": "meyer",
}

_OKVED_CODE_RE = re.compile(r"\b\d{2}(?:\.\d{1,2}){0,2}\b")


def norm_inn(raw: object) -> str:
    """Канон ИНН: только цифры (10/12 значимы, но не валидируем жёстко)."""
    return re.sub(r"\D", "", str(raw or ""))


def division_from_segment(segment: object) -> Optional[str]:
    """Сегмент кампании/получателя (свободный текст импорта) → kc|meyer|None.

    Для гейта на этапе СБОРКИ ОЧЕРЕДИ: ящик ещё не выбран, направление
    кампании — прокси (кампании сегментированы по P1.5.1). None = сегмент
    не распознан, очередь-гейт сравнить не может (решают точки 2 и 3)."""
    s = str(segment or "").strip().lower()
    if not s:
        return None
    if "meyer" in s or "мейер" in s or "мейр" in s:
        return "meyer"
    if "кц" in s or "kc" in s or "компрессор" in s:
        return "kc"
    return None


# Товарные маркеры направлений в колонке «Все категории оборудования» базы.
# Решение владельца 25.07: направление отправки определяют ПОТРЕБНОСТИ компании,
# а не одна метка. Основание — данные базы: 23709 из 32421 компаний Meyer-сегмента
# нуждаются и в КЦ-товарах, то есть жёсткая метка запрещала писать им законное
# компрессорное предложение от того же юрлица (ООО «Руспром»).
_EQUIP_MARKERS = {
    "kc": ("компрессор", "азот", "кислород", "мкс", "пневмо", "воздуходув"),
    "meyer": ("рентген", "фотосепаратор", "фото-сепаратор", "инспекц"),
}


def divisions_by_equipment(categories: object) -> set:
    """«Все категории оборудования» → {kc}|{meyer}|{kc,meyer}|set(). Пустое
    множество = потребности неизвестны (колонка пуста/без маркеров)."""
    text = str(categories or "").lower()
    if not text:
        return set()
    return {d for d, keys in _EQUIP_MARKERS.items() if any(k in text for k in keys)}


def campaign_division(campaign) -> Optional[str]:
    """Направление кампании: segment из config_json (P1.5.1) → kc|meyer|None."""
    seg = None
    cfgd = getattr(campaign, "config", None)
    if isinstance(cfgd, dict):
        seg = cfgd.get("segment")
    if seg is None:
        seg = getattr(campaign, "segment", None)
    return division_from_segment(seg)


# --------------------------------------------------------------------------- #
# Индекс базы обзвона
# --------------------------------------------------------------------------- #

# CSV-заголовок (36 колонок) → имя колонки индекса. Маппинг по ИМЕНАМ, не по
# позициям — переупорядочивание выгрузки не ломает построение.
_CSV_TO_INDEX = {
    "База": "base_label",
    "ИНН": "inn",
    "ОГРН": "ogrn",
    "КПП": "kpp",
    "Краткое": "name_short",
    "Полное": "name_full",
    "Статус": "status",
    "ДатаРег": "reg_date",
    "Адрес": "address",
    "Регион": "region",
    "ОПФ": "opf",
    "УстКапитал": "ust_capital",
    "Директор": "director",
    "ИННдир": "dir_inn",
    "Учредители": "founders",
    "ОсновнойОКВЭД": "okved_main",
    "ВсеОКВЭД": "okved_all_codes",        # компактится до кодов
    "Телефоны": "phones_base",
    "Emails": "emails_base",
    "Сайты": "sites",
    "Телефоны с сайта": "phones_site",
    "Email с сайта": "emails_site",
    "ГодОтч": "god_otch",
    "Выручка": "revenue",
    "ЧистПрибыль": "profit",
    "Капитал": "capital",
    "ССЧ": "ssch",
    "Итоговый балл приоритета": "priority_total",
    "Макс. балл по связке": "priority_max",
    "Оборудование по основному ОКВЭД": "equip_by_okved",
    "Все категории оборудования": "equip_categories",
    "Найденные ОКВЭД": "found_okveds",
    "Комментарий расчёта": "calc_comment",
    "Выручка, руб.": "revenue_rub",
    "Приоритет × выручка / 10000": "pxr",
}
_INDEX_COLUMNS = ["division"] + list(_CSV_TO_INDEX.values())
_TRUNCATE = {"founders": 600, "calc_comment": 1500}


def build_obzvon_index(lines: Iterable[str], db_path: str) -> dict:
    """Стрим CSV (итератор строк, BOM допустим) → SQLite-индекс по ИНН.

    Возвращает статистику {rows, by_division, skipped_no_inn, unknown_base}.
    Повторный ИНН перезаписывает строку (в базе дублей нет — страховка).
    """
    reader = csv.reader(lines, delimiter=";")
    header = next(reader)
    header[0] = header[0].lstrip("﻿")
    missing = [h for h in _CSV_TO_INDEX if h not in header]
    if missing:
        raise ValueError(f"obzvon CSV: нет ожидаемых колонок {missing}")
    pos = {name: header.index(h) for h, name in _CSV_TO_INDEX.items()}

    cx = sqlite3.connect(db_path)
    cx.execute("PRAGMA journal_mode=OFF")
    cx.execute("PRAGMA synchronous=OFF")
    cols = ", ".join(_INDEX_COLUMNS)
    cx.execute(f"CREATE TABLE IF NOT EXISTS obzvon ({cols}, PRIMARY KEY (inn))")
    ins = (f"INSERT OR REPLACE INTO obzvon ({cols}) VALUES "
           f"({','.join('?' for _ in _INDEX_COLUMNS)})")

    stats = {"rows": 0, "by_division": {}, "skipped_no_inn": 0,
             "unknown_base": 0}
    batch = []
    for row in reader:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        rec = {name: (row[i] or "").strip() for name, i in pos.items()}
        inn = norm_inn(rec["inn"])
        if not inn:
            stats["skipped_no_inn"] += 1
            continue
        rec["inn"] = inn
        division = DIVISION_BY_BASE.get(rec["base_label"].strip().lower(), "")
        if not division:
            stats["unknown_base"] += 1
        rec["division"] = division
        # компакция: «ВсеОКВЭД» с названиями → только коды (в ~10 раз меньше)
        rec["okved_all_codes"] = "|".join(
            dict.fromkeys(_OKVED_CODE_RE.findall(rec["okved_all_codes"])))
        for field, limit in _TRUNCATE.items():
            if len(rec[field]) > limit:
                rec[field] = rec[field][:limit] + "…"
        batch.append([rec[c] for c in _INDEX_COLUMNS])
        stats["rows"] += 1
        stats["by_division"][division or "?"] = (
            stats["by_division"].get(division or "?", 0) + 1)
        if len(batch) >= 2000:
            cx.executemany(ins, batch)
            batch.clear()
    if batch:
        cx.executemany(ins, batch)
    cx.commit()
    cx.close()
    return stats


class ObzvonIndex:
    """Read-only доступ к индексу обзвона. Нет файла — честный degraded-режим:
    get()/division() отдают None, available=False (гейт направлений при этом
    ОБЯЗАН блокировать отправку — «пустое направление», см. division_gate)."""

    def __init__(self, db_path: Optional[str]):
        self._path = db_path or ""
        self._cx: Optional[sqlite3.Connection] = None
        if self._path and Path(self._path).exists():
            self._cx = sqlite3.connect(
                f"file:{self._path}?mode=ro", uri=True, check_same_thread=False)
            self._cx.row_factory = sqlite3.Row

    @property
    def available(self) -> bool:
        return self._cx is not None

    def get(self, inn: object) -> Optional[dict]:
        if self._cx is None:
            return None
        row = self._cx.execute(
            "SELECT * FROM obzvon WHERE inn=?", (norm_inn(inn),)).fetchone()
        return dict(row) if row else None

    def division(self, inn: object) -> Optional[str]:
        """kc|meyer|None. None = ИНН не из базы обзвона ИЛИ индекс недоступен —
        по ТЗ это «направление ПУСТОЕ», отправка запрещена."""
        if self._cx is None:
            return None
        row = self._cx.execute(
            "SELECT division FROM obzvon WHERE inn=?",
            (norm_inn(inn),)).fetchone()
        div = (row["division"] or "").strip() if row else ""
        return div or None

    def equip_for_okved(self, okved: object) -> str:
        """Канонический текст «Оборудование по основному ОКВЭД» для кода.

        Единый формат владельца (27.07: «договаривались, что всё будет в едином
        формате записано»): для компаний ВНЕ базы обзвона потребность в
        оборудовании берём из САМОЙ базы — у неё для каждого основного ОКВЭД
        уже посчитан текст equip_by_okved. Ищем по точному коду, затем
        обрезаем сегменты (35.30.11 → 35.30 → 35). Нет совпадения — ''."""
        if self._cx is None:
            return ""
        код = str(okved or "").strip().split()[0] if str(okved or "").strip() else ""
        while код:
            row = self._cx.execute(
                "SELECT equip_by_okved FROM obzvon "
                "WHERE okved_main LIKE ? AND COALESCE(equip_by_okved,'')<>'' "
                "LIMIT 1", (код + "%",)).fetchone()
            текст = (row["equip_by_okved"] or "").strip() if row else ""
            # «Не найдено»/«нет» в базе = ОКВЭД нецелевой, оборудования нет —
            # это НЕ значение (владелец 27.07: карточка ПО-разработчика
            # показывала «Не найдено» как потребность)
            if текст and текст.lower() not in ("не найдено", "нет", "-", "—"):
                return текст
            if "." not in код:
                break
            код = код.rsplit(".", 1)[0]
        return ""

    def divisions(self, inn: object) -> Optional[set]:
        """Направления, которым РАЗРЕШЕНО писать этой компании. Объединение:
        1) метка division базы (поддерживает составную «kc+meyer»);
        2) потребности из «Все категории оборудования» (divisions_by_equipment).
        None = ИНН не из базы обзвона / индекс недоступен — отправка запрещена,
        как и раньше. set() = в базе есть, но ни метки, ни потребностей нет."""
        if self._cx is None:
            return None
        row = self._cx.execute(
            "SELECT division, equip_categories FROM obzvon WHERE inn=?",
            (norm_inn(inn),)).fetchone()
        if row is None:
            return None
        out = {p for p in (row["division"] or "").strip().split("+") if p}
        try:
            out |= divisions_by_equipment(row["equip_categories"])
        except (IndexError, KeyError):   # индекс старой схемы без колонки
            pass
        return out

    def close(self) -> None:
        if self._cx is not None:
            self._cx.close()
            self._cx = None


# --------------------------------------------------------------------------- #
# enrich.db (динамические колонки: снапшоты бывают новее схемы в репо)
# --------------------------------------------------------------------------- #

_SITE_VERIFIED_OK = frozenset({"inn", "ogrn", "phone", "provider"})


def _load_enrich(inn: str, db_path: Optional[str]) -> dict:
    import os
    path = db_path or os.environ.get("ENRICH_DB", "")
    if not path or not Path(path).exists():
        return {"available": False, "company": {}, "emails": [], "signals": []}
    cx = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    try:
        comp = cx.execute(
            "SELECT * FROM companies WHERE inn=?", (inn,)).fetchone()
        emails = [dict(r) for r in cx.execute(
            "SELECT * FROM emails WHERE inn=?", (inn,)).fetchall()]
        signals = [dict(r) for r in cx.execute(
            "SELECT * FROM signals WHERE inn=? ORDER BY hotness DESC, ts DESC",
            (inn,)).fetchall()]
    finally:
        cx.close()
    return {"available": True, "company": dict(comp) if comp else {},
            "emails": emails, "signals": signals}


# --------------------------------------------------------------------------- #
# Карточка
# --------------------------------------------------------------------------- #

def _split_list(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[|,;]", raw or "") if p.strip()]


def _merge_contacts(base_row: Optional[dict], enrich: dict) -> dict:
    """Контакты: enrich приоритетнее; телефоны — оба набора с источником."""
    emails: list[dict] = []
    seen = set()
    for e in enrich.get("emails", []):
        addr = (e.get("email") or "").strip().lower()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        emails.append({
            "email": addr, "role": e.get("role") or "",
            "person": e.get("person") or "",
            "mx_ok": bool(e.get("mx_ok")),
            "source": e.get("source") or "enrich",
            "source_url": e.get("source_url") or "",
            "origin": "enrich",
        })
    if base_row:
        for field, src in (("emails_base", "база"), ("emails_site", "сайт (база)")):
            for addr in _split_list(base_row.get(field, "")):
                addr = addr.lower()
                if "@" not in addr or addr in seen:
                    continue
                seen.add(addr)
                emails.append({"email": addr, "role": "", "person": "",
                               "mx_ok": None, "source": src, "source_url": "",
                               "origin": "obzvon"})
    phones: list[dict] = []
    if base_row:
        for field, src in (("phones_base", "база"),
                           ("phones_site", "сайт, с доб.")):
            for ph in _split_list(base_row.get(field, "")):
                phones.append({"phone": ph, "source": src})
    ephones = (enrich.get("company") or {}).get("phones") or ""
    for ph in _split_list(str(ephones)):
        phones.append({"phone": ph, "source": "enrich"})
    return {"emails": emails, "phones": phones}


def _site_view(ecomp: dict) -> dict:
    """site по правилу verified; cand_site всегда с пометкой «не подтверждён»."""
    verified = (ecomp.get("verified") or "").strip().lower()
    site = (ecomp.get("site") or "").strip()
    cand = (ecomp.get("cand_site") or "").strip()
    ok = verified in _SITE_VERIFIED_OK
    return {
        "site": site if (site and ok) else "",
        "site_verified": verified if ok else "",
        "cand_site": cand or (site if (site and not ok) else ""),
        "cand_site_note": "не подтверждён" if (cand or (site and not ok)) else "",
    }


def build_company_card(
    inn: object,
    *,
    obzvon: Optional[ObzvonIndex] = None,
    enrich_db_path: Optional[str] = None,
    scoring: Optional[dict] = None,
) -> dict:
    """Карточка одним dict — этот же JSON идёт в панель pending_review.

    Ключевые поля:
      division      — kc|meyer|None, ТОЛЬКО из базы обзвона (маршрутизация);
      division_guess — предположение enrich (division_for_okveds), НЕ основание;
      obzvon        — компактная строка базы (36 полей) или None;
      enrich        — company/emails/signals как есть (+available);
      contacts      — слитые правилами приоритета;
      site_view     — site/cand_site по правилу verified.
    """
    inn_n = norm_inn(inn)
    base_row = obzvon.get(inn_n) if obzvon is not None else None
    enrich = _load_enrich(inn_n, enrich_db_path)
    ecomp = enrich.get("company") or {}

    division = None
    if base_row:
        division = (base_row.get("division") or "").strip() or None
    guess = (ecomp.get("division") or "").strip() or None

    card = {
        "inn": inn_n,
        "division": division,
        "division_source": "obzvon" if division else None,
        "division_guess": guess if guess != division else None,
        "obzvon_available": obzvon is not None and obzvon.available,
        "obzvon": base_row,
        "enrich": enrich,
        "contacts": _merge_contacts(base_row, enrich),
        "site_view": _site_view(ecomp),
        "scoring": scoring or {},
    }
    if base_row:
        card["fin"] = {k: base_row.get(k, "") for k in
                       ("god_otch", "revenue", "profit", "capital", "ssch",
                        "revenue_rub")}
        card["priority"] = {k: base_row.get(k, "") for k in
                            ("priority_total", "priority_max", "pxr")}
        card["product"] = {k: base_row.get(k, "") for k in
                           ("equip_by_okved", "equip_categories",
                            "found_okveds", "calc_comment")}
    return card


class CompanyCards:
    """Фасад с кэшем: card(inn) для панели/гейтов. Композит собирает один раз
    в wiring и раздаёт (orchestrator/confirm/sender)."""

    def __init__(self, *, index_path: Optional[str] = None,
                 enrich_db_path: Optional[str] = None, cache_size: int = 512):
        self._obzvon = ObzvonIndex(index_path)
        self._enrich_path = enrich_db_path
        self._cache: dict[str, dict] = {}
        self._cache_size = cache_size

    @property
    def obzvon(self) -> ObzvonIndex:
        return self._obzvon

    @property
    def active(self) -> bool:
        """Гейт направлений активен, когда индекс обзвона реально подключён."""
        return self._obzvon.available

    def division(self, inn: object) -> Optional[str]:
        return self._obzvon.division(inn)

    def divisions(self, inn: object) -> Optional[set]:
        """Разрешённые направления по метке + потребностям (см. ObzvonIndex)."""
        return self._obzvon.divisions(inn)

    def equip_for_okved(self, okved: object) -> str:
        """Канонический текст оборудования по ОКВЭД (единый формат базы) с
        кэшем: карточки вне базы дёргают одинаковые коды пачками."""
        код = str(okved or "").strip()
        key = "equip:" + код
        if key in self._cache:
            return self._cache[key]
        текст = self._obzvon.equip_for_okved(код)
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = текст
        return текст

    def card(self, inn: object) -> dict:
        key = norm_inn(inn)
        if key in self._cache:
            return self._cache[key]
        card = build_company_card(
            key, obzvon=self._obzvon, enrich_db_path=self._enrich_path)
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = card
        return card
