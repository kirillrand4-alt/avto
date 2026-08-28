# -*- coding: utf-8 -*-
"""Запас копий по условиям владельца: 1 адрес на компанию, письмо ушло
раньше 3 дней назад, кадры и бухгалтерию не берём. Только SELECT."""
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ДНЕЙ = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))
ПОЧТОВИКИ = {
    "mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru", "yandex.ru",
    "ya.ru", "yandex.com", "narod.ru", "gmail.com", "googlemail.com",
    "rambler.ru", "lenta.ru", "autorambler.ru", "ro.ru", "myrambler.ru",
    "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com",
    "yahoo.com", "bigmir.net", "ukr.net", "i.ua", "tut.by", "mail.by",
    "qq.com", "163.com", "126.com", "sina.com",
}
ПРИГОВОР = {"нет ящика", "нет MX"}
НЕЛЬЗЯ_РОЛЬ = {"кадры", "бухгалтерия"}
# Шкала едина с skolko_eshchyo_dostanem.py: продажи внизу, потому что отдел
# продаж ничего не покупает (владелец 28.08).
ВЕС = {"снабжение/закупки": 0,
       "нач.производства": 1, "нач.цеха": 1, "гл.инженер": 1,
       "гл.конструктор": 2, "инженер (не главный)": 2,
       "техконтакт": 3, "директор": 4,
       "общий": 5, "приёмная": 6, "свой": 7,
       "продажи": 8}
порог = (datetime.now(timezone.utc) - timedelta(days=ДНЕЙ)).strftime("%Y-%m-%d")
print("берём компании, которым письмо ушло не позже %s" % порог)

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
s.row_factory = sqlite3.Row
послано, давность = {}, {}
for r in s.execute(
        "SELECT m.recipient_id rid, r.inn, r.email, MAX(m.sent_at) kogda "
        "  FROM messages m JOIN recipients r ON r.id = m.recipient_id "
        " WHERE m.status='sent' AND m.sent_at IS NOT NULL "
        " GROUP BY m.recipient_id"):
    if r["inn"]:
        послано[int(r["rid"])] = (str(r["inn"]), (r["email"] or "").lower())
        давность[int(r["rid"])] = str(r["kogda"])[:10]
ответили = {int(r[0]) for r in s.execute(
    "SELECT DISTINCT recipient_id FROM events "
    " WHERE event_type IN ('reply','reply_auto') AND recipient_id IS NOT NULL")}
инн_ответили = {послано[rid][0] for rid in ответили if rid in послано}

свежие = {rid for rid, д in давность.items() if д > порог}
молч = {}
for rid, (инн, почта) in послано.items():
    if инн in инн_ответили or rid in свежие:
        continue
    молч.setdefault(инн, set()).add(почта)
print("получателей с отправленным письмом: %d" % len(послано))
print("   отсеяли ответивших:              %d компаний" % len(инн_ответили))
print("   отсеяли свежее %d дней:           %d получателей" % (ДНЕЙ, len(свежие)))
print("компаний-кандидатов:                %d" % len(молч))

уже = {(r[0] or "").lower() for r in s.execute(
    "SELECT email FROM recipients WHERE email IS NOT NULL")}
стоп = {(r[0] or "").lower() for r in s.execute(
    "SELECT value FROM suppression WHERE scope IN ('email','address')")}
s.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
инны = sorted(молч)
сайт = {}
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, site FROM companies WHERE inn IN (%s)" % зн, к):
        м = re.search(r"//([^/]+)", str(r["site"] or ""))
        д = (м.group(1) if м else str(r["site"] or "")).lower()
        д = д[4:] if д.startswith("www.") else д
        if д and "." in д:
            сайт[str(r["inn"])] = д

этап = Counter()
годные = defaultdict(list)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute(
            "SELECT inn, email, role, person, probe_verdict, mx_ok "
            "  FROM emails WHERE inn IN (%s)" % зн, к):
        инн = str(r["inn"])
        почта = (r["email"] or "").lower().strip()
        if "@" not in почта:
            continue
        дом = почта.split("@", 1)[1]
        этап["адресов у кандидатов"] += 1
        родной = {d for d in ({сайт.get(инн)} |
                              {a.split("@", 1)[1] for a in молч[инн] if "@" in a})
                  if d and d not in ПОЧТОВИКИ}
        if дом in ПОЧТОВИКИ or дом not in родной:
            этап["не домен компании"] += 1
            continue
        if почта in молч[инн]:
            этап["тот же адрес"] += 1
            continue
        if почта in уже:
            этап["уже заведён получателем"] += 1
            continue
        if почта in стоп:
            этап["в стоп-листе"] += 1
            continue
        if (r["probe_verdict"] or "") in ПРИГОВОР or r["mx_ok"] == 0:
            этап["приговор пробы / нет MX"] += 1
            continue
        роль = (r["role"] or "").strip()
        if роль in НЕЛЬЗЯ_РОЛЬ:
            этап["кадры/бухгалтерия"] += 1
            continue
        этап["ГОДЕН"] += 1
        годные[инн].append((ВЕС.get(роль, 9), 0 if r["person"] else 1,
                            0 if (r["probe_verdict"] or "") == "есть" else 1,
                            почта, роль, r["person"] or ""))
e.close()

print("")
print("=== отсев адресов ===")
for к, n in этап.most_common():
    print("   %-30s %7d" % (к, n))

выбор = {инн: sorted(v)[0] for инн, v in годные.items()}
print("")
print("=== ИТОГ: по 1 письму на компанию ===")
print("писем получится:               %d" % len(выбор))
print("   с известным именем адресата: %d" % sum(1 for v in выбор.values() if v[5]))
print("")
print("=== роли выбранных ===")
for к, n in Counter(v[4] or "—" for v in выбор.values()).most_common(12):
    print("   %-24s %6d" % (к, n))
print("")
print("=== примеры выбора ===")
for инн, v in list(sorted(выбор.items()))[:6]:
    print("   %-13s %-32s %-20s %s" % (инн, v[3][:32], v[4], v[5][:26]))
