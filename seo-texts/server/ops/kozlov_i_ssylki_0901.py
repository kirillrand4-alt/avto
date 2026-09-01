# -*- coding: utf-8 -*-
"""Вернуть нулевой потолок a.kozlov и проверить ссылки в письмах.

Без primenit потолок не трогает; проверка ссылок только читает."""
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ПРИМЕНИТЬ = "primenit" in sys.argv
Я = "a.kozlov@zernosort.ru"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ССЫЛКИ В ОТПРАВЛЕННЫХ ПИСЬМАХ (последние 200) ===")
тела = [str(р["body_rendered"] or "") for р in s.execute(
    "SELECT body_rendered FROM messages WHERE status='sent'"
    " AND body_rendered IS NOT NULL AND body_rendered<>''"
    " ORDER BY id DESC LIMIT 200")]
if not тела:
    тела = [str(р["body"] or "") for р in s.execute(
        "SELECT body FROM confirm_reviews WHERE status IN ('sent','approved')"
        " ORDER BY id DESC LIMIT 200")]
url = re.compile(r"https?://[^\s<>\"']+", re.I)
c = Counter()
всего_сссылок = 0
for t in тела:
    н = url.findall(t)
    всего_сссылок += len(н)
    for u in н:
        дом = u.split("//", 1)[-1].split("/")[0].lower()
        c[дом] += 1
print("  писем просмотрено: %d" % len(тела))
print("  писем СО ссылками: %d" % sum(1 for t in тела if url.search(t)))
print("  всего ссылок: %d" % всего_сссылок)
for k, v in c.most_common(10):
    print("     %-40s %d" % (k, v))
print("  упоминаний prokompressor.ru: %d"
      % sum(t.lower().count("prokompressor") for t in тела))

print("\n=== ЗАГОЛОВКИ: List-Unsubscribe и трекинг ===")
for к in ("tracking.open_enabled", "tracking.click_enabled", "unsub.base_url",
          "unsubscribe.base_url", "unsub.enabled", "compliance.unsubscribe_url"):
    try:
        print("  %-32s = %r" % (к, cfg.get(к)))
    except Exception:
        print("  %-32s = (нет ключа)" % к)
import io
import os
try:
    src = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
                  errors="replace").read()
    for м in ("List-Unsubscribe", "unsub_token", "unsubscribe"):
        print("  в sender.py «%s»: %d вхождений" % (м, src.count(м)))
except Exception as ex:
    print("  ", str(ex)[:60])

print("\n=== ПОТОЛОК a.kozlov ===")
v = store.get_setting("send_limits")
if isinstance(v, str) and v:
    v = json.loads(v)
if not isinstance(v, dict):
    v = {}
per = dict(v.get("per_mailbox") or {})
print("  сейчас: %r" % per.get(Я, "не задан"))
if ПРИМЕНИТЬ:
    per[Я] = 0
    v["per_mailbox"] = per
    store.set_setting("send_limits", v)
    store.set_mailbox_paused(Я, True, "владелец: ящик в спаме, не использовать")
    print("  ПРИМЕНЕНО: потолок 0 и пауза")

print("\n=== ИТОГ ===")
v2 = store.get_setting("send_limits")
if isinstance(v2, str) and v2:
    v2 = json.loads(v2)
p2 = (v2 or {}).get("per_mailbox") or {}
print("  потолок a.kozlov: %r" % p2.get(Я, "не задан"))
р = s.execute("SELECT paused, pause_reason FROM mailbox_state WHERE mailbox_id=?",
              (Я,)).fetchone()
print("  paused=%s | %s" % (р["paused"] if р else "?",
                            str(р["pause_reason"] if р else "")[:70]))
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "показ без изменений"))
