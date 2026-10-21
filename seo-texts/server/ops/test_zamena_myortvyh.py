# -*- coding: utf-8 -*-
"""Почему подмена мёртвого адреса (partiya_gen._следующий_живой) не находит
замену: та же логика без записи, по компаниям КЦ-1 с мёртвым основным адресом —
на каком условии отсеивается каждый живой запасной. Только чтение."""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\server")
try:
    from lead_scoring import _rol_ball
except Exception:  # noqa: BLE001
    def _rol_ball(_р):
        return 2
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
занят = {str(r[0]).lower() for r in c.execute("SELECT email FROM recipients")}
ушло = {str(r[0]).lower() for r in c.execute("SELECT DISTINCT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'")}
сч, нашлось = Counter(), 0
for rid, inn, em in c.execute("SELECT id, inn, lower(email) FROM recipients WHERE extra_json LIKE '%КЦ-1%'").fetchall():
    if проба.get(em) not in ("нет ящика", "нет MX"):
        continue
    к = e.execute("SELECT site FROM companies WHERE inn=?", (inn,)).fetchone()
    сайт = str((к and к[0]) or "").lower().split("//")[-1].replace("www.", "").split("/")[0]
    if not сайт:
        сч["нет сайта в обогащении"] += 1
        continue
    годные = 0
    for а, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,)):
        роль = str(роль or "")
        if а == em:
            continue
        if проба.get(а) not in ("есть", "принимает всё"):
            сч["запасной: не живой по пробе"] += 1
            continue
        дом = а.rsplit("@", 1)[-1]
        if дом != сайт and not дом.endswith("." + сайт):
            сч["запасной живой, но домен не сайта (%s)" % ("публичный" if дом in ("mail.ru", "yandex.ru", "gmail.com", "bk.ru", "list.ru", "inbox.ru") else "другой")] += 1
            continue
        if а in занят:
            сч["запасной живой, свой домен, но УЖЕ получатель в панели"] += 1
            continue
        if а in ушло:
            сч["запасной живой, свой домен, но ему уже писали"] += 1
            continue
        if "не для письма" in роль.lower() or _rol_ball(роль) <= 1:
            сч["запасной живой, свой домен, но роль низкая (%s)" % роль[:25]] += 1
            continue
        годные += 1
    if годные:
        нашлось += 1
print("компаний, где подмена найдёт адрес:", нашлось)
for k, v in сч.most_common(15):
    print("  %5d  %s" % (v, k))
