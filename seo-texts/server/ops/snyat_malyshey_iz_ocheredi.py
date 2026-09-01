# -*- coding: utf-8 -*-
"""Снять из очереди неотправленные письма компаниям ниже порога выручки.

Отправленное не трогаем — его уже не вернуть. Снимаем только то, что ещё
не улетело: карточка переводится в skipped с причиной, письмо — тоже.
Компания при этом возвращается в пул: резюм partiya_gen считает снятых по
профилю возвращаемыми, а выручка от письма не зависит — вырастет, напишем.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ПОРОГ = 30_000_000
ПРИМЕНИТЬ = "--primenit" in sys.argv
ПРИЧИНА = ("выручка ниже 30 млн — вне условия отбора владельца "
           "(письмо создано до появления фильтра)")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
мелкие = set()
for r in e.execute("SELECT inn, revenue_rub FROM companies"
                   " WHERE revenue_rub IS NOT NULL AND revenue_rub > 0"
                   "   AND revenue_rub < ?", (ПОРОГ,)):
    и = цифры(r[0])
    if и:
        мелкие.add(и)
e.close()
print("компаний с известной выручкой ниже порога: %d" % len(мелкие))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
c.row_factory = sqlite3.Row
кандидаты = []
for r in c.execute(
        "SELECT cr.id, cr.inn, cr.status, cr.message_id, cr.email,"
        "       COALESCE(m.status,'нет письма') ms, m.sent_at,"
        "       r.company_name FROM confirm_reviews cr"
        "  LEFT JOIN messages m ON m.id=cr.message_id"
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id"
        " WHERE cr.campaign_id=11 AND cr.status IN ('pending','approved','edited')"
        "   AND COALESCE(cr.kind,'outbound')<>'reply' AND cr.inn IS NOT NULL"):
    if цифры(r["inn"]) in мелкие and not r["sent_at"]:
        кандидаты.append(dict(r))
c.close()

from collections import Counter
print("\n=== ЧТО СНИМАЕМ ===")
print("   писем к снятию: %d" % len(кандидаты))
print("   по статусу карточки: %s"
      % dict(Counter(x["status"] for x in кандидаты)))
print("   по статусу письма:   %s"
      % dict(Counter(x["ms"] for x in кандидаты)))
print("\n   примеры:")
for x in кандидаты[:8]:
    print("      %6s %-30s %s" % (x["id"], str(x["company_name"])[:30],
                                  x["email"]))

if not ПРИМЕНИТЬ:
    print("\n[сухой прогон] снять — с ключом --primenit")
    raise SystemExit(0)

снято_карточек = снято_писем = 0
for x in кандидаты:
    try:
        if store.confirm_decide(int(x["id"]), status="skipped",
                                decided_by="фильтр выручки",
                                reason=ПРИЧИНА):
            снято_карточек += 1
    except Exception:                                         # noqa: BLE001
        pass
    if x["message_id"]:
        try:
            if store.mark_skipped_if_not_terminal(int(x["message_id"]),
                                                  ПРИЧИНА):
                снято_писем += 1
        except Exception:                                     # noqa: BLE001
            pass
print("\n=== ИТОГ ===")
print("снято карточек: %d, снято писем: %d" % (снято_карточек, снято_писем))
