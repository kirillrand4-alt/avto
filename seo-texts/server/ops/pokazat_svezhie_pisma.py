# -*- coding: utf-8 -*-
"""Показать свежие письма целиком — правило «одно из пятидесяти глазами».

Берём последние письма очереди с вердиктом «годно» и печатаем как есть.
Модель их уже проверила; смысл этого шага — чтобы человек (или я вместо
него ночью) увидел живой текст, а не только счётчики.
"""
import io
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))
РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"

верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        "SELECT id, COALESCE(email,''), COALESCE(subject,''), "
        "COALESCE(body,'') FROM confirm_reviews WHERE campaign_id=10 "
        "AND status='pending' ORDER BY id DESC LIMIT 400").fetchall()
# С аргументом «последние» показываем самые новые письма независимо от
# вердикта: у свежего прогона рецензии ещё нет, а посмотреть надо именно на
# то, что пишется сейчас.
ПОСЛЕДНИЕ = "последние" in sys.argv
годные = ([r for r in ряды] if ПОСЛЕДНИЕ
          else [r for r in ряды if верд.get(int(r[0])) == "годно"])
if ПОСЛЕДНИЕ:
    показ = годные[:СКОЛЬКО]
else:
    шаг = max(1, len(годные) // max(1, СКОЛЬКО))
    показ = [годные[i] for i in range(0, len(годные), шаг)][:СКОЛЬКО]
print(f"годных среди последних {len(ряды)} строк очереди: {len(годные)}; "
      f"показываю {len(показ)}\n")
for rid, email, тема, тело in показ:
    print("=" * 72)
    print(f"#{rid}  {email}")
    print(f"ТЕМА: {тема}\n")
    print(тело)
    print()
