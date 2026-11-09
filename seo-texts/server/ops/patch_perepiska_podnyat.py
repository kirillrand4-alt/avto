# -*- coding: utf-8 -*-
"""«ВЕДЁТСЯ ПЕРЕПИСКА» + НОВОЕ ПИСЬМО = ЛИД СНОВА В ЛЕНТЕ (владелец 09.11:
«если ведётся переписка и там новый ответ, возвращай его в новый лид всегда
(даже автоответ)»).

Было: _podnyat_otlozhennuyu поднимала только not_interested/avtootvet/v_otpuske
и только по живому ответу (не отказ, не автоответ). Лид в статусе perepiska
новым письмом не поднимался вовсе - ответ ложился в переписку молча.
Стало: лид в perepiska поднимается в «new» на ЛЮБОЕ новое входящее, в том числе
отказ и автоответ. Для прочих статусов поведение прежнее.

Правка в leaddesk.py по якорю, .bak, py_compile, откат. [--primenit]"""
import io
import os
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\leaddesk.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ПАРЫ = [
    ('''        if str(статус_вызова or "new") != "new":
            return
        if str(reply_kind or "") in self._НЕ_ПОДНИМАЮТ:
            return
        try:
            lead = self._store.get_lead(lead_id)
            if lead is None:
                return
''',
     '''        # «ВЕДЁТСЯ ПЕРЕПИСКА» ПОДНИМАЕТСЯ ВСЕГДА (владелец 09.11): продавец
        # ведёт разговор и обязан увидеть любое новое письмо - даже отказ и
        # автоответ («в отпуске до…» тоже меняет его планы).
        try:
            _lead = self._store.get_lead(lead_id)
            if _lead is not None and str(getattr(_lead, "status", "") or "") == "perepiska":
                self._store.update_lead_cas(
                    lead_id, expected_version=_lead.version,
                    action="поднят новым письмом из переписки", status="new")
                return
        except Exception:  # noqa: BLE001 - подъём не должен ронять приём почты
            logger.exception("карточка %s из переписки не поднялась", lead_id)
        if str(статус_вызова or "new") != "new":
            return
        if str(reply_kind or "") in self._НЕ_ПОДНИМАЮТ:
            return
        try:
            lead = self._store.get_lead(lead_id)
            if lead is None:
                return
'''),
]

т = io.open(ФАЙЛ, encoding="utf-8").read()
print("файл: %d Б, строк %d" % (len(т.encode("utf-8")), len(т.splitlines())))
ошибок = 0
for i, (стар, нов) in enumerate(ПАРЫ, 1):
    n = т.count(стар)
    print("   якорь %d: вхождений %d %s" % (i, n, "ок" if n == 1 else "ОТКАЗ"))
    if n != 1:
        ошибок += 1
if ошибок:
    print("\nякоря не уникальны — не трогаю файл")
    raise SystemExit(1)

новый = т
for стар, нов in ПАРЫ:
    новый = новый.replace(стар, нов, 1)
print("\nстанет строк: %d (было %d)" % (len(новый.splitlines()),
                                        len(т.splitlines())))
if not ПРИМЕНИТЬ:
    print("\n[сухой прогон] применить — с ключом --primenit")
    raise SystemExit(0)

запас = "%s.bak-%d" % (ФАЙЛ, int(time.time()))
io.open(запас, "w", encoding="utf-8").write(т)
print("бэкап: %s" % запас)
with io.open(ФАЙЛ, "w", encoding="utf-8") as f:
    f.write(новый)
    f.flush()
    os.fsync(f.fileno())
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    print("py_compile: ок")
except Exception as e:                                        # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    print("КОМПИЛЯЦИЯ УПАЛА, откатил: %s" % str(e)[:200])
    raise SystemExit(1)
print("\n=== ИТОГ ===")
print("правки на месте. Нужен перезапуск службы, чтобы панель их подхватила.")
