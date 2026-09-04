# -*- coding: utf-8 -*-
"""Обойти refeel.ru и найти, на какой странице лежит адрес."""
import re
import sys
import urllib.parse
from collections import deque

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ПОЧТА = "marushkiiin"
БАЗА = "https://refeel.ru"
ЗАГ = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

очередь = deque([БАЗА, БАЗА + "/contacts", БАЗА + "/kontakty", БАЗА + "/about",
                 БАЗА + "/o-nas", БАЗА + "/vacancies", БАЗА + "/vakansii",
                 БАЗА + "/opt", БАЗА + "/wholesale"])
видели, находки, коды = set(), [], []
все_почты = {}

while очередь and len(видели) < 40:
    у = очередь.popleft()
    if у in видели:
        continue
    видели.add(у)
    try:
        r = requests.get(у, headers=ЗАГ, timeout=25)
    except Exception as ex:                                    # noqa: BLE001
        коды.append("%s -> ошибка %s" % (у[:60], str(ex)[:40]))
        continue
    коды.append("%s -> %s, %d Б" % (у[:60], r.status_code, len(r.text or "")))
    if r.status_code != 200:
        continue
    html = r.text or ""
    for м in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                         html):
        все_почты.setdefault(м.group(0).lower(), set()).add(у)
    if ПОЧТА in html.lower():
        i = html.lower().find(ПОЧТА)
        кусок = re.sub(r"<[^>]+>", " ", html[max(0, i - 500):i + 400])
        находки.append((у, re.sub(r"\s+", " ", кусок).strip()[:700]))
    if len(видели) < 20:
        for м in re.finditer(r'href="([^"#?]+)"', html):
            сс = urllib.parse.urljoin(у, м.group(1))
            if сс.startswith(БАЗА) and сс not in видели and len(очередь) < 30:
                очередь.append(сс)

print("=" * 84)
print("=== СВОДКА: ОБХОД refeel.ru ===")
print("страниц обойдено: %d" % len(видели))
print("")
print("--- НАЙДЕН ЛИ АДРЕС ---")
if находки:
    for у, кусок in находки:
        print("   СТРАНИЦА: %s" % у)
        print("   ...%s..." % кусок)
else:
    print("   адрес %s@yandex.ru на обойдённых страницах НЕ найден" % ПОЧТА)
print("")
print("--- ВСЕ ПОЧТЫ, НАЙДЕННЫЕ НА САЙТЕ ---")
for п, где in sorted(все_почты.items()):
    print("   %-34s %s" % (п[:34], list(где)[0][:60]))
print("")
print("--- ответы страниц ---")
for с in коды[:26]:
    print("   " + с)
