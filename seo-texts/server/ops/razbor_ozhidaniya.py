# -*- coding: utf-8 -*-
"""Что держит карточки в «Подтвердить отправку»: по кампаниям — стоп-флаги (коды), заслон, гейт направлений,
для recent_contact — кто и когда писал на тот же адрес (правило владельца 11.11: мешает только КЦ < 15 дн).
Только чтение.   razbor_ozhidaniya.py [кампания]"""
import json, re, sqlite3, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
cs = build_deps(cfg, st, dry_run=True).confirm
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True); c.row_factory = sqlite3.Row
now = datetime.now(timezone.utc)
КАМП = [int(a) for a in sys.argv[1:] if a.isdigit()]
сч = defaultdict(Counter); созд = defaultdict(Counter)
for r in c.execute("SELECT * FROM confirm_reviews WHERE status='pending' AND COALESCE(kind,'outbound')!='reply'").fetchall():
    к = int(r["campaign_id"] or 0)
    if КАМП and к not in КАМП: continue
    созд[к][str(r["created_at"] or "")[:10]] += 1
    п = json.loads(r["panel_json"] or "{}") or {}
    if (п.get("actions") or {}).get("confirm_hold"):
        коды = "+".join(sorted({(f.get("code") if isinstance(f, dict) else str(f)) for f in (п.get("stop_flags") or [])}))
        сч[к]["стоп-флаг: " + коды[:50]] += 1; continue
    б = cs._guard(inn=r["inn"], email=r["email"] or "")
    if б and str(б).startswith("recent_contact"):
        em = (r["email"] or "").lower()
        посл = c.execute("SELECT m.mailbox_id, m.sent_at FROM messages m JOIN recipients rr ON rr.id=m.recipient_id WHERE lower(rr.email)=? AND m.status='sent' ORDER BY m.sent_at DESC LIMIT 1", (em,)).fetchone()
        if not посл: сч[к]["recent_contact: тот же адрес не писали (писали компании)"] += 1; continue
        мейер = bool(re.search(r"sort|rentgen|inspection|optic", посл[0] or ""))
        дн = (now - datetime.fromisoformat(посл[1][:19]).replace(tzinfo=timezone.utc)).days
        сч[к]["recent_contact: " + ("Meyer" if мейер else ("КЦ <15 дн" if дн < 15 else "КЦ 15+ дн"))] += 1; continue
    if б: сч[к]["заслон: " + str(б)[:40]] += 1; continue
    дб = cs._division_blocked(dict(r))
    if дб: сч[к]["гейт направлений"] += 1; continue
    сч[к]["пройдёт в автоотправку"] += 1
for к in sorted(сч):
    print("кампания %d: всего %d, созданы %s" % (к, sum(сч[к].values()), dict(созд[к])))
    for п, n in сч[к].most_common(): print("   %-62s %4d" % (п, n))
