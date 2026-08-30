# -*- coding: utf-8 -*-
"""Своя проверка ключей: сам решаю вердикт и сам пишу список живых.

Разбор чужого вывода дал ноль живых при том, что сам check_keys напечатал 267 —
значит парсил не то. Здесь никакого разбора текста: беру ту же библиотеку,
хожу сам, храню (ключ → HTTP-код и вердикт).

Живые пишутся в СЕРВЕРНЫЙ файл, вердикты — в jsonl с fsync.
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

КОРЕНЬ = r"C:\seostat\Parser2"
sys.path.insert(0, КОРЕНЬ)
ФАЙЛ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
ЖИВЫЕ = r"C:\sender\_ops\checko-zhivye-klyuchi.txt"
ЖУРНАЛ = r"C:\sender\_ops\checko-klyuchi-verdikty.jsonl"
ПОТОКОВ = int(([а.split("=", 1)[1] for а in sys.argv if а.startswith("--pot=")]
               or ["6"])[0])

import requests                                              # noqa: E402
from metalparser.checko import (read_keys_file, _parse_keys,  # noqa: E402
                                build_search_params, _is_limit_meta,
                                SEARCH_URL, DEFAULT_UA)

ключи = [к for к in dict.fromkeys(_parse_keys(read_keys_file(ФАЙЛ)))
         if re.fullmatch(r"[A-Za-z0-9]{16}", к)]
print("настоящих ключей: %d, потоков: %d" % (len(ключи), ПОТОКОВ))
СЛОВА = ("лимит", "превыш", "тариф", "суточн", "limit", "exceed", "quota")


def проверить(ключ):
    п = {**build_search_params("25.62", None, True, 1), "key": ключ}
    for попытка in range(3):
        try:
            r = requests.get(SEARCH_URL, params=п, timeout=25,
                             headers={"User-Agent": DEFAULT_UA})
        except Exception as e:                                # noqa: BLE001
            if попытка == 2:
                return ключ, 0, "сеть", type(e).__name__
            time.sleep(1.5 * (попытка + 1))
            continue
        тело = r.text or ""
        try:
            pl = r.json()
        except Exception:                                     # noqa: BLE001
            pl = {}
        низ = тело.lower()
        if _is_limit_meta(pl) or any(с in низ for с in СЛОВА):
            return ключ, r.status_code, "лимит", тело[:80]
        if r.status_code in (401, 403):
            return ключ, r.status_code, "битый", тело[:80]
        if r.status_code == 429:
            time.sleep(3.0 * (попытка + 1))
            continue
        if r.status_code == 200:
            return ключ, 200, "живой", ""
        return ключ, r.status_code, "иное", тело[:80]
    return ключ, 429, "троттлинг", ""


т0 = time.time()
итоги = []
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as п:
    for i, рез in enumerate(п.map(проверить, ключи), 1):
        итоги.append(рез)
        if i % 100 == 0:
            print("   проверено %d/%d…" % (i, len(ключи)))

with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    for ключ, код, вердикт, прим in итоги:
        f.write(json.dumps({"ts": int(time.time()), "hvost": ключ[-4:],
                            "http": код, "verdikt": вердикт,
                            "prim": прим}, ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())

живые = [к for к, код, в, _ in итоги if в in ("живой", "лимит")]
with io.open(ЖИВЫЕ, "w", encoding="utf-8") as f:
    f.write("\n".join(живые) + ("\n" if живые else ""))
    f.flush()
    os.fsync(f.fileno())

счёт = Counter(в for _, _, в, _ in итоги)
коды = Counter(код for _, код, _, _ in итоги)
для_примера = [(к[-4:], код, в, п[:60]) for к, код, в, п in итоги
               if в not in ("живой",)][:6]
print("\n=== ВЕРДИКТЫ ===")
for в, n in счёт.most_common():
    print("   %-10s %4d" % (в, n))
print("HTTP-коды: %s" % dict(коды))
print("примеры не-живых: %s" % для_примера)
print("\n=== ИТОГ ===")
print("ключей всего:     %d" % len(ключи))
print("живых + в лимите: %d  → записал в %s" % (len(живые), ЖИВЫЕ))
print("суточная ёмкость при 100 запросов/ключ: ≈ %d запросов ≈ %d компаний"
      % (len(живые) * 100, len(живые) * 100 * 100))
print("заняло %.0f с" % (time.time() - т0))
