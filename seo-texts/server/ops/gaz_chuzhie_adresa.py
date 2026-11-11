# -*- coding: utf-8 -*-
"""Разбор адресов из лесенок газовых писем, которые в панели (recipients) записаны за ДРУГИМ ИНН.
Чья привязка верна: сравниваем названия, домен адреса с сайтами обеих компаний, источник контакта у ЦА,
источник записи в панели, писали ли на адрес. Только чтение баз.  [--vygruzit] — адреса «домен = сайт другой
компании» в CSV на дроп GAZ-CHUZHIE-ADRESA-54.csv (владелец 11.11: «выпиши для другой сессии»)."""
import csv, io, os, re, sqlite3
from collections import Counter, defaultdict
csv.field_size_limit(10 ** 9)
ДРОП = r"C:\seostat\drop\drop-storage"
def читать(имя):
    return list(csv.DictReader(io.open(os.path.join(ДРОП, имя), encoding="utf-8-sig", errors="replace"), delimiter=";"))
def цифры(x): return re.sub(r"\D", "", str(x or ""))
def ядро(н):
    н = re.sub(r"(?i)общество с ограниченной ответственностью|акционерное общество|публичное|непубличное|закрытое|открытое|"
               r"\b(ооо|ао|пао|зао|оао|нпо|нпп|гк|пк|тк|ск|нпц|ип|тд|нпф|пкф|фирма|компания|завод|группа)\b|[«»\"'()\-.,&;]|quot", " ", str(н or ""))
    return " ".join(н.lower().split())
def домен_сайта(с):
    с = str(с or "").lower().split("//")[-1].split("/")[0]
    return с[4:] if с.startswith("www.") else с
ПУБЛ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru", "internet.ru", "narod.ru", "yandex.com"}
лпр, комп = читать("CA-ENGER-ZALIVKA.csv"), читать("CA-ENGER-ZALIVKA-kompanii.csv")
база = {цифры(р.get("ИНН")): р for р in лпр + комп}
САЙТ = {цифры(р.get("ИНН")): р for р in читать("CA-ENGER-BAZA-kompanii.csv")}
адреса = defaultdict(list)   # email -> [(наш ИНН, источник ЦА, файл)]
for имя_ф, rows in (("ЛПР", лпр), ("компании", комп)):
    for р in rows:
        for e in re.split(r"[,;\s]+", (р.get("Почта") or "").lower()):
            if "@" in e: адреса[e].append((цифры(р.get("ИНН")), р.get("Источник контакта") or "", имя_ф))
for р in читать("CA-ENGER-BAZA-kontakty.csv"):
    и = цифры(р.get("ИНН"))
    if и in база:
        for e in re.split(r"[,;\s]+", (р.get("Почта") or "").lower()):
            if "@" in e: адреса[e].append((и, р.get("Источник") or "", "контакты"))
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
en = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=60)
rec = {}
for em, inn, cn, src in s.execute("SELECT lower(email), inn, company_name, source FROM recipients WHERE email IS NOT NULL"):
    rec[em] = (цифры(inn), cn or "", src or "")
писали = {r[0].lower() for r in s.execute("SELECT DISTINCT email FROM send_log WHERE outcome='sent'")}
def имя_и_сайт(inn):
    r = en.execute("SELECT name, site FROM companies WHERE inn=?", (inn,)).fetchone()
    return (r[0] or "", r[1] or "") if r else ("", "")
кат = Counter(); примеры = defaultdict(list); ист = Counter(); ист_панели = Counter(); ЧУЖИЕ = []
for em, наши in адреса.items():
    if em not in rec: continue
    чужой, имя_п, src = rec[em]
    if not чужой: continue
    наш_инн = наши[0][0]
    if чужой == наш_инн or чужой in {x[0] for x in наши}: continue
    наш = база.get(наш_инн, {})
    наш_имя = наш.get("Компания") or ""
    наш_сайт = домен_сайта(наш.get("Сайт") or САЙТ.get(наш_инн, {}).get("Сайт"))
    их_имя_en, их_сайт_raw = имя_и_сайт(чужой)
    их_имя = имя_п or их_имя_en
    их_сайт = домен_сайта(их_сайт_raw)
    дом = em.rsplit("@", 1)[-1]
    if чужой.startswith("0000"): к = "в панели псевдо-ИНН 0000…"
    elif ядро(наш_имя) and ядро(их_имя) and (ядро(наш_имя) == ядро(их_имя) or ядро(наш_имя) in ядро(их_имя) or ядро(их_имя) in ядро(наш_имя)):
        к = "одна группа / то же название (другой ИНН)"
    elif дом in ПУБЛ: к = "публичный ящик, названия разные"
    elif наш_сайт and (дом == наш_сайт or дом.endswith("." + наш_сайт) or наш_сайт.endswith("." + дом)):
        к = "домен = сайт НАШЕЙ компании (панель, вероятно, ошибается)"
    elif их_сайт and (дом == их_сайт or дом.endswith("." + их_сайт) or их_сайт.endswith("." + дом)):
        к = "домен = сайт ДРУГОЙ компании (ошибается ЦА)"
    else: к = "корп. домен, ни с одним сайтом не совпал"
    кат[к] += 1
    if к.startswith("домен = сайт ДРУГОЙ"):
        ЧУЖИЕ.append([em, наш_инн, наш_имя, наш_сайт, чужой, их_имя, их_сайт, src, "да" if em in писали else "нет", "; ".join(sorted({x[1] or x[2] for x in наши}))])
    for x in наши: ист["%s: %s" % (x[2], x[1][:40])] += 1
    ист_панели[src[:30]] += 1
    if len(примеры[к]) < 4:
        примеры[к].append("%s | наш: %s (%s, сайт %s) | в панели: %s (%s, сайт %s, источник %s) | писали: %s" % (
            em, наш_имя[:45], наш_инн, наш_сайт or "-", их_имя[:45], чужой, их_сайт or "-", src[:20], "да" if em in писали else "нет"))
if "--vygruzit" in __import__("sys").argv:
    п = os.path.join(ДРОП, "GAZ-CHUZHIE-ADRESA-54.csv")
    with io.open(п, "w", encoding="utf-8-sig", newline="") as ф:
        w = csv.writer(ф, delimiter=";")
        w.writerow(["Почта", "ИНН в файле ЦА", "Компания в файле ЦА", "Сайт в файле ЦА", "ИНН в панели", "Компания в панели",
                    "Сайт компании в панели", "Источник записи в панели", "Писали на адрес", "Источник контакта у ЦА"])
        w.writerows(ЧУЖИЕ)
    print("выгружено на дроп: %s (%d строк)" % (п, len(ЧУЖИЕ)))
print("ВСЕГО адресов с другой привязкой:", sum(кат.values()))
for к, n in кат.most_common():
    print("\n%5d  %s" % (n, к))
    for п in примеры[к]: print("       ", п)
print("\nисточник контакта у ЦА:", dict(ист.most_common(10)))
print("источник записи в панели:", dict(ист_панели.most_common(10)))
