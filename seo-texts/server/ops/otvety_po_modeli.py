# -*- coding: utf-8 -*-
"""Доля живых ответов по модели-писателю (журнал партии 935, Meyer, отправленные)."""
import io
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
кол = [р[1] for р in c.execute("PRAGMA table_info(leads)")]
вид_п = "reply_kind" if "reply_kind" in кол else None
ответ = set()
for р in c.execute("SELECT * FROM leads"):
    р = dict(р)
    if вид_п and str(р.get(вид_п) or "") in ("auto_reply", "unsub_request", "avtootvet"):
        continue
    if р.get("recipient_id"):
        ответ.add(int(р["recipient_id"]))
отпр, отв = Counter(), Counter()
for с in io.open(r"C:\sender\_ops\gen-partiya-935.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if not z.get("тело") or str(z.get("направление") or "") != "meyer":
        continue
    м = "opus" if "opus" in str(z.get("модель")) else ("sonnet" if "sonnet" in str(z.get("модель")) else str(z.get("модель")))
    ok = c.execute("SELECT 1 FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
                   "WHERE cr.id=? AND m.status='sent'", (z.get("review_id"),)).fetchone()
    if not ok:
        continue
    отпр[м] += 1
    if z.get("recipient_id") in ответ:
        отв[м] += 1
for м in отпр:
    print("%-8s отправлено %4d  живых ответов %3d  = %.1f%%" % (м, отпр[м], отв[м], 100.0 * отв[м] / отпр[м]))
print("=== ОТВЕТЫ ПО МОДЕЛИ ===")
