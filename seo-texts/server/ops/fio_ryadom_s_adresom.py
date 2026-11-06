# -*- coding: utf-8 -*-
"""Есть ли ФИО рядом с адресом закупщика на странице сайта компании (источник own-site, url = сайт
компании). Скачивает страницу, ищет ФИО (Фамилия Имя Отчество / Имя Фамилия) в окне ±200 символов
от адреса. fio_ryadom_s_adresom.py [N=30] [--vse]  — только выборка, в базу не пишет."""
import collections, html, io, json, random, re, sqlite3, ssl, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
N = next((int(a) for a in sys.argv[1:] if a.isdigit()), 30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
сайт = {str(i): str(x or "").lower().split("//")[-1].split("/")[0].replace("www.", "") for i, x in e.execute("SELECT inn, site FROM companies WHERE site IS NOT NULL")}
цели = []
for с in io.open(r"C:\sender\_ops\zakupshchiki-imena.jsonl", encoding="utf-8"):
    з = json.loads(с)
    if з["napr"] != "КЦ" or not з["reshenie"].startswith("без"): continue
    r = e.execute("SELECT COALESCE(source_url,'') FROM emails WHERE inn=? AND lower(email)=?", (з["inn"], з["email"])).fetchone()
    url = r[0] if r else ""
    if url.startswith("http") and сайт.get(з["inn"]) and сайт[з["inn"]] in url.lower():
        цели.append((з["inn"], з["email"], url))
random.seed(7); выб = цели if "--vse" in sys.argv else random.sample(цели, min(N, len(цели)))
кт = ssl.create_default_context(); кт.check_hostname = False; кт.verify_mode = ssl.CERT_NONE
ФИО = re.compile(r"([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]+(?:вич|вна|ична|ьич))|([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)")
def одна(ц):
    inn, em, url = ц
    try:
        р = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15, context=кт).read(800000)
        т = р.decode("utf-8", "ignore")
        if "�" in т[:2000] or not re.search("[а-я]", т): т = р.decode("cp1251", "ignore")
        т = html.unescape(re.sub(r"<[^>]+>", " ", т)); т = re.sub(r"\s+", " ", т)
        i = т.lower().find(em)
        if i < 0: return (em, url, "адреса на странице нет", "")
        окно = т[max(0, i - 200): i + 200]
        м = ФИО.search(окно)
        return (em, url, "ФИО рядом" if м else "ФИО нет", (м.group(0) if м else окно[150:260]))
    except Exception as ex:  # noqa: BLE001
        return (em, url, "не скачалась", str(ex)[:60])
with ThreadPoolExecutor(10) as п:
    рез = list(п.map(одна, выб))
print("целей всего:", len(цели), "| проверено:", len(рез), collections.Counter(x[2] for x in рез).most_common())
for x in рез:
    if x[2] == "ФИО рядом": print("  +", x[0], "|", x[3])
