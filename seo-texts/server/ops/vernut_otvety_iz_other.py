# -*- coding: utf-8 -*-
"""Догнать письма живых людей, которые лежат «вне переписки».

Новый разбор такие письма считает ответом, но 90 записей уже лежат. Правим по
тем же трём условиям: привязано к получателю, отправитель не машина, мы этому
получателю писали. Что не подходит — не трогаем.
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
БАЗА = r"C:\sender\sender.db"
ЖУРНАЛ = r"C:\sender\_ops\vozvrat-otvetov.jsonl"
МАШИНА = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
          "daemon", "postmaster@", "notification", "notifications@",
          "notify@", "robot@", "bounce@", "abuse@")
try:
    from sender.reply_classify import classify_reply
except Exception:                                                  # noqa: BLE001
    classify_reply = None

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
писали = {r[0] for r in c.execute(
    "SELECT DISTINCT recipient_id FROM messages WHERE sent_at IS NOT NULL")}
годные, отсев = [], []
for r in c.execute("SELECT id, event_ts, recipient_id, detail_json FROM events "
                   " WHERE event_type='other' ORDER BY id"):
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        continue
    h = d.get("headers") or {}
    от = str(h.get("From") or "").lower()
    т = " ".join(str(d.get("snippet") or "").split())
    if not r["recipient_id"]:
        отсев.append((r["id"], "нет привязки к компании", от, т[:50]))
        continue
    if any(м in от for м in МАШИНА):
        отсев.append((r["id"], "машинный отправитель", от, т[:50]))
        continue
    if r["recipient_id"] not in писали:
        отсев.append((r["id"], "мы им не писали", от, т[:50]))
        continue
    if not re.search(r"[а-яА-Я]{8}", т):
        отсев.append((r["id"], "нет человеческого текста", от, т[:50]))
        continue
    # КАКОЙ ИМЕННО ОТВЕТ — решает тот же классификатор, что и в бою. Иначе
    # автоответчики («Ваш запрос принят», «нахожусь в отпуске», «мы его
    # получили и уже передали») попали бы в живые ответы и раздули сводку.
    вид = "reply"
    метка = ""
    if classify_reply is not None:
        try:
            с = classify_reply(str(h.get("Subject") or ""), т, h)
            метка = getattr(с, "kind", "") or ""
            if метка == "auto_reply":
                вид = "reply_auto"
        except Exception:                                          # noqa: BLE001
            pass
    годные.append((r["id"], r["recipient_id"], str(r["event_ts"])[:10], от,
                   str(h.get("Subject") or "")[:30], т[:52], вид, метка))
c.close()

живых = sum(1 for x in годные if x[6] == "reply")
print("=== СТАНУТ ОТВЕТАМИ (%d: живых %d, автоответов %d) ==="
      % (len(годные), живых, len(годные) - живых))
for eid, rid, д, от, тема, т, вид, метка in годные:
    print("   ev=%-7s rid=%-6s %s %-12s %-9s %-30s %s"
          % (eid, rid, д, вид, метка[:9], тема, т))
print("\n=== ОСТАНУТСЯ «ВНЕ ПЕРЕПИСКИ» (%d), по причинам ===" % len(отсев))
причины = {}
for _, п, _, _ in отсев:
    причины[п] = причины.get(п, 0) + 1
for п, n in sorted(причины.items(), key=lambda x: -x[1]):
    print("   %-28s %d" % (п, n))
print("\n   из них живые люди без привязки (их стоит посмотреть глазами):")
for eid, п, от, т in отсев:
    if п == "нет привязки к компании" and re.search(r"[а-яА-Я]{8}", т) \
            and not any(м in от for м in МАШИНА):
        print("      ev=%-7s %-36s %s" % (eid, от[:36], т))

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit переведу в ответы")
    raise SystemExit(0)

from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
ж = open(ЖУРНАЛ, "a", encoding="utf-8")
сделано = 0
try:
    with store.transaction() as conn:
        for eid, rid, _, _, _, _, вид, метка in годные:
            ж.write(json.dumps({"id": eid, "rid": rid, "bylo": "other",
                                "stalo": вид, "metka": метка},
                               ensure_ascii=False) + "\n")
            строка = conn.execute("SELECT detail_json FROM events WHERE id=?",
                                  (eid,)).fetchone()
            try:
                d = json.loads(строка["detail_json"] or "{}")
            except Exception:                                      # noqa: BLE001
                d = {}
            if метка and isinstance(d, dict):
                d["reply_kind"] = метка
                conn.execute("UPDATE events SET event_type=?, detail_json=? "
                             " WHERE id=?",
                             (вид, json.dumps(d, ensure_ascii=False), eid))
            else:
                conn.execute("UPDATE events SET event_type=? WHERE id=?",
                             (вид, eid))
            сделано += 1
    ж.flush()
    os.fsync(ж.fileno())
finally:
    ж.close()
print("\nпереведено в ответы: %d (журнал %s)" % (сделано, ЖУРНАЛ))
