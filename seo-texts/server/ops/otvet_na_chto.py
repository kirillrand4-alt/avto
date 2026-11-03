# -*- coding: utf-8 -*-
"""На что ответили: по ИНН — отправленные напоминания (время, версия, re_ab) и прочие письма.
    otvet_na_chto.py ИНН [ИНН…]"""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for инн in sys.argv[1:]:
    print("==", инн)
    for i, s, d, п in c.execute("SELECT id, subject, decided_at, panel_json FROM confirm_reviews WHERE inn=? AND status='sent' ORDER BY decided_at", (инн,)):
        п = json.loads(п or "{}")
        print("   карточка %s %s | %s | %s | re_ab=%s" % (i, (d or "")[:16], s, "заход" if "заходы" in str(п.get("vruchnuyu", "")) else ("напоминание" if п.get("napominanie") else "письмо"), п.get("re_ab", "-")))
    for mid, sa, s, cid in c.execute("SELECT m.id, m.sent_at, m.subject, m.campaign_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.inn=? AND m.status='sent' ORDER BY m.sent_at", (инн,)):
        print("   письмо %s %s | %s | кампания %s" % (mid, (sa or "")[:16], s, cid))
