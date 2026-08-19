# -*- coding: utf-8 -*-
"""Через что письмо могло попасть в мейеровскую группу: id, почта или ИНН.

Фильтр очереди ищет группы по трём ключам подряд: id получателя, затем
адрес, затем ИНН. Если у компании несколько строк-получателей и хоть одна
лежит в мейеровской группе, письмо КЦ может показаться под мейеровским
фильтром - через ИНН.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

RID = int(next((a for a in sys.argv[1:] if a.isdigit()), "2646"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
row = store.confirm_get(RID) or {}
rcid = int(row.get("recipient_id") or 0)
инн = "".join(c for c in str(row.get("inn") or "") if c.isdigit())
почта = str(row.get("email") or "").strip().lower()

карта = store.recipient_groups()
print(f"#{RID}: получатель {rcid}, ИНН {инн}, почта {почта}")
print(f"  по_id[{rcid}]      = {sorted((карта.get('по_id') or {}).get(rcid, []))}")
print(f"  по_почте[{почта}]  = "
      f"{sorted((карта.get('по_почте') or {}).get(почта, []))}")
print(f"  по_инн[{инн}]      = {sorted((карта.get('по_инн') or {}).get(инн, []))}")

with store._lock:
    ряды = store._conn.execute(
        "SELECT id, email, COALESCE(segment,''), COALESCE(extra_json,'') "
        "FROM recipients WHERE inn=?", (row.get("inn"),)).fetchall()
print(f"\nстрок-получателей у этого ИНН: {len(ряды)}")
for rid_, email, seg, ex in ряды:
    гр = sorted((карта.get("по_id") or {}).get(int(rid_), []))
    print(f"  #{rid_:<7} {str(email)[:34]:<36} segment={seg!r:<18} группы={гр}")
