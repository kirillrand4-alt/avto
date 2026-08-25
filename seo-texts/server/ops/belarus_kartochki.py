# -*- coding: utf-8 -*-
"""Карточки компаний из каталога ProdExpo: сайт, УНП, почта, текст сайта.

Что делаем и зачем. Из каталога вытащены название, город, почта, телефон и
строка «чем занимается» — для письма этого мало: модель по одной строке
начинает пересказывать название рода деятельности. Поэтому идём на сайт
штатным обходчиком рассыльщика и берём ЖИВОЙ текст — им письмо вправе
оперировать, потому что его можно проверить.

Заодно достаём УНП (у белорусов он обычно в подвале сайта) — он заменит
ИНН как ключ компании, и почту, если в каталоге её нет.

Пишем durable: каждая карточка сразу уходит строкой в kartochki.jsonl с
fsync. Прогон резюмируемый — перезапуск не платит за уже обойденные.

    python belarus_kartochki.py [бюджет_сек] [потоков]
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender\server")
import enrich_contacts as EC  # noqa: E402

КАТАЛОГ = r"C:\sender\_ops\belarus"
ЖУРНАЛ = os.path.join(КАТАЛОГ, "katalog-razbor.jsonl")
КАРТОЧКИ = os.path.join(КАТАЛОГ, "kartochki.jsonl")
КЭШ = os.path.join(КАТАЛОГ, "pagecache")
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 1500.0
ПОТОКОВ = int(sys.argv[2]) if len(sys.argv) > 2 else 8
НАЧАЛО = time.time()
os.makedirs(КЭШ, exist_ok=True)

УНП = re.compile(r"УНП\s*[:№\-]?\s*(\d{9})", re.I)
ПОЧТА = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Почты обходчиков, витрин и движков — не контакты компании.
ЧУЖИЕ = ("example.com", "sentry.io", "wixpress.com", "domain.com",
         "yourdomain", "email.com", "site.ru", "tilda")


def компании():
    из = {}
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            d = json.loads(с)
        except Exception:                                    # noqa: BLE001
            continue
        for к in (d.get("компании") or []):
            имя = str(к.get("название") or "").strip()
            if имя:
                из.setdefault(имя.lower(), к)
    return list(из.values())


готово = set()
if os.path.exists(КАРТОЧКИ):
    for с in io.open(КАРТОЧКИ, encoding="utf-8", errors="replace"):
        try:
            готово.add(str(json.loads(с).get("название") or "").lower())
        except Exception:                                    # noqa: BLE001
            pass

все = компании()
работа = [к for к in все if str(к.get("название") or "").lower() not in готово]
print("компаний в каталоге: %d, уже с карточкой: %d, к обходу: %d"
      % (len(все), len(готово), len(работа)))

ф = io.open(КАРТОЧКИ, "a", encoding="utf-8")
замок = threading.Lock()
счёт = {"обошли": 0, "сайт нашли": 0, "УНП": 0, "почту добыли": 0, "без сайта": 0,
        "сайт не дался": 0}


def записать(з):
    with замок:
        ф.write(json.dumps(з, ensure_ascii=False) + "\n")
        ф.flush()
        os.fsync(ф.fileno())


def один(к):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    имя = str(к.get("название") or "").strip()
    сайт = str(к.get("сайт") or "").strip()
    з = {"название": имя, "город": к.get("город"), "телефон": к.get("телефон"),
         "чем_занимается": к.get("чем_занимается"), "продукция": к.get("продукция"),
         "почта_каталог": к.get("почта"), "сайт": сайт, "унп": "",
         "почта": str(к.get("почта") or "").strip(), "текст_сайта": "",
         "как_нашли_сайт": "каталог" if сайт else ""}
    if not сайт:
        try:
            найден, как = EC.find_site_via_search(
                {"name": имя, "city": к.get("город") or ""})
        except Exception as ex:                              # noqa: BLE001
            найден, как = None, "search-err:%s" % repr(ex)[:40]
        if найден:
            сайт = з["сайт"] = найден
            з["как_нашли_сайт"] = как
            with замок:
                счёт["сайт нашли"] += 1
        else:
            з["как_нашли_сайт"] = как or "не нашли"
            with замок:
                счёт["без сайта"] += 1
    if сайт:
        try:
            текст, _стр, _x, _src = EC.crawl_contacts(
                сайт, pace=(0.8, 2.0), cache_dir=КЭШ,
                cache_key=re.sub(r"\W+", "_", имя)[:60])
        except Exception as ex:                              # noqa: BLE001
            текст = ""
            з["ошибка_обхода"] = repr(ex)[:90]
        if текст:
            м = УНП.search(текст)
            if м:
                з["унп"] = м.group(1)
                with замок:
                    счёт["УНП"] += 1
            if not з["почта"]:
                for а in ПОЧТА.findall(текст):
                    ан = а.strip().lower()
                    if any(ч in ан for ч in ЧУЖИЕ):
                        continue
                    з["почта"] = ан
                    with замок:
                        счёт["почту добыли"] += 1
                    break
            з["текст_сайта"] = " ".join(текст.split())[:9000]
        else:
            with замок:
                счёт["сайт не дался"] += 1
    записать(з)
    with замок:
        счёт["обошли"] += 1
        if счёт["обошли"] % 5 == 0:
            print("   %d/%d  %s" % (счёт["обошли"], len(работа), счёт))


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(один, работа))
ф.close()
print("")
print("итог: %s" % счёт)
print("карточки: %s" % КАРТОЧКИ)
