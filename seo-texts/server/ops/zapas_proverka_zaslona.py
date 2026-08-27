# -*- coding: utf-8 -*-
"""Три проверки перед постановкой: заслон 90 дней, источник тела, формат ФИО."""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])
выбор = {инн: sorted(v)[0] for инн, v in годные.items()}
print("")
print("выбрано компаний: %d" % len(выбор))

from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

задет = 0
пример = []
for инн, v in list(выбор.items()):
    last = store.last_contact(email=v[3], inn=инн)
    if last:
        задет += 1
        if len(пример) < 3:
            пример.append((инн, v[3], str(last.get("ts"))[:10]))
print("")
print("=== заслон «повторный контакт <90 дней» ===")
print("упрётся в заслон: %d из %d" % (задет, len(выбор)))
for и, п, т in пример:
    print("   %-13s %-30s последняя отправка %s" % (и, п[:30], т))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
инны = list(выбор)
есть_шаблон = метка = приветствие_с_именем = 0
темы = []
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in c.execute(
            "SELECT inn, subject, body FROM confirm_reviews "
            " WHERE inn IN (%s) AND status IN ('approved','sent','pending') "
            "   AND COALESCE(body,'') <> ''" % зн, к):
        есть_шаблон += 1
        б = r["body"] or ""
        if "ИМЯ_ОТПРАВИТЕЛЯ" in б:
            метка += 1
        if re.match(r"(?i)^\s*(добрый день|здравствуйте)\s*,", б):
            приветствие_с_именем += 1
        if len(темы) < 3:
            темы.append((r["inn"], r["subject"], б.split("\n", 1)[0]))
c.close()
print("")
print("=== источник тела (confirm_reviews) ===")
print("карточек с телом:            %d" % есть_шаблон)
print("   с меткой ИМЯ_ОТПРАВИТЕЛЯ: %d" % метка)
print("   приветствие с именем:     %d" % приветствие_с_именем)
for и, т, п in темы:
    print("   %-13s тема: %-40s | %s" % (и, str(т)[:40], п[:38]))

формы = Counter()
for v in выбор.values():
    п = (v[5] or "").strip()
    формы["пусто" if not п else "слов: %d" % len(п.split())] += 1
print("")
print("=== формат ФИО в обогащении ===")
for к, n in формы.most_common():
    print("   %-12s %5d" % (к, n))
print("   примеры: %s" % "; ".join(
    v[5] for v in list(выбор.values()) if v[5])[:140])
