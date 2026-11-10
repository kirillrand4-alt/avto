# -*- coding: utf-8 -*-
"""Не режет ли Яндекс наши письма как спам: за N часов — исходы отправки (send_log), упавшие карточки
и отбивки/DSN с признаками спам-фильтра (5.7.x, spam, suspicion, policy) по ящикам. Только чтение.
    spam_otkazy_dnya.py [часов=24]"""
import json, re, sqlite3, sys
from collections import Counter
Ч = int(sys.argv[1]) if len(sys.argv) > 1 else 24
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
окно = "-%d hours" % Ч
print("ОТПРАВКИ за %d ч по исходу:" % Ч, c.execute("SELECT outcome, count(*) FROM send_log WHERE ts >= datetime('now', ?) GROUP BY 1", (окно,)).fetchall())
print("напоминания-карточки за %d ч по статусу:" % Ч, c.execute("SELECT status, count(*) FROM confirm_reviews WHERE kind='reply' AND panel_json LIKE '%napominanie%' AND updated_at >= datetime('now', ?) GROUP BY 1", (окно,)).fetchall())
ош = Counter()
for (r,) in c.execute("SELECT COALESCE(reason,'') FROM confirm_reviews WHERE kind='reply' AND status NOT IN ('sent','pending') AND updated_at >= datetime('now', ?)", (окно,)):
    ош[r[:90]] += 1
print("причины несработавших карточек:", ош.most_common(8))
СПАМ = re.compile(r"(?i)spam|\b5\.7\.\d|suspicion|blocked|blacklist|reputation|спам")
КОД = re.compile(r"(?i)\b[45]\d\d[ -][45]\.\d{1,3}\.\d{1,3}[^\\]{0,140}|\b[45]\d\d [A-Za-z][^\\]{0,140}")
причины = Counter()
сп, всего, по_ящ, прим = 0, Counter(), Counter(), []
for et, mb, det in c.execute("SELECT event_type, mailbox_id, detail_json FROM events WHERE event_type IN ('dsn','bounce') AND event_ts >= datetime('now', ?)", (окно,)):
    всего[et] += 1
    т = det or ""
    к = КОД.search(т)
    причины[re.sub(r"[0-9a-f]{8,}|\S+@\S+", "…", (к.group(0) if к else "код не найден"))[:110]] += 1
    if СПАМ.search(к.group(0) if к else ""):
        сп += 1; по_ящ[mb] += 1
        if len(прим) < 8:
            try: д = json.loads(т)
            except Exception: д = {}
            прим.append((mb, к.group(0)[:200] if к else ""))
print("отбивок/DSN за %d ч:" % Ч, dict(всего), "| из них с признаками спам-фильтра/политики:", сп)
print("по ящикам:", по_ящ.most_common(10))
print("причины отбивок (код сервера):")
for k, n in причины.most_common(12): print("   %3d  %s" % (n, k))
for x in прим: print("   ", x)
