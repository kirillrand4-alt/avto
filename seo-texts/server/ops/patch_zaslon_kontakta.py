# -*- coding: utf-8 -*-
"""Правка заслона повторного контакта в C:\\sender\\sender\\confirm.py по якорям.

Файл делится с соседней сессией — целиком не перезаписываем, меняем только
свои куски, с .bak и проверкой компиляции.
"""
import io
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\confirm.py"
ЗАМЕНЫ = [
 [
  "RECENT_CONTACT_DAYS = 90\n",
  "RECENT_CONTACT_DAYS = 90\n\n# Сколько РАЗНЫХ адресов одной компании можно тронуть за то же окно.\n# Владелец 27.08: заслон считал повторным контактом любое письмо в ту же\n# компанию (last_contact сверяется по email ИЛИ ИНН), поэтому второе письмо\n# коллеге на том же домене — когда первое осталось без ответа — не попадало\n# в очередь вовсе: из 1125 отобранных упиралось 1123.\n# Снять ограничение по компании целиком нельзя: тогда у компании с десятью\n# адресами ничто не помешает отправить ей десять писем за квартал, а это\n# ровно тот шаблон, на котором 21.08 просели три домена Meyer (с одного\n# отказа на 114 писем до двадцати девяти на сорок восемь). Поэтому окно на\n# САМ АДРЕС осталось прежним, а на компанию встал потолок разных адресов.\nCOMPANY_CONTACTS_PER_PERIOD = 2\n"
 ],
 [
  "        \"\"\"Причина блокировки или None. Проверяет suppression (отписка\n        навсегда и пр.), повторный контакт <90 дней (Задача 3) и заведомо\n        недоставимый адрес.\"\"\"",
  "        \"\"\"Причина блокировки или None. Проверяет suppression (отписка\n        навсегда и пр.), заведомо недоставимый адрес, повторное письмо на ТОТ\n        ЖЕ адрес <90 дней (Задача 3) и потолок разных адресов одной компании\n        за то же окно.\"\"\""
 ],
 [
  "        last = self._recent_contact(inn=inn, email=email)\n        if last is not None:\n            return f\"recent_contact<{RECENT_CONTACT_DAYS}d:{last.get('ts', '')[:10]}\"\n        return None",
  "        last = self._recent_contact(email=email)\n        if last is not None:\n            return (f\"recent_contact<{self._okno_dney()}d:\"\n                    f\"{last.get('ts', '')[:10]}\")\n        квота = self._kvota_kompanii(inn=inn, email=email)\n        if квота is not None:\n            return (f\"company_quota>={self._potolok_kompanii()}\"\n                    f\"/{self._okno_dney()}d:{квота.get('ts', '')[:10]}\")\n        return None"
 ],
 [
  "    def _recent_contact(self, *, inn: Optional[str], email: str):\n        from datetime import datetime, timedelta, timezone\n        last = None\n        try:\n            last = self._store.last_contact(email=email, inn=inn)\n        except Exception:  # noqa: BLE001 - нет таблицы у мок-store\n            return None\n        if not last:\n            return None\n        ts = str(last.get(\"ts\") or \"\")\n        try:\n            then = datetime.fromisoformat(ts.replace(\"Z\", \"+00:00\"))\n            if then.tzinfo is None:\n                then = then.replace(tzinfo=timezone.utc)\n        except ValueError:\n            return last  # дата не парсится → консервативно считаем недавним\n        if datetime.now(timezone.utc) - then < timedelta(days=RECENT_CONTACT_DAYS):\n            return last\n        return None\n",
  "    def _okno_dney(self) -> int:\n        \"\"\"Окно повторного контакта в днях (confirm.recent_contact_days).\"\"\"\n        try:\n            return max(0, int(self._config.get(\"confirm.recent_contact_days\",\n                                               RECENT_CONTACT_DAYS)))\n        except (TypeError, ValueError, AttributeError):\n            return RECENT_CONTACT_DAYS\n\n    def _potolok_kompanii(self) -> int:\n        \"\"\"Сколько РАЗНЫХ адресов компании можно тронуть за окно.\n        confirm.company_contacts_per_period; 0 — потолка нет.\"\"\"\n        try:\n            return max(0, int(self._config.get(\n                \"confirm.company_contacts_per_period\",\n                COMPANY_CONTACTS_PER_PERIOD)))\n        except (TypeError, ValueError, AttributeError):\n            return COMPANY_CONTACTS_PER_PERIOD\n\n    def _v_okne(self, ts: str) -> Optional[bool]:\n        \"\"\"Метка времени попадает в окно? None — дату не разобрать.\"\"\"\n        from datetime import datetime, timedelta, timezone\n        try:\n            then = datetime.fromisoformat(str(ts or \"\").replace(\"Z\", \"+00:00\"))\n            if then.tzinfo is None:\n                then = then.replace(tzinfo=timezone.utc)\n        except ValueError:\n            return None\n        return datetime.now(timezone.utc) - then < timedelta(days=self._okno_dney())\n\n    def _recent_contact(self, *, email: str, inn: Optional[str] = None):\n        \"\"\"Последняя отправка на ЭТОТ ЖЕ адрес в окне — или None.\n\n        Раньше сюда передавался ещё и ИНН, а last_contact сверяет по email ИЛИ\n        ИНН, поэтому любое письмо в компанию закрывало ей все адреса на 90\n        дней. Компанию теперь стережёт _kvota_kompanii, а здесь — только сам\n        адрес. Параметр inn оставлен ради старых вызовов и игнорируется.\"\"\"\n        last = None\n        try:\n            last = self._store.last_contact(email=email)\n        except Exception:  # noqa: BLE001 - нет таблицы у мок-store\n            return None\n        if not last:\n            return None\n        в_окне = self._v_okne(str(last.get(\"ts\") or \"\"))\n        if в_окне is None:\n            return last  # дата не парсится → консервативно считаем недавним\n        return last if в_окне else None\n\n    def _kvota_kompanii(self, *, inn: Optional[str], email: str):\n        \"\"\"Потолок разных адресов компании за окно: запись последней отправки,\n        если потолок уже выбран, иначе None.\n\n        Считаем РАЗНЫЕ адреса, а не письма: пять повторов на один info@ —\n        это один потревоженный человек, а пять разных ящиков — пять.\"\"\"\n        потолок = self._potolok_kompanii()\n        цифры = \"\".join(c for c in str(inn or \"\") if c.isdigit())\n        if not потолок or not цифры:\n            return None\n        свой = str(email or \"\").strip().lower()\n        try:\n            строки = self._store.send_log_history(inn=цифры, limit=500)\n        except Exception:  # noqa: BLE001 - нет таблицы у мок-store\n            return None\n        адреса, последняя = {}, None\n        for r in строки or []:\n            if str(r.get(\"outcome\") or \"\") != \"sent\":\n                continue\n            адрес = str(r.get(\"email\") or \"\").strip().lower()\n            if not адрес or адрес == свой:\n                continue\n            if self._v_okne(str(r.get(\"ts\") or \"\")) is False:\n                continue\n            адреса[адрес] = r\n            ts = str(r.get(\"ts\") or \"\")\n            if последняя is None or ts > str(последняя.get(\"ts\") or \"\"):\n                последняя = r\n        return последняя if len(адреса) >= потолок else None\n\n"
 ]
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if "COMPANY_CONTACTS_PER_PERIOD" in т:
    print("правка уже стоит — ничего не делаю")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    n = т.count(стар)
    if n != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (n, стар[:70]))
        raise SystemExit(1)
для_отката = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)

бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(для_отката)
    f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т)
    f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as e:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(для_отката)
        f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % e)
    raise SystemExit(1)
print("готово: %d -> %d байт, бэкап %s" % (len(для_отката), len(т), os.path.basename(бэк)))
