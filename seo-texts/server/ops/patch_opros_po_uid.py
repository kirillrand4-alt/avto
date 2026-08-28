# -*- coding: utf-8 -*-
"""Опрос ящика по UID вместо порядкового номера письма."""
import io
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\imap_watcher.py"
ЗАМЕНЫ = [
 [
  "            typ, data = imap.search(None, *crit)\n            if typ != \"OK\":\n                logger.warning(f\"IMAP search failed for {mailbox_id}: {typ}\")",
  "            # ИЩЕМ ПО UID, А НЕ ПО ПОРЯДКОВОМУ НОМЕРУ. imap.search отдаёт\n            # НОМЕРА В ПАПКЕ, а ключ дедупа события собирается как\n            # imap:{uidvalidity}:{номер}:{kind} — то есть номер выдавался за\n            # UID. Номера сдвигаются при удалении писем: 28.08 в шести ящиках\n            # из двадцати одного они разошлись с UID (у i.lyapin@kompressor-\n            # air-expert.ru — у 50 писем из 52). Новое письмо получало ключ,\n            # уже занятый старым, и молча отбрасывалось как «уже видели» —\n            # так терялись живые ответы клиентов.\n            typ, data = imap.uid(\"SEARCH\", None, *crit)\n            if typ != \"OK\":\n                logger.warning(f\"IMAP uid search failed for {mailbox_id}: {typ}\")"
 ],
 [
  "                typ, msg_data = imap.fetch(uid, \"(BODY.PEEK[])\")",
  "                typ, msg_data = imap.uid(\"FETCH\", uid, \"(BODY.PEEK[])\")"
 ],
 [
  "                            imap.store(uid, \"+FLAGS\", \"\\\\Seen\")",
  "                            imap.uid(\"STORE\", uid, \"+FLAGS\", \"\\\\Seen\")"
 ]
]

т = io.open(ПУТЬ, encoding="utf-8").read()
if 'imap.uid("SEARCH"' in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:60]))
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
