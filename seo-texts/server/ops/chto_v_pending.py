# -*- coding: utf-8 -*-
"""Что на самом деле лежит в «без решения»: не просужено или уже отвергнуто.

Я посчитал 64 мейеровских и 267 КЦ «в очереди на рецензию» и пообещал, что
оттуда выйдет ещё полсотни годных. Рецензент нашёл всего 6 непросуженных —
значит остальные уже с вердиктом, просто вердикт не «годно». Проверяем.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                           # noqa: BLE001
        pass

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
ЧУЖИЕ = ("yandex", "mailru", "google", "outlook")

for камп, имя in ((11, "Meyer"), (10, "КЦ")):
    with store._lock:
        строки = store._conn.execute(
            "SELECT c.id, COALESCE(r.mx_provider,'') mx, "
            "       COALESCE(p.verdict,'') proba "
            "FROM confirm_reviews c "
            "LEFT JOIN recipients r ON r.id=c.recipient_id "
            "LEFT JOIN addr_probe p ON p.email=lower(c.email) "
            "WHERE c.campaign_id=? AND c.status='pending'",
            (камп,)).fetchall()
    счёт = Counter()
    годных_но_стоят = 0
    for r in строки:
        v = верд.get(int(r["id"]), "НЕ ПРОСУЖЕНО")
        счёт[v] += 1
        if v == "годно":
            if str(r["mx"]).lower() not in ЧУЖИЕ:
                счёт[f"  из них годно, но корп. сервер ({r['mx'] or '?'})"] += 1
            elif str(r["proba"]) in ("нет ящика", "нет MX"):
                счёт["  из них годно, но приговор пробы"] += 1
            else:
                годных_но_стоят += 1
    print(f"\n== {имя} (кампания {камп}): без решения {len(строки)} ==")
    for k, v in счёт.most_common():
        print(f"  {v:>5}  {k}")
    print(f"  ГОДНЫХ И ГОТОВЫХ К ОТПРАВКЕ, НО СТОЯТ: {годных_но_стоят}")
