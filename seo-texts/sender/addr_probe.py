# -*- coding: utf-8 -*-
"""Проверка адресов без отправки писем: существует ли ящик.

Зачем. Половину отбивок 07.08 дали несуществующие адреса («user not found»),
и узнавали мы о них только по факту отправки — то есть ценой репутации
домена. Разговор с сервером получателя доходит до команды RCPT TO и
обрывается: ящик отвечает «приму» или «нет такого», письмо не уходит,
получатель ничего не видит.

Что этот модуль делает и чего НЕ делает:

  * «нет ящика» принимается ТОЛЬКО по явному ответу сервера («no such user»,
    «user unknown», «5.1.1»). Отказ САМОЙ пробе (нужен TLS, у нашего IP нет
    PTR, серый список, callback обратного адреса) адрес не хоронит. Это не
    перестраховка: 07.08 из восьми ответов 5xx четыре были про пробу, и
    выброс «по коду» убил бы четыре живых контакта;
  * ничего не выбрасывает молча: мёртвый адрес снимает письмо с очереди и
    пишет причину, живой просто отмечается в кэше;
  * бережёт IP. Массовые вопросы «есть ли такой ящик» для антиспама
    неотличимы от перебора адресов, поэтому есть пауза между пробами, лимит
    на домен и кэш: один адрес проверяется раз в TTL, а не каждый тик.

Кэш durable — таблица addr_probe в sender.db.
"""
from __future__ import annotations

import logging
import re
import smtplib
import socket
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENABLED_KEY = "addr_probe_enabled"

ЕСТЬ = "есть"
НЕТ_ЯЩИКА = "нет ящика"
ОТКАЗ_ПРОБЕ = "отказ пробе"
НЕЯСНО = "неясно"
НЕТ_MX = "нет MX"
# Домен принимает ЛЮБОЙ адрес: сервер сказал «приму» и про заведомо
# несуществующий ящик. Тогда его «приму» про настоящий адрес не значит ничего.
# Поймано 11.08: kk@vebfabrika.ru проба назвала живым, а письмо отбилось
# «invalid mailbox. Local mailbox is unavailable». Такой вердикт НЕ хоронит
# адрес (писать можно), но и не подтверждает его.
ПРИНИМАЕТ_ВСЁ = "принимает всё"

# Явное «такого пользователя нет» — только на эти слова выбрасываем адрес.
_МЁРТВ = (
    "no such user", "user unknown", "unknown user", "user not found",
    "no such recipient", "recipient not found", "invalid mailbox",
    "mailbox unavailable", "mailbox not found", "mailbox does not exist",
    "address does not exist", "no mailbox", "recipient address rejected: user",
    "нет такого пользователя", "пользователь не найден",
    "почтовый ящик не найден", "адрес не существует",
)
# Сервер отверг НАС, а не адрес: про адрес он ничего не сказал.
_ПРО_ПРОБУ = (
    "encryption is required", "starttls", "ptr", "reverse", "hostname",
    "verification failed", "spf", "dmarc", "greylist", "try again",
    "policy", "blocked", "blacklist", "access denied", "not permitted",
    "rejected: message", "ip name lookup", "relay", "too many", "rate",
)
_МЁРТВЫЙ_КОД = re.compile(r"\b5\.1\.[01]\b")


def классифицировать(код: Optional[int], ответ: str) -> str:
    """Вердикт по ответу сервера на RCPT TO."""
    низ = (ответ or "").lower()
    if код is not None and 200 <= код < 300:
        return ЕСТЬ
    if код is not None and 500 <= код < 600:
        if any(m in низ for m in _МЁРТВ) or _МЁРТВЫЙ_КОД.search(низ):
            return НЕТ_ЯЩИКА
        if any(m in низ for m in _ПРО_ПРОБУ):
            return ОТКАЗ_ПРОБЕ
    return НЕЯСНО


_СОЗДАНИЕ = """
CREATE TABLE IF NOT EXISTS addr_probe (
    email    TEXT PRIMARY KEY,
    verdict  TEXT NOT NULL,
    code     INTEGER,
    answer   TEXT,
    mx       TEXT,
    ts       TEXT NOT NULL
)"""


class AddrProbe:
    """Проба адресов с durable-кэшем и щадящим темпом.

    helo/mail_from — как мы представляемся. По умолчанию берутся из
    настройки addr_probe (технический домен), а НЕ из боевых доменов
    рассылки: пробы с домена, которым мы шлём письма, портят его репутацию.
    """

    def __init__(self, db_path: str, *, helo: str = "", mail_from: str = "",
                 ttl_days: int = 30, pause_sec: float = 3.0,
                 per_domain: int = 3, timeout: float = 15.0,
                 source_ip: str = ""):
        self._db = str(db_path)
        self.helo = helo or ""
        self.mail_from = mail_from or ""
        # С какого IP выходить. Пустое — с основного адреса сервера. Отдельный
        # адрес нужен, чтобы риск не касался основного: если проверочный IP
        # попадёт в чёрные списки, его меняют, а панель, дроп и сервер отписки
        # продолжают работать со своего. Сам адрес должен быть поднят на
        # сетевом адаптере сервера и иметь PTR-запись.
        self.source_ip = (source_ip or "").strip()
        self.ttl = max(1, int(ttl_days))
        self.pause = max(0.0, float(pause_sec))
        self.per_domain = max(1, int(per_domain))
        self.timeout = float(timeout)
        self._lock = threading.Lock()
        self._mx: dict = {}
        self._catch: dict = {}
        self._последняя_проба = 0.0
        self._счёт_домена: dict = {}
        self._ensure()

    # -- кэш ----------------------------------------------------------------- #

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db, timeout=20)
        c.row_factory = sqlite3.Row
        return c

    def _ensure(self) -> None:
        try:
            with self._lock, self._conn() as c:
                c.execute(_СОЗДАНИЕ)
        except Exception:  # noqa: BLE001
            logger.exception("addr_probe: таблица кэша не создалась")

    def cached(self, email: str) -> Optional[dict]:
        """Свежая запись кэша или None (протухшую не отдаём)."""
        адрес = (email or "").strip().lower()
        if not адрес:
            return None
        try:
            with self._lock, self._conn() as c:
                r = c.execute("SELECT * FROM addr_probe WHERE email=?",
                              (адрес,)).fetchone()
        except Exception:  # noqa: BLE001
            return None
        if r is None:
            return None
        try:
            ts = datetime.fromisoformat(r["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            return dict(r)
        # «нет ящика» не протухает: ящик, которого нет, сам не заведётся;
        # остальные вердикты перепроверяем через TTL.
        if r["verdict"] != НЕТ_ЯЩИКА and \
                datetime.now(timezone.utc) - ts > timedelta(days=self.ttl):
            return None
        return dict(r)

    def _save(self, адрес: str, вердикт: str, код, ответ: str, mx: str) -> None:
        try:
            with self._lock, self._conn() as c:
                c.execute(
                    "INSERT INTO addr_probe (email,verdict,code,answer,mx,ts) "
                    "VALUES (?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
                    "verdict=excluded.verdict, code=excluded.code, "
                    "answer=excluded.answer, mx=excluded.mx, ts=excluded.ts",
                    (адрес, вердикт, код, (ответ or "")[:200], mx or "",
                     datetime.now(timezone.utc).isoformat()))
        except Exception:  # noqa: BLE001
            logger.exception("addr_probe: не записался вердикт %s", адрес)

    def verdict_emails(self, вердикт: str) -> set:
        """Все адреса кэша с данным вердиктом (заслону ловушек — «есть»)."""
        try:
            with self._lock, self._conn() as c:
                rows = c.execute("SELECT email FROM addr_probe WHERE verdict=?",
                                 (вердикт,)).fetchall()
            return {str(r[0]).strip().lower() for r in rows if r[0]}
        except Exception:  # noqa: BLE001
            return set()

    def stats(self) -> dict:
        try:
            with self._lock, self._conn() as c:
                rows = c.execute("SELECT verdict, COUNT(*) n FROM addr_probe "
                                 "GROUP BY verdict").fetchall()
            return {r["verdict"]: int(r["n"]) for r in rows}
        except Exception:  # noqa: BLE001
            return {}

    # -- сеть ---------------------------------------------------------------- #

    def mx_for(self, домен: str) -> Optional[str]:
        with self._lock:
            если = self._mx.get(домен, "__нет__")
        if если != "__нет__":
            return если
        хост = None
        try:
            import dns.resolver  # type: ignore
            о = dns.resolver.resolve(домен, "MX", lifetime=8)
            хост = sorted((r.preference, str(r.exchange).rstrip("."))
                          for r in о)[0][1]
        except Exception:  # noqa: BLE001 - без dnspython спрашиваем систему
            try:
                import subprocess
                out = subprocess.run(["nslookup", "-type=MX", домен],
                                     capture_output=True, text=True,
                                     timeout=20, errors="replace").stdout
                м = re.findall(r"mail exchanger = (\S+)", out)
                хост = м[0].rstrip(".") if м else None
            except Exception:  # noqa: BLE001
                хост = None
        with self._lock:
            self._mx[домен] = хост
        return хост

    def _тормоз(self, домен: str) -> None:
        """Пауза между пробами: щадим и чужой сервер, и свой IP."""
        with self._lock:
            прошло = time.monotonic() - self._последняя_проба
            ждать = max(0.0, self.pause - прошло)
        if ждать:
            time.sleep(ждать)
        with self._lock:
            self._последняя_проба = time.monotonic()

    def probe(self, email: str, *, force: bool = False,
              _без_catch_all: bool = False) -> dict:
        """Проверить один адрес. Возвращает запись вердикта."""
        адрес = (email or "").strip().lower()
        if "@" not in адрес:
            return {"email": адрес, "verdict": НЕЯСНО, "answer": "не адрес"}
        if not force:
            есть = self.cached(адрес)
            if есть:
                return есть
        домен = адрес.rsplit("@", 1)[-1]
        with self._lock:
            если_много = self._счёт_домена.get(домен, 0) >= self.per_domain
        if если_много and not force:
            return {"email": адрес, "verdict": НЕЯСНО,
                    "answer": "лимит проб на домен в этом проходе"}
        хост = self.mx_for(домен)
        if not хост:
            self._save(адрес, НЕТ_MX, None, "у домена нет MX-записи", "")
            return {"email": адрес, "verdict": НЕТ_MX, "mx": None}

        self._тормоз(домен)
        код, ответ = None, ""
        try:
            откуда = (self.source_ip, 0) if self.source_ip else None
            with smtplib.SMTP(хост, 25, timeout=self.timeout,
                              local_hostname=self.helo or None,
                              source_address=откуда) as s:
                s.ehlo_or_helo_if_needed()
                # Шифрование, если сервер умеет: часть требует его до RCPT.
                try:
                    if s.has_extn("starttls"):
                        s.starttls()
                        s.ehlo()
                except Exception:  # noqa: BLE001 - без TLS продолжаем как есть
                    pass
                s.mail(self.mail_from or "")
                код, сырой = s.rcpt(адрес)
                ответ = (сырой or b"").decode("utf-8", "replace")
        except UnicodeEncodeError:
            ответ = "адрес не-ASCII, проба неприменима"
        except (smtplib.SMTPException, OSError, socket.timeout) as e:
            ответ = str(e)[:150]
        except Exception as e:  # noqa: BLE001 - одна проба не рвёт проход
            ответ = str(e)[:150]
        with self._lock:
            self._счёт_домена[домен] = self._счёт_домена.get(домен, 0) + 1
        вердикт = классифицировать(код, ответ)
        # «Приму» от домена, который принимает всё, — не подтверждение.
        # Проверяем ТОЛЬКО когда сервер сказал «есть»: на прочих вердиктах
        # выяснять нечего, а лишний разговор с чужим сервером не нужен.
        if вердикт == ЕСТЬ and not _без_catch_all:
            if self.catch_all(домен):
                вердикт = ПРИНИМАЕТ_ВСЁ
                ответ = (ответ + " | домен принимает любой адрес").strip()
        self._save(адрес, вердикт, код, ответ, хост)
        return {"email": адрес, "verdict": вердикт, "code": код,
                "answer": ответ[:200], "mx": хост}

    # -- ловушка catch-all --------------------------------------------------- #

    def catch_all(self, домен: str, *, force: bool = False) -> Optional[bool]:
        """Принимает ли домен любой адрес. None — выяснить не удалось.

        Спрашиваем про заведомо несуществующий ящик. Ответ «приму» означает
        catch-all: сервер соглашается на всё, а разбирается потом (или не
        разбирается вовсе). Проверка одна НА ДОМЕН, а не на адрес: домены в
        базе повторяются, и лишние разговоры с чужим сервером нам не нужны.
        """
        дом = (домен or "").strip().lower()
        if not дом:
            return None
        with self._lock:
            если = self._catch.get(дом, "__нет__")
        if если != "__нет__" and not force:
            return если
        выдумка = f"nesushchestvuyushchiy-{uuid.uuid4().hex[:12]}@{дом}"
        рез = self.probe(выдумка, force=True, _без_catch_all=True)
        ответ = None
        if рез.get("verdict") == ЕСТЬ:
            ответ = True
        elif рез.get("verdict") in (НЕТ_ЯЩИКА,):
            ответ = False
        with self._lock:
            self._catch[дом] = ответ
        return ответ

    def new_pass(self) -> None:
        """Сбросить счётчики домена — новый проход."""
        with self._lock:
            self._счёт_домена = {}


class AddrProbeLoop:
    """Фоновый цикл: проверяет адреса новых писем очереди.

    Мёртвый адрес снимает письмо с очереди и уходит в стоп-лист (повторно
    туда никто не напишет). Все прочие вердикты письмо НЕ трогают: пока у
    нашего IP нет PTR-записи, «не подтверждён» означает claim про нас, а не
    про адрес, и выбрасывать по нему живые контакты нельзя.
    """

    def __init__(self, *, store: Any, probe: AddrProbe, batch: int = 40,
                 interval_sec: int = 300):
        self.store = store
        self.probe_ = probe
        self.batch = max(1, int(batch))
        self.interval = max(30, int(interval_sec))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last: dict = {}

    def enabled(self) -> bool:
        try:
            return bool(self.store.get_setting(ENABLED_KEY, False))
        except Exception:  # noqa: BLE001
            return False

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tick(self) -> dict:
        итог = {"проверено": 0, ЕСТЬ: 0, НЕТ_ЯЩИКА: 0, ОТКАЗ_ПРОБЕ: 0,
                НЕЯСНО: 0, НЕТ_MX: 0, "снято_писем": 0, "ловушек": 0}
        if not self.enabled():
            return итог
        try:
            письма = [r for r in self.store.confirm_list(status="pending",
                                                         limit=100000)
                      if (r.get("kind") or "outbound") != "reply"
                      and r.get("email")]
        except Exception:  # noqa: BLE001
            logger.exception("addr_probe: очередь не прочиталась")
            return итог
        # Ловушки убираем ДО проб: писать в ящик для жалоб не надо, и
        # спрашивать у него «а ты существуешь?» — тоже не надо.
        try:
            from sender.lovushki import ЗаслонЛовушек
            л = ЗаслонЛовушек(store=self.store, probe=self.probe_).применить(письма)
            итог["ловушек"] = л["снято"]
            итог["снято_писем"] += л["снято"]
            if л["ид"]:
                письма = [r for r in письма if r.get("id") not in л["ид"]]
        except Exception:  # noqa: BLE001 - заслон упал, проба работает дальше
            logger.exception("addr_probe: заслон ловушек не отработал")
        self.probe_.new_pass()
        свежие = [r for r in письма if not self.probe_.cached(r["email"])]
        for r in свежие[:self.batch]:
            res = self.probe_.probe(r["email"])
            в = res.get("verdict") or НЕЯСНО
            итог["проверено"] += 1
            итог[в] = итог.get(в, 0) + 1
            if в != НЕТ_ЯЩИКА:
                continue
            try:
                ok = self.store.confirm_decide(
                    int(r["id"]), status="skipped",
                    decided_by="проба адресов",
                    reason=f"адрес не существует: {res.get('code')} "
                           f"{(res.get('answer') or '')[:60]}")
                if ok:
                    итог["снято_писем"] += 1
                from sender.dtos import SuppressionIn
                self.store.suppression_add(SuppressionIn(
                    scope="email", value=res["email"], reason="bounce_hard",
                    source="addr_probe"))
            except Exception:  # noqa: BLE001
                logger.exception("addr_probe: не снялось письмо %s", r.get("id"))
        self.last = dict(итог, at=datetime.now(timezone.utc).isoformat(),
                         осталось_непроверенных=max(0, len(свежие) - self.batch))
        return итог

    def start(self) -> None:
        if self.running():
            return
        self._stop.clear()

        def _run() -> None:
            logger.info("addr_probe: цикл запущен (каждые %sс)", self.interval)
            while not self._stop.wait(self.interval):
                try:
                    r = self.tick()
                    if r.get("проверено"):
                        logger.info("addr_probe: %s", r)
                except Exception:  # noqa: BLE001
                    logger.exception("addr_probe: тик упал")

        self._thread = threading.Thread(target=_run, name="addr-probe",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def build_addr_probe(store: Any, config: Any) -> AddrProbeLoop:
    """Сборка из конфига. Технический домен — addr_probe.helo/mail_from."""
    db = str(getattr(store, "_db_path", None)
             or config.get("service.db_path", "sender.db"))

    def нас(ключ, умолч=None):
        try:
            return config.get(ключ, умолч)
        except Exception:  # noqa: BLE001
            return умолч

    probe = AddrProbe(
        db,
        helo=str(нас("addr_probe.helo", "") or ""),
        mail_from=str(нас("addr_probe.mail_from", "") or ""),
        ttl_days=int(нас("addr_probe.ttl_days", 30) or 30),
        source_ip=str(нас("addr_probe.source_ip", "") or ""),
        pause_sec=float(нас("addr_probe.pause_sec", 3.0) or 3.0),
        per_domain=int(нас("addr_probe.per_domain", 3) or 3),
    )
    return AddrProbeLoop(
        store=store, probe=probe,
        batch=int(нас("addr_probe.batch", 40) or 40),
        interval_sec=int(нас("addr_probe.interval_sec", 300) or 300))
