# -*- coding: utf-8 -*-
"""У карточек, снятых пробой адреса, есть ли ещё адреса на домене компании."""
import io
import json
import re
import sqlite3
from collections import Counter, defaultdict

ПОЧТОВИКИ = {
    "mail.ru", "inbox.ru", "list.ru", "bk.ru", "internet.ru", "yandex.ru",
    "ya.ru", "yandex.com", "narod.ru", "gmail.com", "googlemail.com",
    "rambler.ru", "outlook.com", "hotmail.com", "live.com", "icloud.com",
    "me.com", "yahoo.com", "tut.by", "mail.by",
}
ПРИГОВОР = {"нет ящика", "нет MX"}
НЕЛЬЗЯ_РОЛЬ = {"кадры", "бухгалтерия"}
СЛУЖЕБНЫЕ = {"gosuslugi", "buh", "buhgalter", "kadry", "kadri", "kadr", "ok",
             "hr", "vacancy", "rabota", "job", "press", "pr", "smi", "edo",
             "diadoc", "sbis", "nalog", "fss", "pfr", "noreply", "no-reply",
             "postmaster", "abuse", "spam", "rassylka", "news"}
_ЦИФ = re.compile(r"\d+$")

партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = (str(d["inn"]), d["email"].lower())

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
s.row_factory = sqlite3.Row
зн = ",".join("?" * len(партия))
пробой = []
for r in s.execute(
        "SELECT id, email, reason, decided_by FROM confirm_reviews "
        " WHERE id IN (%s) AND status='skipped' "
        "   AND (COALESCE(decided_by,'') LIKE '%%проба%%' "
        "        OR COALESCE(reason,'') LIKE '%%проба%%')" % зн, list(партия)):
    пробой.append((int(r["id"]), партия[int(r["id"])][0], r["email"],
                   str(r["reason"] or "")))
print("снято пробой: %d" % len(пробой))
print("")
print("=== по вердиктам ===")
for к, n in Counter(р[3].split(":")[0] for р in пробой).most_common():
    print("   %-40s %3d" % (к[:40], n))

инны = sorted({и for _, и, _, _ in пробой})
уже = {(r[0] or "").lower() for r in s.execute(
    "SELECT email FROM recipients WHERE email IS NOT NULL")}
стоп = {(r[0] or "").lower() for r in s.execute(
    "SELECT value FROM suppression WHERE scope IN ('email','address')")}
# все адреса, куда компании уже писали
писали = defaultdict(set)
зн2 = ",".join("?" * len(инны))
for r in s.execute("SELECT inn, email FROM recipients WHERE inn IN (%s)" % зн2, инны):
    писали[str(r[0])].add((r[1] or "").lower())
s.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
запас = defaultdict(list)
for r in e.execute(
        "SELECT inn, email, role, person, probe_verdict, mx_ok "
        "  FROM emails WHERE inn IN (%s)" % зн2, инны):
    инн = str(r["inn"])
    почта = (r["email"] or "").lower().strip()
    if "@" not in почта:
        continue
    дом = почта.split("@", 1)[1]
    родной = {d.split("@", 1)[1] for d in писали[инн] if "@" in d} - ПОЧТОВИКИ
    if дом in ПОЧТОВИКИ or дом not in родной:
        continue
    if почта in писали[инн] or почта in уже or почта in стоп:
        continue
    if (r["probe_verdict"] or "") in ПРИГОВОР or r["mx_ok"] == 0:
        continue
    if (r["role"] or "").strip() in НЕЛЬЗЯ_РОЛЬ:
        continue
    if _ЦИФ.sub("", почта.split("@", 1)[0]) in СЛУЖЕБНЫЕ:
        continue
    запас[инн].append((почта, r["role"] or "—", r["probe_verdict"] or "—"))
e.close()

есть = [(rev, и, а) for rev, и, а, _ in пробой if запас.get(и)]
print("")
print("=== есть ли чем заменить ===")
print("   компаний со снятой картой:      %d" % len({и for _, и, _, _ in пробой}))
print("   у них есть ещё адрес на домене: %d" % len({и for _, и, _ in есть}))
print("   без запаса вовсе:               %d"
      % len({и for _, и, _, _ in пробой} - {и for _, и, _ in есть}))
print("")
print("=== вердикты запасных адресов ===")
for к, n in Counter(в for сп in запас.values() for _, _, в in сп).most_common():
    print("   %-24s %4d" % (к, n))
print("")
print("=== примеры замен ===")
for rev, и, а in есть[:8]:
    з = sorted(запас[и])[:2]
    print("   %-13s снято %-28s -> %s"
          % (и, а[:28], "; ".join("%s [%s, %s]" % (п, р, в) for п, р, в in з)[:76]))
