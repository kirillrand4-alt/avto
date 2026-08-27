# -*- coding: utf-8 -*-
"""Сколько копий письма можно поставить в очередь на ЗАПАСНЫЕ адреса того же
домена компании — там, где письмо ушло, а ответа не было.

Считаем, не трогая базу: только SELECT.
"""
import re
import sqlite3
from collections import Counter, defaultdict

ПОЧТОВИКИ = {
    "mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru",
    "yandex.ru", "ya.ru", "yandex.com", "narod.ru",
    "gmail.com", "googlemail.com", "rambler.ru", "lenta.ru", "autorambler.ru",
    "ro.ru", "myrambler.ru", "outlook.com", "hotmail.com", "live.com",
    "icloud.com", "me.com", "yahoo.com", "bigmir.net", "ukr.net", "i.ua",
    "tut.by", "mail.by", "qq.com", "163.com", "126.com", "sina.com",
}
ПРИГОВОР = {"нет ящика", "нет MX"}

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
s.row_factory = sqlite3.Row

# 1. кому реально ушло письмо
послано = {}                       # recipient_id -> (inn, email, domain)
for r in s.execute(
        "SELECT DISTINCT m.recipient_id rid, r.inn, r.email, r.domain "
        "  FROM messages m JOIN recipients r ON r.id = m.recipient_id "
        " WHERE m.status = 'sent'"):
    if r["inn"]:
        послано[int(r["rid"])] = (str(r["inn"]), (r["email"] or "").lower(),
                                  (r["domain"] or "").lower())
print("получателей, которым ушло письмо: %d" % len(послано))

# 2. кто ответил / у кого письмо отскочило
ответили = {int(r[0]) for r in s.execute(
    "SELECT DISTINCT recipient_id FROM events "
    " WHERE event_type IN ('reply','reply_auto') AND recipient_id IS NOT NULL")}
отскок = {int(r[0]) for r in s.execute(
    "SELECT DISTINCT recipient_id FROM events "
    " WHERE event_type IN ('bounce','reject_spam') AND recipient_id IS NOT NULL")}
инн_ответили = {послано[rid][0] for rid in ответили if rid in послано}
молчат = {rid: v for rid, v in послано.items() if v[0] not in инн_ответили}
print("   из них ответили:            %d получателей (%d компаний)"
      % (len(ответили & set(послано)), len(инн_ответили)))
print("   молчат:                     %d получателей" % len(молчат))
print("   (из молчащих письмо отскочило у %d)"
      % len([r for r in молчат if r in отскок]))

# компании-молчуны и адрес, на который уже писали
молч_инн = defaultdict(set)        # inn -> {адреса, на которые уже писали}
for rid, (инн, почта, дом) in молчат.items():
    молч_инн[инн].add(почта)
print("компаний-молчунов:             %d" % len(молч_инн))

# все адреса, на которые вообще заводили получателя (чтобы не дублировать)
уже_заведены = set()
for r in s.execute("SELECT email FROM recipients WHERE email IS NOT NULL"):
    уже_заведены.add((r[0] or "").lower())

# стоп-лист
стоп = {(r[0] or "").lower() for r in s.execute(
    "SELECT value FROM suppression WHERE scope IN ('email','address')")}
стоп_дом = {(r[0] or "").lower() for r in s.execute(
    "SELECT value FROM suppression WHERE scope = 'domain'")}
s.close()
print("в стоп-листе адресов: %d, доменов: %d" % (len(стоп), len(стоп_дом)))

# 3. запасные адреса из обогащения
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
инны = sorted(молч_инн)
сайт_дом = {}
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, site FROM companies WHERE inn IN (%s)" % зн, к):
        м = re.search(r"//([^/]+)", str(r["site"] or ""))
        д = (м.group(1) if м else str(r["site"] or "")).lower().lstrip("www.")
        if д and "." in д:
            сайт_дом[str(r["inn"])] = д

этап = Counter()
кандидаты = defaultdict(list)
роли = Counter()
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute(
            "SELECT inn, email, role, person, probe_verdict, addr_class, mx_ok "
            "  FROM emails WHERE inn IN (%s)" % зн, к):
        инн = str(r["inn"])
        почта = (r["email"] or "").lower().strip()
        if not почта or "@" not in почта:
            continue
        дом = почта.split("@", 1)[1]
        этап["всего адресов у молчунов"] += 1
        # только корпоративный домен компании
        свой = сайт_дом.get(инн)
        родной = {d for d in (свой,) if d}
        родной |= {a.split("@", 1)[1] for a in молч_инн[инн] if "@" in a}
        родной = {d for d in родной if d not in ПОЧТОВИКИ}
        if дом in ПОЧТОВИКИ or not родной or дом not in родной:
            этап["не домен компании"] += 1
            continue
        if почта in молч_инн[инн]:
            этап["это тот же адрес, куда писали"] += 1
            continue
        if почта in уже_заведены:
            этап["уже заведён получателем"] += 1
            continue
        if почта in стоп or дом in стоп_дом:
            этап["в стоп-листе"] += 1
            continue
        if (r["probe_verdict"] or "") in ПРИГОВОР:
            этап["приговор пробы"] += 1
            continue
        if r["mx_ok"] == 0:
            этап["нет MX"] += 1
            continue
        этап["ГОДЕН"] += 1
        кандидаты[инн].append(почта)
        роли[(r["role"] or r["addr_class"] or "—")] += 1
e.close()

print("")
print("=== куда делись адреса молчунов ===")
for к, n in этап.most_common():
    print("   %-32s %7d" % (к, n))

print("")
print("=== что получится ===")
print("компаний с запасным адресом:   %d из %d" % (len(кандидаты), len(молч_инн)))
print("всего годных адресов:          %d" % sum(len(v) for v in кандидаты.values()))
раскл = Counter(len(v) for v in кандидаты.values())
for низ, верх, имя in ((1, 1, "1 адрес"), (2, 2, "2 адреса"), (3, 5, "3-5"),
                       (6, 10, "6-10"), (11, 1000, "больше 10")):
    n = sum(k2 for k1, k2 in раскл.items() if низ <= k1 <= верх)
    if n:
        print("   %-12s %5d компаний" % (имя, n))
print("")
print("если брать не больше N на компанию:")
for N in (1, 2, 3):
    print("   N=%d -> %5d писем" % (N, sum(min(N, len(v)) for v in кандидаты.values())))
print("")
print("=== роли годных адресов (топ) ===")
for к, n in роли.most_common(8):
    print("   %-24s %6d" % (к, n))
