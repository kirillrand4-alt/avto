# -*- coding: utf-8 -*-
"""Правка привязки в C:\\sender\\sender\\imap_watcher.py по якорям.

Файл делится с соседней сессией (там на 5 КБ больше нашего) — целиком не
перезаписываем.
"""
import io
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
ЗАМЕНЫ = [
 [
  "        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_imya_domena(from_addr)\n",
  "        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_imya_domena(from_addr)\n        # ДОМЕН ДЕЛЯТ ДВЕ КОМПАНИИ — СМОТРИМ, КОМУ МЫ ПИСАЛИ ПОСЛЕДНИМИ.\n        # Владелец 28.08 показал автоответ «я закончила работу в компании,\n        # обращайтесь к Пушиной Александре» с virtex-food.ru: там у нас АО\n        # «Виртекс» и ООО «ВТ Логистик», и привязка по домену честно\n        # отказалась гадать. Гадать и не нужно: письмо ушло на\n        # sales-p@virtex-food.ru в 03:09, автоответ пришёл в 03:10.\n        if recipient_id is None and kind != \"dsn\":\n            recipient_id = self._recipient_by_svezhey_otpravkoy(from_addr)\n"
 ],
 [
  "    def _recipient_by_domain(self, from_addr: str) -> Optional[int]:",
  "    # Окно, в котором ответ ещё считается ответом на наше письмо. Автоответы\n    # приходят за минуты, живые ответы — за дни; две недели с запасом.\n    ОКНО_СВЕЖЕЙ_ОТПРАВКИ_ДНЕЙ = 14\n    # Насколько последняя отправка должна опережать предыдущую, чтобы выбор\n    # был однозначным. Час: две компании на одном домене, которым писали в\n    # одну минуту, — это не разрешимый случай, и гадать там нельзя.\n    ЗАЗОР_СЕК = 3600\n\n    def _recipient_by_svezhey_otpravkoy(self, from_addr: str) -> Optional[int]:\n        \"\"\"Домен делят несколько компаний — берём ту, которой писали последней.\n\n        Работает там, где _recipient_by_domain честно отказался: несколько\n        ИНН на одном домене. Ответ приходит следом за нашим письмом, поэтому\n        «кому писали последними» — не догадка, а самый прямой признак.\n        Отказываемся, если последняя отправка старше окна или если две\n        компании получили письмо почти одновременно.\n        \"\"\"\n        from datetime import datetime, timedelta, timezone\n        адрес = str(from_addr or \"\").strip().lower()\n        if \"@\" not in адрес:\n            return None\n        домен = адрес.rsplit(\"@\", 1)[-1]\n        if not домен or домен in self.ОБЩИЕ_ДОМЕНЫ:\n            return None\n        finder = getattr(self._store, \"recipients_by_domain\", None)\n        история = getattr(self._store, \"send_log_history\", None)\n        if not callable(finder) or not callable(история):\n            return None\n        try:\n            строки = finder(домен) or []\n        except Exception:  # noqa: BLE001 - сбой поиска не роняет приём\n            logger.exception(\"recipients_by_domain failed for %s\", домен)\n            return None\n        if len(строки) < 2:\n            return None\n\n        def поле(r, имя):\n            return r.get(имя) if isinstance(r, dict) else getattr(r, имя, None)\n\n        когда = []\n        for r in строки:\n            почта = str(поле(r, \"email\") or \"\").strip().lower()\n            rid = поле(r, \"id\")\n            if not почта or not rid:\n                continue\n            try:\n                ряд = история(email=почта, limit=5) or []\n            except Exception:  # noqa: BLE001\n                continue\n            метки = [str(x.get(\"ts\") or \"\") for x in ряд\n                     if str(x.get(\"outcome\") or \"\") == \"sent\"]\n            if метки:\n                когда.append((max(метки), int(rid), почта))\n        if not когда:\n            return None\n        когда.sort(reverse=True)\n        try:\n            последняя = datetime.fromisoformat(когда[0][0].replace(\"Z\", \"+00:00\"))\n            if последняя.tzinfo is None:\n                последняя = последняя.replace(tzinfo=timezone.utc)\n        except ValueError:\n            return None\n        порог = datetime.now(timezone.utc) - timedelta(\n            days=self.ОКНО_СВЕЖЕЙ_ОТПРАВКИ_ДНЕЙ)\n        if последняя < порог:\n            return None\n        if len(когда) > 1:\n            try:\n                вторая = datetime.fromisoformat(когда[1][0].replace(\"Z\", \"+00:00\"))\n                if вторая.tzinfo is None:\n                    вторая = вторая.replace(tzinfo=timezone.utc)\n            except ValueError:\n                вторая = None\n            if вторая is not None and (последняя - вторая).total_seconds() < self.ЗАЗОР_СЕК:\n                logger.info(\"привязка по свежей отправке %s пропущена: \"\n                            \"две компании писаны почти разом\", домен)\n                return None\n        return когда[0][1]\n\n    def _recipient_by_domain(self, from_addr: str) -> Optional[int]:"
 ]
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if "_recipient_by_svezhey_otpravkoy" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as e:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % e)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
