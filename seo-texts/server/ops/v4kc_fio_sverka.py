# -*- coding: utf-8 -*-
"""Владелец 06.11: контакты с ФИО из FSA-MEYER-v4-KC.xlsx (лист «Контакты с сайта») — включены ли
в КЦ-1 / панель / «КЦ по имени», писали ли им. Файл берётся с дропа на сервер; только счёт.
    v4kc_fio_sverka.py [ИМЯ_ФАЙЛА=FSA-MEYER-v4-KC.xlsx]"""
import collections, io, json, os, sqlite3, sys
import requests, openpyxl
Ф = next((a for a in sys.argv[1:] if a.endswith(".xlsx")), "FSA-MEYER-v4-KC.xlsx")
for line in io.open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))
путь = os.path.join(r"C:\sender\_ops", Ф)
if not os.path.exists(путь):
    р = requests.get(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/" + Ф,
                     headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=300)
    р.raise_for_status(); io.open(путь, "wb").write(р.content)
wb = openpyxl.load_workbook(путь, read_only=True)
ws = wb["Контакты с сайта"]; rows = ws.iter_rows(values_only=True); h = list(next(rows))
ix = {k: h.index(k) for k in ("ИНН / УНП", "ФИО", "Роль", "E-mail")}
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
пан = {}
for em, ex, inn in s.execute("SELECT lower(email), extra_json, inn FROM recipients"):
    пан[em] = (json.loads(ex or "{}").get("gruppy") or [])
писали = {r[0].lower() for r in s.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent'")}
писали_инн = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM send_log WHERE outcome='sent' AND inn IS NOT NULL")}
кц1 = {str(r[0]) for r in s.execute("SELECT DISTINCT inn FROM recipients WHERE extra_json LIKE '%КЦ-1%'")}
в19 = {r[0].lower() for r in s.execute("SELECT cr.email FROM confirm_reviews cr JOIN campaigns c ON c.id=cr.campaign_id WHERE c.name='КЦ по имени 06.11'")}
в_enrich = {r[0].lower(): (r[1], r[2]) for r in e.execute("SELECT email, person, imya_ok FROM emails WHERE email IS NOT NULL")}
сч = collections.Counter(); комп = set(); комп_кц1 = set()
for r in rows:
    fio = str(r[ix["ФИО"]] or "").strip(); em = str(r[ix["E-mail"]] or "").strip().lower(); inn = str(r[ix["ИНН / УНП"]] or "")
    if not fio or not em: continue
    сч["контактов ФИО+email"] += 1; комп.add(inn)
    if inn in кц1: комп_кц1.add(inn); сч["компания в группе КЦ-1"] += 1
    if em in пан: сч["адрес в панели"] += 1
    if em in пан and "КЦ-1" in пан[em]: сч["адрес в панели в группе КЦ-1"] += 1
    if em in писали: сч["на адрес писали"] += 1
    elif inn in писали_инн: сч["адресу не писали, компании писали"] += 1
    else: сч["компании не писали вовсе"] += 1
    if em in в19: сч["уже в «КЦ по имени»"] += 1
    if em in в_enrich:
        сч["адрес есть в enrich"] += 1
        if (в_enrich[em][0] or "").strip(): сч["  …и с именем в enrich"] += 1
        if str(в_enrich[em][1]) == "1": сч["  …imya_ok=1"] += 1
    else: сч["адреса НЕТ в enrich"] += 1
print("компаний с ФИО+email:", len(комп), "| из них в группе КЦ-1:", len(комп_кц1))
for k, v in сч.items(): print("  %-40s %d" % (k, v))
