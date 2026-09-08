# -*- coding: utf-8 -*-
"""Только чтение: маршрут панели, который выбирает ящик и адрес для ответа."""
import io
import os
import re

# 1) как называется метод отправки ответа
имя = None
п_send = None
for корень in (r"C:\sender\sender",):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "tests")]
        for ф in фф:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            i = т.find("kopiya_otvetov_v_otpravlennye")
            if i > 0:
                j = т.rfind("\n    def ", 0, i)
                имя = re.match(r"\n    def (\w+)", т[j:j + 80]).group(1)
                п_send = п
                print("метод отправки ответа: %s%s"
                      % (имя, str(re.search(r"\n    def %s\(([^)]*)" % имя,
                                            т).group(1))[:400]))
                break

print("\n=== КТО ЕГО ЗОВЁТ ===")
for корень in (r"C:\sender\server", r"C:\sender\web"):
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            if имя and (имя + "(") in т:
                for м in re.finditer(re.escape(имя) + r"\(", т):
                    нач = max(т.rfind("\n@", 0, м.start()),
                              т.rfind("\ndef ", 0, м.start()),
                              т.rfind("\nasync def ", 0, м.start()))
                    нач = нач if нач > 0 else max(0, м.start() - 3000)
                    print("\n" + "=" * 12 + " %s " % п.replace(r"C:\sender", "")
                          + "=" * 12)
                    print(т[нач:м.start() + 500])
                    break
