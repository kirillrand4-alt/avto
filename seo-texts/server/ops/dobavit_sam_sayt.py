# -*- coding: utf-8 -*-
"""Доказательством владения сайтом считать и «компания опознана сайтом».

Список доказательств был {inn, ogrn, phone, provider} — всё это номера и
технические совпадения. Но есть законный случай, которого в нём нет: мы
НЕ называли юрлицо вовсе, компания опознана самим сайтом. Приписать такой
сайт чужой компании невозможно — чужой компании тут просто нет, сайт и
есть удостоверение личности. В книгах паспортов таких 3122 из 9565.

argv: --primenit чтобы записать.
"""
import io
import py_compile
import sys
import time

ФАЙЛ = r"C:\sender\sender\company_card.py"
ПРИМЕНИТЬ = "--primenit" in sys.argv

ЯКОРЬ = "_SITE_VERIFIED_OK = frozenset({\"inn\", \"ogrn\", \"phone\", \"provider\"})"
ЗАМЕНА = '''# «sam_sayt» — компания опознана ЭТИМ САЙТОМ, юрлица мы не называли.
# Приписать такой сайт чужой компании невозможно: чужой компании тут нет,
# сайт и есть удостоверение личности. Владелец 12.10: «либо принадлежит
# компании, либо мы вообще не указывали компанию, брали просто сайт».
_SITE_VERIFIED_OK = frozenset({"inn", "ogrn", "phone", "provider", "sam_sayt"})'''

т = io.open(ФАЙЛ, encoding="utf-8").read()
if "sam_sayt" in т:
    raise SystemExit("правка уже применена")
n = т.count(ЯКОРЬ)
print("якорь: вхождений %d" % n)
if n != 1:
    raise SystemExit("НЕ ТРОГАЕМ: якорь не сошёлся")
новый = т.replace(ЯКОРЬ, ЗАМЕНА, 1)
if not ПРИМЕНИТЬ:
    print("")
    print("=" * 74)
    print("=== ПОКАЗ БЕЗ ЗАПИСИ (нужен --primenit) ===")
    raise SystemExit(0)
бэкап = ФАЙЛ + ".bak-%d" % int(time.time())
io.open(бэкап, "w", encoding="utf-8").write(т)
io.open(ФАЙЛ, "w", encoding="utf-8").write(новый)
try:
    py_compile.compile(ФАЙЛ, doraise=True)
    sys.path.insert(0, r"C:\sender")
    from sender.company_card import _SITE_VERIFIED_OK           # noqa: E402
    итог = "записано; список доказательств: %s" % sorted(_SITE_VERIFIED_OK)
except Exception as ex:                                         # noqa: BLE001
    io.open(ФАЙЛ, "w", encoding="utf-8").write(т)
    итог = "НЕ ЗАРАБОТАЛО, откатили: %s" % str(ex)[:140]
print("")
print("=" * 74)
print("=== sam_sayt КАК ДОКАЗАТЕЛЬСТВО ===")
print("   бэкап: %s" % бэкап)
print("   итог:  %s" % итог)
