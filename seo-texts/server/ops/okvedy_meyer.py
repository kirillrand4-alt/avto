# -*- coding: utf-8 -*-
"""ОКВЭДы, недобранные в базу ПОД MEYER — с настоящими названиями кодов.

Meyer это фотосепараторы и рентген-инспекция: сортировка зерна, круп, семечки,
орехов, овощей и контроль включений в готовой еде. Покупатель — сельское
хозяйство и пищевая переработка.

Профиль строим по тем покупателям, у кого направление в карточке проставлено
как meyer, и отдельно показываем массу «направление не решено»: их 3 тысячи,
и по коду ОКВЭД видно, что большинство из них того же поля.

Названия ОКВЭД берём из seo.db call_company — там коды лежат С ПОДПИСЯМИ
(161k строк). Категории оборудования из obzvon.found_okveds для этого НЕ
годятся: это «Фотосепараторы», «Генераторы азота» — что мы продаём, а не чем
компания занимается.
"""
import os
import re
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ОБОГ = r"C:\sender\enrich.db"
SEO = r"C:\seostat\data\seo.db"
_ПАРА = re.compile(r"(\d{2}(?:\.\d{1,2}){0,3})\s+([А-ЯЁA-Z][^|;,\n]{4,120})")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def код(з):
    з = str(з or "").strip()
    if not з or not з[0].isdigit():
        return ""
    к = з.split()[0].strip().rstrip(".,;")
    return к if к and к[0].isdigit() else ""


# --- словарь кодов ------------------------------------------------------- #
имена = {}
if os.path.exists(SEO):
    s = sqlite3.connect("file:%s?mode=ro" % SEO, uri=True, timeout=30)
    s.row_factory = sqlite3.Row
    кол = {r["name"] for r in s.execute("PRAGMA table_info(call_company)")}
    поля = [p for p in ("okved_main", "okved_all") if p in кол]
    if поля:
        for r in s.execute("SELECT %s FROM call_company" % ", ".join(поля)):
            for п in поля:
                for м in _ПАРА.finditer(str(r[п] or "")):
                    имена.setdefault(м.group(1), м.group(2).strip()[:52])
    s.close()
print("названий ОКВЭД собрано: %d" % len(имена))

# --- покупатели ---------------------------------------------------------- #
c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()

e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
e.row_factory = sqlite3.Row
кодп, статус = {}, {}
for r in e.execute("SELECT inn, okved_main, status FROM requisites "
                   " WHERE COALESCE(ogrn,'')<>''"):
    и = цифры(r["inn"])
    if и:
        кодп[и] = код(r["okved_main"])
        статус[и] = str(r["status"] or "")
напр = {}
for r in e.execute("SELECT inn, division, okved FROM companies"):
    и = цифры(r["inn"])
    if и:
        напр[и] = str(r["division"] or "")
        if not кодп.get(и):
            кодп[и] = код(r["okved"])
e.close()

живые = [и for и in сделки
         if кодп.get(и) and статус.get(и, "ACTIVE") == "ACTIVE"]
мейер = [и for и in живые if напр.get(и) == "meyer"]
кц = [и for и in живые if напр.get(и) == "kc"]
неясно = [и for и in живые if напр.get(и, "") not in ("meyer", "kc")]
print("действующих покупателей с кодом: %d — meyer %d, кц %d, не решено %d"
      % (len(живые), len(мейер), len(кц), len(неясно)))

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
базкод = Counter()
for r in o.execute("SELECT okved_main FROM obzvon"):
    к = код(r[0])
    if к:
        базкод[к] += 1
o.close()
всего_базы = sum(базкод.values())


def таблица(инны, заголовок, порог=4):
    c = Counter(кодп[и] for и in инны)
    n = sum(c.values())
    print("\n=== %s (покупателей %d) ===" % (заголовок, n))
    print("%-10s %7s %8s %9s  %s"
          % ("ОКВЭД", "покуп.", "в базе", "доля пок.", "название"))
    итого_пок = итого_баз = 0
    for к, k in c.most_common(40):
        if k < порог:
            continue
        есть = базкод.get(к, 0)
        итого_пок += k
        итого_баз += есть
        print("%-10s %7d %8d %8.1f%%  %s"
              % (к, k, есть, 100.0 * k / n, имена.get(к, "—")[:48]))
    print("   покрыто строк: %d из %d; в базе по этим кодам всего %d компаний"
          % (итого_пок, n, итого_баз))
    return c, n


таблица(мейер, "ПРОФИЛЬ MEYER — направление проставлено")
таблица(неясно, "НАПРАВЛЕНИЕ НЕ РЕШЕНО — но код говорит сам", порог=12)
