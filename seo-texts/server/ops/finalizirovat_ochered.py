# -*- coding: utf-8 -*-
"""Финал разбора очереди: снять неисправимых, одобрить остальных на завтра.

Владелец 19.08: «перекинь в отправку на завтра годные письма, не годные
перепиши, если компании вообще нельзя писать по нашим направлениям - скип с
причиной», и следом: «те которые в очереди корпоративные но готовые
отправляй на отправку тоже».

Три ведра:
  * НЕИСПРАВИМЫЕ — письмо переписали по претензиям, и оно всё равно не
    сходится с сайтом. Сайт не даёт фактов на замену, значит писать этой
    компании по нашим направлениям нечего. Снимаем с причиной;
  * ГОДНЫЕ — в отправку со слотом на завтра. КОРПОРАТИВНЫЕ ТЕПЕРЬ ТОЖЕ (по
    прямому указанию владельца). Оговорка честная: свои почтовые серверы
    чаще отбивают письма с молодых доменов, и отбивка бьёт по репутации —
    но это решение владельца, а не недосмотр;
  * приговор пробы («нет ящика», «нет MX») — не трогаем ни при каких
    указаниях: туда письмо физически не дойдёт.
"""
import io
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПЕРЕПИСАНО = r"C:\sender\_ops\perepisano-po-recenzii.jsonl"
РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
КАТИТЬ = "--katit" in sys.argv
КАМПАНИИ = "10,11"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)

# ---- кто не выправился ---------------------------------------------------- #
неисправимые = {}
for s in io.open(ПЕРЕПИСАНО, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    итог = str(z.get("итог") or "")
    if "не годно" in итог:
        пр = z.get("pretenzii") or []
        неисправимые[int(z["id"])] = ("; ".join(str(x) for x in пр)
                                      if isinstance(пр, list) else str(пр))
    elif "годно после правки" in итог:
        неисправимые.pop(int(z["id"]), None)     # выправился позже — не снимать

верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

with store._lock:
    строки = store._conn.execute(
        f"SELECT c.id, c.campaign_id, c.recipient_id, c.message_id, c.email, "
        f"       COALESCE(rc.mx_provider,'') mx, COALESCE(p.verdict,'') proba "
        f"FROM confirm_reviews c "
        f"LEFT JOIN recipients rc ON rc.id=c.recipient_id "
        f"LEFT JOIN addr_probe p ON p.email=lower(c.email) "
        f"WHERE c.campaign_id IN ({КАМПАНИИ}) AND c.status='pending'"
    ).fetchall()

счёт = Counter()
на_снятие, на_отправку = [], []
for r in строки:
    rid = int(r["id"])
    if str(r["proba"]) in ("нет ящика", "нет MX"):
        счёт[f"приговор пробы: {r['proba']} — не трогаем"] += 1
        continue
    if rid in неисправимые:
        на_снятие.append((rid, неисправимые[rid]))
        счёт["СНЯТЬ: писать нечего, сайт не подтверждает"] += 1
        continue
    v = верд.get(rid, "")
    if v == "годно":
        на_отправку.append(r)
        счёт["В ОТПРАВКУ: годно" + (" (корп. сервер)" if str(r["mx"]).lower()
                                    in ("other", "unknown", "") else "")] += 1
    elif v == "нечем проверить":
        счёт["нечем проверить — оставляем в очереди"] += 1
    else:
        счёт[f"прочее ({v or 'без вердикта'}) — оставляем"] += 1

for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

снято = 0
for rid, причина in на_снятие:
    try:
        ок = store.confirm_decide(
            rid, status="skipped",
            reason=f"писать нечего: сайт не подтверждает профиль. {причина[:200]}",
            decided_by="разбор очереди 19.08")
        снято += 1 if ок is not False else 0
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{rid} не снялось: {str(ex)[:90]}")

одобрено = слотов = 0
for r in на_отправку:
    try:
        ок = store.confirm_decide(int(r["id"]), status="approved",
                                  decided_by="разбор очереди 19.08")
        if ок is False:
            continue
        одобрено += 1
        rec = store.get_recipient(r["recipient_id"])
        if r["message_id"] and rec is not None:
            store.reschedule_message(
                int(r["message_id"]),
                next_slot(окно, recipient_tz_name(окно, rec), сейчас))
            слотов += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} не одобрилось: {str(ex)[:90]}")

print(f"\nснято с причиной: {снято}")
print(f"одобрено в отправку: {одобрено} (слотов поставлено {слотов})")
