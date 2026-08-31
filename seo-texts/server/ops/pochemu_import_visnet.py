# -*- coding: utf-8 -*-
"""Гипотеза: файл результатов вырос, и GET не укладывается в таймаут 90 с.

В ProbeSync._дроп таймаут urlopen жёстко 90 секунд. Если скачивание
probe-rezultat.jsonl дольше — забрать() падает, tick ловит исключение и пишет
в лог «приём вердиктов упал», а вердикты копятся на дропе. Проверяем размер
и время скачивания, HEAD и Range.
"""
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\sender")
from sender.probe_sync import build_probe_sync, РЕЗУЛЬТАТ, ЗАДАНИЕ  # noqa: E402
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
цикл = build_probe_sync(store, getattr(build_addr_probe(store, cfg),
                                       "probe_", None), cfg)
база, токен = цикл._ключи()
url = "%s/%s" % (база, РЕЗУЛЬТАТ)
print("цикл: enabled=%s running=%s interval=%s"
      % (цикл.enabled(), цикл.running(), getattr(цикл, "interval", "?")))
print("последний tick: %s" % str(getattr(цикл, "last", None))[:300])


def запрос(метод, доп=None):
    з = urllib.request.Request(url, method=метод)
    з.add_header("X-Drop-Token", токен)
    for к, v in (доп or {}).items():
        з.add_header(к, v)
    return з


print("\n=== HEAD ===")
try:
    т0 = time.time()
    with urllib.request.urlopen(запрос("HEAD"), timeout=60) as о:
        длина = о.headers.get("Content-Length")
        print("   Content-Length: %s (%.1f МБ), за %.1f с"
              % (длина, int(длина or 0) / 1048576.0, time.time() - т0))
        print("   Accept-Ranges: %s" % о.headers.get("Accept-Ranges"))
except Exception as e:                                        # noqa: BLE001
    print("   HEAD не прошёл: %s: %s" % (type(e).__name__, str(e)[:120]))

print("\n=== ХВОСТ ЧЕРЕЗ Range (последние 300 КБ) ===")
try:
    т0 = time.time()
    with urllib.request.urlopen(запрос("GET", {"Range": "bytes=-300000"}),
                                timeout=60) as о:
        кусок = о.read()
    print("   получено %d Б за %.1f с, код диапазона поддержан: %s"
          % (len(кусок), time.time() - т0, len(кусок) < 1000000))
    строк = кусок.decode("utf-8", "replace").splitlines()
    print("   строк в хвосте: %d" % len(строк))
    print("   последняя: %s" % (строк[-1][:150] if строк else "—"))
except Exception as e:                                        # noqa: BLE001
    print("   Range не прошёл: %s: %s" % (type(e).__name__, str(e)[:120]))

print("\n=== ПОЛНОЕ СКАЧИВАНИЕ С ЗАПАСОМ ПО ВРЕМЕНИ ===")
try:
    т0 = time.time()
    with urllib.request.urlopen(запрос("GET"), timeout=600) as о:
        данные = о.read()
    сек = time.time() - т0
    print("   скачано %.1f МБ за %.1f с" % (len(данные) / 1048576.0, сек))
    print("   штатный таймаут 90 с: %s"
          % ("НЕ УКЛАДЫВАЕМСЯ — вот и причина" if сек > 90 else "укладываемся"))
    строки = данные.decode("utf-8", "replace").splitlines()
    print("   строк всего: %d" % len(строки))
except Exception as e:                                        # noqa: BLE001
    print("   полное скачивание упало: %s: %s" % (type(e).__name__, str(e)[:140]))

print("\n=== ИТОГ ===")
print("если полное скачивание дольше 90 с — забрать() падает каждый круг,")
print("и лечится это либо ротацией файла, либо докачкой хвостом по Range.")
