# -*- coding: utf-8 -*-
"""Расшифровать уже записанные кракозябры: utf-8, прочитанный как cp1251.

Обратная операция однозначна: берём текст, кодируем обратно в cp1251 и читаем
как utf-8. Правим ТОЛЬКО когда обратный ход удался и на выходе появилась
нормальная кириллица — иначе оставляем как есть.
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"
ЖУРНАЛ = r"C:\sender\_ops\pochinka-krakozyabr.jsonl"
ПРИМЕТА = re.compile(r"[РС][ЂЅ‚ѓ„…†‡€‰Љ‹ЊЋЏђ‘’“”•–—™љ›њћџ\u0400-\u04FF]")


def расшифровать(т: str):
    """Обратный ход. Сниппет обрезан по 4000 знаков и может кончиться посреди
    многобайтового символа — поэтому строгий разбор, а при обрыве на хвосте
    добираем с игнором: теряется только сам обрубок."""
    try:
        сырое = т.encode("cp1251")
    except UnicodeEncodeError:
        return None
    try:
        новое = сырое.decode("utf-8")
    except UnicodeDecodeError:
        новое = сырое.decode("utf-8", errors="ignore")
    if not re.search(r"[а-яА-Я]{4}", новое):
        return None
    return новое


c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
правки = []
for r in c.execute("SELECT id, detail_json FROM events "
                   " WHERE event_type IN ('reply','reply_auto','other','bounce',"
                   "                      'complaint')"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    т = str(d.get("snippet") or "")
    if not т or len(ПРИМЕТА.findall(т[:400])) < 5:
        continue
    новое = расшифровать(т)
    if новое and новое != т:
        правки.append((r["id"], т[:60], новое[:60]))
print("событий с кракозябрами: %d" % len(правки))
for eid, было, стало in правки[:12]:
    print("   ev=%-7s было: %s" % (eid, было))
    print("            стало: %s" % стало)
c.close()

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit починю")
    raise SystemExit(0)

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
ж = open(ЖУРНАЛ, "a", encoding="utf-8")
сделано = 0
try:
    with store.transaction() as conn:
        for eid, _, _ in правки:
            строка = conn.execute("SELECT detail_json FROM events WHERE id=?",
                                  (eid,)).fetchone()
            d = json.loads(строка["detail_json"] or "{}")
            т = str(d.get("snippet") or "")
            новое = расшифровать(т)
            if not новое:
                continue
            ж.write(json.dumps({"id": eid, "bylo": т}, ensure_ascii=False) + "\n")
            d["snippet"] = новое
            d["kodirovka_pochinena"] = "utf-8 под шапкой cp1251"
            conn.execute("UPDATE events SET detail_json=? WHERE id=?",
                         (json.dumps(d, ensure_ascii=False), eid))
            сделано += 1
    ж.flush()
    os.fsync(ж.fileno())
finally:
    ж.close()
print("\nпочинено: %d (журнал %s)" % (сделано, ЖУРНАЛ))
