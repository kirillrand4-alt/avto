# -*- coding: utf-8 -*-
"""69 отказов «подозрение на спам» — когда, у каких ящиков и что говорили."""
import json
import sqlite3
from collections import Counter, defaultdict
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
по_дням, по_ящику = Counter(), Counter()
тексты = Counter()
for r in c.execute("SELECT event_ts, mailbox_id, detail_json FROM events "
                   " WHERE event_type='reject_spam' ORDER BY event_ts"):
    по_дням[str(r["event_ts"])[:10]] += 1
    по_ящику[str(r["mailbox_id"] or "—")] += 1
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    т = " ".join(str(d.get("oshibka") or d.get("error")
                     or d.get("snippet") or "").split())
    тексты[т[:110]] += 1
всего = sum(по_дням.values())
print("отказов «подозрение на спам» всего: %d" % всего)
print("\nпо дням:")
for д in sorted(по_дням):
    print("   %s  %d" % (д, по_дням[д]))
print("\nпо нашему ящику:")
for я, n in по_ящику.most_common(12):
    print("   %-42s %d" % (я, n))
print("\nчто отвечал почтовик:")
for т, n in тексты.most_common(6):
    print("   %3d  %s" % (n, т or "(текст не сохранён)"))
отпр = {}
for r in c.execute("SELECT substr(event_ts,1,10) д, COUNT(*) n FROM events "
                   " WHERE event_type='sent' GROUP BY 1"):
    отпр[r["д"]] = r["n"]
print("\nдоля отказов от попыток отправки в тот день:")
for д in sorted(по_дням):
    н = отпр.get(д, 0)
    print("   %s  %3d из %5d  %.2f%%"
          % (д, по_дням[д], н, (100.0 * по_дням[д] / (н + по_дням[д]))
             if (н + по_дням[д]) else 0))
c.close()
