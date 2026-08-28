# -*- coding: utf-8 -*-
"""Потолок компании должен считать и НЕОТПРАВЛЕННЫЕ письма."""
import io
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\confirm.py"
ЗАМЕНЫ = [
 [
  "        return последняя if len(адреса) >= потолок else None\n\n\n    # -- постановка в очередь",
  "        # ПИСЬМА, КОТОРЫЕ ЕЩЁ НЕ УШЛИ, ТОЖЕ ЗАНИМАЮТ ПОТОЛОК. send_log знает\n        # только отправленное, и две копии, поставленные разными партиями до\n        # того, как хоть одна ушла, обе проходили проверку законно: у ТЗК\n        # «Имсб» два письма разошлись с разницей в две минуты (владелец\n        # 28.08). Считаем и то, что уже стоит в расписании.\n        for адрес in self._adresa_v_rabote(цифры):\n            if адрес and адрес != свой:\n                адреса.setdefault(адрес, {\"ts\": \"\"})\n        return последняя if len(адреса) >= потолок else None\n\n    def _adresa_v_rabote(self, inn_cifry: str) -> set:\n        \"\"\"Адреса компании, письма которым уже стоят в очереди отправки.\"\"\"\n        try:\n            store = self._store\n            with getattr(store, \"_lock\"):\n                строки = store._conn.execute(\n                    \"SELECT LOWER(r.email) FROM messages m \"\n                    \"  JOIN recipients r ON r.id = m.recipient_id \"\n                    \" WHERE r.inn = ? AND m.status IN \"\n                    \"       ('scheduled','sending','pending_review')\",\n                    (inn_cifry,)).fetchall()\n            return {str(x[0]) for x in строки if x and x[0]}\n        except Exception:  # noqa: BLE001 - сбой подсчёта не рвёт очередь\n            return set()\n\n\n    # -- постановка в очередь"
 ]
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if "_adresa_v_rabote" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d)" % т.count(стар))
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
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
