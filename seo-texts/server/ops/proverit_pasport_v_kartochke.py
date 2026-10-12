# -*- coding: utf-8 -*-
"""Доехал ли паспорт до карточки: собираем карточку так же, как генератор."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.company_card import build_company_card              # noqa: E402

КЛЮЧИ = ["0106008761", "100058367", "00000000001", "5502035895"]
for к in КЛЮЧИ:
    карта = build_company_card(к, enrich_db_path=r"C:\sender\enrich.db")
    ен = карта.get("enrich") or {}
    комп = ен.get("company") or {}
    print("")
    print("=" * 74)
    print("ключ %s → %s" % (к, str(комп.get("name") or "НЕ НАЙДЕНА")[:50]))
    if not комп:
        continue
    print("   сайт:      %s   сверен: «%s»"
          % (комп.get("site"), комп.get("verified") or ""))
    print("   направление: %s   выручка: %s"
          % (комп.get("division"), комп.get("revenue_rub")))
    print("   метка:     %s" % str(комп.get("istochnik_kompanii"))[:70])
    print("   адресов в карточке: %d" % len(ен.get("emails") or []))
    for а in (ен.get("emails") or [])[:4]:
        print("      %-34s роль=%-26s %s"
              % (str(а.get("email"))[:34], str(а.get("role"))[:26],
                 str(а.get("person") or "")[:24]))
    вид = карта.get("site_view") or {}
    print("   site_view: site=«%s» verified=«%s»"
          % (вид.get("site"), вид.get("site_verified")))
    акт = str(комп.get("activity") or "")
    print("   activity (%d знаков):" % len(акт))
    for с in акт.split("; ")[:6]:
        print("      • %s" % с[:110])
print("")
print("=" * 74)
print("=== ПАСПОРТ В КАРТОЧКЕ ===")
