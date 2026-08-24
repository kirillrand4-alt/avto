# -*- coding: utf-8 -*-
"""Ловит ли линза направления письмо про рентген переработчику медотходов.

По всей очереди линза дала ноль отказов на 325 писем — значит либо писем
такого рода не осталось, либо линза их не видит. Проверяем на конкретном
письме, которое владелец показал как бредовое.
"""
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import vf_prompt                        # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT cr.id, cr.status, cr.subject, cr.body, r.company_name, r.okved "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE r.company_name LIKE '%МЕРИДИАН%' ORDER BY cr.id DESC LIMIT 3").fetchall()
if not строки:
    print("карточек «Меридиан» не найдено")
    raise SystemExit(0)
for р in строки:
    print("=== #%s (%s) %s | ОКВЭД %s ==="
          % (р["id"], р["status"], str(р["company_name"])[:44],
             str(р["okved"])[:44]))
    print("тема: %s" % р["subject"])
    print(str(р["body"])[:600])
    п = vf_prompt([(0, str(р["subject"]), str(р["body"]))], "meyer")
    сис, тело = gen_provider.razrezat_promt(п)
    m = gen_provider._raw_stream([{"role": "user", "content": тело}],
                                 "claude-sonnet-4-6", 700, thinking=False,
                                 effort="low", system=сис)
    т = "".join(b.text for b in m.content if getattr(b, "type", "") == "text")
    print("\nОТВЕТ ЛИНЗЫ: %s" % т[:400])
    print("-" * 70)

print("\n=== ЧТО ВООБЩЕ ПРОВЕРЯЕТ vf_prompt (первые строки) ===")
п = vf_prompt([(0, "тема", "тело")], "meyer")
сис, _ = gen_provider.razrezat_promt(п)
for с in (сис or п).split("\n")[:22]:
    print("  | %s" % с[:120])
