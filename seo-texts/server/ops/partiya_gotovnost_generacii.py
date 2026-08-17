# -*- coding: utf-8 -*-
"""Всё ли доехало, чтобы написать ПОЛНОЦЕННОЕ письмо новым компаниям группы.

Вопрос владельца после заливки: группа «Партия 935» выросла с 920 до 6 892
получателей - хватает ли у них данных на письмо, или половина уйдёт в брак.

Считаем ДВЕ вещи разом.

1. ВОРОНКА ГЕНЕРАЦИИ - ровно та, что в ops/partiya_gen.py: ИНН и почта,
   дубль по ИНН, письмо уже есть в журнале, исчерпанные попытки, заслон
   (стоп-лист, мёртвый адрес, контакт моложе 90 дней). На выходе - сколько
   писем реально можно сделать сейчас.

2. ПОЛНОТА КАРТОЧКИ у тех, кто дошёл до генерации. Письмо без ОКВЭДа и без
   описания деятельности выходит общим («сжатый воздух нужен всем») и
   бракуется гейтом; без направления оно не знает, про какой товар писать.
   Поэтому меряем каждое поле отдельно, а не «карточка есть/нет».

Отчёт целиком уходит на дроп: в стандартный вывод задания не влезает.

    python zapusk_svoego_skripta.py ops/partiya_gotovnost_generacii.py
"""
import io
import json
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ИМЯ = "GOTOVNOST-GENERACII.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

С = []
примеры = {}


def п(s=""):
    С.append(s)


def пример(вид, строка):
    примеры.setdefault(вид, [])
    if len(примеры[вид]) < 6:
        примеры[вид].append(строка)


# --- журнал: кому письмо уже написано ------------------------------------- #
сделано_инн, попыток_инн = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                       # noqa: BLE001
            continue
        inn = str(z.get("inn") or "")
        if not inn:
            continue
        if z.get("этап") != "итог":
            попыток_инн[inn] += 1
        if z.get("ок") or z.get("тело"):
            сделано_инн.add(inn)

# --- воронка -------------------------------------------------------------- #
группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)

счёт = Counter()
готовые = []
видели_инн = set()
for rid in в_группе:
    r = store.get_recipient(rid)
    if not r:
        счёт["строка пропала из базы"] += 1
        continue
    inn = "".join(c for c in str(getattr(r, "inn", "") or "") if c.isdigit())
    email = str(getattr(r, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        пример("без ИНН или почты", f"{getattr(r, 'company_name', '')} "
                                    f"| ИНН {inn!r} | {email!r}")
        continue
    if inn in видели_инн:
        счёт["вторая строка той же фирмы"] += 1
        continue
    видели_инн.add(inn)
    if inn in сделано_инн:
        счёт["письмо уже написано"] += 1
        continue
    if попыток_инн[inn] >= 3:
        счёт["исчерпал три попытки"] += 1
        continue
    причина = cs._guard(inn=inn, email=email)
    if причина:
        ключ = f"заслон: {причина.split(':')[0]}"
        счёт[ключ] += 1
        пример(ключ, f"{getattr(r, 'company_name', '')} | {email} | {причина[:60]}")
        continue
    готовые.append(r)

счёт["ГОТОВЫ К ГЕНЕРАЦИИ"] = len(готовые)

# --- полнота данных у готовых --------------------------------------------- #
полнота = Counter()
for r in готовые:
    try:
        ex = json.loads(getattr(r, "extra_json", "") or "{}")
    except Exception:                                           # noqa: BLE001
        ex = {}
    оквэд = str(getattr(r, "okved", "") or "").strip()
    деятельность = str(ex.get("activity") or ex.get("profile") or "").strip()
    имя_фирмы = str(getattr(r, "company_name", "") or "").strip()
    сегмент = str(getattr(r, "segment", "") or "").strip()
    напр_карточки = str(ex.get("division") or "").strip()

    полнота["есть название компании"] += bool(имя_фирмы)
    полнота["есть ОКВЭД"] += bool(оквэд)
    полнота["есть описание деятельности"] += bool(деятельность)
    полнота["есть ОКВЭД ИЛИ описание"] += bool(оквэд or деятельность)
    полнота["НЕТ НИ ОКВЭДА, НИ ОПИСАНИЯ"] += not (оквэд or деятельность)
    полнота["есть сегмент (партия)"] += bool(сегмент)
    полнота["есть направление в extra"] += bool(напр_карточки)
    полнота["есть контактное имя"] += bool(
        str(getattr(r, "contact_name", "") or "").strip())
    полнота["есть роль ящика"] += bool(str(ex.get("role") or "").strip())
    полнота["адрес проверен (valid_status=valid)"] += (
        str(getattr(r, "valid_status", "") or "") == "valid")
    полнота["регион известен"] += bool(str(getattr(r, "region", "") or "").strip())
    if not (оквэд or деятельность):
        пример("нечего писать: нет профиля",
               f"{имя_фирмы} | {getattr(r, 'email', '')}")

# --- отчёт ---------------------------------------------------------------- #
п("# Готовность партии 935 к генерации")
п()
п(f"Группа «{ГРУППА}»: **{len(в_группе)}** строк получателей, "
  f"уникальных компаний по ИНН **{len(видели_инн)}**.")
п()
п("## Воронка (та же, что в ops/partiya_gen.py)")
п()
for k, n in счёт.most_common():
    п(f"- {k}: **{n}**")
п()
п("## Полнота данных у тех, кто дошёл до генерации")
п()
if готовые:
    for k, n in полнота.most_common():
        п(f"- {k}: **{n}** из {len(готовые)} "
          f"({100.0 * n / len(готовые):.0f}%)")
else:
    п("- генерировать некого, считать нечего")
п()
for вид, строки in примеры.items():
    п(f"## Примеры: {вид}")
    п()
    for s in строки:
        п(f"- {s}")
    п()

текст = "\n".join(С) + "\n"
try:
    with io.open(ОТЧЁТ, "w", encoding="utf-8") as f:
        f.write(текст)
    rq = urllib.request.Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with urllib.request.urlopen(rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                         # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

print(f"в группе {len(в_группе)} строк | компаний {len(видели_инн)}")
for k, n in счёт.most_common():
    print(f"  {k:<38} {n}")
print("--- полнота у готовых ---")
for k, n in полнота.most_common():
    print(f"  {k:<42} {n}")
