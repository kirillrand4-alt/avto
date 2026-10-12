# -*- coding: utf-8 -*-
"""Что сломается, если ключом сделать домен сайта вместо ИНН.

Проверяем живьём на трёх видах ключа: домен, белорусский УНП и его же
цифрами. Ничего не записываем — только читаем.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.company_card import build_company_card, norm_inn    # noqa: E402
from sender.store import Store                                  # noqa: E402

КЛЮЧИ = ["rassvet.by", "BY100058367", "100058367", "2318030280"]
store = Store(r"C:\sender\sender.db")

print("--- norm_inn: во что превращается ключ перед поиском ---")
for к in КЛЮЧИ:
    print("   %-16s → «%s»" % (к, norm_inn(к)))

print("")
print("--- build_company_card: что вернётся ---")
for к in КЛЮЧИ:
    try:
        карта = build_company_card(к, enrich_db_path=r"C:\sender\enrich.db")
    except Exception as ex:                                     # noqa: BLE001
        print("   %-16s ОШИБКА: %s" % (к, str(ex)[:70]))
        continue
    ен = карта.get("enrich") or {}
    комп = ен.get("company") or {}
    print("   %-16s inn в карточке «%s», обогащение доступно=%s, "
          "компания найдена=%s, адресов=%d"
          % (к, карта.get("inn"), ен.get("available"),
             "да" if комп else "НЕТ", len(ен.get("emails") or [])))

print("")
print("--- dialog_thread_company: переписка карточки лида ---")
for к in КЛЮЧИ:
    try:
        н = len(store.dialog_thread_company(к) or [])
        print("   %-16s элементов переписки: %d%s"
              % (к, н, "   ← пусто, лента диалога не соберётся"
                 if н == 0 else ""))
    except Exception as ex:                                     # noqa: BLE001
        print("   %-16s ОШИБКА: %s" % (к, str(ex)[:70]))

print("")
print("--- confirm_dedup_key: ключ идемпотентности письма ---")
for к in КЛЮЧИ:
    print("   %-16s → %s" % (к, store.confirm_dedup_key(к, "a@b.ru", 11)))

print("")
print("--- сколько мест режут ИНН до цифр ---")
import os
import re
n = 0
for корень, _, файлы in os.walk(r"C:\sender\sender"):
    for ф in файлы:
        if not ф.endswith(".py") or ".bak" in ф:
            continue
        try:
            т = open(os.path.join(корень, ф), encoding="utf-8",
                     errors="replace").read()
        except Exception:                                       # noqa: BLE001
            continue
        к = len(re.findall(r"if c\.isdigit\(\)|if ch\.isdigit\(\)", т))
        if к:
            n += к
            print("   %-28s %d" % (ф, к))
print("   всего мест: %d" % n)
print("")
print("=" * 74)
print("=== ЧТО СЛОМАЕТ КЛЮЧ-ДОМЕН ===")
