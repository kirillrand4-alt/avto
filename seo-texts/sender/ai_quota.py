# -*- coding: utf-8 -*-
"""sender/ai_quota.py — дневная квота AI-генерации писем в панели (C6).

Владелец задаёт темп НЕ одним числом, а расписанием: «3 сегодня, 3 завтра,
5 послезавтра». Одно число этого не выражает (прогрев разгоняется день ото
дня), поэтому храним карту дата -> сколько сгенерировать в panel_settings
(ключ ``ai_daily_quota``), а ФАКТ берём из ai_letter_log — того же лога, что
пишет скрипт ai_gen_quota.py. Двух источников правды не заводим.

Идемпотентность: квота считается по УЖЕ СДЕЛАННЫМ за день попыткам, а не по
нажатиям кнопки. Повторный запуск доливает только недостающее, второй клик в
тот же день не удваивает генерацию. Брак (status='brak') тоже съедает квоту:
это расход провайдерского API, и в плохой день дневной лимит должен держать
именно расход, а не количество удачных писем (счётчик брака отдаётся в UI
отдельно, чтобы владелец видел причину недобора).

Движок stdlib: LLM-вызов приходит снаружи (``gen_factory``), в тестах — фейк.
Долгий прогон крутится в фоне-потоке, состояние durable в panel_settings
(``ai_quota_run``): рестарт службы посреди прогона не оставляет UI без ответа.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

try:  # zoneinfo есть в 3.9+, оставляем безопасный фолбэк (как в sender.sender)
    from zoneinfo import ZoneInfo
except Exception:  # noqa: BLE001
    ZoneInfo = None  # type: ignore[assignment]

from sender.errors import ValidationError

# ai_letter держим на stdlib и импортируем мягко: панель должна подниматься и
# без генератора (очередь, ответы, отчёты от него не зависят).
try:
    from sender import ai_letter as _ai_letter
except Exception:  # noqa: BLE001
    _ai_letter = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# --- ВТОРАЯ ПОПЫТКА ПОСЛЕ БРАКА (владелец 12.08: «делай») -------------------- #
#
# Брак был окончательным: получатель попадал в «уже сделанные» и письма больше
# не получал никогда. Разбор 36 браков по всем кампаниям показал, что по
# существу отсеялось шесть, а тридцать вылетели по ФОРМЕ текста: оборот
# «закладываю» (18 раз — его же диктовала наша собственная подсказка), нет
# строки отказа, финал не «С уважением», объём, проценты. Такое исправляется
# следующей попыткой, и терять из-за этого предприятие с техконтактом глупо.
#
# Различаем два вида брака:
#   brak       — по СУЩЕСТВУ: инженерная линза сказала, что профиль не тот
#                (розничная сеть, торговля, аренда). Второй заход ничего не
#                изменит: письмо этой компании не нужно вовсе;
#   brak_forma — по ФОРМЕ: всё остальное. Получатель остаётся кандидатом и
#                берётся следующим прогоном с новой ротацией механик.
#
# Повторов не больше ПРЕДЕЛ_ПОПЫТОК: письмо, которое дважды не получилось,
# дальше крутить бессмысленно — это уже не случайность, а свойство карточки.
СТАТУС_БРАК = "brak"
СТАТУС_БРАК_ФОРМА = "brak_forma"
ПРЕДЕЛ_ПОПЫТОК = 2
_БРАК_ПО_СУЩЕСТВУ = ("инженерная линза", "профиль -", "профиль —",
                     "не производств")


def статус_брака(причины) -> str:
    """Форма или существо: от этого зависит, будет ли вторая попытка."""
    текст = " ".join(str(p) for p in (причины or [])).lower()
    return (СТАТУС_БРАК if any(м in текст for м in _БРАК_ПО_СУЩЕСТВУ)
            else СТАТУС_БРАК_ФОРМА)


QUOTA_KEY = "ai_daily_quota"      # {"<campaign_id>": {"YYYY-MM-DD": N}}
RUN_KEY = "ai_quota_run"          # {"<campaign_id>": {...состояние последнего прогона}}
DEFAULT_TZ = "Europe/Moscow"
DEFAULT_HORIZON = 7               # сколько дней показываем в карточке
MAX_PER_DAY = 200                 # предохранитель от опечатки «30» -> «300»
KEEP_PAST_DAYS = 30               # прошлое старше этого чистим при сохранении
SCAN_LIMIT = 20000                # потолок просмотра базы при поиске кандидатов
_PAGE = 500
_STALE_RUN_SEC = 1800             # прогон старше получаса считаем оборванным

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


_CITY_PREP = None


def _city_index():
    """Справочник городов: из индекса опубликованных проектов (263 города) плюс
    регионы из sender.regions. Собирается один раз на процесс."""
    global _CITY_PREP
    if _CITY_PREP is not None:
        return _CITY_PREP
    города = set()
    for path in (r'C:\sender\projects-index.json',
                 os.path.join(os.path.dirname(os.path.dirname(
                     os.path.abspath(__file__))), 'projects-index.json')):
        try:
            with open(path, encoding='utf-8') as f:
                for x in json.load(f):
                    c = (x.get('city') or '').strip()
                    if c and len(c) > 3 and 'область' not in c and 'край' not in c:
                        города.add(c)
            break
        except Exception:  # noqa: BLE001
            continue
    try:
        from sender.regions import REGION_TZ
        города |= {k.capitalize() for k in REGION_TZ if len(k) > 5}
    except Exception:  # noqa: BLE001
        pass
    # длинные впереди: «Нижний Новгород» должен победить «Новгород»
    _CITY_PREP = sorted(города, key=len, reverse=True)
    return _CITY_PREP


# Латиница в ссылках новостей: «zavod-v-saratove» — город часто есть только там.
_TRANSLIT = {'shch': 'щ', 'sch': 'щ', 'zh': 'ж', 'kh': 'х', 'ts': 'ц', 'ch': 'ч',
             'sh': 'ш', 'yu': 'ю', 'ya': 'я', 'yo': 'ё', 'jo': 'ё', 'ey': 'ей',
             'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е',
             'z': 'з', 'i': 'и', 'j': 'й', 'k': 'к', 'l': 'л', 'm': 'м',
             'n': 'н', 'o': 'о', 'p': 'п', 'r': 'р', 's': 'с', 't': 'т',
             'u': 'у', 'f': 'ф', 'h': 'х', 'c': 'ц', 'y': 'ы', "'": ''}
_CITY_PREP_RE = re.compile(
    r'(?:^|[\s(«"])(?:в|во|под|близ|около|рядом с)\s+'
    r'([А-ЯЁ][а-яё]{3,}(?:[- ][А-ЯЁ]?[а-яё]{3,})?)')


def _translit(s: str) -> str:
    out, i = [], 0
    low = s.lower()
    while i < len(low):
        for n in (4, 3, 2, 1):
            if low[i:i + n] in _TRANSLIT:
                out.append(_TRANSLIT[low[i:i + n]])
                i += n
                break
        else:
            i += 1
    return ''.join(out)


def _nominative(word: str) -> str:
    """Косвенный падеж -> именительный, эвристикой. Точность тут не критична:
    это подсказка генератору, а не подстановка в текст — модель всё равно
    склоняет сама, и результат проверяют линзы."""
    w = word.strip()
    спр = _city_index_lower()
    if w.lower() in спр:
        return спр[w.lower()]
    for окончание, замена in (('е', ''), ('и', 'ь'), ('и', ''), ('у', ''),
                              ('ом', ''), ('ой', 'а'), ('ах', 'и'), ('ы', '')):
        if w.lower().endswith(окончание):
            кандидат = w[:len(w) - len(окончание)] + замена
            if кандидат.lower() in спр:
                return спр[кандидат.lower()]
    # в справочнике нет — отдаём первую разумную обрезку
    for окончание, замена in (('е', ''), ('и', 'ь'), ('ом', ''), ('у', '')):
        if w.lower().endswith(окончание) and len(w) - len(окончание) >= 4:
            return w[:len(w) - len(окончание)] + замена
    return w


def _city_index_lower():
    return {c.lower(): c for c in _city_index()}


# Непромышленные разделы ОКВЭД (для отсечки НЕПРОВЕРЕННЫХ компаний без
# попадания в целевую карту): ИТ/медиа 58-63, финансы 64-66, недвижимость 68,
# консалтинг/юр/реклама 69-70-71-73-74, аренда/агентства 77-82, госуправление
# 84, образование 85, здравоохранение/соцуслуги 86-88, культура/спорт 90-93,
# прочие услуги 94-96, домохозяйства 97-98, экстерриториальные 99, торговля
# 45-47. Промышленные (01-43, 49-53, 55-56, 72 НИИ) НЕ режем — карта покрывает
# не все их коды, а компрессоры там реальны (пример владельца: добыча угля).
_NONINDUSTRIAL_PREFIXES = (
    "45", "46", "47", "58", "59", "60", "61", "62", "63", "64", "65", "66",
    "68", "69", "70", "71", "73", "74", "75", "77", "78", "79", "80", "81",
    "82", "84", "85", "86", "87", "88", "90", "91", "92", "93", "94", "95",
    "96", "97", "98", "99")


def _nonindustrial_okved(code: str) -> bool:
    """Основной ОКВЭД из явно непромышленного раздела?"""
    c = str(code or "").strip()
    return bool(c) and c.split(".")[0] in _NONINDUSTRIAL_PREFIXES


def _city_from_news(text: str, url: str = '') -> str:
    """Город ИЗ НОВОСТИ. Приоритет владельца: сначала место события, потом база —
    новость про «завод в Саратове» важнее юр-адреса головной компании, который
    может быть в другом регионе.

    Порядок: предлог места в тексте («в Саратове») -> справочник городов ->
    латиница в ссылке («-v-saratove»).
    """
    t = (text or '').strip()
    if t:
        m = _CITY_PREP_RE.search(t)
        if m:
            назв = _nominative(m.group(1))
            if назв and len(назв) >= 4:
                return назв
        low = t.lower()
        for c in _city_index():
            if c.lower() in low:
                return c
    if url:
        translit = _translit(re.sub(r'[^a-zA-Z\-]', ' ', url))
        спр = _city_index_lower()
        for c in sorted(спр, key=len, reverse=True):
            if len(c) >= 5 and c in translit:
                return спр[c]
    return ''


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _zone(name: str):
    if ZoneInfo is None or not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - на Windows бывает нет tzdata
        return timezone(timedelta(hours=3)) if name == DEFAULT_TZ else timezone.utc


def _parse_utc(ts: str) -> Optional[datetime]:
    """created_at из ai_letter_log (UTC ISO). Naive-строки считаем UTC."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@dataclass
class QuotaDay:
    """Один день расписания: план + факт по ai_letter_log."""

    date: str
    quota: int = 0
    generated: int = 0      # status='ok' — письмо ушло в очередь подтверждений
    rejected: int = 0       # status='brak' — не прошло гейт/линзы
    weekday: int = 1        # ISO 1=Пн..7=Вс (подпись в UI)

    @property
    def attempts(self) -> int:
        return self.generated + self.rejected

    @property
    def remaining(self) -> int:
        return max(0, self.quota - self.attempts)

    def as_json(self) -> dict:
        return {"date": self.date, "quota": self.quota,
                "generated": self.generated, "rejected": self.rejected,
                "attempts": self.attempts, "remaining": self.remaining,
                "weekday": self.weekday}


@dataclass
class RunResult:
    """Итог одного прогона «сгенерировать сейчас»."""

    campaign_id: int
    date: str
    quota: int = 0
    before: int = 0         # попыток за день ДО запуска
    planned: int = 0        # сколько взяли в работу
    generated: int = 0
    rejected: int = 0
    candidates: int = 0     # сколько получателей без письма нашлось
    reason: str = ""        # почему ничего не сделали (пусто = работали)
    errors: list = field(default_factory=list)

    def as_json(self) -> dict:
        return {"campaign_id": self.campaign_id, "date": self.date,
                "quota": self.quota, "before": self.before,
                "planned": self.planned, "generated": self.generated,
                "rejected": self.rejected, "candidates": self.candidates,
                "reason": self.reason, "errors": list(self.errors)}


class AiQuota:
    """Расписание квоты + прогон генерации по остатку на сегодня.

    ``store`` — панельный Store (panel_settings, получатели, очередь confirm).
    ``db_path`` — тот же файл БД: ai_letter_log живёт в нём, но пишется своим
    соединением (как в sender.ai_letter.log_results), поэтому путь нужен явно.
    ``gen_factory`` — ленивая фабрика генератора: боевая тянет провайдерский
    API, в тестах подставляется фейк и сеть не трогается.
    """

    def __init__(self, store, *, db_path: Optional[str] = None,
                 gen_factory: Optional[Callable[[], Any]] = None,
                 enrich_db: Optional[str] = None, batch: int = 4,
                 tz: str = DEFAULT_TZ,
                 today_fn: Optional[Callable[[], str]] = None,
                 config=None):
        self._store = store
        # конфиг нужен для превью подписи в карточке подтверждения (оператор
        # должен видеть письмо целиком, включая юр-атрибуцию ФЗ-38)
        self._config = config
        self._db_path = str(db_path or getattr(store, "_db_path", "") or "sender.db")
        self._gen_factory = gen_factory or self._default_gen_factory
        self._enrich_db = enrich_db
        self._batch = max(1, int(batch))
        self._tz = _zone(tz)
        self._today_fn = today_fn
        self._lock = threading.Lock()

    # ---------------------------------------------------------- вспомогалки --

    def _default_gen_factory(self):
        """Боевой генератор: провайдерский API через review_lenses (правило
        владельца — вся тяжёлая работа туда, не в токены сессии).

        best-of-3 по умолчанию (директива владельца 28.07: «бюджет на письмо
        небольшой, если что-то мешает качеству - можно увеличивать в разы»):
        три независимых варианта + судья-редактор. ai_quota.best_of в конфиге
        меняет N (1 = выключить)."""
        from sender.ai_letter import AiLetterGen, load_facts
        from sender.review_lenses import default_caller

        def caller(prompt: str) -> str:
            # Потолок ответа больше линзового: партия — до четырёх писем, а
            # канон редактора (13.08) удлинил письмо вдвое. На старых 2000
            # JSON партии обрывался на середине, и письмо шло в брак «нет
            # JSON» — не по качеству, а по длине ответа.
            text, _meta = default_caller(prompt, max_tokens=8000)
            return text

        try:
            best = int(self._config.get("ai_quota.best_of", 3)) if (
                self._config is not None and hasattr(self._config, "get")) else 3
        except Exception:  # noqa: BLE001
            best = 3
        return AiLetterGen(caller, facts=load_facts(), best_of=best)

    def today(self) -> str:
        if self._today_fn is not None:
            return self._today_fn()
        return datetime.now(timezone.utc).astimezone(self._tz).strftime("%Y-%m-%d")

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _ensure_log(con: sqlite3.Connection) -> None:
        """Схема ai_letter_log совпадает с sender.ai_letter.log_results: панель
        может открыть карточку раньше, чем отработает первая генерация."""
        con.execute("""CREATE TABLE IF NOT EXISTS ai_letter_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER,
            recipient_id INTEGER, email TEXT, status TEXT, subject TEXT,
            body TEXT, rounds_json TEXT, created_at TEXT)""")
        con.commit()

    # ------------------------------------------------------------ расписание --

    def schedule(self, campaign_id: int) -> dict:
        """Карта дата -> квота для кампании (пусто, если не задавали)."""
        raw = self._store.get_setting(QUOTA_KEY, None) or {}
        if not isinstance(raw, dict):
            return {}
        got = raw.get(str(int(campaign_id))) or {}
        if not isinstance(got, dict):
            return {}
        out = {}
        for day, n in got.items():
            try:
                out[str(day)] = int(n)
            except (TypeError, ValueError):
                continue
        return out

    def set_schedule(self, campaign_id: int, patch: dict) -> dict:
        """Слить правки в расписание. 0 = день удаляется (квота не задана),
        прошлое старше KEEP_PAST_DAYS чистим — иначе настройка растёт вечно."""
        if not isinstance(patch, dict):
            raise ValidationError("расписание: ожидается объект дата -> число")
        self._require_campaign(campaign_id)
        cur = self.schedule(campaign_id)
        for day, n in patch.items():
            day = str(day).strip()
            if not _DATE_RE.match(day):
                raise ValidationError(f"дата в формате ГГГГ-ММ-ДД: {day!r}")
            try:
                _date.fromisoformat(day)
            except ValueError:
                raise ValidationError(f"несуществующая дата: {day!r}")
            try:
                val = int(n)
            except (TypeError, ValueError):
                raise ValidationError(f"квота на {day}: нужно целое число")
            if val < 0 or val > MAX_PER_DAY:
                raise ValidationError(
                    f"квота на {day}: допустимо 0..{MAX_PER_DAY}, задано {val}")
            if val == 0:
                cur.pop(day, None)
            else:
                cur[day] = val
        edge = (_date.fromisoformat(self.today()) - timedelta(days=KEEP_PAST_DAYS))
        cur = {d: v for d, v in cur.items() if d >= edge.isoformat()}
        raw = self._store.get_setting(QUOTA_KEY, None)
        raw = dict(raw) if isinstance(raw, dict) else {}
        if cur:
            raw[str(int(campaign_id))] = cur
        else:
            raw.pop(str(int(campaign_id)), None)
        self._store.set_setting(QUOTA_KEY, raw)
        return cur

    # ---------------------------------------------------------------- факты --

    def counters(self, campaign_id: int, days: list) -> dict:
        """{дата: (ok, brak)} по ai_letter_log за перечисленные дни.

        Лог пишется в UTC, а владелец считает днями по Москве, поэтому дату
        берём из локального времени: иначе письма после 21:00 МСК уезжали бы
        в завтрашний счётчик и квота на день «сама собой» восстанавливалась.
        """
        out = {d: [0, 0] for d in days}
        if not days:
            return {}
        lo = min(days)
        lo_utc = (_date.fromisoformat(lo) - timedelta(days=2)).isoformat()
        con = self._connect()
        try:
            self._ensure_log(con)
            rows = con.execute(
                "SELECT created_at, status FROM ai_letter_log "
                "WHERE campaign_id=? AND created_at >= ?",
                (int(campaign_id), lo_utc)).fetchall()
        finally:
            con.close()
        for r in rows:
            dt = _parse_utc(r["created_at"])
            if dt is None:
                continue
            key = dt.astimezone(self._tz).strftime("%Y-%m-%d")
            if key not in out:
                continue
            if (r["status"] or "") == "ok":
                out[key][0] += 1
            else:
                out[key][1] += 1
        return {d: tuple(v) for d, v in out.items()}

    def days(self, campaign_id: int, *, horizon: int = DEFAULT_HORIZON,
             today: Optional[str] = None) -> list:
        """Ближайшие дни: план из расписания + факт из лога.

        Дальние даты, заданные вручную за горизонтом, тоже показываем — иначе
        владелец «потеряет» свою же настройку и решит, что она не сохранилась.
        """
        today = today or self.today()
        base = _date.fromisoformat(today)
        horizon = max(1, min(int(horizon), 31))
        window = [(base + timedelta(days=i)).isoformat() for i in range(horizon)]
        sched = self.schedule(campaign_id)
        tail = sorted(d for d in sched if d > window[-1])
        dates = window + tail
        cnt = self.counters(campaign_id, dates)
        out = []
        for d in dates:
            ok, brak = cnt.get(d, (0, 0))
            out.append(QuotaDay(date=d, quota=int(sched.get(d, 0)),
                                generated=ok, rejected=brak,
                                weekday=_date.fromisoformat(d).isoweekday()))
        return out

    # ------------------------------------------------------------ кандидаты --

    def _require_campaign(self, campaign_id: int):
        camp = self._store.get_campaign(int(campaign_id))
        if camp is None:
            raise ValidationError(f"кампания {campaign_id} не найдена")
        return camp

    def _segment(self, campaign_id: int) -> str:
        camp = self._require_campaign(campaign_id)
        cfg = camp.config if isinstance(camp.config, dict) else {}
        return str(cfg.get("segment") or camp.name)

    def _already(self, campaign_id: int) -> set:
        """Кому письмо уже делали: лог генерации + очередь подтверждений.
        Второй источник обязателен — письмо могло попасть в очередь скриптом
        ai_gen_quota.py до того, как появился этот модуль."""
        con = self._connect()
        try:
            self._ensure_log(con)
            # Формальный брак получателя НЕ хоронит: он остаётся кандидатом и
            # получает вторую попытку. Блокируем, если есть хоть одна запись
            # не-формальная (готовое письмо или брак по существу) либо
            # формальных уже накопилось ПРЕДЕЛ_ПОПЫТОК.
            ids = {r[0] for r in con.execute(
                "SELECT recipient_id FROM ai_letter_log "
                "WHERE campaign_id=? AND recipient_id IS NOT NULL "
                "GROUP BY recipient_id "
                "HAVING SUM(CASE WHEN status=? THEN 0 ELSE 1 END) > 0 "
                "    OR COUNT(*) >= ?",
                (int(campaign_id), СТАТУС_БРАК_ФОРМА,
                 ПРЕДЕЛ_ПОПЫТОК)).fetchall()}
            ids |= {r[0] for r in con.execute(
                "SELECT DISTINCT recipient_id FROM confirm_reviews "
                "WHERE campaign_id=? AND recipient_id IS NOT NULL",
                (int(campaign_id),)).fetchall()}
        finally:
            con.close()
        return ids

    # Имя кампании отраслевой партии = «<группа> — <направление>»: сегмент
    # кампании 10 это «Партия 935 — КЦ», а группа в базе просто «Партия 935».
    # Разделитель длинное тире с пробелами, как его пишет оператор.
    _РАЗДЕЛ_НАПРАВЛЕНИЯ = " — "
    _НАПРАВЛЕНИЕ_ПО_ХВОСТУ = {"кц": "kc", "kc": "kc",
                              "meyer": "meyer", "мейер": "meyer"}

    def _gruppa_i_napravlenie(self, seg: str) -> tuple:
        """«Партия 935 — КЦ» -> ('Партия 935', 'kc'). Без суффикса -> (seg, '')."""
        s = str(seg or "")
        if self._РАЗДЕЛ_НАПРАВЛЕНИЯ not in s:
            return s, ""
        группа, хвост = s.rsplit(self._РАЗДЕЛ_НАПРАВЛЕНИЯ, 1)
        return группа.strip(), self._НАПРАВЛЕНИЕ_ПО_ХВОСТУ.get(
            хвост.strip().lower(), "")

    def _kandidaty_po_gruppe(self, seg: str, used: set, запас: int,
                             campaign_id=None) -> list:
        """Кандидаты по ГРУППЕ получателя, когда по колонке segment пусто.

        Зачем. Отбор кнопки «Сгенерировать в очередь» идёт запросом
        query_recipients({"segment": seg}) - то есть смотрит ТОЛЬКО на колонку
        segment. А группа получателя это segment ПЛЮС список
        extra_json.gruppy: одно поле segment одно-значное, и компания из
        новостной кампании, попавшая ещё и в отраслевую партию, иначе выпадала
        бы из новостной (для того список и заведён, см. recipient_groups).

        Замер 17.08: в группе «Партия 935» 920 получателей, а с
        segment == «Партия 935» - НОЛЬ. Все 920 лежат в extra_json.gruppy.
        Поэтому кнопка отвечала «нет получателей без письма в этом сегменте» и
        не генерировала ничего, сколько ни жми: остаток партии ей просто не
        виден. Серверный прогон брал их через recipient_groups и видел все 920.

        Запасной путь, а не замена: включается ТОЛЬКО когда обычный отбор дал
        пусто. Кампании, у которых segment проставлен, работают как работали.

        Стоп-лист отсекаем сами - в обычном пути это делал фильтр
        suppressed=False, и терять его нельзя: письмо отписавшемуся это и
        расход впустую, и жалоба.
        """
        if not seg:
            return []
        try:
            по_id = self._store.recipient_groups().get("по_id") or {}
        except Exception:  # noqa: BLE001 - нет индекса групп → без запасного пути
            return []
        группа, направление = self._gruppa_i_napravlenie(seg)
        # ОТБОР ПО НАПРАВЛЕНИЮ ОБЯЗАТЕЛЕН. Партия набрана ОДНОЙ группой на оба
        # направления («Партия 935», 920 человек), а кампаний под неё две:
        # 10 — КЦ, 11 — Meyer. Без этого фильтра кнопка на кампании 10 забрала
        # бы и мейеровские компании, и письмо про рентген-инспекцию легло бы в
        # компрессорную кампанию — ровно тот дефект, который чинили 17.08
        # («направление решает карточка»), только теперь на входе.
        out = []
        for rid, группы in sorted(по_id.items()):
            гр = группы or ()
            if seg not in гр and (not группа or группа not in гр):
                continue
            if rid in used:
                continue
            try:
                rec = self._store.get_recipient(rid)
            except Exception:  # noqa: BLE001
                continue
            if rec is None:
                continue
            почта = str(getattr(rec, "email", "") or "").strip().lower()
            if not почта:
                continue
            try:
                домен = почта.split("@")[-1] if "@" in почта else ""
                инн = "".join(c for c in str(getattr(rec, "inn", "") or "")
                              if c.isdigit())
                if self._store.suppression_lookup(
                        email=почта, domain=домен, inn=инн or None) is not None:
                    continue
            except Exception:  # noqa: BLE001 - сбой проверки не молчит про стоп-лист
                continue
            if направление:
                try:
                    карта = self._card_for(getattr(rec, "inn", None)) or {}
                    ecomp = (карта.get("enrich") or {}).get("company") or {}
                    свой = self._division_kartochki(ecomp, rec)
                except Exception:  # noqa: BLE001
                    свой = ""
                # Составное «kc+meyer» и пустое направление пропускаем: карточка
                # не решила, и отсекать по догадке нельзя — направление письма
                # доопределит target_division уже при генерации.
                if свой in ("kc", "meyer") and свой != направление:
                    continue
            out.append(rec)
            if len(out) >= запас:
                break
        return out

    def candidates(self, campaign_id: int, limit: int) -> list:
        """Получатели сегмента кампании без письма. Suppression отсекаем сразу:
        генерировать письмо отписавшемуся — расход API впустую.

        Порядок — по НАКАЛУ новостного повода (#70): дневная квота маленькая,
        и уходить она должна самым горячим лидам, а не первым по id. Сканируем
        кандидатов с запасом, сортируем по hotness из enrich.db, отдаём верх."""
        limit = max(0, int(limit))
        if limit == 0:
            return []
        seg = self._segment(campaign_id)
        used = self._already(campaign_id)
        out, offset = [], 0
        запас = limit * 10          # чтобы горячий лид из хвоста не потерялся
        while len(out) < запас and offset < SCAN_LIMIT:
            rows = self._store.query_recipients(
                {"segment": seg, "suppressed": False}, limit=_PAGE, offset=offset)
            if not rows:
                break
            offset += len(rows)
            for r in rows:
                if r.id in used:
                    continue
                out.append(r)
                if len(out) >= запас:
                    break
        if not out:
            out = self._kandidaty_po_gruppe(seg, used, запас,
                                            campaign_id=campaign_id)
        # Отсечка по ЦЕЛЕВЫМ ОКВЭД (владелец 27.07: «как сюда банк попал?
        # должно же быть отсечение по нашему списку оквэд»). Классификация
        # enrich (okved_v2/checko) пишет tgt/div в stage_log; при заливке
        # новостных лидов division в companies проставлялся дефолтом «kc»,
        # и банк ВТБ (64.19, tgt=0) доехал до генерации. Непроверенных
        # (нет стадии) НЕ режем — им письмо лучше, чем молчание, а аудит
        # ОКВЭД (#38) их доберёт.
        нецелевые = self._nontarget_inns([r.inn for r in out if r.inn])
        if нецелевые:
            out = [r for r in out if str(r.inn) not in нецелевые]
        # Гейт адресата по РОДУ ДЕЯТЕЛЬНОСТИ (06.08). Отсечка выше судит по
        # ОКВЭД, а он врёт молча: с кодом 25.61 «обработка металлов» в очередь
        # доехали разработчик мобильной ОС и контора независимой оценки, с
        # 25.92 — оператор спутниковой связи. Их видно только по строке
        # деятельности с их же сайта, и решают это две линзы (продавец и
        # скептик) — режем лишь при обоюдном «не покупатель».
        не_покупатели = self._not_buyers([r for r in out if r.inn])
        if не_покупатели:
            logger.info("target_gate: отсеяно %s адресатов (не покупатели)",
                        len(не_покупатели))
            out = [r for r in out if str(r.inn) not in не_покупатели]
        # Адреса, про которые сервер получателя уже сказал «такого ящика нет»
        # (проверка addr_probe). Письмо им не нужно: это оплаченная генерация
        # в никуда и отбивка следом. Все прочие вердикты пробы здесь не
        # участвуют — «не подтверждён» не повод не писать.
        мёртвые = self._dead_addresses([r.email for r in out if r.email])
        if мёртвые:
            logger.info("addr_probe: пропущено %s несуществующих адресов",
                        len(мёртвые))
            out = [r for r in out
                   if (r.email or "").strip().lower() not in мёртвые]
        if len(out) > limit:
            жар = self._hotness_map([r.inn for r in out if r.inn])
            out.sort(key=lambda r: -(жар.get(str(r.inn), 0)))
        return out[:limit]

    def _nontarget_inns(self, inns: list) -> set:
        """ИНН с провальной классификацией ОКВЭД: tgt=0 или div=- в последней
        стадии okved_v2/checko. Сбой/нет базы -> пустое множество (не режем)."""
        if not inns or not self._enrich_db or not os.path.exists(self._enrich_db):
            return set()
        try:
            con = sqlite3.connect(self._enrich_db, timeout=5)
            try:
                marks = ",".join("?" * len(inns))
                плохие = set()
                проверенные = set()
                for inn, detail in con.execute(
                        f"SELECT inn, detail FROM stage_log "
                        f"WHERE stage IN ('okved_v2','checko') "
                        f"AND inn IN ({marks}) ORDER BY ts",
                        [str(i) for i in inns]):
                    d = str(detail or "")
                    m = re.search(r"tgt=(\d+)", d)
                    дм = re.search(r"div=([\w+-]+)", d)
                    if m is None and дм is None:
                        continue
                    проверенные.add(str(inn))
                    # последняя стадия побеждает (ORDER BY ts): перезапись
                    if (m and int(m.group(1)) == 0) or (дм and дм.group(1) in ("-", "")):
                        плохие.add(str(inn))
                    else:
                        плохие.discard(str(inn))
                # БЕЗ стадии классификации (владелец 27.07: ПО-разработчик
                # КАРТАС с 62.01 дошёл до очереди) — режем по целевой карте,
                # но ТОЛЬКО явно непромышленных: карта покрывает не все
                # промышленные коды (добыча угля 05.20.11 в ней отсутствует,
                # а «ЭН+ УГОЛЬ» — живой клиент, владелец: «её скипать не
                # надо»). Правило: нет попадания в карту И основной ОКВЭД из
                # непромышленных разделов (ИТ/финансы/торговля/консалтинг/
                # госуправление/образование/услуги) -> нецелевая.
                непроверенные = ({str(i) for i in inns} - проверенные)
                if непроверенные:
                    try:
                        import enrich_db as _EDB
                        for inn2, ок, оа in con.execute(
                                f"SELECT inn, okved, okved_all FROM companies "
                                f"WHERE inn IN ({','.join('?' * len(непроверенные))})",
                                list(непроверенные)):
                            основной = str(ок or "").split()[0] if str(ок or "").strip() else ""
                            коды = " ".join(
                                ([основной] if основной else [])
                                + str(оа or "").split("|"))
                            if not коды.strip():
                                continue      # данных нет — не режем вслепую
                            d2, _b = _EDB.division_for_okveds(коды)
                            if d2:
                                continue
                            if _nonindustrial_okved(основной):
                                плохие.add(str(inn2))
                    except Exception:  # noqa: BLE001 - нет модуля/таблицы
                        pass
                return плохие
            finally:
                con.close()
        except sqlite3.Error:
            return set()

    def _hotness_map(self, inns: list) -> dict:
        """{инн: max(hotness)} одним запросом к enrich.db; сбой -> пустая карта
        (порядок просто останется прежним, генерация не падает)."""
        if not inns or not self._enrich_db or not os.path.exists(self._enrich_db):
            return {}
        try:
            con = sqlite3.connect(self._enrich_db, timeout=5)
            try:
                marks = ",".join("?" * len(inns))
                try:
                    # карантин тёзок не греет кандидата (см. _digest)
                    return {str(r[0]): int(r[1] or 0) for r in con.execute(
                        f"SELECT inn, MAX(COALESCE(hotness,0)) FROM signals "
                        f"WHERE inn IN ({marks}) AND COALESCE(suspect,0)=0 "
                        f"GROUP BY inn", [str(i) for i in inns])}
                except sqlite3.OperationalError:
                    return {str(r[0]): int(r[1] or 0) for r in con.execute(
                        f"SELECT inn, MAX(COALESCE(hotness,0)) FROM signals "
                        f"WHERE inn IN ({marks}) GROUP BY inn",
                        [str(i) for i in inns])}
            finally:
                con.close()
        except sqlite3.Error:
            return {}

    def candidates_left(self, campaign_id: int) -> int:
        """Оценка «сколько ещё есть кому писать» для карточки. Именно оценка:
        считаем двумя дешёвыми запросами, без постраничного скана базы, так
        что письма получателям вне сегмента вычитаются тоже."""
        seg = self._segment(campaign_id)
        total = self._store.count_recipients({"segment": seg, "suppressed": False})
        return max(0, int(total.get("total", 0)) - len(self._already(campaign_id)))

    # ------------------------------------------------------------- обогащение --

    # Организационно-правовые формы из сверки имени выкидываем: «ООО» есть в
    # каждой второй новости и подтверждает ровно ничего. Зеркало _ORG_STOPWORDS
    # в infopanel — там та же сверка показывается оператору флагом
    # «НЕТ имени — проверь».
    _ОПФ = frozenset({"ооо", "ао", "пао", "зао", "оао", "ип", "нко"})

    @classmethod
    def _novost_pro_etu_kompaniyu(cls, текст: str, имя: str) -> bool:
        """Встречается ли имя компании в тексте новости.

        Панель считает это с 27.07 и честно показывает оператору жёлтым
        «НЕТ имени — проверь», а генерация ту же проверку не делала —
        и строила письмо на чужой новости. Замер 12.08: 26 писем очереди
        из 49 сославшихся на новость стояли на неподтверждённой, 18 из них
        приехали из ВКонтакте. Хуже того, столкнувшись с явно чужим поводом
        (омскому свинокомплексу — завод полиформальдегида в Кирово-Чепецке),
        модель не отказывалась от него, а СОЧИНЯЛА новость под профиль
        компании: «прочитал новость о расширении производства комбикормов».
        Такого события не было — письмо врало получателю.

        Сверяем по ОСНОВАМ, а не по целым словам: русский склоняется, и
        «Кирово-Чепецкий» в новости стоит как «Кирово-Чепецком». Точное
        сравнение резало бы законные поводы наравне с чужими.
        """
        слова = [w for w in re.findall(r"[А-Яа-яЁёA-Za-z0-9\-]{3,}",
                                       str(имя or ""))
                 if w.lower() not in cls._ОПФ]
        if not слова:
            return False
        т = str(текст or "").lower()
        for w in слова:
            w = w.lower()
            # У длинного слова отбрасываем окончание, короткое ищем целиком:
            # основа короче четырёх букв даёт случайные совпадения.
            основа = w[:-2] if len(w) >= 6 else w
            if len(основа) >= 4 and основа in т:
                return True
        return False

    def _digest(self, inn, company_name: str = "") -> dict:
        """Выжимка новостного сигнала из enrich.db — то же, что делает
        ai_gen_quota.py: без неё письмо скатывается в GENERIC-режим.

        company_name задан — берём только новости, где это имя есть в тексте.
        Пустое имя означает «сверить нечем»: тогда прежнее поведение, иначе
        мы молча выключили бы новостной режим всей базе."""
        if not self._enrich_db or not inn or not os.path.exists(self._enrich_db):
            return {}
        try:
            con = sqlite3.connect(self._enrich_db, timeout=5)
            con.row_factory = sqlite3.Row
            try:
                # При равном накале берём САМЫЙ СОДЕРЖАТЕЛЬНЫЙ сигнал, а не
                # случайный первый: у компании часто 2-3 сигнала об одном
                # событии, и короткий («модернизация производства») вытеснял
                # развёрнутый («техническое обновление заводов по производству
                # компонентов для пассажирских вагонов») — задача #61.
                # suspect=1 — карантин новостей-тёзок (27.07): на них нельзя
                # строить заход письма. В базе без колонки suspect откатываемся
                # на старый запрос (OperationalError — не sqlite3.Error ветки
                # ниже, ловим отдельно).
                try:
                    rows = con.execute(
                        "SELECT event_type, what, sum, source_url, "
                        "COALESCE(inn_conf,'') AS inn_conf FROM signals "
                        "WHERE inn=? AND COALESCE(suspect,0)=0 "
                        "ORDER BY COALESCE(hotness,0) DESC, "
                        "LENGTH(COALESCE(what,'')) DESC LIMIT 5",
                        (str(inn),)).fetchall()
                except sqlite3.OperationalError:
                    rows = con.execute(
                        "SELECT event_type, what, sum, source_url, '' AS inn_conf "
                        "FROM signals WHERE inn=? ORDER BY COALESCE(hotness,0) DESC, "
                        "LENGTH(COALESCE(what,'')) DESC LIMIT 5",
                        (str(inn),)).fetchall()
                # Вычитка 27.07 («наём в компрессорную» от вакансий кладовщиков
                # и охраны труда): вакансия — повод только когда она про
                # профильную технику. Непрофильную вакансию пропускаем, берём
                # следующий по накалу сигнал.
                row = None
                for кандидат in rows:
                    т = f"{кандидат['event_type'] or ''} {кандидат['what'] or ''}".lower()
                    if any(в in т for в in ('ваканси', 'наём', 'найм', 'ищет '
                                            'сотрудник', 'требуется')):
                        if not re.search(r'компрессор|пневм|кип\b|киповец|азот|'
                                         r'кислород|осушител|рентген|сепарат|'
                                         r'слесар|механик|энергетик', т):
                            continue
                    # Новость должна быть ПРО ЭТУ компанию. Доказательств два,
                    # достаточно любого: имя встречается в тексте или ссылке,
                    # либо матчинг сам отметил привязку надёжной (inn_conf).
                    # Одной сверки имени мало: в короткой выжимке «what» имя
                    # часто не повторяется («ЭКОЛАНТ» → «электросталеплавильный
                    # комплекс»), и жёсткое правило выбросило бы 52% поводов
                    # вместе с правдой. Замер 12.08: у ложных поводов
                    # (полиформальдегид у омского свинокомплекса, фабрика
                    # мороженого из видео ВК) inn_conf пуст, у верных — 'high'.
                    if company_name:
                        сверка = " ".join(str(кандидат[k] or "") for k in
                                          ("what", "sum", "source_url"))
                        надёжен = str(кандидат["inn_conf"] or "").lower() == "high" \
                            if "inn_conf" in кандидат.keys() else False
                        if not надёжен and not self._novost_pro_etu_kompaniyu(
                                сверка, company_name):
                            continue
                    row = кандидат
                    break
                if row is None and rows:
                    row = None    # только непрофильные вакансии -> повода нет
            finally:
                con.close()
        except sqlite3.Error:
            return {}
        if not row:
            return {}
        what = (row["what"] or "").strip()
        etype = (row["event_type"] or "").strip()
        summ = (row["sum"] or "").strip()
        rd = " - ".join(x for x in (etype, what) if x) + (f" ({summ})" if summ else "")
        return {"news_detail": what, "news_type": etype, "news_sum": summ,
                "news_url": row["source_url"], "digest": rd}

    def _izbytochnyy_zahod(self, campaign_id, доля: float = 0.34,
                           смотреть: int = 200) -> str:
        """Форма захода, которой в кампании УЖЕ перебрали квоту. '' — если нет.

        Зачем. Антиштамп (ai_letter.zahod_overflow) считает квоту по списку,
        поданному в ОДИН вызов generate(). Между вызовами память теряется: в
        панели пачка по 4 письма, и каждая начинается с чистого счётчика, а
        серверный прогон партии подаёт вообще по одному письму - там квота не
        срабатывает НИКОГДА (при списке из одного предел равен единице, а
        счётчик формы - тоже единице, «больше предела» не наступает).

        Замер 17.08 по GENERIC-письмам:

          кампания 9 «Богатые карточки»  верхняя форма 26%  (квота цела)
          кампания 10 «Партия 935 — КЦ»  верхняя форма 87%  (квота мертва)

        87% партии заходят одним и тем же - это подпись рассылки, её видно
        глазами и её видят фильтры.

        Поэтому даём квоте память: смотрим заходы уже сделанных писем
        кампании и, если верхняя форма перебрала долю, возвращаем её. Дальше
        она уезжает в extra['сменить_заход'] - поле, которое УЖЕ понимают и
        промпт перегенерации, и гейт. Новых механизмов не заводим.

        Читает очередь на чтение, сбой чтения возвращает '' - подсказка не
        обязана работать, генерация из-за неё падать не смеет.
        """
        if not campaign_id or _ai_letter is None:
            return ""
        try:
            строки = self._store.confirm_list(campaign_id=int(campaign_id),
                                              limit=int(смотреть)) or []
        except Exception:  # noqa: BLE001 - очередь недоступна → без подсказки
            return ""
        счёт: dict = {}
        всего = 0
        for row in строки:
            тело = (row.get("edited_body") or row.get("body") or "")
            if not тело:
                continue
            ф = _ai_letter.форма_захода(тело)
            if not ф:
                continue
            всего += 1
            счёт[ф] = счёт.get(ф, 0) + 1
        if всего < 3:            # на двух письмах доля ничего не значит
            return ""
        # Обязательные заходы (у Meyer канон ТРЕБУЕТ «Меня зовут …») из счёта
        # выкидываем: подсказать «начни иначе» там значит потребовать
        # невозможного, и письмо не пройдёт ни одной попыткой.
        обяз = getattr(_ai_letter, "ЗАХОДЫ_ОБЯЗАТЕЛЬНЫЕ", frozenset())
        счёт = {ф: n for ф, n in счёт.items() if ф not in обяз}
        if not счёт:
            return ""
        форма, n = max(счёт.items(), key=lambda p: p[1])
        return форма if n > всего * доля else ""

    @staticmethod
    def _division_kartochki(ecomp: dict, r) -> str:
        """Направление ТАК, КАК ЕГО ПОКАЗЫВАЕТ КАРТОЧКА оператору.

        Повторяет infopanel._company_block дословно: сперва поле division
        компании из обогащения, при пустом - расчёт по ОКВЭД. Держать это
        одной функцией обязательно: две копии правила разъезжаются молча, и
        оператор снова увидит карточку про одно, а письмо про другое.

        Возвращает 'kc' | 'meyer' | 'kc+meyer' | '' — решает только первые два.
        """
        division = str((ecomp or {}).get("division") or "").strip()
        okved = str((ecomp or {}).get("okved") or getattr(r, "okved", "") or "")
        if not division and okved:
            try:
                import enrich_db as EDB
                division = str(EDB.division_for_okveds(okved)[0] or "")
            except Exception:  # noqa: BLE001 - нет базы (тесты) → карточка молчит
                division = ""
        return division

    def _request(self, r) -> dict:
        extra = dict(r.extra) if isinstance(r.extra, dict) else {}
        dg = self._digest(r.inn, str(getattr(r, "company_name", "") or ""))
        for k in ("news_detail", "news_type", "news_sum", "news_url"):
            if dg.get(k) and not extra.get(k):
                extra[k] = dg[k]
        if not extra.get("news_object") and dg.get("news_detail"):
            extra["news_object"] = dg["news_detail"]
        # Re-enrich 28.07: сигналы пересобраны по полному тексту статьи, и
        # СВЕЖИЙ дайджест из enrich.db может быть сильно жирнее устаревшего
        # news_object, вшитого в extra при создании кампании (огрызки «модер-
        # низация производства» со старых заголовков). Жирный побеждает —
        # иначе перегенерация письма остаётся на огрызке. Вместе с текстом
        # переезжает и ссылка (news_url), чтобы текст и источник совпадали.
        if dg.get("news_detail") and len(str(dg["news_detail"])) > len(
                str(extra.get("news_object") or "")):
            extra["news_object"] = dg["news_detail"]
            extra["news_detail"] = dg["news_detail"]
            if dg.get("news_url"):
                extra["news_url"] = dg["news_url"]
        # ЧТО КОМПАНИИ МОЖЕТ ПРИГОДИТЬСЯ. В промпте генерации есть слот
        # «Оборудование по профилю» (_equipment_hint), но заполняется он из
        # extra['equipment'], а сюда это поле никто не клал — слот был пуст
        # ВСЕГДА, и письмо не могло сказать, что именно нужно предприятию.
        # Берём «Все категории оборудования» по ОКВЭД из базы обзвона и род
        # деятельности из обогащения — то же, чем обосновывается направление.
        card = self._card_for(r.inn)
        activity = ""
        if card:
            ob = card.get("obzvon") or {}
            ecomp = (card.get("enrich") or {}).get("company") or {}
            if not extra.get("equipment"):
                eq = ob.get("equip_categories") or ob.get("equip_by_okved") or ""
                if not eq:
                    # вне базы обзвона — канонический текст по основному ОКВЭД
                    # из самой базы (единый формат, решение владельца 27.07)
                    try:
                        cards = self._cards()
                        if cards is not None and getattr(cards, "active", False):
                            eq = cards.equip_for_okved(
                                ecomp.get("okved") or r.okved or "")
                    except Exception:  # noqa: BLE001
                        eq = ""
                if eq:
                    extra["equipment"] = eq
            activity = ecomp.get("activity") or ""
            # ПАСПОРТ С САЙТА (13.08). Одной строки activity мало: когда её
            # нет, модель пересказывает НАЗВАНИЕ ОКВЭД как продукцию — так
            # завод конфет-суфле получил «какао-порошок» (это текст кода
            # 10.82). Обходчик складывает в enrich.db/site_facts перечень
            # продукции, упаковку, сырьё, мощности и контроль качества —
            # словами самого сайта и с источником. Такие факты письмо вправе
            # утверждать, потому что их можно проверить.
            паспорт = self._site_facts(r.inn)
            if паспорт:
                extra["site_facts"] = паспорт
            # Чем доказана принадлежность сайта компании: от этого зависит,
            # можно ли вообще опираться в письме на данные с сайта.
            if not extra.get("verified") and ecomp.get("verified"):
                extra["verified"] = ecomp["verified"]
            # §7а: РОЛЬ адресата — от неё зависит угол письма. Роли ставит
            # разбор сайта; ищем ящик получателя среди контактов компании.
            if not extra.get("role"):
                email_l = (r.email or "").strip().lower()
                for c in (card.get("contacts") or {}).get("emails") or []:
                    if (c.get("email") or "").strip().lower() == email_l:
                        if c.get("role"):
                            extra["role"] = c["role"]
                        # АДРЕС САМ ПОДТВЕРЖДАЕТ ИМЯ. Признак imya_ok из
                        # enrich.db/emails: имя согласуется с написанием
                        # ящика (a.demchenko@momez.ru ↔ А. Демченко). С
                        # 17.08 это самостоятельная улика надёжности имени
                        # наравне со ссылкой на страницу сотрудников — без
                        # неё именных приветствий не было почти нигде
                        # (в партии 935 имя известно у 96 писем и
                        # использовано ноль раз).
                        if c.get("imya_ok"):
                            extra["imya_ok"] = True
                        break
            # §7б: размер бизнеса по выручке из отчётности (база обзвона)
            if not extra.get("revenue"):
                fin = card.get("fin") or {}
                rev = fin.get("revenue") or fin.get("vyruchka") or ""
                if rev:
                    extra["revenue"] = rev
            # ГОРОД. Порядок по решению владельца: СНАЧАЛА из новости, потом
            # из базы. Логика простая — заход строится на событии, и место
            # события («завод в Саратове») бьёт юр-адрес головной компании,
            # который может быть в другом регионе. Промпт в NEWS-режиме прямо
            # просит склонять город, а раньше строка приходила как «город: None»:
            # заход вырождался в безличное «вы развиваетесь», что гейт
            # справедливо считает псевдо-новостью.
            if not extra.get("city"):
                город = _city_from_news(
                    " ".join(str(extra.get(k) or "") for k in
                             ("news_object", "news_detail")),
                    str(extra.get("news_url") or ""))
                источник = "новость"
                if not город:
                    город = (ob.get("city") or ecomp.get("region")
                             or ob.get("region") or "")
                    источник = "карточка"
                if not город and ob.get("address"):
                    # адрес «423827, Татарстан, Набережные Челны, пр-т ...»
                    части = [c.strip() for c in str(ob["address"]).split(",")]
                    город = части[2] if len(части) > 2 else ""
                    источник = "карточка"
                if город:
                    extra["city"] = город
                    # вычитка 27.07: юрадрес вместо места события — самый
                    # массовый источник ложной географии; промпт (§16) при
                    # «карточке» запрещает привязывать событие к городу
                    extra["city_source"] = источник

        # МЕТКА НАПРАВЛЕНИЯ. Без неё target_division не может применить правило
        # base_label и падает на профиль — а профиль врёт ровно там, где метка
        # и нужна: «ТОКК Металлпак» (жестяная банка, метка kc, партия
        # металлообработки) получил письмо про рентген-инспекцию, потому что в
        # его категориях лежат И компрессоры, И фотосепараторы (правило
        # «по потребностям» молчит при двух), а в описании стоит «консервная
        # промышленность» — пищевой маркер Meyer. Метку кладём из базы обзвона,
        # запасной вариант — сегмент получателя. Приоритет она не ломает:
        # новостной повод и однозначная потребность по-прежнему выше.
        метка = ""
        if card:
            метка = str((card.get("obzvon") or {}).get("division") or "")
        # ПАРТИЯ РЕШАЕТ. Метки мало: правило «однозначная потребность» стоит
        # выше неё, и компания с одними фотосепараторами в категориях всё
        # равно получит письмо Meyer, хотя владелец заливал её в компрессорную
        # партию. Поэтому у отраслевых партий направление задаётся явно —
        # это и есть смысл слова «партия»: оператор уже решил, о чём пишем.
        # Карта редактируется настройкой segment_division, без правки кода.
        сегмент = str(getattr(r, "segment", "") or "").strip()
        явное = self._segment_division().get(сегмент.lower())
        # ДВЕ ОЧЕРЕДИ MEYER. У направления два разных станка, и по коду ОКВЭД
        # они часто оба уместны. Владелец 11.08 просил развести их по отдельным
        # очередям — значит станок задаёт НАЗВАНИЕ ПАРТИИ, а не догадка по коду.
        # Кладём градацию в extra: направление остаётся meyer (факты, правила и
        # шапка промпта у него общие), а боль и запрет на второй станок берутся
        # из градации.
        if not extra.get("meyer_gradaciya") and сегмент and _ai_letter:
            гр = _ai_letter.градация_из_текста(сегмент)
            if гр and str(явное or "").startswith("meyer"):
                extra["meyer_gradaciya"] = гр

        # НАПРАВЛЕНИЕ РЕШАЕТ КАРТОЧКА (владелец, 17.08: «если в карточке
        # написано направление, то и письмо должно быть под это направление»).
        #
        # Что было не так. Направление считали ДВА независимых пути из РАЗНЫХ
        # источников. Письмо: target_division() по цепочке новость → потребности
        # → метка базы обзвона → профиль → запасной «kc». Карточка:
        # infopanel._company_block берёт enrich.company.division, а если пусто -
        # расчёт по ОКВЭД. Совпадать они не обязаны и не совпадали: замер 17.08
        # на 18 письмах дал 4 расхождения (22%), во всех карточка говорила
        # meyer и «сортировка и инспекция», а письмо ушло про компрессоры в
        # кампанию КЦ. Стоп-флаг панели при этом молчал: он сверяет ЯЩИК с
        # письмом, а не письмо с карточкой.
        #
        # Оператор принимает решение по карточке - значит письмо обязано быть
        # про то, что в карточке написано, иначе он подтверждает одно, а уходит
        # другое.
        #
        # Считаем ТЕМ ЖЕ способом, что и карточка, иначе разъедется снова.
        # Составное «kc+meyer» ничего не решает - там продолжает работать
        # обычная цепочка приоритетов. Партия (segment_division) остаётся выше:
        # это осознанное решение оператора «о чём пишем», и карточка его не
        # отменяет.
        if not явное:
            карточное = self._division_kartochki(ecomp if card else {}, r)
            if карточное in ("kc", "meyer"):
                явное = карточное
        return {"company_name": r.company_name, "okved": r.okved,
                "activity": activity,
                "target_division": явное or None,
                "division": метка or None,
                "segment": сегмент or None,
                "contact_name": r.contact_name, "mode": "auto", "extra": extra,
                "_digest": dg.get("digest", ""), "_url": dg.get("news_url", "")}

    # -- перегенерация одного письма очереди (#71) --------------------------- #

    def regenerate_review(self, review_id: int) -> dict:
        """Перегенерировать ОДНО pending-письмо очереди под текущие правила:
        свежий запрос (_request: новость/город/роль/боль/идея), новый текст и
        новая панель ложатся в ту же строку. Возвращает исход для UI."""
        row = self._store.confirm_get(int(review_id))
        if not row or row.get("status") != "pending":
            return {"ok": False, "reason": "письмо не в очереди (не pending)"}
        if (row.get("kind") or "outbound") == "reply":
            return {"ok": False, "reason": "черновики ответов не перегенерируем"}
        r = self._store.get_recipient(row.get("recipient_id"))
        if r is None:
            return {"ok": False, "reason": "получатель не найден"}
        req = self._request(r)
        # Ротация заходов считается от места письма в партии, а здесь партия из
        # одного: без сдвига каждое перегенерированное письмо получало бы одну
        # и ту же первую механику — мы бы просто поменяли один штамп на другой.
        # Номер письма очереди даёт устойчивый разброс.
        req.setdefault("extra", {})["angle_shift"] = int(review_id)
        self._add_ideas_generic([req])
        gen = self._gen_factory()
        res = gen.generate([req])
        L = res.ok.get(0)
        if not L:
            причины = [str(x)[:120] for x in (res.rejected.get(0) or [])][:4]
            return {"ok": False, "reason": "генерация забракована",
                    "fails": причины}
        panel = self._panel(r, L, self.today(), req)
        # Ревью #48: панель собирается заново, но выбор ЯЩИКА оператором живёт
        # именно в panel.mailbox_id (ConfirmSend.set_mailbox) — перегенерация
        # текста не должна молча сбрасывать решение человека об отправителе.
        old_panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
        if (old_panel or {}).get("mailbox_id") and not panel.get("mailbox_id"):
            panel["mailbox_id"] = old_panel["mailbox_id"]
        done = self._store.confirm_update_letter(
            int(review_id), subject=L["subject"], body=L["body"], panel=panel)
        return {"ok": bool(done), "subject": L["subject"]}

    # -- линзы-идеи для GENERIC (#68, решение владельца 26.07) --------------- #

    # ЛИНЗЫ ПО НАПРАВЛЕНИЮ. Первая редакция знала только компрессоры, и письма
    # Meyer получали идею «аудит пневматических систем в цехе» — кофейному
    # производству про сжатый воздух (замер 14.08, карточки #1049 и #1054).
    # Идея едет в промпт как «на что опереться», так что мимо направления она
    # не безобидна: модель тянется к ней и уводит письмо в чужой станок.
    _IDEA_LENSES_KC = {
        'снабженец': ('Ты снабженец завода. Холодные письма удаляешь пачками. '
                      'Какие 2 захода письма от поставщика компрессорного '
                      'оборудования заставили бы тебя ОТВЕТИТЬ?'),
        'инженер': ('Ты главный инженер производства. Какие 2 захода письма '
                    'про сжатый воздух/азот зацепили бы тебя как технаря — '
                    'без рекламы, по делу?'),
        'скептик': ('Ты циничный получатель холодных писем. Придумай 2 захода, '
                    'которые НЕ выглядят как рассылка и вызывают желание '
                    'ответить одной строкой.'),
    }
    _IDEA_LENSES_MEYER = {
        'технолог': ('Ты технолог пищевого производства. Какие 2 захода письма '
                     'про контроль качества продукции — рентген-инспекцию '
                     'упаковки или оптическую сортировку сырья — заставили бы '
                     'тебя ОТВЕТИТЬ?'),
        'качество': ('Ты руководитель службы качества на пищевом предприятии, '
                     'у тебя ХАССП и аудиты сетей. Какие 2 захода письма про '
                     'выявление посторонних включений зацепили бы тебя по '
                     'делу, без страшилок и без рекламы?'),
        'скептик': ('Ты циничный получатель холодных писем. Придумай 2 захода, '
                    'которые НЕ выглядят как рассылка и вызывают желание '
                    'ответить одной строкой.'),
    }
    _IDEA_LENSES = {
        'снабженец': ('Ты снабженец завода. Холодные письма удаляешь пачками. '
                      'Какие 2 захода письма от поставщика компрессорного '
                      'оборудования заставили бы тебя ОТВЕТИТЬ?'),
        'инженер': ('Ты главный инженер производства. Какие 2 захода письма '
                    'про сжатый воздух/азот зацепили бы тебя как технаря — '
                    'без рекламы, по делу?'),
        'скептик': ('Ты циничный получатель холодных писем. Придумай 2 захода, '
                    'которые НЕ выглядят как рассылка и вызывают желание '
                    'ответить одной строкой.'),
    }

    def _add_ideas_generic(self, reqs: list) -> None:
        """Идея захода для писем БЕЗ новостного крючка (режим GENERIC).

        A/B на эталоне (idea-lenses-ab.json): на гейт не влияет, но письма
        заметно конкретнее. У NEWS-писем крючок уже есть — им идея не нужна.
        Три дешёвые линзы (haiku) предлагают по 2 идеи, судья (боевой caller)
        выбирает одну; она уходит в extra['idea'] и печатается в блоке
        получателя. Любой сбой — письмо просто идёт без идеи."""
        # Ревью #48: без конфига (юнит-тесты, песочница) в провайдера НЕ ходим.
        # Раньше AiQuota(config=None) считал тумблер включённым, и pytest на
        # каждом GENERIC-письме жёг реальные вызовы haiku (~45 с/письмо и
        # деньги владельца). Боевая сборка (build_ai_quota) конфиг передаёт
        # всегда — там дефолт «включено» сохраняется.
        if self._config is None:
            return
        if not bool(self._config.get("ai_quota.idea_lenses_generic", True)
                    if hasattr(self._config, "get") else True):
            return
        generic = [r for r in reqs
                   if not ((r.get("extra") or {}).get("news_object")
                           and (r.get("extra") or {}).get("city"))]
        if not generic:
            return
        try:
            from sender.review_lenses import default_caller
            import gen_provider as GP
        except Exception:  # noqa: BLE001 - нет провайдера (тесты) → без идей
            return
        for r in generic:
            ctx = (f"Компания: {r.get('company_name')}. ОКВЭД: {r.get('okved')}."
                   f" Деятельность: {r.get('activity') or 'неизвестна'}.")
            # Направление берём из того же, чем его определяет генерация:
            # партия (target_division) главнее метки базы обзвона, а признак
            # градации Meyer в extra ставится только для Meyer-очередей.
            _нап = str(r.get("target_division") or r.get("division") or "")
            if not _нап.startswith("meyer") and (r.get("extra") or {}).get(
                    "meyer_gradaciya"):
                _нап = "meyer"
            линзы = (self._IDEA_LENSES_MEYER if _нап.startswith("meyer")
                     else self._IDEA_LENSES_KC)
            варианты = []
            for имя, линза in линзы.items():
                try:
                    msg = GP.call(None, [{"role": "user", "content":
                                          f"{линза}\n\n{ctx}\n\nОтветь 2 "
                                          "строками, по одной идее на строку, "
                                          "без нумерации."}],
                                  model="claude-haiku-4-5", attempts=2)
                    текст = "".join(b.text for b in msg.content
                                    if b.type == "text")
                    варианты += [f"[{имя}] {s.strip()}"
                                 for s in текст.splitlines() if s.strip()][:2]
                except Exception:  # noqa: BLE001
                    continue
            if not варианты:
                continue
            try:
                суд, _ = default_caller(
                    "Выбери ОДНУ лучшую идею захода холодного письма для этой "
                    f"компании.\n{ctx}\n\nИдеи:\n"
                    + "\n".join(f"{i+1}. {v}" for i, v in enumerate(варианты))
                    + "\n\nОтветь только текстом выбранной идеи, без номера.")
                r.setdefault("extra", {})["idea"] = суд.strip()[:300]
            except Exception:  # noqa: BLE001
                r.setdefault("extra", {})["idea"] = варианты[0][:300]

    # Партия -> направление письма. Отраслевые партии заливает оператор, и он
    # уже решил, о чём пишем: «металлообработка» это компрессорная партия, и
    # письмо про рентген-инспекцию там ошибка независимо от того, что лежит в
    # категориях компании. Новостные партии сюда НЕ входят: там направление
    # обязан выбирать повод.
    # «мейер-фото» и «мейер-рентген» — две очереди одного направления (владелец
    # 11.08). Направление у обеих meyer; какой из двух станков — в extra по
    # названию сегмента, см. _request.
    _SEGMENT_DIVISION_DEF = {"металлообработка": "kc", "кц": "kc",
                             "meyer": "meyer", "мейер": "meyer",
                             "мейер-фото": "meyer", "мейер-рентген": "meyer"}

    def _segment_division(self) -> dict:
        """Карта «сегмент -> направление» (настройка segment_division)."""
        карта = dict(self._SEGMENT_DIVISION_DEF)
        try:
            своё = self._store.get_setting("segment_division", None)
        except Exception:  # noqa: BLE001
            своё = None
        if isinstance(своё, dict):
            for k, v in своё.items():
                ключ = str(k or "").strip().lower()
                значение = str(v or "").strip().lower()
                if ключ and значение in ("kc", "meyer"):
                    карта[ключ] = значение
                elif ключ and not значение:
                    карта.pop(ключ, None)      # пустое значение = снять правило
        return карта

    def _dead_addresses(self, emails: list) -> set:
        """Адреса, которых точно нет: вердикт пробы «нет ящика».

        Читаем кэш addr_probe напрямую — модуль пробы сюда не тянем, генерации
        не нужна ни сеть, ни её настройки. Нет таблицы (проба не включалась) —
        пустое множество, никого не режем.
        """
        коды = [str(e or "").strip().lower() for e in emails if e]
        if not коды:
            return set()
        try:
            con = sqlite3.connect(self._db_path, timeout=10)
            try:
                out = set()
                for i in range(0, len(коды), 400):
                    часть = коды[i:i + 400]
                    q = ",".join("?" * len(часть))
                    out |= {r[0] for r in con.execute(
                        f"SELECT email FROM addr_probe WHERE verdict='нет ящика'"
                        f" AND email IN ({q})", часть)}
                return out
            finally:
                con.close()
        except Exception:  # noqa: BLE001 - нет таблицы/базы -> не фильтруем
            return set()

    def _gate(self):
        """Гейт адресата (ленивая сборка, один на процесс)."""
        g = getattr(self, "_target_gate", None)
        if g is None:
            try:
                from sender.target_gate import build_target_gate
                g = build_target_gate(self._db_path, self._config)
            except Exception:  # noqa: BLE001 - гейт не обязан существовать
                logger.exception("target_gate: не собрался")
                g = False
            self._target_gate = g
        return g or None

    def _not_buyers(self, recipients: list) -> set:
        """ИНН получателей, которым писать не надо: обе торговые линзы против.

        Род деятельности берём из той же карточки, что и генератор писем
        (enrich.company.activity — строка с сайта компании). Нет карточки или
        нет строки — компанию не судим и НЕ режем.
        """
        гейт = self._gate()
        if гейт is None or not recipients:
            return set()
        компании = []
        for r in recipients:
            карточка = self._card_for(r.inn) or {}
            ec = (карточка.get("enrich") or {}).get("company") or {}
            компании.append({
                "inn": str(r.inn),
                "name": getattr(r, "company_name", "") or ec.get("name") or "",
                "okved": getattr(r, "okved", "") or ec.get("okved") or "",
                "activity": ec.get("activity") or "",
            })
        try:
            return гейт.not_buyers(компании, source="ai_quota")
        except Exception:  # noqa: BLE001 - сбой гейта не должен рвать генерацию
            logger.exception("target_gate: суд не состоялся")
            return set()

    def _card_for(self, inn):
        """Карточка компании из базы обзвона (с кэшем внутри CompanyCards)."""
        if not inn:
            return None
        try:
            cards = self._cards()
            if cards is not None and getattr(cards, "active", False):
                return cards.card(inn)
        except Exception:  # noqa: BLE001
            logger.exception("карточка обзвона не собралась (%s)", inn)
        return None

    def _site_facts(self, inn) -> dict:
        """Паспорт предприятия с его сайта (enrich.db/site_facts) или {}.

        Таблицы может не быть вовсе (старый снапшот) — тогда пусто: генерация
        обязана работать и без паспорта, он делает письмо точнее, но не
        является условием отправки.
        """
        if not inn or not self._enrich_db or not os.path.exists(self._enrich_db):
            return {}
        try:
            con = sqlite3.connect(f"file:{self._enrich_db}?mode=ro", uri=True,
                                  timeout=5)
            try:
                row = con.execute(
                    "SELECT facts_json, sources_json FROM site_facts WHERE inn=?",
                    (str(inn).strip(),)).fetchone()
            finally:
                con.close()
        except Exception:  # noqa: BLE001 - нет таблицы/файла: работаем без него
            return {}
        if not row or not (row[0] or "").strip():
            return {}
        try:
            факты = json.loads(row[0])
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(факты, dict):
            return {}
        try:
            факты["источники"] = json.loads(row[1] or "[]")
        except Exception:  # noqa: BLE001
            факты["источники"] = []
        return факты

    # ----------------------------------------------------------------- прогон --

    def run_today(self, campaign_id: int, *, today: Optional[str] = None,
                  quota: Optional[int] = None,
                  progress_cb: Optional[Callable[[int, int], None]] = None) -> RunResult:
        """Догенерировать до дневной квоты. Без квоты на день — ничего не делаем.

        progress_cb(ok, brak) — пульс после каждого батча: фоновый прогон
        (#71) пишет его в состояние, и UI видит живой прогресс вместо ложного
        «оборван» на длинной генерации (200 писем — это часы)."""
        campaign_id = int(campaign_id)
        day = today or self.today()
        res = RunResult(campaign_id=campaign_id, date=day)
        sched = self.schedule(campaign_id)
        res.quota = int(quota) if quota is not None else int(sched.get(day, 0))
        if res.quota <= 0:
            res.reason = "квота на этот день не задана"
            return res
        ok, brak = self.counters(campaign_id, [day]).get(day, (0, 0))
        res.before = ok + brak
        remaining = max(0, res.quota - res.before)
        if remaining <= 0:
            res.reason = "дневная квота уже выбрана"
            return res
        todo = self.candidates(campaign_id, remaining)
        res.candidates = len(todo)
        if not todo:
            res.reason = "нет получателей без письма в этом сегменте"
            return res
        res.planned = len(todo)
        # ПАРАЛЛЕЛЬНО (решение владельца 27.07: «смысл ждать»): батчи уходят
        # провайдеру одновременно. Пишем в очередь под локом — SQLite один
        # писатель; свой генератор на поток, чтобы не делить состояние раундов.
        воркеров = 1
        try:
            воркеров = max(1, int(self._config.get("ai_quota.workers", 15) or 15))
        except Exception:  # noqa: BLE001 - конфиг без dotted get (тесты)
            воркеров = 15
        чанки = [todo[i:i + self._batch] for i in range(0, len(todo), self._batch)]
        замок = threading.Lock()

        # ПАМЯТЬ АНТИШТАМПА ПО КАМПАНИИ. Считаем ОДИН раз на прогон, а не на
        # каждый батч: лишние чтения очереди тут ни к чему, а доля за один
        # прогон существенно не сдвинется.
        _перебор = self._izbytochnyy_zahod(campaign_id)
        if _перебор:
            logger.info("антиштамп: заход «%s» перебран в кампании %s — "
                        "новым письмам велено зайти иначе", _перебор, campaign_id)

        def _батч(nчанк, chunk):
            reqs = [self._request(r) for r in chunk]
            # Форма, перебравшая квоту РАНЬШЕ этого прогона. Поле понимают и
            # промпт перегенерации, и гейт; своё значение, выставленное
            # квотой внутри батча, не трогаем — оно свежее.
            # ПОДСКАЗКУ ДАЁМ НЕ ВСЕМ, А ДВУМ ИЗ ТРЁХ. Первая редакция гнала
            # прочь от перебранной формы ВЕСЬ круг — и письма дружно уходили
            # на одну и ту же замену, а внутрибатчевая квота бракова ла уже
            # её. Замер 17.08, письмо #2039: сначала «заход «от профиля»
            # израсходован», следующей попыткой «заход «от площадки»
            # израсходован». Одна монокультура менялась на другую.
            #
            # Квота на партии 34%: чтобы форма с 87% опустилась к ней, менять
            # заход должны примерно две трети писем, а не все. Кому именно -
            # решает позиция в круге, без случайности: прогон должен
            # повторяться одинаково.
            if _перебор:
                for _i, req in enumerate(reqs):
                    if _i % 3 == 2:      # каждому третьему — как есть
                        continue
                    req.setdefault("extra", {}).setdefault(
                        "сменить_заход", _перебор)
            self._add_ideas_generic(reqs)
            try:
                out = self._gen_factory().generate(reqs)
            except Exception as e:  # noqa: BLE001 - батч упал, остальные едут
                with замок:
                    res.errors.append(f"батч {nчанк}: {str(e)[:120]}")
                return
            items = []
            for j, r in enumerate(chunk):
                letter = out.ok.get(j)
                if letter:
                    try:
                        with замок:
                            mid, _step_id, why = self._ensure_message(campaign_id, r.id)
                            if mid is not None:
                                self._store.confirm_submit(
                                    email=r.email, subject=letter["subject"],
                                    body=letter["body"], inn=r.inn,
                                    campaign_id=campaign_id, recipient_id=r.id,
                                    message_id=mid,
                                    panel=self._panel(r, letter, day, reqs[j]))
                        if mid is None:
                            with замок:
                                res.errors.append(f"{r.email}: {why}")
                            continue
                    except Exception as e:  # noqa: BLE001
                        with замок:
                            res.errors.append(
                                f"{r.email}: очередь отклонила ({str(e)[:80]})")
                        continue
                    with замок:
                        res.generated += 1
                    items.append({"email": r.email, "recipient_id": r.id,
                                  "status": "ok", "subject": letter["subject"],
                                  "body": letter["body"],
                                  "rounds": letter.get("rounds")})
                else:
                    with замок:
                        res.rejected += 1
                    rej = [str(x)[:120] for x in (out.rejected.get(j) or [])]
                    items.append({"email": r.email, "recipient_id": r.id,
                                  "status": статус_брака(rej),
                                  "subject": "", "body": "",
                                  "rounds": [{"rejected": rej}]})
            with замок:
                self._log(campaign_id, items, res)
                if progress_cb is not None:
                    try:
                        progress_cb(res.generated, res.rejected)
                    except Exception:  # noqa: BLE001 - пульс не роняет прогон
                        pass

        if воркеров <= 1 or len(чанки) <= 1:
            for n, ch in enumerate(чанки):
                _батч(n, ch)
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=воркеров) as пул:
                list(пул.map(lambda t: _батч(t[0], t[1]), enumerate(чанки)))
        return res


    def _cards(self):
        """Индекс базы обзвона (CompanyCards). Ленивый: файл 400 МБ, открываем
        один раз на процесс и только когда действительно нужен."""
        if getattr(self, "_cards_obj", None) is None:
            try:
                from sender.company_card import CompanyCards
                cfg = self._config
                get = getattr(cfg, "get", None)
                self._cards_obj = CompanyCards(
                    index_path=(str(get("obzvon.index_path", "") or "") or None)
                               if callable(get) else None,
                    enrich_db_path=(str(get("obzvon.enrich_db", "") or "") or None)
                                   if callable(get) else self._enrich_db)
            except Exception:  # noqa: BLE001
                logger.exception("индекс обзвона не открылся")
                self._cards_obj = False
        return self._cards_obj or None

    def _signature_preview(self, division: str = "kc") -> str:
        """Подпись ровно в том виде, в каком её допишет отправка.

        Берём тот же шаблон и тот же ИНН, что Sender._apply_signature
        (personalization.signature_template + legal.inn). Имя менеджера здесь
        неизвестно — ящик выбирается на отправке, поэтому подставляем плейсхолдер:
        оператору важно видеть, что письмо заканчивается юр-атрибуцией
        «ООО «Руспром», ИНН …», а не обрывается на «С уважением,».
        Настройки нет — пустая строка, панель просто не показывает подпись.

        division обязателен для {brand}: после появления бренда в шаблоне
        (28.07) format без brand кидал KeyError, превью молча становилось
        пустым, и комплаенс-блок показывал «атрибуции НЕТ» у КАЖДОЙ карточки
        (скрин владельца: «атрибуция же есть»)."""
        try:
            from sender.sender import Sender, brand_for_division
            cfg = self._config
            get = getattr(cfg, "get", None) if cfg is not None else None
            tmpl = (get("personalization.signature_template", None)
                    if callable(get) else None) or Sender._DEFAULT_SIGNATURE
            inn = ""
            legal_fn = getattr(cfg, "legal", None) if cfg is not None else None
            if callable(legal_fn):
                try:
                    inn = str(getattr(legal_fn(), "inn", "") or "")
                except Exception:  # noqa: BLE001
                    inn = ""
            return tmpl.format(name="менеджер (имя по ящику отправки)", inn=inn,
                               role="Менеджер по продажам",
                               brand=brand_for_division(cfg, division))
        except Exception:  # noqa: BLE001
            logger.exception("подпись для превью не собралась")
            return ""

    def _panel(self, r, letter: dict, day: str, req: dict) -> dict:
        """ПОЛНАЯ инфо-панель карточки подтверждения + ai-специфика сверху.

        Раньше здесь клался только ai-блок ({ai, quota_day, rounds, news_digest,
        news_url}), а сборщик infopanel.build_panel не вызывался вовсе — в
        отличие от обычной постановки в очередь (orchestrator._build_confirm_panel).
        Последствия были ровно два, и оба серьёзные:

        1. Оператор при подтверждении не видел НИЧЕГО для решения — ни ЛПР, ни
           направления, ни атрибуции по ФЗ-38, ни стоп-флагов. А подтверждает он
           живую отправку живому юрлицу.
        2. Экран «Подтвердить отправку» падал в белый экран: карточки читают
           panel.contact.lpr / panel.company.division / panel.legal.attribution_ok
           напрямую, а этих узлов не было. Воспроизведено в браузере на боевом
           бандле: TypeError «Cannot read properties of undefined (reading 'lpr')».

        Сбой сборки не должен ронять генерацию: письмо всё равно ложится в
        очередь, панель тогда остаётся ai-минимумом (фронт это переживает после
        парной правки Confirm.tsx)."""
        base = {"ai": True, "quota_day": day,
                "rounds": len(letter.get("rounds") or []),
                # Направление, ПОД КОТОРОЕ письмо написано (target_division).
                # Компания бывает «kc+meyer», письмо — всегда про одно; без
                # этой метки очередь подтверждений выбирала ящик по компании и
                # у смешанных подставляла компрессорный даже под meyer-письмо.
                "letter_division": letter.get("division") or "",
                "letter_division_reason": letter.get("division_reason") or "",
                "news_digest": req.get("_digest", ""),
                "news_url": req.get("_url", "")}
        try:
            from sender.infopanel import build_panel, load_enrich_lead
            ctx = load_enrich_lead(str(r.inn or ""), db_path=self._enrich_db,
                                   email=r.email)
            # КАРТОЧКА ИЗ БАЗЫ ОБЗВОНА — обязательна. В ней выручка, директор и
            # «Все категории оборудования» по ОКВЭД, то есть ровно то, чем
            # обосновывается направление и чем письмо может оперировать.
            # Без неё карточка показывала «выручка: в базе нет данных» даже для
            # компаний, которые в базе есть, а балл за выручку всегда был 0/20.
            card = self._card_for(r.inn)
            full = build_panel(
                inn=str(r.inn) if r.inn else None, email=r.email,
                letter_subject=letter["subject"], letter_body=letter["body"],
                company=ctx.get("company") or {}, emails=ctx.get("emails") or [],
                signals=ctx.get("signals") or [], store=self._store,
                card=card, signature=self._signature_preview(
                    str(letter.get("division") or "kc")))
            if isinstance(full, dict):
                full.update(base)      # ai-ключи главнее при совпадении имён
                return full
        except Exception:  # noqa: BLE001
            logger.exception("build_panel для ai-письма не собрался (%s)", r.email)
        return base

    def _ensure_message(self, campaign_id: int, recipient_id: int):
        """message_id для confirm_submit: без него письмо в очереди НЕОТПРАВЛЯЕМО
        (approve падает «нет message_id»). Пишем в messages со статусом
        pending_review (claim_due его не берёт — авто-поток не подхватит),
        идемпотентный ключ — как у cadence (кампания|получатель|шаг).
        Возврат (message_id|None, step_id|None, причина)."""
        import hashlib
        from datetime import datetime, timezone as _tz
        from sender.dtos import MessageIn
        try:
            steps = self._store.get_steps(campaign_id)
        except Exception:  # noqa: BLE001
            steps = []
        if not steps:
            return None, None, "у кампании нет шага-письма (campaign-add-step)"
        step = steps[0]
        step_id = getattr(step, "id", None) or (step.get("id") if isinstance(step, dict) else None)
        step_index = getattr(step, "step_index", 0) or 0
        key = hashlib.sha256(f"{campaign_id}|{recipient_id}|{step_index}".encode()).hexdigest()
        mid, _created = self._store.enqueue_message(MessageIn(
            idempotency_key=key, campaign_id=int(campaign_id),
            recipient_id=int(recipient_id), sequence_step_id=int(step_id),
            scheduled_at=datetime.now(_tz.utc)), status="pending_review")
        return mid, step_id, ""

    def _log(self, campaign_id: int, items: list, res: RunResult) -> None:
        """Единый калибровочный лог: и ok, и брак. Пишем СРАЗУ после батча —
        durability важнее скорости: оборванный прогон не должен обнулить квоту."""
        if not items:
            return
        try:
            from sender.ai_letter import log_results
            # метка времени — от часов движка: если «сегодня» переопределено
            # (тесты, ручной дозапуск за прошлый день), лог и счётчик совпадают
            stamp = ''
            if self._today_fn is not None:
                stamp = self._today_fn() + 'T12:00:00+00:00'
            log_results(self._db_path, campaign_id, items, now=stamp)
        except Exception as e:  # noqa: BLE001
            res.errors.append(f"ai_letter_log: {str(e)[:100]}")

    # ------------------------------------------------------- фоновый запуск --

    def run_state(self, campaign_id: int) -> dict:
        raw = self._store.get_setting(RUN_KEY, None) or {}
        st = raw.get(str(int(campaign_id))) if isinstance(raw, dict) else None
        st = dict(st) if isinstance(st, dict) else {"running": False}
        if st.get("running"):
            started = _parse_utc(st.get("started_at") or "")
            age = (datetime.now(timezone.utc) - started).total_seconds() if started else 0
            # свежий пульс батча = прогон жив, какой бы длинной ни была
            # генерация (200 писем — часы); «оборван» — только без пульса
            бился = _parse_utc((st.get("progress") or {}).get("at") or "")
            if бился is not None:
                age = (datetime.now(timezone.utc) - бился).total_seconds()
            if age > _STALE_RUN_SEC:
                # Служба перезапустилась посреди прогона: не держим UI в «идёт»
                st["running"] = False
                st["stale"] = True
        return st

    def _save_run(self, campaign_id: int, state: dict) -> None:
        raw = self._store.get_setting(RUN_KEY, None)
        raw = dict(raw) if isinstance(raw, dict) else {}
        raw[str(int(campaign_id))] = state
        self._store.set_setting(RUN_KEY, raw)

    def start_run(self, campaign_id: int, *, actor: Optional[str] = None,
                  count: Optional[int] = None) -> dict:
        """Запустить прогон в фоне. Второй клик по кнопке подхватывает текущий
        прогон, а не стартует параллельный (иначе квота уедет вдвое).

        count (#71) — «сгенерировать ещё N писем в очередь» СВЕРХ уже сделанных
        сегодня, независимо от расписания квоты: владелец поднял дневной лимит
        и хочет добить очередь под него."""
        campaign_id = int(campaign_id)
        # Проверяем кампанию ДО фонового потока: иначе опечатка в id молча
        # уедет в state.error и оператор увидит её только через поллинг.
        self._require_campaign(campaign_id)
        with self._lock:
            st = self.run_state(campaign_id)
            if st.get("running"):
                return st
            state = {"running": True, "started_at": _now_iso(), "date": self.today(),
                     "actor": actor or "", "result": None, "error": None,
                     "count": int(count) if count else None}
            self._save_run(campaign_id, state)
        threading.Thread(target=self._run_thread, args=(campaign_id, state),
                         daemon=True).start()
        return state

    def _run_thread(self, campaign_id: int, state: dict) -> None:
        try:
            def _пульс(ok_n, brak_n):
                state["progress"] = {"ok": ok_n, "brak": brak_n,
                                     "at": _now_iso()}
                self._save_run(campaign_id, state)

            count = state.get("count")
            if count:
                # квота = уже сделано сегодня + N: run_today отнимет сделанное
                # и сгенерирует ровно N новым получателям
                день = self.today()
                ok, brak = self.counters(campaign_id, [день]).get(день, (0, 0))
                res = self.run_today(campaign_id, today=день,
                                     quota=ok + brak + int(count),
                                     progress_cb=_пульс)
            else:
                res = self.run_today(campaign_id, progress_cb=_пульс)
            state["result"] = res.as_json()
        except Exception as e:  # noqa: BLE001 - ошибка уходит в статус, не в тишину
            state["error"] = str(e)[:300]
        finally:
            state["running"] = False
            state["finished_at"] = _now_iso()
            try:
                self._save_run(campaign_id, state)
            except Exception:  # noqa: BLE001
                pass


def build_ai_quota(store, config) -> AiQuota:
    """Сборка из панельного конфига (вызывается из sender/api/app.py)."""
    db_path = getattr(store, "_db_path", None) or config.get("service.db_path", "sender.db")
    enrich = config.get("service.enrich_db", None)
    if not enrich:
        guess = os.path.join(os.path.dirname(os.path.abspath(str(db_path))), "enrich.db")
        enrich = guess if os.path.exists(guess) else None
    # День считаем по Москве: владелец говорит «3 сегодня» про свой день, а не
    # про UTC. service.timezone уважаем, но дефолт тут МСК, а не UTC.
    tz = config.get("ai.quota_tz", None) or config.get("timezone", None) or DEFAULT_TZ
    return AiQuota(store, db_path=str(db_path), enrich_db=enrich, tz=str(tz),
                   config=config)
