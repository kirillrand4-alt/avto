# -*- coding: utf-8 -*-
"""Сколько из отобранных 1125 проходит заслон ПОСЛЕ правки."""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])
выбор = {инн: sorted(v)[0] for инн, v in годные.items()}

from sender.confirm import (COMPANY_CONTACTS_PER_PERIOD,          # noqa: E402
                            RECENT_CONTACT_DAYS, ConfirmSend)
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.suppression import Suppression                        # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
print("")
print("окно: %d дн, потолок адресов компании: %d"
      % (cs._okno_dney(), cs._potolok_kompanii()))
print("(в коде: RECENT_CONTACT_DAYS=%d, COMPANY_CONTACTS_PER_PERIOD=%d)"
      % (RECENT_CONTACT_DAYS, COMPANY_CONTACTS_PER_PERIOD))

итог = Counter()
пример = []
for инн, v in выбор.items():
    адрес = v[3]
    if cs._recent_contact(email=адрес) is not None:
        итог["режет заслон по адресу"] += 1
        continue
    к = cs._kvota_kompanii(inn=инн, email=адрес)
    if к is not None:
        итог["режет потолок компании"] += 1
        if len(пример) < 3:
            пример.append((инн, адрес, str(к.get("ts"))[:10]))
        continue
    итог["ПРОХОДИТ"] += 1
print("")
print("=== заслон после правки, на 1125 отобранных ===")
for к, n in итог.most_common():
    print("   %-28s %5d" % (к, n))
for и, а, т in пример:
    print("   потолок: %-13s %-28s последняя %s" % (и, а[:28], т))
