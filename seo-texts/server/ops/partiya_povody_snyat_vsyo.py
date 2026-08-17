# -*- coding: utf-8 -*-
"""Компания с чужим поводом снимается целиком: все её новости и все письма.

Владелец 17.08: «сними все поводы у тех, которых были сняты сейчас + сними
письма компаний как я тебе показал».

Почему это правильнее моего первого захода. Я карантинил только осуждённый
сигнал, берёг остальные - и у осуждённых ИНН тут же всплыл следующий по
накалу повод, у «Агрофирмы Прогресс» ровно та же беда с тёзкой. Если
матчинг привязал к компании чужую новость один раз, доверия нет всей её
подборке: там сидит один и тот же однофамилец.

Два действия, оба обратимые:
1. ВСЕ сигналы осуждённого ИНН -> suspect=1. Строки остаются в базе.
2. ВСЕ письма этой компании в очереди (pending и approved) -> skipped,
   независимо от того, звучит в них новость или нет. Одобренные снимаются
   тем же путём, каким это делает штатный скип - карточка и письмо в
   messages одной транзакцией, - потому что confirm_decide уже решённую
   карточку не перерешивает. Отправленное не трогаем: историю отправки
   переписывать нельзя.

Сухой прогон; писать - argv[1] == "primenit".
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ПРИГОВОРЫ = r"C:\sender\_ops\povody-prigovory.jsonl"
ENRICH = r"C:\sender\enrich.db"
ПРИЧИНА = ("компания снята судом поводов 17.08: новость оказалась про "
           "другое предприятие")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

приговор = {}
for s in (io.open(ПРИГОВОРЫ, encoding="utf-8")
          if os.path.exists(ПРИГОВОРЫ) else []):
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    if "своя" in (z.get("приговор") or {}):
        приговор[str(z.get("inn"))] = z
чужие = sorted(k for k, v in приговор.items()
               if v["приговор"].get("своя") is False)
print(f"приговоров {len(приговор)} | ЧУЖИХ КОМПАНИЙ {len(чужие)}")
if not чужие:
    raise SystemExit(0)

# --- 1. все новости этих компаний в карантин -----------------------------
con = sqlite3.connect(ENRICH, timeout=60)
q = ",".join("?" * len(чужие))
было = con.execute(
    f"SELECT COUNT(*) FROM signals WHERE inn IN ({q})", чужие).fetchone()[0]
вне = con.execute(
    f"SELECT COUNT(*) FROM signals WHERE COALESCE(suspect,0)=0 "
    f"AND inn IN ({q})", чужие).fetchone()[0]
print(f"сигналов у этих компаний: {было} | вне карантина было: {вне}")
if ПРИМЕНИТЬ:
    cur = con.execute(
        f"UPDATE signals SET suspect=1 WHERE COALESCE(suspect,0)=0 "
        f"AND inn IN ({q})", чужие)
    con.commit()
    осталось = con.execute(
        f"SELECT COUNT(*) FROM signals WHERE COALESCE(suspect,0)=0 "
        f"AND inn IN ({q})", чужие).fetchone()[0]
    print(f"уведено в карантин: {cur.rowcount} | вне карантина осталось: "
          f"{осталось}")
con.close()

# --- 2. все письма этих компаний из очереди ------------------------------
чужие_нн = set(чужие)
письма = []
for ст in ("pending", "approved"):
    for r in (store.confirm_list(status=ст, limit=100000) or []):
        if str(r.get("inn") or "") in чужие_нн:
            письма.append(r)
print(f"\nписем этих компаний в очереди: {len(письма)}")

счёт = Counter()
now = datetime.now(timezone.utc).isoformat()
for r in письма:
    rid = int(r["id"])
    имя = str(приговор[str(r.get("inn"))].get("имя"))[:38]
    print(f"  #{rid:<6} {str(r.get('status')):<9} {имя:<40} "
          f"{str(r.get('subject'))[:52]}")
    if not ПРИМЕНИТЬ:
        счёт["снял бы"] += 1
        continue
    if str(r.get("status")) == "pending":
        ок = store.confirm_decide(rid, status="skipped",
                                  decided_by="суд поводов", reason=ПРИЧИНА)
        счёт["снято pending" if ок else "pending не снялось"] += 1
        continue
    # approved: штатный путь уже решённое не перерешивает - делаем то же
    # самое руками, одной транзакцией, и не трогаем уже отправленное.
    with store.transaction() as conn:
        conn.execute(
            "UPDATE confirm_reviews SET status='skipped', reason=?, "
            "decided_by=?, decided_at=?, updated_at=? WHERE id=?",
            (ПРИЧИНА, "суд поводов", now, now, rid))
        mid = r.get("message_id")
        if mid is not None:
            c2 = conn.execute(
                "UPDATE messages SET status='skipped', last_error=?, "
                "updated_at=? WHERE id=? AND status NOT IN "
                "('sent','skipped','failed')",
                (f"confirm:skipped:{ПРИЧИНА}", now, int(mid)))
            счёт["снято approved" if c2.rowcount
                 else "approved снят, но письмо уже ОТПРАВЛЕНО"] += 1
        else:
            счёт["снято approved (без message_id)"] += 1

print()
for k, n in счёт.most_common():
    print(f"  {k:<44} {n}")
if not ПРИМЕНИТЬ:
    print("\nсухой прогон: ничего не менял")
