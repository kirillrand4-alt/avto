# -*- coding: utf-8 -*-
"""Отбивки за день против пробы: была ли SMTP-проба адреса ДО отправки и какой вердикт; разрез по
кампаниям и типу отбивки. Плюс покрытие пробой писем, стоящих в расписании.
    otbivki_i_proba.py [YYYY-MM-DD]   Только чтение."""
import json, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
день = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кам = {i: n for i, n in c.execute("SELECT id, name FROM campaigns")}
шк = [x[1] for x in c.execute("PRAGMA table_info(addr_probe)")]
тс = "ts" if "ts" in шк else ("checked_at" if "checked_at" in шк else None)
def проба(em):
    r = c.execute("SELECT verdict, %s, %s FROM addr_probe WHERE email=?" % (тс or "NULL", "source" if "source" in шк else "NULL"), (em,)).fetchone()
    return (r[0], r[1], r[2]) if r else (None, None, None)
сч, кк, тип, прим = Counter(), Counter(), Counter(), []
for eid, mid, rid, кид, det, ets in c.execute("SELECT id, message_id, recipient_id, campaign_id, detail_json, event_ts FROM events "
                                              "WHERE event_type IN ('bounce','dsn') AND substr(event_ts,1,10)=?", (день,)):
    д = json.loads(det or "{}")
    em = (c.execute("SELECT lower(email) FROM recipients WHERE id=?", (rid,)).fetchone() or [None])[0] if rid else None
    if not em: сч["без получателя"] += 1; continue
    отпр = c.execute("SELECT min(ts) FROM send_log WHERE lower(email)=? AND outcome='sent' AND substr(ts,1,10)<=?", (em, день)).fetchone()[0]
    в, пт, ист = проба(em)
    if в is None: к = "пробы нет вовсе"
    elif пт and отпр and str(пт) > str(отпр): к = "проба ПОСЛЕ отправки: " + str(в)
    else: к = "проба до отправки: " + str(в)
    к += " | источник: " + str(ист)[:25]
    сч[к] += 1; кк[кам.get(кид, кид)] += 1; тип[str(д.get("verdict") or д.get("kind") or "?")] += 1
    if len(прим) < 12: прим.append((em, к, str(д.get("smtp_code") or д.get("status") or "")[:12], кам.get(кид, кид)))
print("колонки addr_probe:", шк)
print("ОТБИВКИ %s, всего %d" % (день, sum(сч.values())))
for k, n in сч.most_common(): print("  %4d  %s" % (n, k))
print("по кампаниям:", кк.most_common(8)); print("тип:", тип.most_common(6))
for x in прим: print("   ", x)
р = Counter()
for (em,) in c.execute("SELECT lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','sending')"):
    р[str(проба(em)[0])] += 1
print("В РАСПИСАНИИ по вердикту пробы:", р.most_common(10))
# --- что было ДО отбивки: история в obzvon email_probe (строки по источникам) и journal пробы
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=90)
ист = Counter(); до = Counter()
for (em,) in c.execute("SELECT DISTINCT lower(r.email) FROM events e JOIN recipients r ON r.id=e.recipient_id "
                       "WHERE e.event_type IN ('bounce','dsn') AND substr(e.event_ts,1,10)=?", (день,)):
    строки = o.execute("SELECT verdict, source, ts FROM email_probe WHERE lower(email)=? ORDER BY ts", (em,)).fetchall()
    ист[len(строки)] += 1
    прежние = [s for s in строки if "bounce" not in str(s[1]) and "отбив" not in str(s[1])]
    до[(прежние[-1][0], str(прежние[-1][1])[:20]) if прежние else "нет записи до отбивки"] += 1
print("строк в obzvon.email_probe на адрес:", dict(ист))
print("вердикт ДО отбивки (obzvon):", до.most_common(8))
# --- отправленные за день: вердикт/источник пробы сейчас, по кампаниям
сп = Counter()
for em, кид in c.execute("SELECT lower(email), campaign_id FROM send_log WHERE outcome='sent' AND substr(ts,1,10)=?", (день,)):
    в, пт, и = проба(em)
    сп[(кам.get(кид, кид), str(в), str(и)[:12])] += 1
print("ОТПРАВЛЕНО за день: (кампания, вердикт, источник):")
for k, n in sorted(сп.items(), key=lambda x: (str(x[0][0]), -x[1])): print("  %4d  %s" % (n, k))
# --- домены отбивок и вердикты «принимает всё» в расписании по доменам
дом = Counter(em.split("@")[-1] for (em,) in c.execute("SELECT DISTINCT lower(r.email) FROM events e JOIN recipients r ON r.id=e.recipient_id "
              "WHERE e.event_type IN ('bounce','dsn') AND substr(e.event_ts,1,10)=?", (день,)))
print("домены отбивок:", дом.most_common(10))
пд = Counter()
for (em,) in c.execute("SELECT lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','sending')"):
    в = проба(em)[0]
    д = em.split("@")[-1]; д = д if д in ("mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru") else "корпоративные"
    пд[(д, str(в))] += 1
print("РАСПИСАНИЕ (домен, вердикт):", sorted(пд.items(), key=lambda x: -x[1])[:14])
