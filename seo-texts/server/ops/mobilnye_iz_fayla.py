# -*- coding: utf-8 -*-
"""Мобильные прокси из файла: сколько запросов к Чеко держат.

Пароли не печатаем — только схема, хост, порт и маска логина.
"""
import io
import os
import re
import sqlite3
import sys
import time
import urllib.parse

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ФАЙЛЫ = [r"C:\sender\proxies-mobile.txt",
         r"C:\seostat\drop\zenno\proxy_mobile.txt"]
ЗАПРОСОВ = 30


def маска(с):
    с = str(с or "")
    return (с[:2] + "***" + с[-2:]) if len(с) > 5 else "***"


строки = []
источник = {}
for ф in ФАЙЛЫ:
    if not os.path.exists(ф):
        continue
    for l in io.open(ф, encoding="utf-8", errors="replace"):
        l = l.strip()
        if l and not l.startswith("#"):
            строки.append(l)
            источник[l] = os.path.basename(ф)

def в_url(l):
    """Понимаем и host:port:user:pass, и user:pass@host:port, и со схемой."""
    if "://" in l:
        return l
    ч = l.split(":")
    if len(ч) == 4 and "@" not in l:
        х, п, u, pw = ч
        return "socks5://%s:%s@%s:%s" % (u, pw, х, п)
    m = re.match(r"(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)$", l)
    if m:
        u, pw, х, п = m.groups()
        return ("socks5://%s:%s@%s:%s" % (u, pw, х, п)) if u \
            else "socks5://%s:%s" % (х, п)
    return None

урлы, описания = [], []
for l in строки:
    u = в_url(l)
    if not u:
        описания.append("не разобрал строку: %s" % l[:30])
        continue
    р = urllib.parse.urlsplit(u)
    урлы.append(u)
    описания.append("%s://%s:%s логин %s   [%s]"
                    % (р.scheme, р.hostname, р.port, маска(р.username),
                       источник.get(l, "?")))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
огрны = [r[0] for r in c.execute(
    "SELECT ogrn FROM requisites WHERE COALESCE(ogrn,'')<>'' "
    "  AND COALESCE(revenue_rub,'') IN ('','0') LIMIT 200")]
c.close()

итоги = []
for н, url in enumerate(урлы[:6], 1):
    ок, коды, первый_отказ = 0, {}, None
    t0 = time.time()
    for i in range(ЗАПРОСОВ):
        try:
            r = requests.get(
                "https://checko.ru/company/%s" % огрны[(н * 37 + i) % len(огрны)],
                proxies={"http": url, "https": url},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; "
                                       "x64) AppleWebKit/537.36"},
                timeout=25)
            коды[r.status_code] = коды.get(r.status_code, 0) + 1
            if r.status_code == 200:
                ок += 1
            elif первый_отказ is None:
                первый_отказ = i + 1
        except Exception as ex:                                # noqa: BLE001
            коды[str(ex)[:20]] = коды.get(str(ex)[:20], 0) + 1
            if первый_отказ is None:
                первый_отказ = i + 1
        time.sleep(0.25)
    итоги.append("мобильный %d: ок %2d из %d, первый отказ на %s, %.0f с, %s"
                 % (н, ок, ЗАПРОСОВ,
                    первый_отказ if первый_отказ else "—",
                    time.time() - t0, коды))

print("=" * 74)
print("=== СВОДКА: МОБИЛЬНЫЕ ПРОКСИ ИЗ ФАЙЛА ===")
print("строк в файлах: %d, разобрано: %d" % (len(строки), len(урлы)))
for с in описания[:10]:
    print("   " + с)
print("")
print("проба по Чеко, %d запросов на прокси:" % ЗАПРОСОВ)
for с in (итоги or ["   нечего пробовать"]):
    print("   " + с)
