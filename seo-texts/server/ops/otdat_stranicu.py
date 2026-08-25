# -*- coding: utf-8 -*-
"""Положить страницу каталога на дроп и показать сырой ответ модели.

Тринадцать страниц подряд дали ноль компаний. Причин ровно три: на
страницах правда нет карточек, модель не видит картинку, или ответ не
разбирается. Чтобы не гадать — смотрим и страницу глазами, и сырой ответ.
"""
import base64
import glob
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, r"C:\sender\seo-texts")
sys.path.insert(0, r"C:\sender")
КАТАЛОГ = r"C:\sender\_ops\belarus"
КАРТИНКИ = os.path.join(КАТАЛОГ, "pages")
НОМЕР = int(sys.argv[1]) if len(sys.argv) > 1 else 21

import fitz  # noqa: E402
файл = glob.glob(os.path.join(КАТАЛОГ, "*.pdf"))[0]
док = fitz.open(файл)
путь = os.path.join(КАРТИНКИ, "p%03d.png" % НОМЕР)
if not os.path.exists(путь):
    док.load_page(НОМЕР - 1).get_pixmap(dpi=150).save(путь)
print("страница %d: %s (%d б)" % (НОМЕР, путь, os.path.getsize(путь)))

# 1. На дроп, чтобы посмотреть глазами.
токен = ""
for п in (r"C:\sender\server\runner-secrets.env",):
    if os.path.exists(п):
        for с in io.open(п, encoding="utf-8", errors="replace"):
            if с.startswith("DROP_TOKEN="):
                токен = с.split("=", 1)[1].strip()
к = ("$ProgressPreference='SilentlyContinue'; "
     "Invoke-WebRequest -Uri 'https://parsercompressor.online/drop/"
     "katalog-p%03d.png' -Method PUT -UseBasicParsing -Headers @{'X-Drop-Token'='%s'} "
     "-InFile '%s'" % (НОМЕР, токен, путь))
в = subprocess.run(["powershell", "-NoProfile", "-Command", к],
                   capture_output=True, timeout=300)
print("на дроп: rc=%s %s" % (в.returncode,
                             (в.stdout or в.stderr).decode("cp866", "replace")[:120]))

# 2. Сырой ответ модели на эту же страницу.
from gen_provider import call, make_client  # noqa: E402
b64 = base64.b64encode(open(путь, "rb").read()).decode()
сообщения = [{"role": "user", "content": [
    {"type": "image", "source": {"type": "base64",
                                 "media_type": "image/png", "data": b64}},
    {"type": "text", "text": "Опиши коротко, что ты видишь на этой картинке: "
                             "тип страницы, есть ли карточки компаний, "
                             "перечисли названия, если они есть."}]}]
ответ = call(make_client(), сообщения, model="claude-fable-5", attempts=2,
             thinking=False)
print("\n=== ЧТО ВИДИТ МОДЕЛЬ ===")
текст = ответ if isinstance(ответ, str) else "".join(
    б.text for б in getattr(ответ, "content", [])
    if getattr(б, "type", "") == "text")
print(текст[:1500] if текст else "(пусто) тип ответа: %s, поля: %s"
      % (type(ответ), dir(ответ)[:20]))
