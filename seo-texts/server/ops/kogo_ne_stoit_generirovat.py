# -*- coding: utf-8 -*-
"""По каким признакам ВИДНО ЗАРАНЕЕ, что письмо забракуют.

Владелец: «которым заслон всё равно откажет - как определить можно?».
Отвечать надо не рассуждением, а долей брака по признакам, которые есть
ДО генерации. Считаем по накопленным исходам: 1300+ писем партии, у
каждого известен финал.

Исход письма (худший из двух рубежей):
  «брак генерации»  - конвейер не выпустил письмо вовсе (гейт, линза,
                      верификатор, анти-штамп) - оплачено, результата нет;
  «не годно»        - письмо вышло, но рецензент по сайту его снял;
  «годно»           - дошло до очереди и подтверждено сайтом.

Признаки берём только те, что известны ДО первого вызова модели:
  * есть ли собранный текст сайта и сколько его;
  * есть ли на сайте хоть одно цеховое слово (тот же список, которым
    механический гейт ловит выдуманные процессы);
  * класс ОКВЭД (две первые цифры).

Печатаем долю брака и объём по каждому ведру: отсекать имеет смысл только
там, где брак высокий И компаний много.
"""
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import _ПРОЦЕССЫ_ПИСЬМА                    # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ГЕН = r"C:\sender\_ops\gen-partiya-935.jsonl"
ENRICH = r"C:\sender\enrich.db"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- исход по ИНН ---------------------------------------------------------
исход = {}
брак_причина = {}
for s in io.open(ГЕН, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    inn = str(z.get("inn") or "")
    if not inn or z.get("этап") == "отмена_попытки":
        continue
    if z.get("ок") or z.get("тело"):
        исход[inn] = "дошло"
    else:
        исход.setdefault(inn, "брак генерации")
        брак_причина.setdefault(inn, (z.get("брак") or [""])[0])

# вердикт рецензента - поверх, по ИНН письма
верд_по_инн = {}
верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass
with store._lock:
    for rid, inn in store._conn.execute(
            "SELECT id, COALESCE(inn,'') FROM confirm_reviews "
            "WHERE campaign_id IN (10,11)").fetchall():
        в = верд.get(int(rid))
        if в:
            верд_по_инн[str(inn)] = в
for inn, в in верд_по_инн.items():
    if в == "годно":
        исход[inn] = "годно"
    elif в == "не годно":
        исход[inn] = "не годно"

# --- признаки, известные ДО генерации -------------------------------------
сайт = {}
try:
    con = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True, timeout=20)
    for inn, chars, txt in con.execute(
            "SELECT inn, chars, substr(text,1,20000) FROM site_text"):
        t = (txt or "").lower()
        сайт[str(inn)] = (int(chars or 0),
                          any(сл in t for сл in _ПРОЦЕССЫ_ПИСЬМА))
    con.close()
except Exception as ex:                                          # noqa: BLE001
    print("site_text не прочитан:", str(ex)[:100])

оквэд = {}
with store._lock:
    for inn, ок in store._conn.execute(
            "SELECT COALESCE(inn,''), COALESCE(okved,'') FROM recipients"):
        if inn:
            оквэд.setdefault(str(inn), str(ок))


def _ведро_сайта(inn):
    ч, _ = сайт.get(inn, (0, False))
    if ч == 0:
        return "сайта нет вовсе"
    if ч < 500:
        return "сайт до 500 знаков"
    if ч < 2000:
        return "сайт 500-2000"
    return "сайт больше 2000"


def _разрез(имя, ключ):
    вед = defaultdict(Counter)
    for inn, и in исход.items():
        вед[ключ(inn)][и] += 1
    print(f"\n{имя}:")
    print(f"  {'ведро':<24} {'решено':>6} {'годно':>6} {'не годно':>9} "
          f"{'брак ген':>9} {'мимо, %':>8}")
    for к, c in sorted(вед.items(), key=lambda x: -sum(x[1].values())):
        # ЗНАМЕНАТЕЛЬ - ТОЛЬКО РЕШЁННЫЕ. «дошло» значит, что письмо вышло, но
        # рецензент до него не добрался: считать его удачей нельзя, а класть
        # в знаменатель - значит развести долю брака водой. Первый прогон
        # этого замера так и сделал и показал по компаниям без сайта 41%
        # вместо настоящих 88%.
        решено = c["годно"] + c["не годно"] + c["брак генерации"]
        мимо = c["не годно"] + c["брак генерации"]
        if решено < 15:
            continue
        print(f"  {str(к):<24} {решено:>6} {c['годно']:>6} "
              f"{c['не годно']:>9} {c['брак генерации']:>9} "
              f"{100.0 * мимо / решено:>7.0f}% "
              f"(ждут рецензии {c['дошло']})")


print(f"компаний с известным исходом: {len(исход)}")
print("исходы:", dict(Counter(исход.values())))
_разрез("по тексту сайта", _ведро_сайта)
_разрез("по цеховым словам на сайте",
        lambda inn: ("цеховые слова есть" if сайт.get(inn, (0, False))[1]
                     else ("цеховых слов нет" if сайт.get(inn)
                           else "сайта нет вовсе")))
_разрез("по классу ОКВЭД",
        lambda inn: (оквэд.get(inn, "")[:2] or "?"))
