# -*- coding: utf-8 -*-
"""Массовое чтение писем со сверкой по сайту - через провайдерский API.

Владелец: «если будут читать агенты и отправлять - будет быстрее? хотелось бы
за полчаса перевести 500 писем в автоотправку».

Своими токенами сессии сто писем я читал часами: это дословное чтение, и
быстрее оно не станет. Правило владельца на этот счёт прямое - всю тяжёлую
работу через провайдерский API, а сессию беречь. Пятьсот писем - ровно
такой массовый прогон.

Что делает рецензент. На каждое письмо кладёт рядом ТЕКСТ САЙТА компании
(главная плюс до шести внутренних страниц, снятых с сервера) и спрашивает
модель об одном: какие утверждения ПИСЬМА о компании сайтом не
подтверждаются. Это ровно то, на чём я ловил брак руками - «диализное
оборудование» у визитки без слова «диализ», «крепёж до М76» там, где на
сайте только «метизы».

Почему не регулярка: она видит слова, а не утверждения. Почему не мои
токены: 500 писем по 700 знаков сайта - это миллионы знаков чтения.

Вердикты durable: пишутся в *.jsonl на СЕРВЕРЕ по мере готовности, а не
копятся в возвращаемом JSON (урок рестарта 25.07 из CLAUDE.md).

    python zapusk_svoego_skripta.py ops/rezenzent_pisem.py 60 2200 2400
"""
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                       # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

_числа = [a for a in sys.argv[1:] if a.lstrip("-").isdigit()]
СКОЛЬКО = int(_числа[0]) if len(_числа) > 0 else 60
ОТ_ID = int(_числа[1]) if len(_числа) > 1 else 0
ДО_ID = int(_числа[2]) if len(_числа) > 2 else 10 ** 9
ЖУРНАЛ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ПАЧКА = 4                     # писем в одном вызове модели
ПОТОКОВ_САЙТ = 16
ПОТОКОВ_МОДЕЛЬ = 20
ЗНАКОВ_САЙТА = 4500

СИСТЕМА = (
    "Ты придирчивый редактор холодных B2B-писем. Тебе дают ПИСЬМО и ТЕКСТ "
    "САЙТА компании-получателя. Задача одна: найти в письме утверждения О "
    "КОМПАНИИ, которые сайт опровергает или которых там нет.\n\n"
    "СУДИ ПО САЙТУ, А НЕ ПО ОКВЭД. Код ОКВЭД в России сплошь и рядом "
    "формален: у компании может стоять «разборка и снос зданий», а на сайте "
    "- проектирование и монтаж инженерных систем, и сайт тут прав. ОКВЭД "
    "дан для справки; расхождение письма с ОКВЭД САМО ПО СЕБЕ не претензия. "
    "Претензия - только когда сайт говорит другое или молчит о том, что "
    "письмо утверждает как факт.\n\n"
    "Нарушение это:\n"
    "* письмо приписывает компании ДРУГОЙ род занятий, чем показывает сайт "
    "(письмо про диализное оборудование, а сайт - косметология);\n"
    "* конкретика, которой на сайте нет: числа, модели, размеры, состав "
    "парка («крепёж до М76», «больше сотни тягачей», «парк ЧПУ-станков», "
    "«весь спектр операций от катаракты до витреоретинальных»);\n"
    "* профиль совсем не тот: письмо про промышленные компрессоры, а "
    "получатель - клиника, магазин, консалтинг, управляющая компания.\n\n"
    "НЕ нарушение:\n"
    "* элементы ТИПОВОГО техпроцесса рядом с подтверждённым занятием: если "
    "сайт говорит «производим металлоконструкции», то «металлообработка, "
    "сборка, окраска» - нормальное описание, придираться к слову «окраска» "
    "не надо;\n"
    "* отраслевые общие места с оговоркой: «на таких производствах обычно», "
    "«если у вас есть», «часто нужен» - они ничего не утверждают о "
    "конкретной компании;\n"
    "* рассказ о НАШЕМ товаре (компрессоры, генераторы азота и кислорода, "
    "пневмоаудит) - его на сайте получателя быть и не должно;\n"
    "* вежливость, приветствие, подпись, просьба перенаправить;\n"
    "* сайт пустой или не открылся - тогда verdict = 'нечем проверить'.\n\n"
    "Сомневаешься - ставь 'годно'. Письмо, снятое зря, стоит дороже "
    "пропущенной мелочи.\n\n"
    "ОТВЕТ - СТРОГО JSON без текста вокруг:\n"
    '{"pisma":[{"id":N,"verdict":"годно|не годно|нечем проверить",'
    '"pretenzii":["одной фразой, с цитатой из письма"]}]}')


def в_punycode(url: str) -> str:
    """Кириллический домен — в punycode. Иначе запрос не уходит вовсе.

    urllib кодирует хост в latin-1 и на «вбк-дв.рф» падает
    UnicodeEncodeError. Падение ловится общим except, сайт молча остаётся
    пустым, и рецензент выносит «нечем проверить» — сайт при этом жив.
    Замер 18.08: 60 писем из 147 «нечем проверить» — ровно домены на .рф.
    """
    from urllib.parse import urlsplit, urlunsplit
    try:
        ч = urlsplit(url)
        хост = ч.hostname or ""
        хост.encode("ascii")
        return url
    except UnicodeEncodeError:
        pass
    except Exception:                                           # noqa: BLE001
        return url
    try:
        пуни = хост.encode("idna").decode("ascii")
    except Exception:                                           # noqa: BLE001
        return url
    порт = f":{ч.port}" if ч.port else ""
    return urlunsplit((ч.scheme, пуни + порт, ч.path, ч.query, ч.fragment))


def взять(url, таймаут=25):
    url = в_punycode(url)
    try:
        r = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(r, timeout=таймаут) as o:
            b = o.read(2_000_000)
            if o.headers.get("Content-Encoding") == "gzip":
                b = gzip.decompress(b)
            return b.decode("utf-8", "replace")
    except Exception:                                           # noqa: BLE001
        return ""


def сайт(база):
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
                r"katalog|catalog|oborud|tehn)", u) and u not in ссылки:
            ссылки.append(u.split("#")[0])
    куски = [сыро] + [взять(u, 18) for u in ссылки[:6]]
    т = " ".join(куски)
    т = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", т)
    т = re.sub(r"<[^>]+>", " ", т)
    return re.sub(r"\s+", " ", т)[:ЗНАКОВ_САЙТА]


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# Уже отрецензированные пропускаем - прогон резюмируемый. Исключение:
# «нечем проверить» это не вердикт о письме, а признание, что сайт не
# открылся. С аргументом --перечитать-непроверенные такие письма берём
# заново: 18.08 выяснилось, что 60 из 147 - домены на .рф, до которых
# запрос вообще не уходил (UnicodeEncodeError внутри urllib).
ПЕРЕЧИТАТЬ = "--перечитать-непроверенные" in sys.argv
# После перегенерации письмо ДРУГОЕ, и старый вердикт к нему не относится.
ПЕРЕЧИТАТЬ_БРАК = "--перечитать-брак" in sys.argv
# «сбой рецензии» - это не вердикт о письме, а молчание модели: пачка упала
# на разборе JSON. 18.08 таких набралось 20 из 1213, и они висели в очереди
# наравне с настоящим браком.
ПЕРЕЧИТАТЬ_СБОИ = "--перечитать-сбои" in sys.argv
готово = set()
неproverennye = set()
брак = set()
сбои = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
            готово.add(int(z.get("id")))
            в = str(z.get("verdict") or "")
            if в == "нечем проверить":
                неproverennye.add(int(z.get("id")))
            else:
                неproverennye.discard(int(z.get("id")))
            if в == "не годно":
                брак.add(int(z.get("id")))
            else:
                брак.discard(int(z.get("id")))
            if в == "сбой рецензии":
                сбои.add(int(z.get("id")))
            else:
                сбои.discard(int(z.get("id")))
        except Exception:                                       # noqa: BLE001
            pass
if ПЕРЕЧИТАТЬ:
    готово -= неproverennye
    print(f"перечитываю «нечем проверить»: {len(неproverennye)}")
if ПЕРЕЧИТАТЬ_БРАК:
    готово -= брак
    print(f"перечитываю «не годно» (после перегенерации): {len(брак)}")
if ПЕРЕЧИТАТЬ_СБОИ:
    готово -= сбои
    print(f"перечитываю «сбой рецензии»: {len(сбои)}")

with store._lock:
    строки = store._conn.execute(
        "SELECT id, email, subject, body, panel_json FROM confirm_reviews "
        "WHERE campaign_id=10 AND status='pending' AND id BETWEEN ? AND ? "
        "ORDER BY id DESC", (ОТ_ID, ДО_ID)).fetchall()
работа = [r for r in строки if r[0] not in готово][:СКОЛЬКО]
print(f"писем к рецензии: {len(работа)} (уже готово {len(готово)})")
if not работа:
    raise SystemExit(0)


def подготовить(row):
    rid, email, subj, body, pj = row
    try:
        p = json.loads(pj or "{}")
    except Exception:                                           # noqa: BLE001
        p = {}
    comp = p.get("company") if isinstance(p.get("company"), dict) else {}
    full = p.get("company_full") if isinstance(p.get("company_full"), dict) else {}
    enr = (full.get("enrich") or {}) if isinstance(full.get("enrich"), dict) else {}
    ec = (enr.get("company") or {}) if isinstance(enr.get("company"), dict) else {}
    url = str(ec.get("site") or ec.get("domain") or comp.get("site") or "").strip()
    return {"id": rid, "фирма": comp.get("name") or "", "email": email,
            "оквэд": str(comp.get("okved") or ""), "url": url,
            "тема": subj or "", "тело": body or "", "сайт": сайт(url)}


СТАРТ = time.time()
with ThreadPoolExecutor(max_workers=ПОТОКОВ_САЙТ) as pool:
    готовые = list(pool.map(подготовить, работа))
print(f"сайты сняты за {time.time() - СТАРТ:.0f}с; "
      f"с текстом {sum(1 for г in готовые if г['сайт'])} из {len(готовые)}")

замок = __import__("threading").Lock()


def в_журнал(строки_):
    with замок:
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            for z in строки_:
                f.write(json.dumps(z, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def рецензия(пачка):
    куски = []
    for г in пачка:
        куски.append(
            f"=== ПИСЬМО id={г['id']} ===\n"
            f"КОМПАНИЯ: {г['фирма']} · ОКВЭД {г['оквэд']}\n"
            f"ТЕМА: {г['тема']}\n{г['тело']}\n"
            f"--- ТЕКСТ САЙТА ({г['url'] or 'сайта нет'}) ---\n"
            f"{г['сайт'] or '(сайт не открылся)'}\n")
    try:
        # СИСТЕМУ НАДО ПЕРЕДАТЬ. Пилот 18.08 упал весь до одного письма
        # («сбой рецензии» 20 из 20) ровно потому, что я собрал инструкцию в
        # СИСТЕМА и не отдал её: модель получила голые письма без задания и
        # ответила прозой вместо JSON.
        #
        # GP.call системы не принимает, поэтому зовём _raw_stream напрямую -
        # он же кладёт инструкцию в поле system с cache_control, и на пачках
        # она читается из кэша, а не оплачивается заново.
        m = GP._raw_stream([{"role": "user", "content": "\n".join(куски)}],
                           "claude-opus-4-8", 3000, thinking=False,
                           system=СИСТЕМА)
        т = m if isinstance(m, str) else "".join(
            getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        j = re.search(r"\{.*\}", т, re.S)
        d = json.loads(j.group(0)) if j else {}
        вышло = {int(x["id"]): x for x in (d.get("pisma") or [])
                 if str(x.get("id", "")).isdigit()}
    except Exception as ex:                                     # noqa: BLE001
        вышло = {}
        print(f"  пачка упала: {type(ex).__name__} {str(ex)[:110]}")
    строки_ = []
    for г in пачка:
        v = вышло.get(г["id"]) or {}
        строки_.append({"id": г["id"], "фирма": г["фирма"], "url": г["url"],
                        "сайт_знаков": len(г["сайт"]),
                        "verdict": v.get("verdict") or "сбой рецензии",
                        "pretenzii": v.get("pretenzii") or []})
    в_журнал(строки_)
    return строки_


пачки = [готовые[i:i + ПАЧКА] for i in range(0, len(готовые), ПАЧКА)]
with ThreadPoolExecutor(max_workers=ПОТОКОВ_МОДЕЛЬ) as pool:
    итоги = [s for часть in pool.map(рецензия, пачки) for s in часть]

из_них = {}
for s in итоги:
    из_них[s["verdict"]] = из_них.get(s["verdict"], 0) + 1
print(f"\nрецензий: {len(итоги)} за {time.time() - СТАРТ:.0f}с")
for k, n in sorted(из_них.items(), key=lambda x: -x[1]):
    print(f"  {k:<20} {n}")
print("\nпретензии (первые 20):")
n = 0
for s in итоги:
    if s["verdict"] == "не годно" and n < 20:
        n += 1
        print(f"  #{s['id']} {s['фирма'][:34]:<36} {'; '.join(s['pretenzii'])[:110]}")
print(f"\nжурнал: {ЖУРНАЛ}")
