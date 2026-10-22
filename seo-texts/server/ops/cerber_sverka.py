# -*- coding: utf-8 -*-
"""«Цербер вне ФСА» (лист файла FSA-MEYER-v4-Meyer, владелец 22.10: «с того
листа можем кому-то писать?»): 233 компании из реестра Цербера. Вход —
cerber-inns.json с дропа. По компании: писал ли Meyer, лид, сделка Meyer,
стоп-лист; адреса — из файла, обогащения (enrich.emails) и базы обзвона, с
вердиктом пробы и признаком «уже в панели под другим ИНН». Только чтение."""
import json
import os
import re
import sqlite3
from collections import Counter

import requests

У = os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/")
д = requests.get(У + "/cerber-inns.json", headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=120).json()
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
о = sqlite3.connect(r"C:\sender\obzvon-index.db")
кам = {r[0]: str(r[1] or "") for r in c.execute("SELECT id, name FROM campaigns")}
meyer = {k for k, v in кам.items() if "meyer" in v.lower() or "мейер" in v.lower()}
писал_m = {str(r[0]) for r in c.execute("SELECT inn, campaign_id FROM send_log WHERE outcome='sent'") if r[1] in meyer}
писал = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent'")}
лиды = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
сделка = {str(r[0]) for r in c.execute("SELECT inn FROM sdelki_napr WHERE meyer=1")}
стоп = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
получ = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, inn FROM recipients")}
вработе = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                        "WHERE m.status NOT IN ('sent','skipped','failed')")}
окол = [r[1] for r in о.execute("PRAGMA table_info(obzvon)")]
EM = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ПЛОХО = re.compile(r"(?i)кадр|бухгалт|hr|резюме|не для письма")
сч = Counter()
годные = []
for inn, к in д.items():
    if inn in лиды:
        сч["лид"] += 1; continue
    if inn in сделка or к.get("meyer"):
        сч["сделка Meyer"] += 1; continue
    if inn in писал_m:
        сч["Meyer уже писал"] += 1; continue
    if inn in вработе:
        сч["письмо в работе"] += 1; continue
    адр = []
    if к.get("email"):
        адр.append((к["email"], "файл: письмо"))
    for em, роль, лпр in к.get("cont") or []:
        if not ПЛОХО.search(роль):
            адр.append((em, "файл: сайт, " + роль))
    for em, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=?", (inn,)):
        if not ПЛОХО.search(str(роль or "")):
            адр.append((em, "обогащение: " + str(роль or "")[:30]))
    for р in о.execute("SELECT * FROM obzvon WHERE inn=?", (inn,)):
        for v in р:
            for em in EM.findall(str(v or "")):
                адр.append((em.lower(), "база обзвона"))
    живые = []
    for em, отк in адр:
        if em in стоп or em.split("@")[-1] in стоп:
            continue
        if проба.get(em) in ("нет ящика", "нет MX", "неясно", "отказ пробе"):
            continue
        if em in получ and получ[em] != inn:
            continue
        живые.append((em, отк, проба.get(em, "") or "не проверен"))
    if not адр:
        сч["нет адреса нигде"] += 1; continue
    if not живые:
        сч["адреса есть, но все мёртвые/чужие/стоп"] += 1; continue
    сч["МОЖНО ПИСАТЬ" + (" (КЦ уже писал)" if inn in писал else "")] += 1
    годные.append((inn, к["name"][:50], к["vid"][:40], живые[0]))
print("\nисточник лучшего адреса:", Counter(g[3][1].split(":")[0] for g in годные))
print("проба лучшего:", Counter(g[3][2] for g in годные))
for g in годные[:25]:
    print("  %s | %-50s | %-40s | %s" % (g[0], g[1], g[2], g[3]))
print("компаний:", len(д))
for k, v in сч.most_common():
    print("  %-45s %d" % (k, v))
requests.put(У + "/cerber-godnye.json", data=json.dumps(годные, ensure_ascii=False).encode(),
             headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
