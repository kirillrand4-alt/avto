# -*- coding: utf-8 -*-
"""Отказы почтовика сегодня: по часам и по направлению.

Убрал ссылку - отказы не ушли: все десять поправленных писем Яндекс всё
равно не принял. Значит дело не в ссылке, а в самих доменах. Если отказы
идут кучно по мейеровским и нарастают к вечеру - домен придушен, и слать с
него сегодня нельзя.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT m.id, m.campaign_id, substr(m.updated_at,12,2) час, "
    "       COALESCE(m.last_error,'') err FROM messages m "
    " WHERE substr(m.updated_at,1,10)='2026-08-21'").fetchall()
отказ = [р for р in ряды if "suspicion of SPAM" in р["err"]]


def напр(камп):
    return "КЦ" if int(камп or 0) in (9, 10) else "Meyer"


print(f"отказов сегодня: {len(отказ)}")
print("по направлению:", dict(Counter(напр(р["campaign_id"]) for р in отказ)))
ушло = c.execute(
    "SELECT campaign_id, substr(COALESCE(sent_at,updated_at),12,2) час "
    "  FROM messages WHERE status='sent' "
    "   AND substr(COALESCE(sent_at,updated_at),1,10)='2026-08-21'").fetchall()
print(f"\n{'час UTC':<9} {'КЦ ушло':>8} {'КЦ отказ':>9} {'Meyer ушло':>11} "
      f"{'Meyer отказ':>12}")
for ч in sorted({str(р["час"]) for р in ушло} | {str(р["час"]) for р in отказ}):
    ку = sum(1 for р in ушло if str(р["час"]) == ч and напр(р["campaign_id"]) == "КЦ")
    ко = sum(1 for р in отказ if str(р["час"]) == ч and напр(р["campaign_id"]) == "КЦ")
    му = sum(1 for р in ушло if str(р["час"]) == ч and напр(р["campaign_id"]) == "Meyer")
    мо = sum(1 for р in отказ if str(р["час"]) == ч and напр(р["campaign_id"]) == "Meyer")
    print(f"{ч}:00     {ку:>8} {ко:>9} {му:>11} {мо:>12}")
кцу = sum(1 for р in ушло if напр(р["campaign_id"]) == "КЦ")
кцо = sum(1 for р in отказ if напр(р["campaign_id"]) == "КЦ")
мйу = sum(1 for р in ушло if напр(р["campaign_id"]) == "Meyer")
мйо = sum(1 for р in отказ if напр(р["campaign_id"]) == "Meyer")
print(f"\n  КЦ:    ушло {кцу:>4}, отказов {кцо:>3} = "
      f"{100.0*кцо/(кцу+кцо) if (кцу+кцо) else 0:.1f}%")
print(f"  Meyer: ушло {мйу:>4}, отказов {мйо:>3} = "
      f"{100.0*мйо/(мйу+мйо) if (мйу+мйо) else 0:.1f}%")
