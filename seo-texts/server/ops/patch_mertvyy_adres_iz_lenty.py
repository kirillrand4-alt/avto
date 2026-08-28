# -*- coding: utf-8 -*-
"""Письмо, которое не дошло, — тоже вон из ленты компании (store.py).

Отбивку мы уже не показываем; если оставить рядом «мы написали» на мёртвый
адрес, продажник прочтёт это как «написали и не ответили». Убираем адрес
целиком — но только когда с него не было ни одного живого ответа."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\store.py"
ЗАМЕНЫ = json.loads(r'''[["        for rid, email in rids:\n            for it in self.dialog_thread(rid, limit=lim):\n                it[\"email\"] = email\n                if (bez_otbivok\n                        and str(it.get(\"kind\") or \"\") in self._OTBIVKI_NE_PEREPISKA):\n                    continue\n                if it.get(\"message_id\") is not None:", "        # Адреса, по которым переписки не было: письмо отбилось, ответа нет.\n        # Показывать продажнику «мы написали» туда, куда письмо не дошло, —\n        # то же враньё, что и показывать саму отбивку.\n        мёртвые: set = set()\n        for rid, email in rids:\n            свои = self.dialog_thread(rid, limit=lim)\n            if bez_otbivok:\n                отбилось = any(str(i.get(\"kind\") or \"\")\n                               in self._OTBIVKI_NE_PEREPISKA for i in свои)\n                ответили = any(i.get(\"direction\") == \"in\"\n                               and str(i.get(\"kind\") or \"\")\n                               not in self._OTBIVKI_NE_PEREPISKA for i in свои)\n                if отбилось and not ответили:\n                    мёртвые.add(str(email or \"\").strip().lower())\n                    continue\n                свои = [i for i in свои if str(i.get(\"kind\") or \"\")\n                        not in self._OTBIVKI_NE_PEREPISKA]\n            for it in свои:\n                it[\"email\"] = email\n                if it.get(\"message_id\") is not None:"], ["        for r in crs:\n            mid = r[\"message_id\"]\n            if mid is not None and int(mid) in seen_msg:\n                continue          # то же письмо уже пришло из messages, с телом", "        for r in crs:\n            mid = r[\"message_id\"]\n            if mid is not None and int(mid) in seen_msg:\n                continue          # то же письмо уже пришло из messages, с телом\n            if str(r[\"email\"] or \"\").strip().lower() in мёртвые:\n                continue          # адрес мёртвый: письма туда не было"], ["        for r in reversed(logs):          # по возрастанию времени: склейка 1:1\n            rfc = r[\"rfc_message_id\"]\n            mid = r[\"message_id\"]", "        for r in reversed(logs):          # по возрастанию времени: склейка 1:1\n            if str(r[\"email\"] or \"\").strip().lower() in мёртвые:\n                continue          # иначе снятое письмо вернётся сюда без тела\n            rfc = r[\"rfc_message_id\"]\n            mid = r[\"message_id\"]"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if "мёртвые: set = set()" in т:
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
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
