# -*- coding: utf-8 -*-
"""Разведка перед заводом карточек партии «провалы Meyer»: кампании Meyer, ящики Meyer (пауза), хвост реального письма
Meyer (подпись), шаги последовательности. Только чтение."""
import re, sqlite3, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
cfg = Config.load(r"C:\sender\sender.yaml")
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
пауз = {r[0] for r in к.execute("SELECT mailbox_id FROM mailbox_state WHERE paused=1")}
for m in cfg.mailboxes():
    if m.division == "meyer": print("ящик", m.mailbox_id, "|", m.from_name, "| пауза" if m.mailbox_id in пауз else "")
for r in к.execute("SELECT c.id, c.name, c.status, COUNT(cr.id), SUM(cr.status='sent') FROM campaigns c LEFT JOIN confirm_reviews cr ON cr.campaign_id=c.id GROUP BY c.id ORDER BY c.id"):
    print("камп", r)
for r in к.execute("SELECT campaign_id, step_no, delay_days FROM sequence_steps WHERE campaign_id IN (SELECT id FROM campaigns WHERE name LIKE '%eyer%' OR name LIKE '%ейер%')") if False else []: print(r)
print([x[1] for x in к.execute("PRAGMA table_info(sequence_steps)")])
for кид, тело, pj in к.execute("SELECT cr.id, COALESCE(m.body_rendered, cr.body), cr.panel_json FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
                                "WHERE cr.status='sent' AND cr.panel_json LIKE '%\"letter_division\": \"meyer\"%' ORDER BY cr.id DESC LIMIT 2"):
    print("== карточка", кид, pj[:300]); print((тело or "")[-700:])
