# -*- coding: utf-8 -*-
"""История проб по адресам (журналы проб) и когда письмо было одобрено/ушло."""
import io
import sqlite3
import sys
адреса = [а.lower() for а in sys.argv[1].split(",")]
for ж in (r"C:\sender\_ops\smtp-proba-partiy.jsonl",):
    for с in io.open(ж, encoding="utf-8", errors="replace"):
        if any(а in с for а in адреса):
            print("   журнал пробы: " + с.strip()[:200])
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
for а in адреса:
    for р in c.execute("SELECT m.id, m.status, m.scheduled_at, m.sent_at, m.created_at, cr.decided_at, cr.status "
                       "FROM messages m JOIN recipients r ON r.id=m.recipient_id LEFT JOIN confirm_reviews cr "
                       "ON cr.message_id=m.id WHERE lower(r.email)=?", (а,)):
        print("   %s: m%s %s создано %s решено %s срок %s ушло %s" % (а, р[0], р[1], str(р[4])[:16], str(р[5])[:16],
              str(р[2])[:16], str(р[3])[:16]))
print("=== ИСТОРИЯ ПРОБЫ ===")
