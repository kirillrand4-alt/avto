# -*- coding: utf-8 -*-
"""Два письма на один адрес: было ли, сколько и почему.

Владелец 19.08: «я видел 2 письма на 1 адрес сегодня, идущих подряд (в
мейере)». Это не косметика: два письма подряд на один ящик читаются
получателем и фильтром как рассылка, а не как обращение.

Считаем по факту отправки, а не по очереди.
"""
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "2"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT m.id, m.campaign_id, m.sent_at, m.mailbox_id, m.recipient_id, "
        "       r.email, r.company_name, r.inn "
        "FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status='sent' AND date(m.sent_at) >= date('now', ?) "
        "ORDER BY m.sent_at", (f"-{ДНЕЙ} day",)).fetchall()

по_почте = defaultdict(list)
по_инн = defaultdict(list)
for r in строки:
    e = str(r["email"] or "").strip().lower()
    if e:
        по_почте[e].append(r)
    ц = "".join(c for c in str(r["inn"] or "") if c.isdigit())
    if ц:
        по_инн[ц].append(r)

дубли_почта = {k: v for k, v in по_почте.items() if len(v) > 1}
дубли_инн = {k: v for k, v in по_инн.items() if len(v) > 1}
print(f"отправлено за {ДНЕЙ} дн.: {len(строки)}")
print(f"АДРЕСОВ с двумя и более письмами: {len(дубли_почта)}")
print(f"КОМПАНИЙ (по ИНН) с двумя и более: {len(дубли_инн)}")

print("\n== адреса с повтором ==")
for e, v in list(дубли_почта.items())[:15]:
    камп = {int(x["campaign_id"]) for x in v}
    времена = [str(x["sent_at"])[11:16] for x in v]
    ящики = {str(x["mailbox_id"]) for x in v}
    print(f"  {e}  x{len(v)}  кампании {sorted(камп)}  время {времена}")
    print(f"      {v[0]['company_name']}  ящики: {', '.join(sorted(ящики))}")

print("\n== компании с повтором (разные адреса) ==")
n = 0
for ц, v in дубли_инн.items():
    почты = {str(x["email"] or "").lower() for x in v}
    if len(почты) < 2:
        continue
    n += 1
    if n <= 10:
        print(f"  ИНН {ц}  {v[0]['company_name']}  адресов {len(почты)}: "
              f"{', '.join(sorted(почты))}")
print(f"  всего таких компаний: {n}")
