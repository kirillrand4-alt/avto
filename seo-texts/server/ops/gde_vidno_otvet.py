# -*- coding: utf-8 -*-
"""Где ответ оператора ВИДЕН в панели, а где его нет.

Три места: диалог компании (dialog_thread_company), лента отправленных
(строится по messages) и журнал касаний send_log. Проверяем каждое по
живому ответу #3052.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
row = store.confirm_get(3052) or {}
инн = str(row.get("inn") or "")
rcid = row.get("recipient_id")
print(f"ответ #3052: ИНН {инн}, получатель {rcid}, "
      f"адрес {row.get('email')}")

print("\n== диалог компании (то, что видит оператор в карточке) ==")
try:
    ветка = store.dialog_thread_company(инн, limit=50) or []
    for э in ветка[-8:]:
        print(f"  {str(э.get('ts'))[:19]}  {э.get('direction'):<4} "
              f"{str(э.get('kind')):<12} {str(э.get('subject'))[:44]:<46} "
              f"источник {э.get('source')}")
    print(f"  всего в ветке: {len(ветка)}")
except Exception as ex:                                          # noqa: BLE001
    print("  не собралась:", type(ex).__name__, str(ex)[:120])

print("\n== журнал касаний send_log ==")
with store._lock:
    ряды = store._conn.execute(
        "SELECT ts, email, COALESCE(subject,''), COALESCE(outcome,'') "
        "FROM send_log WHERE email=? ORDER BY ts DESC LIMIT 5",
        (row.get("email"),)).fetchall()
for ts, email, тема, исход in ряды:
    print(f"  {str(ts)[:19]}  {исход:<12} {тема[:50]}")
if not ряды:
    print("  записей нет")
