# -*- coding: utf-8 -*-
"""Проверка предфильтра вслепую: ловит ли он брак ДО генерации.

Идея: перед тем как платить $0.16 за полный круг генерации, задать один
дешёвый вопрос модели попроще - «по тексту сайта, есть ли у этой компании
производство или участок, где нужен сжатый воздух». Если предфильтр
надёжно отсеивает тех, кого потом снимет рецензент, он окупается в
тридцать раз.

ЧЕСТНОСТЬ ЗАМЕРА. Модель видит ТОЛЬКО то, что известно до генерации:
название, ОКВЭД, вид деятельности и текст сайта. Ни письма, ни вердикта
рецензента она не видит. Сравнение с фактом делается уже в коде.

ВЫБОРКА СТРАТИФИЦИРОВАНА: 50 «не годно» и 50 «годно». В жизни брака ~18%,
и случайная сотня дала бы 18 бракованных - слишком мало, чтобы измерить
ловлю. Стратификация даёт точность по обеим ошибкам, но доли надо потом
пересчитывать на реальную смесь, а не читать как есть.

ЧЕГО ПРЕДФИЛЬТР НЕ МОЖЕТ В ПРИНЦИПЕ: «не годно» бывает двух родов - не тот
адресат (это он поймать обязан) и выдумка в письме о верном адресате (это
про текст, и знать этого заранее нельзя). Поэтому потолок его ловли ниже
100% by design, и низкая цифра сама по себе приговором ему не будет.

Журнал durable на сервере.

    python zapusk_svoego_skripta.py ops/predfiltr_proverka.py 100
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "100"))
МОДЕЛЬ = os.environ.get("GEN_CHECKER_MODEL", "claude-sonnet-4-6")
ЖУРНАЛ = r"C:\sender\_ops\predfiltr-proverka.jsonl"
РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ENRICH = r"C:\sender\enrich.db"
ПАЧКА = 4
ЗНАКОВ_САЙТА = 2500

СИСТЕМА = (
    "Ты отбираешь компании для холодного письма от поставщика ПРОМЫШЛЕННЫХ "
    "КОМПРЕССОРОВ и генераторов азота/кислорода.\n\n"
    "Тебе дают карточку компании: название, ОКВЭД, вид деятельности и текст "
    "её сайта. Письма ещё нет - решай только по компании.\n\n"
    "ВОПРОС ОДИН: есть ли у этой компании СВОЙ производственный участок, "
    "цех, линия или парк техники, где сжатый воздух реально нужен?\n\n"
    "ГОДЕН: производство любого рода, обработка, сборка, литьё, покраска, "
    "фасовка, розлив, деревообработка, пищевое производство, ремонтные и "
    "монтажные базы со своим цехом, добыча, дорожная и строительная техника "
    "со своим парком.\n"
    "НЕ ГОДЕН: чистая торговля и дистрибуция без своего цеха, "
    "проектирование и консалтинг, IT, аренда помещений, оценка и "
    "недвижимость, медицина и диагностика без своего производства, "
    "образование, транспортная экспедиция без своей ремонтной базы, "
    "управляющие компании.\n\n"
    "СУДИ ПО САЙТУ, А НЕ ПО ОКВЭД: код в России сплошь и рядом формален. "
    "Если сайт молчит о деятельности вовсе - ставь \"неясно\", это не "
    "приговор.\n\n"
    "Ответь СТРОГО JSON без пояснений вокруг:\n"
    "{\"kompanii\": [{\"id\": 1, \"verdikt\": \"годен|не годен|неясно\", "
    "\"pochemu\": \"до 15 слов\"}]}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- факт: последний вердикт рецензента, привязанный к ИНН ----------------
верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass
факт = {}
with store._lock:
    for rid, inn in store._conn.execute(
            "SELECT id, COALESCE(inn,'') FROM confirm_reviews "
            "WHERE campaign_id IN (10,11)").fetchall():
        в = верд.get(int(rid))
        if в in ("годно", "не годно") and inn:
            факт[str(inn)] = в

# --- карточки: только то, что известно ДО генерации -----------------------
сайты = {}
con = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True, timeout=20)
for inn, txt in con.execute(
        "SELECT inn, substr(text,1,%d) FROM site_text WHERE chars>200"
        % (ЗНАКОВ_САЙТА * 2)):
    сайты[str(inn)] = (txt or "")[:ЗНАКОВ_САЙТА]
con.close()

карточки = {}
with store._lock:
    for inn, имя, ок, деят in store._conn.execute(
            "SELECT COALESCE(inn,''), COALESCE(company_name,''), "
            "COALESCE(okved,''), COALESCE(extra_json,'') FROM recipients"):
        if inn and str(inn) not in карточки:
            # ВИД ДЕЯТЕЛЬНОСТИ живёт в extra_json, отдельной колонки нет.
            try:
                _e = json.loads(деят or "{}")
            except Exception:                                    # noqa: BLE001
                _e = {}
            карточки[str(inn)] = (
                имя, ок,
                str(_e.get("activity") or _e.get("вид_деятельности") or ""))

годные = sorted(i for i, в in факт.items() if в == "годно" and i in сайты)
брак = sorted(i for i, в in факт.items() if в == "не годно" and i in сайты)
пол = СКОЛЬКО // 2
def _шаг(список, n):
    """n штук равномерно по всему списку, а не первые подряд: ИНН
    отсортированы, и первые полсотни - это один регион и один срез базы."""
    if not список:
        return []
    шаг = max(1, len(список) // max(1, n))
    return [список[i] for i in range(0, len(список), шаг)][:n]


выборка = [(i, "не годно") for i in _шаг(брак, пол)] + \
          [(i, "годно") for i in _шаг(годные, пол)]
print(f"фактов: годно {len(годные)}, не годно {len(брак)} (с текстом сайта)")
print(f"в выборке: {len(выборка)}")

замок = __import__("threading").Lock()
ответы = {}


def _пачка(пачка):
    куски = []
    for n, (inn, _) in enumerate(пачка, 1):
        имя, ок, деят = карточки.get(inn, ("", "", ""))
        куски.append(f"=== КОМПАНИЯ id={n}\nНАЗВАНИЕ: {имя}\n"
                     f"ОКВЭД: {ок}\nВИД ДЕЯТЕЛЬНОСТИ: {деят or '-'}\n"
                     f"ТЕКСТ САЙТА:\n{сайты.get(inn, '')}\n")
    try:
        m = GP._raw_stream([{"role": "user", "content": "\n".join(куски)}],
                           МОДЕЛЬ, 1200, thinking=False, system=СИСТЕМА)
        т = m if isinstance(m, str) else "".join(
            getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        j = re.search(r"\{.*\}", т, re.S)
        d = json.loads(j.group(0)) if j else {}
        вышло = {int(x["id"]): x for x in (d.get("kompanii") or [])
                 if str(x.get("id", "")).isdigit()}
        u = getattr(m, "usage", None)
        расход = (int(getattr(u, "input_tokens", 0) or 0),
                  int(getattr(u, "cache_creation_input_tokens", 0) or 0),
                  int(getattr(u, "cache_read_input_tokens", 0) or 0),
                  int(getattr(u, "output_tokens", 0) or 0))
    except Exception as ex:                                      # noqa: BLE001
        print(f"  пачка упала: {type(ex).__name__} {str(ex)[:100]}")
        вышло, расход = {}, (0, 0, 0, 0)
    строки = []
    for n, (inn, ф) in enumerate(пачка, 1):
        v = вышло.get(n) or {}
        строки.append({"inn": inn, "имя": карточки.get(inn, ("",))[0],
                       "факт": ф, "предфильтр": v.get("verdikt") or "сбой",
                       "почему": v.get("pochemu") or ""})
    with замок:
        for з in строки:
            ответы[з["inn"]] = з
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            for з in строки:
                f.write(json.dumps(з, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    return расход


t0 = time.time()
пачки = [выборка[i:i + ПАЧКА] for i in range(0, len(выборка), ПАЧКА)]
with ThreadPoolExecutor(max_workers=8) as pool:
    расходы = list(pool.map(_пачка, пачки))
вх = sum(r[0] for r in расходы); cw = sum(r[1] for r in расходы)
cr = sum(r[2] for r in расходы); вых = sum(r[3] for r in расходы)
цена = (вх + 1.25 * cw + 0.10 * cr) / 1e6 * 3.0 + вых / 1e6 * 15.0

м = Counter()
for inn, ф in выборка:
    з = ответы.get(inn) or {}
    м[(ф, з.get("предфильтр") or "сбой")] += 1

print(f"\nпрогон за {time.time() - t0:.0f}с, цена ${цена:.3f} "
      f"(${цена / max(1, len(выборка)):.4f} на компанию)")
print("\nфакт \\ предфильтр:")
предф = ["годен", "неясно", "не годен", "сбой"]
print(f"  {'факт':<10} " + " ".join(f"{p:>9}" for p in предф))
for ф in ("годно", "не годно"):
    print(f"  {ф:<10} " + " ".join(f"{м[(ф, p)]:>9}" for p in предф))

поймал = м[("не годно", "не годен")]
всего_брака = sum(м[("не годно", p)] for p in предф)
зря = м[("годно", "не годен")]
всего_годных = sum(м[("годно", p)] for p in предф)
print(f"\nловит брака: {поймал} из {всего_брака} "
      f"({100.0 * поймал / max(1, всего_брака):.0f}%)")
print(f"рубит годных зря: {зря} из {всего_годных} "
      f"({100.0 * зря / max(1, всего_годных):.0f}%)")
print("\nпримеры пойманного брака:")
for inn, ф in выборка:
    з = ответы.get(inn) or {}
    if ф == "не годно" and з.get("предфильтр") == "не годен":
        print(f"  {з.get('имя', '')[:40]:<42} {з.get('почему', '')[:60]}")
print("\nпримеры зря зарубленных годных:")
for inn, ф in выборка:
    з = ответы.get(inn) or {}
    if ф == "годно" and з.get("предфильтр") == "не годен":
        print(f"  {з.get('имя', '')[:40]:<42} {з.get('почему', '')[:60]}")
