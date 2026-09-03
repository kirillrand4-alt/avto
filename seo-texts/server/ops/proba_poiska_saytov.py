# -*- coding: utf-8 -*-
"""Проба поиска сайтов на 25 целях: расход баланса и качество находок."""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

ПИТОН = r"C:\Program Files\Python311\python.exe"
СКРИПТ = r"C:\sender\server\ops\sayty_dlya_celey.py"
ЦЕЛИ = r"C:\seostat\drop\celi_meyer_30mln.jsonl"
ЖУРНАЛ = r"C:\sender\server\sayty_dlya_celey.jsonl"
СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 25


def баланс():
    u = os.environ.get("XMLRIVER_USER", "")
    k = os.environ.get("XMLRIVER_KEY", "")
    if not (u and k):
        return None
    try:
        о = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        з = urllib.request.Request(
            "http://xmlriver.com/api/get_balance/?user=%s&key=%s" % (u, k))
        return float(о.open(з, timeout=30).read().decode().strip())
    except Exception:                                          # noqa: BLE001
        return None


было_строк = 0
if os.path.exists(ЖУРНАЛ):
    было_строк = sum(1 for _ in io.open(ЖУРНАЛ, encoding="utf-8",
                                        errors="replace"))
б1 = баланс()
t0 = time.time()
r = subprocess.run([ПИТОН, СКРИПТ, "--targets", ЦЕЛИ, "--lim", str(СКОЛЬКО)],
                   capture_output=True, text=True, timeout=840,
                   encoding="utf-8", errors="replace")
б2 = баланс()

новые = []
if os.path.exists(ЖУРНАЛ):
    стр = io.open(ЖУРНАЛ, encoding="utf-8", errors="replace").read().splitlines()
    for с in стр[было_строк:]:
        try:
            новые.append(json.loads(с))
        except Exception:                                      # noqa: BLE001
            pass

нашли = sum(1 for z in новые if z.get("сайт") or z.get("site"))
print("=" * 78)
print("=== СВОДКА: ПРОБА ПОИСКА САЙТОВ ===")
print("код возврата %s, время %.0f с" % (r.returncode, time.time() - t0))
print("баланс: было %s, стало %s, потрачено %s"
      % (б1, б2, (round(б1 - б2, 4) if (б1 is not None and б2 is not None)
                  else "?")))
if б1 is not None and б2 is not None and новые:
    print("   на одну компанию: %.4f" % ((б1 - б2) / max(1, len(новые))))
    print("   на 4738 компаний хватит: %s"
          % ("ДА" if (б1 - б2) / max(1, len(новые)) * 4738 <= б2 + (б1 - б2)
             else "НЕТ, нужно больше"))
print("")
print("записей в журнале добавилось: %d, из них с сайтом: %d"
      % (len(новые), нашли))
print("")
print("--- находки ---")
for z in новые[:12]:
    print("   " + json.dumps({к: str(v)[:44] for к, v in z.items()
                              if v not in (None, "", [])},
                             ensure_ascii=False)[:200])
print("")
print("--- вывод скрипта ---")
for с in (r.stdout or "").splitlines()[-14:]:
    print("   " + с[:160])
if r.stderr:
    for с in r.stderr.splitlines()[-6:]:
        print("   ош: " + с[:160])
