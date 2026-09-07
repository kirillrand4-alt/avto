# -*- coding: utf-8 -*-
"""Кто и почему получил «Ваше хозяйство» вместо названия."""
import io, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imya_v_pismo import итоговое_имя, _ЛИЦО, ПРЕДЕЛ_ДЛИНЫ     # noqa: E402

ИМЕНА = r"C:\sender\_ops\agro-imena.jsonl"
имена = {}
for с in io.open(ИМЕНА, encoding="utf-8", errors="replace"):
    с = с.strip()
    if с:
        try:
            z = json.loads(с)
            if z.get("сыро"):
                имена[z["сыро"]] = z
        except Exception:                                      # noqa: BLE001
            pass
счёт = Counter()
строки = []
for сыро, z in sorted(имена.items()):
    подл, вид = итоговое_имя(z.get("имя"), bool(z.get("человек")))
    if вид != "хозяйство":
        continue
    имя = " ".join(str(z.get("имя") or "").split())
    если = ("модель: фамилия владельца" if z.get("человек")
            else "длиннее %d знаков" % ПРЕДЕЛ_ДЛИНЫ if len(имя) > ПРЕДЕЛ_ДЛИНЫ
            else "похоже на ФИО" if _ЛИЦО.match(имя) else "пусто после разбора")
    счёт[если] += 1
    строки.append((сыро, имя, если))
for сыро, имя, если in строки:
    print("   %-40s → %-30s %s" % (сыро[:40], имя[:30], если))
print("")
print("=" * 70)
print("=== ПОЧЕМУ «ВАШЕ ХОЗЯЙСТВО»: %d ===" % len(строки))
for к, в in счёт.most_common():
    print("   %-32s %5d" % (к, в))
