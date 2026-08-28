# -*- coding: utf-8 -*-
"""Отбивки почтовых серверов вон из ленты переписки КОМПАНИИ (store.py).

Карточка лида уходит в отдел продаж; DSN по соседнему мёртвому адресу читается
там как ответ клиента. Событие в журнале остаётся — гейты и kill-switch считают
event_type='bounce'."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\store.py"
ЗАМЕНЫ = json.loads(r'''[["    def dialog_thread_company(self, inn: str, *, limit: int = 200) -> list[dict]:\n        \"\"\"Вся переписка с КОМПАНИЕЙ (#64): по всем адресам всех получателей\n        этого ИНН. Хронология единая; каждый элемент несёт email, чтобы оператор\n        видел, с каким контактом шёл разговор.\n", "    # Уведомления почтовых серверов: это НЕ переписка с компанией. В карточке\n    # лида (её владелец пересылает в отдел продаж) отбивка по мёртвому адресу\n    # читается как ответ клиента и сбивает продажника с толку — 28.08 по\n    # «Импэкс-Дон» рядом с живым ответом висело «Ваше сообщение не доставлено…\n    # user not found» по СОСЕДНЕМУ адресу той же компании. Из ленты компании их\n    # убираем; в технической ленте контакта (dialog_thread) и в гейтах/счётчиках\n    # отбивок они остаются как были.\n    _OTBIVKI_NE_PEREPISKA = (\"bounce\", \"dsn\", \"bounce_skryt\")\n\n    def dialog_thread_company(self, inn: str, *, limit: int = 200,\n                              bez_otbivok: bool = True) -> list[dict]:\n        \"\"\"Вся переписка с КОМПАНИЕЙ (#64): по всем адресам всех получателей\n        этого ИНН. Хронология единая; каждый элемент несёт email, чтобы оператор\n        видел, с каким контактом шёл разговор.\n\n        bez_otbivok=True (по умолчанию) выбрасывает уведомления почтовых серверов\n        (bounce/DSN) — они не переписка, а служебный шум; передайте False, если\n        нужна полная техническая лента.\n"], ["        for rid, email in rids:\n            for it in self.dialog_thread(rid, limit=lim):\n                it[\"email\"] = email\n                if it.get(\"message_id\") is not None:", "        for rid, email in rids:\n            for it in self.dialog_thread(rid, limit=lim):\n                it[\"email\"] = email\n                if (bez_otbivok\n                        and str(it.get(\"kind\") or \"\") in self._OTBIVKI_NE_PEREPISKA):\n                    continue\n                if it.get(\"message_id\") is not None:"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if "_OTBIVKI_NE_PEREPISKA" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %s" % (т.count(стар), стар[:70]))
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
