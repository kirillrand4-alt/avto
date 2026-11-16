# -*- coding: utf-8 -*-
"""Адреса хостингов и конструкторов сайтов вместо адресов компаний (16.11: письмо КЦ ушло на support@beget.com — ответили
«случайно попали в рассылку»). Ищет такие домены в очереди (pending/scheduled), в карточках подтверждения, в отправленных и
в обогащении; с --primenit: домены в стоп-лист (scope=domain), письма в очереди и карточки — снять. Журнал _ops/hosting-adresa.jsonl.
    hosting_adresa.py [--primenit]"""
import io, json, os, sqlite3, sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.store import Store
from sender.dtos import SuppressionIn
ДОМЕНЫ = ["beget.com", "beget.ru", "beget.tech", "timeweb.ru", "timeweb.com", "reg.ru", "nic.ru", "sweb.ru", "spaceweb.ru", "jino.ru",
          "masterhost.ru", "hostland.ru", "ispsystem.com", "ispsystem.ru", "fozzy.com", "firstvds.ru", "ruvds.com", "selectel.ru",
          "tilda.cc", "tilda.ws", "tilda.ru", "wix.com", "ukit.com", "nethouse.ru", "1c-umi.ru", "umi.ru", "bitrix24.ru", "1c-bitrix.ru",
          "hostinger.com", "majordomo.ru", "netangels.ru", "mchost.ru", "sprinthost.ru", "eternalhost.net", "ihc.ru", "hc.ru", "a-cms.ru",
          "insales.ru", "megagroup.ru", "diafan.ru", "cms.ru", "ru-center.ru", "r01.ru"]
ПР = "--primenit" in sys.argv
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
дом = lambda e: (e or "").lower().strip().split("@")[-1]
сч = Counter(); примеры = []
for mid, e, ст, к in c.execute("SELECT m.id, lower(r.email), m.status, m.campaign_id FROM messages m JOIN recipients r ON r.id=m.recipient_id").fetchall():
    if дом(e) in ДОМЕНЫ:
        сч["письма %s" % ст] += 1
        if len(примеры) < 15: примеры.append((e, ст, к))
        if ПР and ст in ("scheduled", "pending_review", "paused"):
            c.execute("UPDATE messages SET status='skipped', last_error='адрес хостинга, не компании (16.11)' WHERE id=? AND status IN ('scheduled','pending_review','paused')", (mid,))
for кид, e in c.execute("SELECT id, lower(email) FROM confirm_reviews WHERE status='pending'").fetchall():
    if дом(e) in ДОМЕНЫ:
        сч["карточки pending"] += 1
        if ПР: c.execute("UPDATE confirm_reviews SET status='skipped', reason='адрес хостинга, не компании (16.11)', decided_at=?, updated_at=? WHERE id=? AND status='pending'", (т, т, кид))
if ПР: c.commit()
е = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
обог = sum(1 for (e,) in е.execute("SELECT lower(email) FROM emails") if дом(e) in ДОМЕНЫ)
print("обогащение: адресов на доменах хостингов", обог)
мей = 0
try:
    мей = sum(1 for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8") if дом(json.loads(с).get("email")) in ДОМЕНЫ)
except FileNotFoundError: pass
print("в партии Meyer (журнал):", мей)
print(dict(сч)); print("примеры:", примеры)
if ПР:
    st = Store(r"C:\sender\sender.db"); n = 0
    for d in ДОМЕНЫ:
        _, нов = st.suppression_add(SuppressionIn(scope="domain", value=d, reason="hosting_not_client", source="владелец 16.11: beget"))
        n += int(bool(нов))
    with io.open(r"C:\sender\_ops\hosting-adresa.jsonl", "a", encoding="utf-8") as ф:
        ф.write(json.dumps({"ts": т, "domenov": len(ДОМЕНЫ), "novyh": n, "itog": dict(сч)}, ensure_ascii=False) + "\n")
    print("ПРИМЕНЕНО: доменов в стоп-лист новых %d из %d" % (n, len(ДОМЕНЫ)))
