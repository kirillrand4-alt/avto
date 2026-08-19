# -*- coding: utf-8 -*-
"""Сколько мейеровских писем ушло/лежит для производителей напитков."""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

НАПИТКИ_В_ТЕКСТЕ = re.compile(
    r'(?i)вино|сидр|пиво|пивовар|лимонад|квас|минеральн\w*\s+вод|'
    r'безалкогольн|соки\b|сокосодерж|напитк|розлив')

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.status, COALESCE(c.edited_body, c.body, ''),
                  COALESCE(rc.company_name,''), COALESCE(rc.okved,''),
                  COALESCE(m.status,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
             LEFT JOIN messages m ON m.id=c.message_id
            WHERE c.campaign_id IN (7,8,9,11)""").fetchall()

счёт = Counter()
найдено = []
for rid, st, тело, фирма, оквэд, mst in ряды:
    т = str(тело or "")
    по_коду = bool(AI.vne_profilya_meyer(оквэд, ""))
    по_тексту = bool(НАПИТКИ_В_ТЕКСТЕ.search(т[:600]))
    if not (по_коду or по_тексту):
        continue
    ушло = mst == "sent"
    счёт[f"{st} / {'ОТПРАВЛЕНО' if ушло else 'не отправлено'}"] += 1
    найдено.append((rid, фирма, оквэд, st, ушло))

print(f"мейеровских писем проверено: {len(ряды)}")
print(f"похоже на напитки: {len(найдено)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
for rid, фирма, оквэд, st, ушло in найдено[:20]:
    print(f"  {'УШЛО ' if ушло else '     '}#{rid:<6} {str(фирма)[:38]:<40} "
          f"ОКВЭД {str(оквэд)[:10]:<12} {st}")
