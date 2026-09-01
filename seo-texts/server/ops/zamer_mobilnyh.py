# -*- coding: utf-8 -*-
"""Сколько запросов к Чеко выдерживают мобильные прокси против обычных.

Берём прокси трёх мобильных профилей Дельфина из его локального API и
гоняем по ним подряд запросы к настоящим карточкам компаний, считая, на
каком по счёту приходит отказ. Для сравнения — то же по двум прокси из
общего пула на 78 штук.

Пароли не печатаем: показываем хост и маску.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

МОБИЛЬНЫЕ = os.environ.get("HH_DOLPHIN_PROFILES",
                           "829115353,829115344,829115332").split(",")
DOLPHIN_BASE = os.environ.get("DOLPHIN_API",
                              "http://localhost:3001/v1.0").rstrip("/")
_ОТКР = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ЗАПРОСОВ = 40


def дельфин(путь):
    з = urllib.request.Request(
        "%s/%s" % (DOLPHIN_BASE, путь.lstrip("/")),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + os.environ.get("DOLPHIN_TOKEN", "")})
    with _ОТКР.open(з, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def маска(с):
    с = str(с or "")
    return (с[:2] + "***" + с[-2:]) if len(с) > 5 else "***"


# --- прокси мобильных профилей -------------------------------------------
мобильные_url, описания = [], []
for пид in [p.strip() for p in МОБИЛЬНЫЕ if p.strip()]:
    try:
        d = дельфин("browser_profiles/%s" % пид)
        p = (d.get("data") or d).get("proxy") or {}
        тип = str(p.get("type") or "socks5").lower()
        хост, порт = p.get("host"), p.get("port")
        лог, пар = p.get("login"), p.get("password")
        if хост and порт:
            url = "%s://%s:%s@%s:%s" % (тип, лог or "", пар or "", хост, порт)
            мобильные_url.append(url)
            описания.append("%s -> %s://%s:%s логин %s"
                            % (пид, тип, хост, порт, маска(лог)))
        else:
            описания.append("%s -> прокси в профиле не задан" % пид)
    except Exception as ex:                                    # noqa: BLE001
        описания.append("%s -> API не ответил: %s" % (пид, str(ex)[:70]))

# --- обычные из общего пула ----------------------------------------------
обычные = []
try:
    з = urllib.request.Request(
        os.environ.get("DROP_URL", "").rstrip("/") + "/dolphin-proxies.txt",
        headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")})
    for l in _ОТКР.open(з, timeout=30).read().decode("utf-8", "replace").splitlines():
        l = l.strip()
        m = (re.match(r"(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)", l)
             if l and not l.startswith("#") else None)
        if m:
            u, pw, h, _ = m.groups()
            обычные.append("socks5://%s:%s@%s:3001" % (u, pw, h))
except Exception as ex:                                        # noqa: BLE001
    описания.append("общий пул не прочитался: %s" % str(ex)[:70])

# --- цели: настоящие ОГРН из базы ----------------------------------------
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
огрны = [r[0] for r in c.execute(
    "SELECT ogrn FROM requisites WHERE COALESCE(ogrn,'')<>'' "
    "  AND COALESCE(revenue_rub,'') IN ('','0') LIMIT 400")]
c.close()


def прогнать(url, метка, сколько=ЗАПРОСОВ):
    ок, коды, первый_отказ = 0, {}, None
    t0 = time.time()
    for i in range(сколько):
        огрн = огрны[(hash(метка) + i) % len(огрны)]
        try:
            r = requests.get("https://checko.ru/company/%s" % огрн,
                             proxies={"http": url, "https": url},
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT "
                                                    "10.0; Win64; x64) "
                                                    "AppleWebKit/537.36"},
                             timeout=25)
            коды[r.status_code] = коды.get(r.status_code, 0) + 1
            if r.status_code == 200:
                ок += 1
            elif первый_отказ is None:
                первый_отказ = i + 1
        except Exception as ex:                                # noqa: BLE001
            коды[str(ex)[:22]] = коды.get(str(ex)[:22], 0) + 1
            if первый_отказ is None:
                первый_отказ = i + 1
        time.sleep(0.2)
    return ("%-26s ок %2d из %d, первый отказ на %s, %.0f с, коды %s"
            % (метка, ок, сколько,
               первый_отказ if первый_отказ else "—",
               time.time() - t0, коды))

итоги = []
for i, url in enumerate(мобильные_url):
    итоги.append(прогнать(url, "мобильный %d" % (i + 1)))
for i, url in enumerate(обычные[:2]):
    итоги.append(прогнать(url, "обычный из пула %d" % (i + 1)))

print("=" * 74)
print("=== СВОДКА: МОБИЛЬНЫЕ ПРОКСИ ПРОТИВ ОБЫЧНЫХ ===")
print("целей в выборке: %d; запросов на прокси: %d" % (len(огрны), ЗАПРОСОВ))
print("")
print("профили:")
for с in описания:
    print("   " + с)
print("   обычных прокси в пуле: %d" % len(обычные))
print("")
print("замер:")
for с in итоги:
    print("   " + с)
