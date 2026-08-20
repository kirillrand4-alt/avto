# -*- coding: utf-8 -*-
"""Стоит ли в боевом auto_send заслон «уже писали» и подтяжка окна."""
import io

Ф = r"C:\sender\sender\auto_send.py"
s = io.open(Ф, encoding="utf-8", errors="replace").read()
for метка, кусок in (
        ("заслон «уже писали» в момент отправки", 'auto_send:уже писали'),
        ("проверка по адресу И по ИНН", "sent_flags("),
        ("подтяжка очереди под окно", "podtyanut_pod_okno"),
):
    print(f"  {'ЕСТЬ ' if кусок in s else 'НЕТ  '} {метка}")
print(f"  файл: {len(s)} знаков")
