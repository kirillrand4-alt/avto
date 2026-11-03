# -*- coding: utf-8 -*-
"""Отбивки за сутки (события bounce): осел ли вердикт «нет ящика» в трёх базах и нет ли
pending-карточек на адрес. --primenit: дописать недостающее (otbivka_v_bazy.zapisat) и
снять pending. Только verdict=hard из detail_json.
    otbivki_tri_bazy_dnya.py [--primenit]"""
import json, os, sqlite3, sys
from datetime import datetime, timezone
BASE = r"C:\sender"
sys.path.insert(0, BASE)
from sender.config import Config            # noqa: E402
from sender import otbivka_v_bazy           # noqa: E402
ПРИМ = "--primenit" in sys.argv
cfg = Config.load(os.path.join(BASE, "sender.yaml"))
c = sqlite3.connect(os.path.join(BASE, "sender.db"), timeout=60)
e = sqlite3.connect(os.path.join(BASE, "enrich.db"), timeout=60)
o = sqlite3.connect(os.path.join(BASE, "obzvon-index.db"), timeout=60)
адр = {}
for dj, em in c.execute("SELECT e.detail_json, r.email FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
                        "WHERE e.event_type='bounce' AND e.event_ts >= datetime('now','-1 day')"):
    д = json.loads(dj or "{}")
    for а in (д.get("failed") or [em]):
        if а:
            адр[а.lower()] = (д.get("verdict"), (д.get("diagnostic") or "")[:90])
нужно = []
for а, (в, диаг) in sorted(адр.items()):
    п1 = c.execute("SELECT verdict FROM addr_probe WHERE lower(email)=?", (а,)).fetchone()
    п2 = e.execute("SELECT probe_verdict FROM emails WHERE lower(email)=?", (а,)).fetchone()
    п3 = o.execute("SELECT verdict FROM email_probe WHERE lower(email)=?", (а,)).fetchone()
    pend = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE lower(email)=? AND status='pending'", (а,)).fetchone()[0]
    print("%-36s %-5s | probe=%s enrich=%s obzvon=%s | pending=%d | %s" % (а, в, п1 and п1[0], п2 and п2[0], п3 and п3[0], pend, диаг))
    if в == "hard" and (not п1 or п1[0] != "нет ящика" or (п2 and п2[0] != "нет ящика") or pend):
        нужно.append((а, диаг))
print("\nдописать/снять:", len(нужно))
if ПРИМ and нужно:
    т = datetime.now(timezone.utc).isoformat()
    for а, диаг in нужно:
        print(а, otbivka_v_bazy.zapisat([а], диаг, db_path=os.path.join(BASE, "sender.db"), config=cfg))
        with c:
            c.execute("UPDATE confirm_reviews SET status='skipped', reason='адрес недоставим: жёсткая отбивка', decided_at=?, updated_at=? WHERE lower(email)=? AND status='pending'", (т, т, а))
    print("применено")
