# -*- coding: utf-8 -*-
"""Два дописанных письма и два обычных — рядом, оба с вердиктом «годно».

Владелец смотрит глазами: разницу между «написано целиком» и «переписан
зачин» должно быть видно, а не следовать из моих слов.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ДОП = r"C:\sender\_ops\dopisannye-zachiny.jsonl"

верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

дописанные = {}
for s in io.open(ДОП, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("review_id") and not z.get("гейт"):
        дописанные[int(z["review_id"])] = z

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, COALESCE(rc.company_name, c.email, ''), "
        "COALESCE(c.subject,''), COALESCE(c.body,'') "
        "FROM confirm_reviews c LEFT JOIN recipients rc "
        "ON rc.id=c.recipient_id WHERE c.campaign_id=10 "
        "AND c.status IN ('pending','approved') ORDER BY c.id DESC "
        "LIMIT 500").fetchall()

доп_годные, обыч_годные = [], []
for rid, имя, тема, тело in ряды:
    if верд.get(int(rid)) != "годно":
        continue
    (доп_годные if int(rid) in дописанные else обыч_годные).append(
        (rid, имя, тема, тело))

print(f"годных в последних 500: дописанных {len(доп_годные)}, "
      f"обычных {len(обыч_годные)}")
for заголовок, список in (("ДОПИСАННЫЕ (переписан только зачин)", доп_годные),
                          ("ОБЫЧНЫЕ (написаны целиком)", обыч_годные)):
    print("\n" + "#" * 72)
    print(f"### {заголовок}")
    for rid, имя, тема, тело in список[:2]:
        print("#" * 72)
        print(f"#{rid}  {имя}\nТЕМА: {тема}\n\n{тело}\n")
