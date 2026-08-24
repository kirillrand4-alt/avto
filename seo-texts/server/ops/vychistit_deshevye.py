# -*- coding: utf-8 -*-
"""Вычистить из очереди письма дешёвой партии, ушедшие не тому адресату.

В дешёвом генераторе я не перенёс три заслона старой схемы: бесплатный
минус_класс (медицина и прочие нецелевые по ОКВЭД), гейт адресата и
инженерную линзу. В очередь легли письма вроде рентген-инспекции для
переработчика медотходов и компрессоров для медицинской лаборатории.

Здесь проходим по карточкам, положенным дешёвой схемой, и снимаем те, что
не проходят минус_класс (бесплатно) и гейт адресата (линза, дёшево).

Без аргумента — сухой прогон. Снимает при --снять.
"""
import io
import json
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.target_gate import build_target_gate, минус_класс  # noqa: E402

СНЯТЬ = "--снять" in sys.argv or "--snyat" in sys.argv
ОТЧЁТ = r"C:\sender\_ops\deshevaya-partiya.jsonl"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

ид = []
for с in io.open(ОТЧЁТ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("ок") and з.get("review_id"):
        ид.append((int(з["review_id"]), з))
print("карточек дешёвой партии в очереди: %d" % len(ид))

# --- 1. минус-класс: бесплатно ------------------------------------------- #
минус, остальные = [], []
for rid_, з in ид:
    rec = store.get_recipient(з.get("recipient_id"))
    if not rec:
        continue
    if минус_класс(getattr(rec, "okved", ""), getattr(rec, "company_name", "")):
        минус.append((rid_, з, rec))
    else:
        остальные.append((rid_, з, rec))
print("\n=== МИНУС-КЛАСС (бесплатный фильтр) ===")
print("  под снятие: %d" % len(минус))
for rid_, з, rec in минус[:12]:
    print("  #%-6s %-40s %s" % (rid_, str(getattr(rec, "company_name", ""))[:40],
                                str(getattr(rec, "okved", ""))[:44]))

# --- 2. гейт адресата: линза --------------------------------------------- #
print("\n=== ГЕЙТ АДРЕСАТА (линза) ===")
не_покупатели = []
try:
    гейт = build_target_gate(cfg.get("service.db_path", r"C:\sender\sender.db"),
                             cfg)
    записи = [{"inn": з.get("inn"),
               "company_name": getattr(rec, "company_name", ""),
               "okved": getattr(rec, "okved", ""),
               "email": getattr(rec, "email", "")}
              for rid_, з, rec in остальные]
    пачка = 8
    плохие_инн = set()
    for i in range(0, len(записи), пачка):
        часть = записи[i:i + пачка]
        try:
            вердикт = гейт.not_buyers(часть)
        except Exception as e:  # noqa: BLE001
            print("  гейт споткнулся: %s" % str(e)[:110])
            вердикт = set()
        плохие_инн |= set(вердикт)
        print("  пачка %d/%d: не покупателей %d"
              % (i // пачка + 1, (len(записи) + пачка - 1) // пачка,
                 len(вердикт)))
    не_покупатели = [(r, з, rec) for r, з, rec in остальные
                     if str(з.get("inn")) in плохие_инн]
except Exception as e:  # noqa: BLE001
    print("  гейт не собрался: %s" % str(e)[:140])
print("  под снятие по гейту: %d" % len(не_покупатели))
for rid_, з, rec in не_покупатели[:10]:
    print("  #%-6s %s" % (rid_, str(getattr(rec, "company_name", ""))[:44]))

к_снятию = {r: (з, rec, "минус-класс") for r, з, rec in минус}
for r, з, rec in не_покупатели:
    к_снятию.setdefault(r, (з, rec, "гейт адресата: не покупатель"))
print("\nвсего под снятие: %d из %d" % (len(к_снятию), len(ид)))

if not СНЯТЬ:
    print("\nсухой прогон. Снять — аргумент --снять")
    raise SystemExit(0)

снято = 0
for r, (з, rec, причина) in к_снятию.items():
    try:
        ok = store.confirm_decide(r, status="skipped",
                                  decided_by="чистка дешёвой партии",
                                  reason=причина)
        if ok:
            снято += 1
        elif з.get("recipient_id"):
            стр = store._conn.execute(
                "SELECT message_id FROM confirm_reviews WHERE id=?",
                (r,)).fetchone()
            if стр and стр[0]:
                store.mark_skipped_if_not_terminal(
                    int(стр[0]), "чистка дешёвой партии: " + причина)
                снято += 1
    except Exception as e:  # noqa: BLE001
        print("  #%s: %s" % (r, str(e)[:100]))
print("\nснято: %d" % снято)
