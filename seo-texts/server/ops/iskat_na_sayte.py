# -*- coding: utf-8 -*-
"""Искать утверждение письма ПО ВСЕМУ САЙТУ, а не на главной.

Урок ночного прогона 17.08, письмо #2130 («Аватар», рекламное производство).
Письмо утверждало: «собственный парк ЧПУ-станков, лазерная резка, УФ-печать
на поле 2х3 метра». Проверка ГЛАВНОЙ страницы дала «ЧПУ - 0 раз», «2х3 - 0
раз», и по ней письмо выглядело выдумкой.

Обход внутренних страниц показал обратное, дословно:
  * «УФ печать(печатное поле - 2х3 м)» - /product/uslugi-proizvodstva/
  * «Мощность станка ЧПУ 4,5 кВТ» - /product/uslugi-proizvodstva/frezerovka/
То есть письмо взяло числа с сайта компании, а неверным был мой прибор.

Отсюда правило: обвинять письмо в выдуманном факте можно только после
обхода страниц, куда этот факт по смыслу и положено класть - услуги,
производство, печать, резка. Одной главной мало.

    python zapusk_svoego_skripta.py ops/iskat_na_sayte.py "http://сайт/" "2[хx]\\s?3|ЧПУ"
"""
import re, sys, urllib.request, gzip
БАЗА = sys.argv[1]
ЧТО = sys.argv[2].split("|")
ГЛУБИНА = int(sys.argv[3]) if len(sys.argv) > 3 else 12
def взять(u):
    try:
        r = urllib.request.Request(u, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(r, timeout=45) as o:
            b = o.read()
            if o.headers.get("Content-Encoding") == "gzip":
                b = gzip.decompress(b)
            return b.decode("utf-8", "replace")
    except Exception as ex:
        return ""
дом = re.match(r"https?://[^/]+", БАЗА).group(0)
главная = взять(БАЗА)
ссылки = set()
for m in re.finditer(r'href="([^"]+)"', главная):
    u = m.group(1)
    if u.startswith("/"):
        u = дом + u
    if u.startswith(дом) and re.search(r"(?i)(pech|print|uf|uslug|servic|frez|lazer)", u):
        ссылки.add(u.split("#")[0])
ссылки = sorted(ссылки)[:ГЛУБИНА]
print(f"страниц к обходу: {len(ссылки)}")
нашли = {ч: [] for ч in ЧТО}
for u in [БАЗА] + ссылки:
    t = взять(u)
    if not t:
        continue
    без = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", t))
    без = re.sub(r"\s+", " ", без)
    for ч in ЧТО:
        if re.search(ч, без, flags=re.I):
            м = re.search(ч, без, flags=re.I)
            нашли[ч].append((u, без[max(0, м.start()-70):м.start()+90]))
for ч, где in нашли.items():
    if где:
        print(f"\n«{ч}» НАЙДЕНО на {len(где)} стр.:")
        for u, фраг in где[:2]:
            print(f"   {u}\n     …{фраг}…")
    else:
        print(f"\n«{ч}» НЕ НАЙДЕНО ни на одной из обойдённых страниц")
