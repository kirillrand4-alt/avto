# -*- coding: utf-8 -*-
"""Привязать лид к другой компании и закрыть её от повторных писем (владелец 26.10:
«последний, который Лилиани, к Наиру привяжи, чтобы не писать ещё раз потом Наиру»).
    lid_k_kompanii.py <lead_id> <recipient_id новой компании> <домен для стоп-листа> [--primenit]"""
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                 # noqa: E402
from sender.suppression import Suppression     # noqa: E402
лид, rid, домен = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3].lower()
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
print("причины в стоп-листе сейчас:", Counter(r[0] for r in c.execute("SELECT reason FROM suppression")).most_common(8))
р = c.execute("SELECT id, inn, company_name, email FROM recipients WHERE id=?", (rid,)).fetchone()
л = c.execute("SELECT id, recipient_id, inn, company_name, email FROM leads WHERE id=?", (лид,)).fetchone()
print("лид было:", л)
print("станет:", р)
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН")
    sys.exit()
with c:
    c.execute("UPDATE leads SET recipient_id=?, inn=?, company_name=?, need=need || ? , updated_at=datetime('now') WHERE id=?",
              (р[0], р[1], р[2], "\n\n[привязан к «%s» (%s) по команде владельца 26.10: ответ пришёл с %s, адрес Лилиани-Центр/agrotekhnik — "
               "переслали письмо, отправленное на %s]" % (р[2], р[1], л[4], р[3]), лид))
st = Store(r"C:\sender\sender.db")
print("стоп-лист домена:", Suppression(st).add_domain(домен, "manual", source="владелец 26.10: Наир — нет потребности, не писать"))
print("готово:", c.execute("SELECT id, recipient_id, inn, company_name FROM leads WHERE id=?", (лид,)).fetchone())
