# -*- coding: utf-8 -*-
"""Полный ответ главного механика в карточку лида 253 («Импэкс-Дон»).

push_warm_lead кладёт в lead.need первый абзац входящего — продажник видел
только «данной темой занимается мой зам», без подписи автора и без его
телефона. Автор ответа — А.Н.Кобзин, главный механик; его письмо переслал нам
секретарский ящик mail@impeks-don.ru. Собираем текст из события 305587 и
кладём целиком.
"""
import io
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ЛИД, СОБЫТИЕ = 253, 305587
БАЗА = r"C:\sender\sender.db"
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402

ТЕКСТ = (
    "Добрый день, тема очень актуальная по стационарным компрессорам. "
    "Данной темой занимается мой зам Поляков Виталий Валерьевич, "
    "+7 949 311 14 62 — проработайте этот вопрос с ним.\n"
    "\n"
    "С уважением, А.Н. Кобзин\n"
    "Главный механик ООО «Импэкс-Дон»\n"
    "тел. мобильный +7 (949) 320 06 53\n"
    "\n"
    "(ответ главного механика от 28.08.2026 12:17 с ящика 210@impeks-don.ru, "
    "к нам переслан с mail@impeks-don.ru)")

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
л = c.execute("SELECT need, phone, reply_kind FROM leads WHERE id=?",
              (ЛИД,)).fetchone()
print("было в карточке [%d знаков]:" % len(str(л["need"] or "")))
print("  %s" % str(л["need"] or "").replace("\n", " | "))
print("телефон в карточке: %s | тип ответа: %s" % (л["phone"], л["reply_kind"]))
c.close()
print()
print("станет [%d знаков]:" % len(ТЕКСТ))
for стр in ТЕКСТ.split("\n"):
    print("  %s" % стр)

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit запишу")
    raise SystemExit(0)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
with store.transaction() as conn:
    n = conn.execute("UPDATE leads SET need=?, updated_at=? WHERE id=?",
                     (ТЕКСТ, time.strftime("%Y-%m-%dT%H:%M:%S"), ЛИД)).rowcount
print("\nобновлено карточек: %d" % n)
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
print("в базе сейчас [%d знаков]"
      % len(str(c.execute("SELECT need FROM leads WHERE id=?",
                          (ЛИД,)).fetchone()[0] or "")))
c.close()
