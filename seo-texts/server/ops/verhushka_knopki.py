# -*- coding: utf-8 -*-
"""Ровно та выборка, что берёт кнопка «В автоотправку» (app.py bulk-to-auto):
pending без reply → фильтр группы → сортировка по баллу → первые N; и по
каждому — та же цепочка проверок. Только чтение.

    verhushka_knopki.py [gruppa=Россия 9000] [n=300]
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

им = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
ГР = им.get("gruppa", "Россия 9000")
N = int(им.get("n", "300"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cards = CompanyCards(index_path=r"C:\sender\obzvon-index.db", enrich_db_path=r"C:\sender\enrich.db")
cs = ConfirmSend(cfg, store, Suppression(store), cards=cards)
rows = cs.pending(limit=100_000)
print("pending всего: %d; шторка confirm.hide_before: %s" % (len(rows), store.get_setting("confirm.hide_before", None)))
rows = [r for r in rows if (r.get("kind") or "outbound") != "reply"]
карта = store.recipient_groups() or {}


def в_группе(r):
    наб = (карта.get("по_id") or {}).get(int(r["recipient_id"])) if r.get("recipient_id") else None
    if наб is None:
        наб = (карта.get("по_почте") or {}).get(str(r.get("email") or "").strip().lower())
    if наб is None:
        наб = (карта.get("по_инн") or {}).get("".join(ч for ч in str(r.get("inn") or "") if ч.isdigit()))
    return bool(наб) and ГР in наб


# gruppa=* — без фильтра группы (кнопка с выбором «все»)
rows = [r for r in rows if ГР == "*" or в_группе(r)]


def балл(r):
    try:
        return float(((r.get("panel") or {}).get("scoring") or {}).get("score") or -1)
    except (TypeError, ValueError):
        return -1.0


rows.sort(key=lambda r: (-балл(r), r.get("id") or 0))
print("в группе «%s»: %d" % (ГР, len(rows)))
св, прим = Counter(), {}
for i, r in enumerate(rows):
    п = r.get("panel") if isinstance(r.get("panel"), dict) else {}
    if ((п or {}).get("actions") or {}).get("confirm_hold"):
        к = "удержание: " + ",".join(sorted(str(f.get("code")) for f in (п.get("stop_flags") or [])))
    else:
        bl = cs._guard(inn=r.get("inn"), email=r.get("email") or "")
        if bl:
            к = "заслон: " + re.sub(r"\d+", "N", str(bl))[:60]
        else:
            dv = cs._division_blocked(r)
            к = ("направления: " + str(dv)[:50]) if dv else "ПРОХОДИТ"
    зона = "в первых %d" % N if i < N else "дальше"
    св[(зона, к)] += 1
    прим.setdefault((зона, к), "камп %s %s балл %.1f" % (r.get("campaign_id"), r.get("email"), балл(r)))
for (зона, к), n in sorted(св.items()):
    print("%-14s %5d  %s   (напр. %s)" % (зона, n, к, прим[(зона, к)]))
print("=== ВЕРХУШКА КНОПКИ ===")
