# -*- coding: utf-8 -*-
"""Регламентные зачины ПО ВСЕМ письмам, включая отправленные.

Владелец: «посмотри все письма, есть ли там этот заход». Прошлый прогон
смотрел только очередь (pending/approved) - но важнее знать, ушло ли такое
письмо людям: отправленное не переписать, зато видно масштаб.

Окно зачина - три абзаца, как в гейте: у мейеровских писем первый абзац
приветствие, второй представление, и регламент садится третьим.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, COALESCE(c.campaign_id,0), c.status,
                  COALESCE(c.edited_body, c.body, ''),
                  COALESCE(rc.company_name,''), COALESCE(m.status,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
             LEFT JOIN messages m ON m.id=c.message_id""").fetchall()

счёт = Counter()
найдено = []
for rid, camp, st, тело, фирма, mst in ряды:
    абз = [a for a in str(тело or "").strip().split("\n\n") if a.strip()]
    зачин = " ".join(абз[:3])[:700]
    if not зачин:
        continue
    # Слово должно ОТКРЫВАТЬ абзац — тем же правилом, что и гейт после
    # правки: иначе в находки попадают описания вроде «масел с сертификацией
    # Халяль», где письмо начинается как раз с получателя.
    м = next((AI._РЕГЛАМЕНТ_В_ЗАЧИНЕ.search(a) for a in абз[:3]
              if AI._РЕГЛАМЕНТ_В_ЗАЧИНЕ.search(a)), None)
    if not м:
        continue
    ушло = (mst == "sent")
    счёт[f"кампания {camp} / решение {st} / "
         f"{'ОТПРАВЛЕНО' if ушло else 'не отправлено'}"] += 1
    найдено.append((rid, фирма, м.group(0), ушло, зачин))

print(f"проверено писем: {len(ряды)}")
print(f"с регламентным зачином: {len(найдено)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print()
for rid, фирма, слово, ушло, зачин in найдено[:25]:
    метка = "УШЛО " if ушло else "     "
    print(f"{метка}#{rid:<6} {str(фирма)[:32]:<34} «{слово}»")
    print(f"       {зачин[:150]}")
