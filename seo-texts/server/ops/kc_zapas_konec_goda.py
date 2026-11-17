# -*- coding: utf-8 -*-
"""Запас для писем КЦ «конец года» (владелец 17.11: «по КЦ нам есть ещё из чего письма генерировать?»).
Источники газовых писем КЦ — дроп CA-ENGER-*.csv; плюс база обзвона. Считает, сколько ИНН ещё без карточки КЦ. Только чтение."""
import csv, io, os, re, sqlite3, glob
from collections import Counter
csv.field_size_limit(10 ** 9)
ДР = r"C:\seostat\drop\drop-storage"
ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
print("файлы CA-* на дропе:", [(os.path.basename(p), os.path.getsize(p) // 1024) for p in glob.glob(os.path.join(ДР, "CA-*"))])
def инн(имя):
    п = os.path.join(ДР, имя)
    if not os.path.exists(п): return set()
    return {ц(р.get("ИНН")) for р in csv.DictReader(io.open(п, encoding="utf-8-sig", errors="replace"), delimiter=";")} - {""}
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
кам = {i: н for i, н in к.execute("SELECT id, name FROM campaigns")}
кц = {i for i, н in кам.items() if re.search(r"(?i)кц|компрессор|\bkc\b", н or "") and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
карт = Counter(); инн_карт = set(); инн_отпр = set()
for i, ст, кид in к.execute("SELECT inn, status, campaign_id FROM confirm_reviews"):
    if кид in кц: инн_карт.add(ц(i)); карт[ст] += 1
for i, кид in к.execute("SELECT r.inn, m.campaign_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent'"):
    if кид in кц: инн_отпр.add(ц(i))
ответ = {ц(r[0]) for r in к.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
print("КЦ-кампании:", sorted(кам[i] for i in кц)); print("карточек КЦ по статусам:", dict(карт), "| ИНН с карточкой КЦ:", len(инн_карт), "| ИНН с отправленным КЦ:", len(инн_отпр))
for имя in ("CA-ENGER-ZALIVKA.csv", "CA-ENGER-ZALIVKA-kompanii.csv", "CA-ENGER-BAZA-kompanii.csv", "CA-ENGER-BAZA-kontakty.csv"):
    s = инн(имя)
    print("%-32s ИНН %6d | без карточки КЦ %6d | из них без ответа/жалобы %6d" % (имя, len(s), len(s - инн_карт), len(s - инн_карт - ответ)))
о = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True)
for (т,) in о.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    кол = [x[1] for x in о.execute("PRAGMA table_info(%s)" % т)]
    print("обзвон: таблица", т, о.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0], кол[:25])
try:
    кол = [x[1] for x in о.execute("PRAGMA table_info(obzvon)")]
    ик = next(x for x in кол if x.lower() in ("inn", "инн")); дк = next((x for x in кол if "division" in x.lower()), None)
    ек = next((x for x in кол if "email" in x.lower()), None)
    сч = Counter(); без = Counter()
    for row in о.execute("SELECT %s, %s, %s FROM obzvon" % (ик, дк or "''", ек or "''")):
        д = str(row[1] or ""); есть_п = bool(row[2] and "@" in str(row[2]))
        if "kc" in д.lower() or "кц" in д.lower():
            сч["КЦ"] += 1; сч["КЦ с почтой"] += есть_п
            if ц(row[0]) not in инн_карт and ц(row[0]) not in ответ:
                без["КЦ без карточки"] += 1; без["КЦ без карточки, с почтой"] += есть_п
    print("обзвон:", dict(сч), dict(без))
except Exception as ex:  # noqa: BLE001
    print("обзвон: не посчитал:", ex)
# --- уже прошли через газовую генерацию (суд модели / лесенка) ---
import json
def жур(имя):
    п = os.path.join(r"C:\sender\_ops", имя); з = {}
    if os.path.exists(п):
        for с in io.open(п, encoding="utf-8", errors="replace"):
            try: x = json.loads(с); з[ц(x.get("inn"))] = x
            except Exception: pass
    return з
суд, лес = жур("gaz-kc-sud.jsonl"), жур("gaz-kc-lesenka.jsonl")
print("газ: суд %d (%s) | лесенка %s" % (len(суд), dict(Counter(str(x.get("ok", x.get("verdict", "?"))) for x in суд.values())), dict(Counter(x.get("status") for x in лес.values()))))
for имя in ("CA-ENGER-ZALIVKA-kompanii.csv", "CA-ENGER-BAZA-kompanii.csv"):
    s = инн(имя) - инн_карт - ответ
    print("%s: без карточки %d | не было в суде газа %d | в суде отсеяны %d | лесенка «все мертвы» %d" % (имя, len(s), len(s - set(суд)),
          len([i for i in s if i in суд and not суд[i].get("ok")]), len([i for i in s if лес.get(i, {}).get("status") == "все мертвы"])))
print("вердикты компаний (обзвон):", dict(Counter((r[0], r[1]) for r in о.execute("SELECT rusprom, napr FROM kompaniya_verdikt")).most_common(8)))
кц_о = {ц(r[0]) for r in о.execute("SELECT inn FROM obzvon WHERE lower(division) LIKE '%kc%' AND (emails_base LIKE '%@%' OR emails_site LIKE '%@%')")}
плох = {ц(r[0]) for r in о.execute("SELECT inn FROM kompaniya_verdikt WHERE lower(COALESCE(rusprom,'')) IN ('не покупатель','нет','конкурент') OR napr IN ('никуда','не кц')")}
print("обзвон КЦ с почтой без карточки, без ответа, не «не наш»: %d (из них в CA-ENGER-BAZA %d)" % (len(кц_о - инн_карт - ответ - плох), len((кц_о - инн_карт - ответ - плох) & инн("CA-ENGER-BAZA-kompanii.csv"))))
хор = {ц(r[0]) for r in о.execute("SELECT inn FROM kompaniya_verdikt WHERE rusprom='покупатель' AND COALESCE(napr,'кц')='кц'")}
ост = кц_о - инн_карт - ответ - плох
print("из них с вердиктом «покупатель/кц»: %d; без вердикта вовсе: %d" % (len(ост & хор), len(ост - {ц(r[0]) for r in о.execute("SELECT inn FROM kompaniya_verdikt")})))
