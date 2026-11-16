# -*- coding: utf-8 -*-
"""Проверка дублей ручной отправки 16.11: по журналу razobrat-ozhidanie-1611.jsonl и по messages (sent за сегодня
на один адрес больше одного раза). Только чтение."""
import io, json, sqlite3
from collections import Counter
з = [json.loads(с) for с in io.open(r"C:\sender\_ops\razobrat-ozhidanie-1611.jsonl", encoding="utf-8")]
от = Counter(x["karta"] for x in з if "otpravka" in x)
print("записей отправки:", sum(от.values()), "карточек:", len(от), "повторов в журнале:", {k: v for k, v in от.items() if v > 1})
print("исходы:", Counter("ok" if x.get("otpravka") == "ok" else x.get("otpravka", "")[:60] for x in з if "otpravka" in x))
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
д = c.execute("SELECT lower(r.email), COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' "
              "AND m.sent_at >= date('now') GROUP BY lower(r.email) HAVING COUNT(*)>1").fetchall()
print("адресов с 2+ письмами за сегодня:", len(д))
print("карточки 18/22/23:", c.execute("SELECT campaign_id, status, COUNT(*) FROM confirm_reviews WHERE campaign_id IN (18,22,23) AND status='pending' GROUP BY 1,2").fetchall())
