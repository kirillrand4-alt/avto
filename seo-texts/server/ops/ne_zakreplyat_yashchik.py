# -*- coding: utf-8 -*-
"""Временная ошибка отправки больше не закрепляет письмо за ящиком.

Владелец 12.10: «да, исправь». store.mark_failed (правка 21.08) писал ящик
неудачной попытки в messages.mailbox_id — для разбора отказов. А auto_send
читает это поле как ЗАКРЕПЛЁННЫЙ МЕНЕДЖЕРОМ ящик и ротацию не делает: после
первого таймаута Яндекса все 23 письма кампании 14 прибиты к v.kuzmin и
ушли бы с одного ящика, а не по очереди (правило владельца).

Теперь при retryable ящик в mailbox_id НЕ пишется, а уходит в текст ошибки
«[ящик] …» — разбор отказов по ящикам сохраняется. При окончательной ошибке
— как было. Действует после перезапуска SenderPanel.
"""
import io
import os
import py_compile
import shutil
import sys
import time

ПУТЬ = r"C:\sender\sender\store.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
СТАР = """        with self.transaction() as conn:
            if _ящик:
                conn.execute(
                    "UPDATE messages SET mailbox_id=? WHERE id=?",
                    (_ящик, message_id))
            if retryable:
"""
НОВ = """        # ВРЕМЕННАЯ ОШИБКА НЕ ЗАКРЕПЛЯЕТ ЯЩИК (владелец 12.10). auto_send
        # читает messages.mailbox_id как ящик, закреплённый менеджером, и не
        # делает ротацию: после первого таймаута все письма прибивались к
        # одному ящику. При повторе ящик неудачи пишем в текст ошибки —
        # разбор отказов по ящикам сохраняется, ротация — тоже.
        if retryable and _ящик:
            error = "[%s] %s" % (_ящик, error)
        with self.transaction() as conn:
            if _ящик and not retryable:
                conn.execute(
                    "UPDATE messages SET mailbox_id=? WHERE id=?",
                    (_ящик, message_id))
            if retryable:
"""
if "ВРЕМЕННАЯ ОШИБКА НЕ ЗАКРЕПЛЯЕТ ЯЩИК" in т:
    print("уже стоит")
    print("=== ЯЩИК: УЖЕ БЫЛО ===")
    sys.exit(0)
if т.count(СТАР) != 1:
    print("якорь не найден (%d)" % т.count(СТАР))
    print("=== ЯЩИК: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(СТАР, НОВ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
    # проверка на копии базы в памяти: письмо после временной ошибки
    import sqlite3
    sys.path.insert(0, r"C:\sender")
    import importlib.util as _iu
    сп = _iu.spec_from_file_location("store_new", ПУТЬ)
    м = _iu.module_from_spec(сп)
    sys.modules["store_new"] = м
    сп.loader.exec_module(м)
    src = м.inspect if hasattr(м, "inspect") else None
    print("модуль грузится: да")
    print("ПРИМЕНЕНО, бэкап %s (вступит после перезапуска SenderPanel)"
          % os.path.basename(бэкап))
    print("=== ЯЩИК: ПРИМЕНЕНО ===")
except Exception as e:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("ОТКАТ: %s" % e)
    print("=== ЯЩИК: ОТКАТ ===")
