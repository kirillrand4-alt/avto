# -*- coding: utf-8 -*-
"""Что из починок 17.08 реально лежит на сервере, а что только в репозитории.

Урок того же дня: я выложил починку сохранения текста в 12:43, когда круг
уже шёл с 12:41 - питон читает файл при старте процесса, и починка не
отработала ни разу. Поэтому перед запуском смотрим не в репозиторий, а в
сам сервер: есть ли в развёрнутых модулях приметы каждой правки.

Оп сам ничего не деплоит и не меняет.
"""
import io
import os
import time

ПРИМЕТЫ = {
    r"C:\sender\sender\ai_letter.py": [
        ("добор оборванного JSON", "_dobrat_obryv"),
        ("кавычки внутри JSON", "_починить_json"),
        ("расходящиеся числа паспорта", "_rashodyashchiesya_chisla"),
        ("запрет марок оборудования", "marki_oborudovaniya"),
    ],
    r"C:\sender\sender\store.py": [
        ("стоп-лист на входе в очередь", "allow_suppressed"),
        ("идемпотентность очереди", "ON CONFLICT(dedup_key) DO NOTHING"),
    ],
    r"C:\sender\sender\sender.py": [
        ("направление письма, а не только компании", "_napravlenie_pisma"),
        ("гейт письмо-против-ящика", "letter_vs_mailbox"),
    ],
    r"C:\sender\sender\review_lenses.py": [
        ("усилие линз из окружения", "LETTER_EFFORT"),
        ("срыв ловится и повторяется", "_eto_sryv"),
    ],
}

for путь, приметы in ПРИМЕТЫ.items():
    if not os.path.exists(путь):
        print(f"{os.path.basename(путь)}: ФАЙЛА НЕТ")
        continue
    т = io.open(путь, encoding="utf-8", errors="replace").read()
    когда = time.strftime("%Y-%m-%d %H:%M:%S",
                          time.localtime(os.path.getmtime(путь)))
    print(f"\n{os.path.basename(путь)}  ({len(т)} байт, изменён {когда})")
    for имя, метка in приметы:
        print(f"  {'ЕСТЬ ' if метка in т else 'НЕТ  '} {имя}")
