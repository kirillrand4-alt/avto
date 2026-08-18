# -*- coding: utf-8 -*-
"""Собрать ТЕКСТ сайтов компаний партии в обогащение — для генерации писем.

Зачем, если паспорт сайта уже есть. Паспорт (enrich.db/site_facts) — это
СПИСКИ: продукция, линии, мощности. Он доезжает до промпта и промпт им
пользуется (проверено 18.08). Но списки лоссовые: «оборудование_линии»
заполнено у 60% компаний, и ровно одинаково у годных и у бракованных писем.
То есть дело не в том, что данных не было, а в том, что там, где списка
нет, модель достраивает цех сама — и рецензент, читающий ЖИВОЙ ТЕКСТ
сайта, эту достройку не находит.

Поэтому кладём рядом с паспортом то же, что читает рецензент: связный текст
главной и внутренних страниц. Хранение durable — таблица site_text в
enrich.db на сервере (урок рестарта из CLAUDE.md), повторный запуск
досбирает недостающее.

    python zapusk_svoego_skripta.py ops/sobrat_teksty_saytov.py            # что есть
    python zapusk_svoego_skripta.py ops/sobrat_teksty_saytov.py 400 --собрать
"""
import gzip
import io
import json
import re
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ENRICH = r"C:\sender\enrich.db"
ЖУРНАЛ = r"C:\sender\_ops\site-text.jsonl"
ЗНАКОВ = 6000
ПОТОКОВ = 16
СОБРАТЬ = "--собрать" in sys.argv
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "300"))

_СОЗДАНИЕ = """
CREATE TABLE IF NOT EXISTS site_text (
    inn    TEXT PRIMARY KEY,
    url    TEXT,
    text   TEXT,
    chars  INTEGER,
    ts     TEXT
)"""


def в_punycode(url: str) -> str:
    """Кириллический хост — в IDNA, иначе urllib падает на latin-1."""
    from urllib.parse import urlsplit, urlunsplit
    try:
        ч = urlsplit(url)
        хост = ч.hostname or ""
        хост.encode("ascii")
        return url
    except UnicodeEncodeError:
        pass
    except Exception:                                            # noqa: BLE001
        return url
    try:
        пуни = хост.encode("idna").decode("ascii")
    except Exception:                                            # noqa: BLE001
        return url
    порт = f":{ч.port}" if ч.port else ""
    return urlunsplit((ч.scheme, пуни + порт, ч.path, ч.query, ч.fragment))


def взять(url, таймаут=20):
    try:
        r = urllib.request.Request(в_punycode(url), headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(r, timeout=таймаут) as o:
            b = o.read(2_000_000)
            if o.headers.get("Content-Encoding") == "gzip":
                b = gzip.decompress(b)
            return b.decode("utf-8", "replace")
    except Exception:                                            # noqa: BLE001
        return ""


# Мусор интерфейса: формы обратного звонка, модалки, кнопки. Он съедает
# место в промпте и ничего не говорит о производстве. Пункты меню НЕ трогаем
# («Животноводческие комплексы», «Мягкие резервуары») - это как раз то, что
# компания делает.
_ШУМ = re.compile(
    r"(?i)^(логин|пароль|войти|вход|регистрац|отправить|отправка|cancel|enter|"
    r"ok|хорошо|закрыть|подробнее|наверх|поиск|option |заголовок модального|"
    r"обратный звонок|оставьте свои данные|ваше имя|ваш телефон|телефон|"
    r"e-?mail|сообщение отправлено|ваше сообщение успешно|"
    r"отправляя (это|эту)|соглашаюсь|политик\w* конфиденциальн|"
    r"мы (постараемся|перезвоним)|наш менеджер|заказать звонок|"
    r"нажимая|cookie|куки|версия для слабовидящих|карта сайта)")


def _текст(html: str) -> str:
    т = re.sub(r"(?is)<(script|style|head|nav|footer)\b.*?</\1>", " ", html)
    т = re.sub(r"<[^>]+>", " ", т)
    import html as _h
    т = _h.unescape(т)
    т = re.sub(r"[ \t\xa0]+", " ", re.sub(r"\s*\n\s*", "\n", т)).strip()
    видел, чисто = set(), []
    for строка in т.split("\n"):
        с = строка.strip()
        if not с or _ШУМ.match(с):
            continue
        ключ = с.lower()
        if ключ in видел:          # одно и то же меню на каждой странице
            continue
        видел.add(ключ)
        чисто.append(с)
    return "\n".join(чисто)


def сайт(база: str) -> str:
    """Главная плюс до шести внутренних страниц про услуги и производство."""
    if not база:
        return ""
    if not база.startswith("http"):
        база = "http://" + база
    сыро = взять(база)
    if not сыро:
        return ""
    дом = re.match(r"https?://[^/]+", база)
    дом = дом.group(0) if дом else база
    ссылки = []
    for m in re.finditer(r'href="([^"]+)"', сыро):
        u = m.group(1)
        if u.startswith("/"):
            u = дом + u
        if u.startswith(дом) and re.search(
                r"(?i)(uslug|servic|produkc|product|proizvod|about|company|"
                r"o-kompanii|oborudovanie|tehnolog|catalog|zavod|cehi?)", u):
            if u not in ссылки:
                ссылки.append(u)
        if len(ссылки) >= 6:
            break
    куски = [_текст(сыро)]
    for u in ссылки:
        с = взять(u, 12)
        if с:
            куски.append(_текст(с))
        if sum(len(x) for x in куски) > ЗНАКОВ * 2:
            break
    return "\n".join(куски)[:ЗНАКОВ]


con = sqlite3.connect(ENRICH, timeout=30)
con.execute(_СОЗДАНИЕ)
con.commit()
уже = {r[0] for r in con.execute("SELECT inn FROM site_text WHERE chars>0")}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряд = store._conn.execute(
        "SELECT DISTINCT inn FROM confirm_reviews WHERE campaign_id=10 "
        "AND inn IS NOT NULL").fetchall()
инн = [str(r[0]).strip() for r in ряд if r[0]]

сайты = {}
for i in инн:
    r = con.execute("SELECT site FROM companies WHERE inn=?", (i,)).fetchone()
    u = (r[0] if r else "") or ""
    if not u:
        r = con.execute("SELECT site FROM site_facts WHERE inn=?",
                        (i,)).fetchone()
        u = (r[0] if r else "") or ""
    if u:
        сайты[i] = u

надо = [i for i in инн if i in сайты and i not in уже]
print(f"ИНН партии: {len(инн)} | известен сайт: {len(сайты)} | "
      f"текст уже собран: {len(уже & set(инн))} | к сбору: {len(надо)}")
if not СОБРАТЬ:
    print("\nсухой прогон. Собрать — аргумент --собрать [сколько]")
    raise SystemExit(0)

надо = надо[:СКОЛЬКО]
начало = time.time()
готово = []


def работа(i):
    т = сайт(сайты[i])
    return i, сайты[i], т


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as ex:
    for i, u, т in ex.map(работа, надо):
        готово.append((i, u, т))

сейчас = datetime.now(timezone.utc).isoformat()
с_текстом = 0
with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
    for i, u, т in готово:
        con.execute(
            "INSERT INTO site_text (inn,url,text,chars,ts) VALUES (?,?,?,?,?) "
            "ON CONFLICT(inn) DO UPDATE SET url=excluded.url, "
            "text=excluded.text, chars=excluded.chars, ts=excluded.ts",
            (i, u, т, len(т), сейчас))
        if т:
            с_текстом += 1
        f.write(json.dumps({"inn": i, "url": u, "знаков": len(т)},
                           ensure_ascii=False) + "\n")
    f.flush()
con.commit()
con.close()
print(f"собрано за {time.time() - начало:.0f}с: {len(готово)} сайтов, "
      f"с текстом {с_текстом}")
