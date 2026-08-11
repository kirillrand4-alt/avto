# -*- coding: utf-8 -*-
"""Связка панели с работником проверки адресов на отдельном сервере.

Зачем отдельный сервер. Массовые вопросы «есть ли такой ящик» для антиспама
неотличимы от перебора адресов, а боевой IP панели один и заменить его дорого:
на нём панель, дроп, сервер отписки. Решение владельца 07.08 — «безопасность в
первую очередь»: проверки унесены на дешёвый VPS со своей обратной записью.
Сгорит он — меняем его, рассылка не замечает.

Прямого доступа между машинами нет и не нужно: обе ходят на дроп.

    панель  --> probe-zadanie.json    --> работник   (кого проверить)
    панель  <-- probe-rezultat.jsonl  <-- работник   (вердикты)

Этот цикл делает три вещи и НИ ОДНА из них не выходит в чужую сеть с боевого
адреса — только на наш собственный дроп:

  1. заслон ловушек по очереди (сети не касается вовсе);
  2. публикация адресов очереди, у которых ещё нет вердикта;
  3. приём вердиктов: «нет ящика» снимает письмо и уходит в стоп-лист,
     прочие вердикты только пополняют кэш.

Поэтому цикл включён по умолчанию, в отличие от собственной пробы панели
(addr_probe_enabled), которая ходила бы к чужим серверам с боевого IP.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENABLED_KEY = "probe_sync_enabled"
ЗАДАНИЕ = "probe-zadanie.json"
РЕЗУЛЬТАТ = "probe-rezultat.jsonl"
ЗАДАЧА = "vjob-"                      # префикс заданий раннера на VPS

# Ключи дропа. У ПРОЦЕССА РАННЕРА они в окружении, а у СЛУЖБЫ панели — нет:
# служба стартует от системы и файл раннера не читает. Первый живой прогон
# упёрся ровно в это («дроп не настроен»), хотя ручной импорт работал. Поэтому
# кроме окружения смотрим в тот же файл, откуда их берёт раннер.
СЕКРЕТЫ = r"C:\sender\server\runner-secrets.env"


def _из_файла(путь: str) -> dict:
    """KEY=VALUE из env-файла раннера. Нет файла — пустой разбор, не ошибка."""
    итог: dict = {}
    try:
        with open(путь, encoding="utf-8", errors="replace") as f:
            for с in f:
                с = с.strip()
                if not с or с.startswith("#") or "=" not in с:
                    continue
                k, v = с.split("=", 1)
                итог[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001 - файла нет или не читается
        return {}
    return итог


class ProbeSync:
    """Обмен с работником через дроп + заслон ловушек по очереди."""

    def __init__(self, *, store: Any, probe: Any, interval_sec: int = 600,
                 batch: int = 400, secrets_file: str = СЕКРЕТЫ):
        self.store = store
        self.probe = probe
        self.interval = max(60, int(interval_sec))
        self.batch = max(1, int(batch))
        self.secrets_file = secrets_file or ""
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last: dict = {}

    # -- настройки ----------------------------------------------------------- #

    def enabled(self) -> bool:
        """По умолчанию включён: цикл ходит только на свой дроп."""
        try:
            v = self.store.get_setting(ENABLED_KEY, None)
        except Exception:  # noqa: BLE001
            return False
        return True if v is None else bool(v)

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- дроп ---------------------------------------------------------------- #

    def _ключи(self) -> tuple:
        база = os.environ.get("DROP_URL") or ""
        токен = os.environ.get("DROP_TOKEN") or ""
        if not база or not токен:
            из = _из_файла(self.secrets_file)
            база = база or из.get("DROP_URL", "")
            токен = токен or из.get("DROP_TOKEN", "")
        return база.rstrip("/"), токен

    def _подпись(self) -> str:
        return (os.environ.get("JOB_SECRET")
                or _из_файла(self.secrets_file).get("JOB_SECRET", ""))

    def _дроп(self, метод: str, имя: str, данные: bytes = None) -> bytes:
        база, токен = self._ключи()
        if not база or not токен:
            raise RuntimeError("дроп не настроен (DROP_URL/DROP_TOKEN "
                               f"нет ни в окружении, ни в {self.secrets_file})")
        з = urllib.request.Request(f"{база}/{имя}", data=данные, method=метод)
        з.add_header("X-Drop-Token", токен)
        with urllib.request.urlopen(з, timeout=90) as о:
            return о.read()

    # -- очередь ------------------------------------------------------------- #

    def _очередь(self) -> list:
        return [r for r in self.store.confirm_list(status="pending",
                                                   limit=100000)
                if (r.get("kind") or "outbound") != "reply" and r.get("email")]

    def опубликовать(self, письма: list = None) -> dict:
        """Выложить на дроп адреса очереди, у которых ещё нет вердикта."""
        письма = self._очередь() if письма is None else письма
        видели, надо = set(), []
        for r in письма:
            а = str(r["email"]).strip().lower()
            if а in видели:
                continue
            видели.add(а)
            if not self.probe.cached(а):
                надо.append(а)
        надо = надо[:self.batch]
        if not надо:
            return {"опубликовано": 0}
        данные = json.dumps(надо, ensure_ascii=False).encode("utf-8")
        self._дроп("PUT", ЗАДАНИЕ, данные)
        return {"опубликовано": len(надо)}

    # -- срочная проба руками введённого адреса ------------------------------ #

    def срочно(self, адреса) -> dict:
        """Проверить названные адреса сейчас, не дожидаясь очередного круга.

        Повод — отбивка 11.08. Оператор подменил адрес письма руками в 05:35:08,
        письмо ушло в 05:35:51, а Google ответил «аккаунт отключён». Проба не
        ошиблась: её просто не успели спросить. Круг публикации идёт раз в десять
        минут, между вводом адреса и отправкой прошло СОРОК ТРИ СЕКУНДЫ.

        Поэтому адрес, введённый человеком, не ждёт круга: он дописывается в
        задание и работнику отправляется задача проверить сейчас. Раннер на VPS
        смотрит задания каждые 20 секунд — вердикт успевает прийти к моменту,
        когда оператор дочитает письмо.

        Задание ДОПИСЫВАЕТСЯ к тому, что уже лежит на дропе, а не подменяет его:
        иначе срочный адрес выбьет из очереди сотни ждущих.
        """
        новые = [str(а).strip().lower() for а in (адреса or [])
                 if а and "@" in str(а)]
        новые = [а for а in новые if not self.probe.cached(а)]
        if not новые:
            return {"срочных": 0}
        было = []
        try:
            было = json.loads(self._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace"))
            если_словарь = было.get("emails") if isinstance(было, dict) else None
            было = если_словарь if если_словарь is not None else было
        except Exception:  # noqa: BLE001 - задания ещё нет, это не беда
            было = []
        список, видели = [], set()
        for а in новые + [str(x).strip().lower() for x in (было or [])]:
            if а and а not in видели:
                видели.add(а)
                список.append(а)
        self._дроп("PUT", ЗАДАНИЕ,
                   json.dumps(список, ensure_ascii=False).encode("utf-8"))

        # Толчок работнику. Не вышло — не беда: адрес уже в задании и уйдёт
        # обычным кругом. Молчать об этом нельзя, поэтому пишем в лог.
        толкнули = False
        try:
            self._толкнуть(len(список))
            толкнули = True
        except Exception as e:  # noqa: BLE001
            logger.warning("probe_sync: срочная проба не растолкала работника: %s",
                           str(e)[:120])
        return {"срочных": len(новые), "в_задании": len(список),
                "работник_разбужен": толкнули}

    def _толкнуть(self, лимит: int) -> None:
        """Задача «проверь адреса сейчас» раннеру проверочного VPS."""
        jid = (f"{int(time.time())}-{os.getpid()}-"
               f"{threading.get_ident() % 100000}-{os.urandom(3).hex()}")
        задача = {"id": jid, "task": "probe",
                  "args": {"limit": max(1, min(int(лимит), 100))},
                  "ts": int(time.time())}
        канон = json.dumps({k: задача[k] for k in ("id", "task", "args", "ts")},
                           sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
        секрет = self._подпись()
        if секрет:
            задача["sig"] = hmac.new(секрет.encode(), канон.encode(),
                                     hashlib.sha256).hexdigest()
        self._дроп("PUT", f"{ЗАДАЧА}{jid}.json",
                   json.dumps(задача, ensure_ascii=False).encode("utf-8"))

    def забрать(self, письма: list = None) -> dict:
        """Забрать вердикты работника и применить их к очереди."""
        from sender.addr_probe import НЕТ_ЯЩИКА
        from sender.dtos import SuppressionIn

        try:
            строки = self._дроп("GET", РЕЗУЛЬТАТ).decode("utf-8",
                                                         "replace").splitlines()
        except Exception as e:  # noqa: BLE001 - работник ещё ничего не клал
            return {"строк": 0, "ошибка": str(e)[:120]}

        письма = self._очередь() if письма is None else письма
        по_почте: dict = {}
        for r in письма:
            по_почте.setdefault(str(r["email"]).strip().lower(), []).append(r)

        свод: dict = {}
        снято = новых = 0
        for с in строки:
            try:
                з = json.loads(с)
            except Exception:  # noqa: BLE001 - битая строка не рвёт приём
                continue
            адрес = str(з.get("email") or "").strip().lower()
            вердикт = str(з.get("verdict") or "")
            if not адрес or not вердикт:
                continue
            if not self.probe.cached(адрес):
                новых += 1
            self.probe._save(адрес, вердикт, з.get("code"),
                             str(з.get("answer") or ""), str(з.get("mx") or ""))
            свод[вердикт] = свод.get(вердикт, 0) + 1
            # Хороним адрес ТОЛЬКО по явному «такого пользователя нет».
            # Отказ самой пробе (TLS, PTR, серый список) — это про работника,
            # а не про адрес: 07.08 по такому «коду» едва не выбросили четыре
            # живых контакта.
            if вердикт != НЕТ_ЯЩИКА:
                continue
            for r in по_почте.get(адрес, []):
                try:
                    if self.store.confirm_decide(
                            int(r["id"]), status="skipped",
                            decided_by="проба адресов (внешний сервер)",
                            reason=f"адрес не существует: {з.get('code')} "
                                   f"{str(з.get('answer') or '')[:60]}"):
                        снято += 1
                except Exception:  # noqa: BLE001
                    logger.exception("probe_sync: не снялось письмо %s", r.get("id"))
            try:
                self.store.suppression_add(SuppressionIn(
                    scope="email", value=адрес, reason="bounce_hard",
                    source="probe-worker"))
            except Exception:  # noqa: BLE001
                logger.exception("probe_sync: адрес не лёг в стоп-лист")
        return {"строк": len(строки), "новых": новых, "снято_писем": снято,
                "свод": свод}

    # -- проход -------------------------------------------------------------- #

    def tick(self) -> dict:
        итог = {"ловушек": 0, "опубликовано": 0, "принято": {}}
        if not self.enabled():
            return итог
        try:
            письма = self._очередь()
        except Exception:  # noqa: BLE001
            logger.exception("probe_sync: очередь не прочиталась")
            return итог

        # 1. Ловушки — до всего прочего: такой адрес не надо ни проверять,
        # ни тем более отправлять на него письмо.
        try:
            from sender.lovushki import ЗаслонЛовушек
            л = ЗаслонЛовушек(store=self.store, probe=self.probe).применить(письма)
            итог["ловушек"] = л["снято"]
            if л["ид"]:
                письма = [r for r in письма if r.get("id") not in л["ид"]]
        except Exception:  # noqa: BLE001
            logger.exception("probe_sync: заслон ловушек не отработал")

        # 2. Приём раньше публикации: вдруг вердикты уже готовы — тогда
        # публиковать эти адреса не нужно.
        try:
            итог["принято"] = self.забрать(письма)
        except Exception as e:  # noqa: BLE001
            logger.exception("probe_sync: приём вердиктов упал")
            итог["принято"] = {"ошибка": str(e)[:120]}

        try:
            итог.update(self.опубликовать(письма))
        except Exception as e:  # noqa: BLE001
            logger.warning("probe_sync: публикация задания не удалась: %s",
                           str(e)[:120])
            итог["ошибка_публикации"] = str(e)[:120]

        self.last = dict(итог, at=datetime.now(timezone.utc).isoformat())
        return итог

    def start(self) -> None:
        if self.running():
            return
        self._stop.clear()

        def _run() -> None:
            logger.info("probe_sync: цикл запущен (каждые %sс)", self.interval)
            while not self._stop.wait(self.interval):
                try:
                    r = self.tick()
                    if r.get("ловушек") or r.get("опубликовано") \
                            or (r.get("принято") or {}).get("новых"):
                        logger.info("probe_sync: %s", r)
                except Exception:  # noqa: BLE001 - тик упал, цикл живёт
                    logger.exception("probe_sync: тик упал")

        self._thread = threading.Thread(target=_run, name="probe-sync",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def build_probe_sync(store: Any, probe: Any, config: Any) -> ProbeSync:
    def нас(ключ, умолч=None):
        try:
            return config.get(ключ, умолч)
        except Exception:  # noqa: BLE001
            return умолч

    return ProbeSync(store=store, probe=probe,
                     interval_sec=int(нас("probe_sync.interval_sec", 600) or 600),
                     batch=int(нас("probe_sync.batch", 400) or 400),
                     secrets_file=str(нас("probe_sync.secrets_file", СЕКРЕТЫ)
                                      or СЕКРЕТЫ))
