# -*- coding: utf-8 -*-
"""Привязать карточку 128 к компании: она нашлась по теме исходного письма.

Заводили её без компании — привязать было нечем. Но тема ответа несла
«Fwd: …для «Север»», и по ней нашлось наше письмо #6507: ООО «СЕВЕР»,
ИНН 7203576280, писали на sever-buhgalter1@mail.ru. Карточке от этого
только лучше: продавец видит, с кем говорит, а адрес ответившего остаётся
прежним — отвечать надо снабженцу, а не в бухгалтерию.
"""
import sqlite3
import sys

ДЕЛАТЬ = "primenit" in sys.argv[1:]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
до = c.execute("SELECT id, email, company_name, inn, recipient_id, version "
               "  FROM leads WHERE id=128").fetchone()
print("было:  %s" % dict(до))
if not ДЕЛАТЬ:
    print("\nвхолостую. Привязать — primenit")
    raise SystemExit(0)
c.execute("UPDATE leads SET recipient_id=15310, company_name='ООО \"СЕВЕР\"', "
          "       inn='7203576280', version=version+1, "
          "       updated_at=datetime('now') WHERE id=128")
c.commit()
после = c.execute("SELECT id, email, company_name, inn, recipient_id, version "
                  "  FROM leads WHERE id=128").fetchone()
print("стало: %s" % dict(после))
