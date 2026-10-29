# -*- coding: utf-8 -*-
"""Сайт дистрибьютора вместо сайта компании: бесплатная механическая проверка.

Случай «Чайнафуда» (ИНН 3300018100, 29.10): поиск приклеил к производителю
снеков интернет-магазин владимирского оптовика рыбком33.рф. Проверка
«имя на сайте» прошла — «ЧАЙНАФУД» стоит там в фильтре брендов, — и письмо
рассказало компании про её «вяленую рыбу и сыры».

В enrich.db текста сайтов почти нет (site_text пуст у 97% писем), поэтому
сайт читается заново: главная + до трёх страниц «контакты/реквизиты/о
компании». Без модели, только HTTP. Только для писем в работе (карточка
ждёт подтверждения или письмо стоит в очереди). Признаки:
  A  на сайте есть ИНН, и среди них нет нашего — реквизиты чужие (сильный);
  Б  ИНН на сайте нет, но это магазин («в корзину», «купить в 1 клик»…),
     а имя компании встречается на нём не больше двух раз (слабый).
Результат по каждому ИНН — в C:\\sender\\_ops\\chuzhoy-sayt-inn.jsonl (с fsync,
перезапуск продолжает с места). Писем не трогает.

  --zapusk   отсоединённо (лог _ops/chuzhoy-sayt-inn.log)
  --itog     только сводка по уже собранному
  --vse      в сводке все строки, а не первые 40 на группу
"""
import concurrent.futures as cf
import html
import io
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r"C:\sender")

if "--zapusk" in sys.argv:
    import subprocess
    л = io.open(r"C:\sender\_ops\chuzhoy-sayt-inn.log", "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)]
                         + [a for a in sys.argv[1:] if a != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(5)
    print("проверка запущена, pid %d, жив %s" % (п.pid, п.poll() is None))
    raise SystemExit(0)

import sqlite3                                                   # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПУТЬ = r"C:\sender\_ops\chuzhoy-sayt-inn.jsonl"
ОБЩИЕ = {"ооо", "оао", "зао", "ао", "пао", "нао", "спк", "мбу", "муп", "гуп",
         "общество", "с", "ограниченной", "ответственностью", "акционерное",
         "завод", "фабрика", "комбинат", "торговый", "дом", "тд", "пк", "нпо",
         "нпп", "группа", "компаний", "компания", "фирма", "производственная",
         "производственный", "агро", "гк", "им", "имени", "по", "и"}
МАГАЗИН = ("в корзину", "купить в 1 клик", "купить в один клик",
           "добавить в корзину", "к сравнению")
РЕ_ИНН = re.compile(r"инн[\s:№/кпп\d]{0,40}?(\d{10}(?:\d{2})?)(?!\d)", re.I)
РЕ_ССЫЛКА = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
ВАЖНЫЕ = re.compile(r"контакт|реквизит|о компании|о нас|contact|rekvizit|kontakt|about|o-nas|o-kompanii", re.I)
ВСЕ = "--vse" in sys.argv
ИТОГ = "--itog" in sys.argv
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def слова(имя):
    ч = re.findall(r"[а-яёa-z0-9]{3,}", str(имя or "").lower())
    return [w for w in ч if w not in ОБЩИЕ]


def адрес_ascii(url):
    ч = urllib.parse.urlsplit(url if "://" in url else "http://" + url)
    хост = ч.hostname or ""
    try:
        хост = хост.encode("idna").decode("ascii")
    except Exception:                                            # noqa: BLE001
        pass
    if ч.port:
        хост += ":%d" % ч.port
    путь = urllib.parse.quote(ч.path or "/", safe="/%:@-._~!$&'()*+,;=")
    return urllib.parse.urlunsplit((ч.scheme or "http", хост, путь, ч.query, ""))


def скачать(url):
    з = urllib.request.Request(адрес_ascii(url), headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9"})
    with urllib.request.urlopen(з, timeout=20, context=_ctx) as о:
        сырьё = о.read(3_000_000)
        кодировка = о.headers.get_content_charset()
        итог = о.geturl()
    if not кодировка:
        м = re.search(rb'charset=["\']?([\w-]+)', сырьё[:4000], re.I)
        кодировка = м.group(1).decode() if м else None
    for к in (кодировка, "utf-8", "cp1251"):
        if not к:
            continue
        try:
            return сырьё.decode(к), итог
        except Exception:                                        # noqa: BLE001
            continue
    return сырьё.decode("utf-8", "replace"), итог


def в_текст(h):
    h = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", h)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)))


def проверить(инн, сайт, имя):
    рез = {"inn": инн, "sayt": сайт, "imya": имя}
    try:
        h, итог = скачать(сайт)
    except Exception as e:                                       # noqa: BLE001
        рез["oshibka"] = str(e)[:120]
        return рез
    тексты = [в_текст(h)]
    страницы = [итог]
    for href, надпись in РЕ_ССЫЛКА.findall(h):
        if len(страницы) >= 4:
            break
        if ВАЖНЫЕ.search(href) or ВАЖНЫЕ.search(в_текст(надпись)):
            u = urllib.parse.urljoin(итог, href.strip())
            if not u.startswith("http") or u in страницы:
                continue
            if urllib.parse.urlsplit(u).hostname != urllib.parse.urlsplit(итог).hostname:
                continue
            страницы.append(u)
            try:
                тексты.append(в_текст(скачать(u)[0]))
            except Exception:                                    # noqa: BLE001
                pass
    весь = " ".join(тексты)
    низ = весь.lower()
    инны = sorted(set(РЕ_ИНН.findall(весь)))
    ключи = слова(имя)
    рез.update({
        "stranic": len(страницы), "simvolov": len(весь),
        "inn_na_sayte": инны[:6], "svoy_inn": инн in весь,
        "upominaniy": sum(низ.count(w[:max(4, len(w) - 2)]) for w in ключи) if ключи else -1,
        "magazin": [м for м in МАГАЗИН if м in низ][:3]})
    if not рез["svoy_inn"] and инны:
        рез["gruppa"] = "A"
    elif not рез["svoy_inn"] and рез["magazin"] and 0 <= рез["upominaniy"] <= 2:
        рез["gruppa"] = "Б"
    return рез


def готовые():
    г = {}
    if os.path.exists(ПУТЬ):
        for с in io.open(ПУТЬ, encoding="utf-8"):
            try:
                з = json.loads(с)
                if "rid" in з:      # строки первой версии (по site_text), не результат
                    continue
                г[з["inn"]] = з
            except Exception:                                    # noqa: BLE001
                pass
    return г


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
enr = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=30)
with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.status AS cst, c.email, "
        "       r.inn, r.company_name, m.status AS mst "
        "FROM confirm_reviews c "
        "LEFT JOIN messages m ON m.id = c.message_id "
        "LEFT JOIN recipients r ON r.id = c.recipient_id "
        "WHERE (c.status='pending') "
        "   OR (c.status IN ('approved','edited') "
        "       AND m.status IN ('scheduled','sending'))").fetchall()
письма_по_инн = {}
имена = {}
for r in ряды:
    инн = str(r["inn"] or "").strip()
    if инн:
        письма_по_инн.setdefault(инн, []).append(
            (int(r["id"]), int(r["campaign_id"] or 0), str(r["email"] or ""), r["cst"], r["mst"]))
        имена[инн] = str(r["company_name"] or "")
сайты = {}
for инн in письма_по_инн:
    с = enr.execute("SELECT site FROM companies WHERE inn=?", (инн,)).fetchone()
    if с and с[0]:
        сайты[инн] = str(с[0]).strip()

if not ИТОГ:
    г = готовые()
    очередь = [и for и in сайты if и not in г]
    print("%s писем в работе %d, компаний %d, с сайтом %d, уже проверено %d, к проверке %d"
          % (time.strftime("%H:%M:%S"), len(ряды), len(письма_по_инн), len(сайты),
             len(г), len(очередь)), flush=True)
    замок = threading.Lock()
    сделано = 0
    with io.open(ПУТЬ, "a", encoding="utf-8") as f, cf.ThreadPoolExecutor(12) as пул:
        будущие = {пул.submit(проверить, и, сайты[и], имена[и]): и for и in очередь}
        for б in cf.as_completed(будущие):
            try:
                з = б.result()
            except Exception as e:                               # noqa: BLE001
                з = {"inn": будущие[б], "oshibka": "сбой: %s" % str(e)[:100]}
            with замок:
                f.write(json.dumps(з, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
                сделано += 1
                if сделано % 50 == 0:
                    print("%s проверено %d/%d" % (time.strftime("%H:%M:%S"), сделано, len(очередь)), flush=True)
    print("%s готово" % time.strftime("%H:%M:%S"), flush=True)

г = готовые()
ошибок = sum(1 for з in г.values() if з.get("oshibka"))
свой = sum(1 for з in г.values() if з.get("svoy_inn"))
print("компаний с сайтом %d | проверено %d | сайт не открылся %d | свой ИНН на сайте %d"
      % (len(сайты), len(г), ошибок, свой))
for группа, назв in (("A", "A: ЧУЖОЙ ИНН НА САЙТЕ, СВОЕГО НЕТ"),
                     ("Б", "Б: МАГАЗИН БЕЗ ИНН, ИМЯ РЕДКО")):
    сп = [з for з in г.values() if з.get("gruppa") == группа and з["inn"] in письма_по_инн]
    писем = sum(len(письма_по_инн[з["inn"]]) for з in сп)
    print("\n%s: компаний %d, писем %d" % (назв, len(сп), писем))
    for з in (сп if ВСЕ else сп[:40]):
        п = письма_по_инн[з["inn"]]
        print("  %s %-38s %-30s ИНН сайта %-26s упом %s %s | %s"
              % (з["inn"], з["imya"][:38], з["sayt"][:30], ",".join(з["inn_na_sayte"][:2]),
                 з["upominaniy"], "/".join(з["magazin"][:1]),
                 " ".join("#%d" % x[0] for x in п[:3])))
