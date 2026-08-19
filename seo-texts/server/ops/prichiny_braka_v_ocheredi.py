# -*- coding: utf-8 -*-
"""За что забракованы письма очереди — чтобы знать, где переписывать, а где
компании вообще нельзя писать.

Владелец: «не годные перепиши, если компании вообще нельзя писать по нашим
направлениям - скип с причиной». Это два РАЗНЫХ ведра, и различить их надо
до, а не после: претензия к ТЕКСТУ лечится переписыванием, а вердикт «не наш
адресат» переписыванием не лечится вовсе — там неверен сам выбор компании.
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z
    except Exception:                                             # noqa: BLE001
        pass

# «Не наш адресат» — профиль компании не наш. Переписыванием не лечится.
НЕ_НАШ = re.compile(
    r'(?i)(не производств|не покупател|вне профиля|торговл|перепрода|'
    r'дистрибь|аренда\b|услуг|логистик|проектирован|монтаж|'
    r'не занимается производством|розничн)')

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    with store._lock:
        строки = store._conn.execute(
            "SELECT c.id, COALESCE(r.mx_provider,'') mx "
            "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
            "WHERE c.campaign_id=? AND c.status='pending'", (камп,)).fetchall()
    вёдра = Counter()
    примеры = {}
    for r in строки:
        z = верд.get(int(r["id"])) or {}
        v = str(z.get("verdict") or "НЕ ПРОСУЖЕНО")
        _пр = z.get("pretenzii")
        если = ("; ".join(str(x) for x in _пр) if isinstance(_пр, list)
                else str(_пр or ""))
        if v == "не годно":
            ведро = ("НЕ НАШ АДРЕСАТ (скип)" if НЕ_НАШ.search(если)
                     else "текст (переписать)")
        elif v == "годно":
            ведро = ("годно, но корп. сервер" if str(r["mx"]).lower()
                     in ("other", "unknown", "") else "ГОДНО -> в отправку")
        else:
            ведро = v
        вёдра[ведро] += 1
        if ведро not in примеры and если:
            примеры[ведро] = f"#{r['id']} {если[:110]}"
    print(f"\n== {имя} (кампания {камп}): {len(строки)} ==")
    for в, n in вёдра.most_common():
        print(f"  {n:>4}  {в}")
        if примеры.get(в):
            print(f"          {примеры[в]}")
