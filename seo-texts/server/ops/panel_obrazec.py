# -*- coding: utf-8 -*-
"""Образец panel_json полной карточки (company, company_full, compliance, pochemu, scoring) и тело ушедшего письма
кампании 21 (есть ли подпись/отписка). Только чтение.  panel_obrazec.py [кампания_полная=17]"""
import json, sqlite3, sys
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
к = int(sys.argv[1]) if len(sys.argv) > 1 else 17
pj = json.loads(c.execute("SELECT panel_json FROM confirm_reviews WHERE campaign_id=? AND panel_json LIKE '%compliance%' ORDER BY id DESC LIMIT 1", (к,)).fetchone()[0])
for ключ in ("company", "company_full", "compliance", "pochemu", "scoring", "contact", "should", "kb", "history"):
    print("==", ключ, ":", json.dumps(pj.get(ключ), ensure_ascii=False)[:600])
м = c.execute("SELECT m.id, m.body_rendered FROM messages m JOIN send_log s ON s.message_id=m.id WHERE s.campaign_id=21 AND s.outcome='sent' ORDER BY s.id DESC LIMIT 1").fetchone()
print("\n== ушедшее письмо кампании 21, message", м[0], "— хвост:\n", (м[1] or "")[-700:])
