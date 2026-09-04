# -*- coding: utf-8 -*-
"""Кто отвечает на мейеровские письма: доля ответов по классам ОКВЭД.

Считаем по ОТПРАВЛЕННЫМ письмам, а не по сгенерированным: годность письма
и готовность человека ответить — разные вещи, и решает вторая.
"""
import sqlite3
from collections import Counter, defaultdict

НАЗВ = {"01": "сельское хозяйство", "10": "производство продуктов",
        "11": "напитки", "03": "рыболовство", "46": "оптовая торговля",
        "52": "склады", "25": "металлоизделия", "20": "химия",
        "22": "пластмассы", "28": "машины", "35": "энергетика",
        "41": "строительство", "42": "инженерные сооружения",
        "43": "стройработы", "macro": ""}


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=180)
оквэд = {}
for и, к in e.execute("SELECT inn, okved FROM companies"):
    ц = цифры(и)
    if ц:
        оквэд[ц] = str(к or "")
e.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=180)
s.row_factory = sqlite3.Row
# отправленные письма Meyer (кампания 11)
отпр = defaultdict(set)
инн_по_получателю = {}
for r in s.execute(
        "SELECT sl.inn, sl.email, sl.campaign_id, r.id AS rid "
        "  FROM send_log sl LEFT JOIN recipients r ON r.email = sl.email "
        " WHERE sl.outcome='sent' AND sl.campaign_id=11"):
    и = цифры(r["inn"])
    if и:
        отпр[и].add(r["email"])
        if r["rid"]:
            инн_по_получателю[int(r["rid"])] = и

ответившие = set()
for r in s.execute("SELECT recipient_id FROM events WHERE event_type='reply'"):
    и = инн_по_получателю.get(int(r["recipient_id"] or 0))
    if и:
        ответившие.add(и)
s.close()

по_классу = defaultdict(lambda: [0, 0])
для_кодов = defaultdict(lambda: [0, 0])
for и in отпр:
    кл = (оквэд.get(и) or "?").split(".")[0]
    по_классу[кл][0] += 1
    для_кодов[(оквэд.get(и) or "?")[:7]][0] += 1
    if и in ответившие:
        по_классу[кл][1] += 1
        для_кодов[(оквэд.get(и) or "?")[:7]][1] += 1

строки = sorted(по_классу.items(), key=lambda x: -x[1][0])

print("=" * 78)
print("=== СВОДКА: КТО ОТВЕЧАЕТ НА ПИСЬМА MEYER ===")
print("компаний с отправленным письмом: %d; ответили: %d (%.1f%%)"
      % (len(отпр), len(ответившие & set(отпр)),
         100.0 * len(ответившие & set(отпр)) / len(отпр) if отпр else 0))
print("")
print("--- ПО КЛАССАМ ОКВЭД (только где писем 20+) ---")
for кл, (всего, отв) in строки:
    if всего < 20:
        continue
    print("   %-4s %-26s писем %5d  ответов %4d  (%4.1f%%)"
          % (кл, НАЗВ.get(кл, "")[:26], всего, отв,
             100.0 * отв / всего if всего else 0))
print("")
print("--- КОДЫ ВНУТРИ КЛАССА 01 ---")
for код, (всего, отв) in sorted(для_кодов.items(), key=lambda x: -x[1][0]):
    if not код.startswith("01") or всего < 5:
        continue
    print("   %-9s писем %4d  ответов %3d  (%4.1f%%)"
          % (код, всего, отв, 100.0 * отв / всего if всего else 0))
