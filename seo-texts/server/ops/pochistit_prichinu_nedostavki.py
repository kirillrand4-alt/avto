# -*- coding: utf-8 -*-
"""Причину недоставки показывать словами, а не питоновским кортежем.

Сейчас оператор видит «не доставлена: (550, b'Message was not accepted --
invalid mailbox.  Local mailbox la». Это repr исключения smtplib, а не
сообщение человеку.
"""
import io
import re
import shutil
import time

ФАЙЛ = r"C:\sender\sender\store.py"
ЯКОРЬ = '''                elif str(пм["s"]) == "failed":
                    почему = str(пм["e"] or "")[:70]
                    слово = "не доставлена" + (f": {почему}" if почему else "")
                    состояние = "failed"
'''
НОВОЕ = '''                elif str(пм["s"]) == "failed":
                    # В last_error лежит repr исключения smtplib:
                    # (550, b'Message was not accepted -- invalid mailbox...').
                    # Оператору нужен код и текст, а не кортеж с байтами.
                    сыро = str(пм["e"] or "")
                    м = re.search(r"\\((\\d{3}),\\s*b?['\\"](.+?)['\\"]", сыро,
                                  re.S)
                    почему = (f"{м.group(1)} {м.group(2)}" if м else сыро)
                    почему = " ".join(почему.split())[:90]
                    слово = "не доставлена" + (f": {почему}" if почему else "")
                    состояние = "failed"
'''
s = io.open(ФАЙЛ, encoding="utf-8").read()
if "repr исключения smtplib" in s:
    print("уже вшито")
    raise SystemExit(0)
if s.count(ЯКОРЬ) != 1:
    print(f"якорь найден {s.count(ЯКОРЬ)} раз - не трогаю")
    raise SystemExit(2)
if "\nimport re" not in s and not s.startswith("import re"):
    print("ВНИМАНИЕ: re в store.py не импортирован")
рез = ФАЙЛ + ".bak-" + time.strftime("%m%d-%H%M%S")
shutil.copy2(ФАЙЛ, рез)
io.open(ФАЙЛ, "w", encoding="utf-8").write(s.replace(ЯКОРЬ, НОВОЕ))
print("бэкап:", рез)
import py_compile                                                # noqa: E402
py_compile.compile(ФАЙЛ, doraise=True)
print("компилируется")
