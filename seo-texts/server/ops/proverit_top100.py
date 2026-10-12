# -*- coding: utf-8 -*-
"""Пройдут ли компании top100 заслоны панели: база обзвона, направление, стоп.

Решает не наличие ИНН в файле, а наличие компании в базе обзвона: гейт
направлений блокирует письмо, если у компании нет метки kc/meyer. Без ИНН
метки нет по определению.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ФАЙЛ = r"C:\sender\server\ops\top100_v2.json"
строки = json.load(io.open(ФАЙЛ, encoding="utf-8"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# тумблер «слать вне базы обзвона»
try:
    from sender.vne_bazy import razreshena_vne_bazy                 # noqa: E402
    вне = razreshena_vne_bazy(store, cfg)
except Exception:                                                # noqa: BLE001
    try:
        from sender.sender import razreshena_vne_bazy              # noqa: E402
        вне = razreshena_vne_bazy(store, cfg)
    except Exception as ex:                                      # noqa: BLE001
        вне = "не прочиталось: %s" % str(ex)[:60]
print("тумблер «слать вне базы обзвона»: %s" % вне)

# карточки обзвона
try:
    from sender.company_card import ObzvonIndex                     # noqa: E402
    карты = ObzvonIndex(cfg.get("obzvon.db_path", r"C:\sender\obzvon-index.db"))
    жив = getattr(карты, "active", False)
except Exception as ex:                                          # noqa: BLE001
    карты, жив = None, False
    print("индекс обзвона не открылся: %s" % str(ex)[:80])
print("индекс обзвона活: %s" % жив)

свод = Counter()
примеры = []
with store._lock:
    c = store._conn
    for р in строки:
        инн = р["inn"]
        почта = р["почта"]
        if not почта:
            свод["нет адреса — грузить нечего"] += 1
            continue
        if not инн:
            свод["без ИНН (сайт/УНП) — гейт направлений закроет"] += 1
            if len(примеры) < 5:
                примеры.append("%s — %s" % (р["название"][:34], р["ид"][:24]))
            continue
        мет = None
        if карты is not None and жив:
            try:
                стр = карты.get(инн)
                мет = (стр or {}).get("division") or None
            except Exception:                                    # noqa: BLE001
                мет = None
        if мет is None:
            свод["ИНН есть, но компании нет в базе обзвона"] += 1
        elif "meyer" in str(мет):
            свод["годна: метка включает meyer"] += 1
        else:
            свод["метка есть, но без meyer (%s)" % мет] += 1
        # стоп-лист
        if c.execute("SELECT 1 FROM suppression WHERE scope='inn' AND value=?",
                     (инн,)).fetchone():
            свод["ИНН в стоп-листе"] += 1
        if c.execute("SELECT 1 FROM suppression WHERE scope='email' AND value=?",
                     (почта,)).fetchone():
            свод["адрес в стоп-листе"] += 1
        if c.execute("SELECT 1 FROM recipients WHERE lower(email)=?",
                     (почта,)).fetchone():
            свод["адрес уже есть в получателях"] += 1

print("")
print("--- что будет с сотней ---")
for к, n in свод.most_common():
    print("   %-52s %3d" % (к[:52], n))
if примеры:
    print("")
    print("   примеры без ИНН: %s" % "; ".join(примеры))
print("")
print("=" * 74)
print("=== ПРОЙДЁТ ЛИ TOP100 ЗАСЛОНЫ ===")
