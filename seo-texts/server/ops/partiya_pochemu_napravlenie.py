# -*- coding: utf-8 -*-
"""Почему письму досталось это направление: печатаем причину, а не догадку.

Вопрос владельца по письму #1280: «почему направление не из карточки
бралось?». В карточке у этого завода стоит `division = 'kc+meyer'` - то
есть направление там ЕСТЬ, но составное, и одно из двух ему выбрал не
карточный признак. Кто именно - записано самим конвейером в
panel.letter_division_reason, и читать надо это поле, а не рассуждать.

Печатаем на письмо: кампанию, letter_division, letter_division_reason,
division карточки, ОКВЭД и роль ящика - весь вход решения разом.

    python zapusk_svoego_skripta.py ops/partiya_pochemu_napravlenie.py 1280 1285
"""
import json
import sqlite3
import sys

БАЗА = r"C:\sender\sender.db"
ОТ = int(sys.argv[1]) if len(sys.argv) > 1 else 1280
ДО = int(sys.argv[2]) if len(sys.argv) > 2 else 1285

conn = sqlite3.connect(f"file:{БАЗА}?mode=ro", uri=True, timeout=30)
conn.row_factory = sqlite3.Row

for r in conn.execute(
        "SELECT id, campaign_id, email, panel_json FROM confirm_reviews "
        "WHERE id BETWEEN ? AND ? ORDER BY id", (ОТ, ДО)):
    try:
        p = json.loads(r["panel_json"] or "{}")
    except Exception:                                          # noqa: BLE001
        p = {}
    comp = p.get("company") if isinstance(p.get("company"), dict) else {}
    full = p.get("company_full") if isinstance(
        p.get("company_full"), dict) else {}
    cont = p.get("contact") if isinstance(p.get("contact"), dict) else {}
    print(f"#{r['id']} камп.{r['campaign_id']} {r['email']}")
    print(f"   letter_division = {p.get('letter_division')!r}")
    print(f"   причина         = {str(p.get('letter_division_reason'))[:300]!r}")
    print(f"   карточка.division = {comp.get('division')!r} | "
          f"company_full.division = {full.get('division')!r}")
    print(f"   ОКВЭД = {comp.get('okved')!r} | роль ящика = {cont.get('role')!r}")
    print(f"   news_url = {str(p.get('news_url') or '')[:90]!r}")
