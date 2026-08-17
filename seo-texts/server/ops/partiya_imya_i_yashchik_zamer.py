# -*- coding: utf-8 -*-
"""Сколько именных приветствий срежет сверка имени с ящиком - до выкатки.

Владелец 17.08 сперва «фио ещё бы с именем ящика проверять, и если не
совпадает, резать», потом честно: «нужно ли тут срезать имя.. не знаю».
Решать такое на глаз нельзя - нужна цена правила в письмах.

Считаем по группе «Партия 935» ровно ту цепочку, что стоит в
ai_letter._recipient_block:
  1. имя в карточке есть?
  2. оно ПОЛНОЕ (два слова без инициалов)?
  3. согласуется с левой частью ящика (транслит, сводка написаний)?
  4. если нет - спасает ли второй путь (имя со страницы своего сайта
     со ссылкой)?
  5. и вообще - разрешено ли именное приветствие роли ящика.

Печатаем не только числа, но и живые примеры каждой категории: правило
оценивается по ним, а не по процентам.

Правило здесь ПОВТОРЕНО, а не импортировано, и это осознанно: замер нужен
ДО выкатки, чтобы владелец решал по числам, а не по уже применённой правке.
На сервере лежит ещё старый ai_letter. Если правило поменяется - править
надо оба места; при следующем замере копия сверяется с боевой функцией.

    python zapusk_svoego_skripta.py ops/partiya_imya_i_yashchik_zamer.py
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

# --- копия правила из sender/ai_letter.py --------------------------------- #
_ТРАНСЛИТ = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'iu', 'я': 'ia'}
_СВОДКА = (('kh', 'h'), ('yo', 'e'), ('ya', 'ia'), ('yu', 'iu'),
           ('j', 'i'), ('y', 'i'), ('ie', 'e'), ('ee', 'e'), ('ii', 'i'))
_ПОЛНОЕ_СЛОВО_ИМЕНИ = re.compile(r'^[А-ЯЁ][а-яё]{2,}$')


def _svesti(с):
    т = (с or '').lower()
    for а, б in _СВОДКА:
        т = т.replace(а, б)
    return т


def _translit(с):
    return ''.join(_ТРАНСЛИТ.get(ch, ch) for ch in (с or '').lower())


def _polnoe_imya(kontakt) -> bool:
    слова = [w.strip('.,') for w in str(kontakt or '').split() if w.strip('.,')]
    return sum(1 for w in слова if _ПОЛНОЕ_СЛОВО_ИМЕНИ.match(w)) >= 2


def _imya_soglasuetsya_s_yashchikom(kontakt, email) -> bool:
    имя = str(kontakt or '').strip()
    почта = str(email or '').strip().lower()
    if not имя or '@' not in почта:
        return False
    левая = _svesti(re.sub(r'[^a-z0-9]', '', почта.split('@')[0]))
    if not левая:
        return False
    for слово in re.findall(r'[А-Яа-яЁё]+', имя):
        if len(слово) >= 4 and _svesti(_translit(слово)) in левая:
            return True
    return False

ГРУППА = "Партия 935"
ИМЯ = "IMYA-I-YASHCHIK.md"
ОТЧЁТ = r"C:\sender\_ops" + "\\" + ИМЯ
ОБЩИЕ_РОЛИ = ("приёмная", "общий", "бухгалтерия")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

С = []
примеры = {}


def п(s=""):
    С.append(s)


def пример(вид, строка):
    примеры.setdefault(вид, [])
    if len(примеры[вид]) < 8:
        примеры[вид].append(строка)


группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)

счёт = Counter()
for rid in в_группе:
    r = store.get_recipient(rid)
    if not r:
        continue
    счёт["всего строк"] += 1
    имя = str(getattr(r, "contact_name", "") or "").strip()
    почта = str(getattr(r, "email", "") or "").strip()
    try:
        ex = json.loads(getattr(r, "extra_json", "") or "{}")
    except Exception:                                           # noqa: BLE001
        ex = {}
    роль = str(ex.get("role") or "").strip().lower()
    источник = str(ex.get("contact_source") or "").strip().lower()
    ссылка = str(ex.get("contact_source_url") or "").strip()
    свой_сайт_путь = bool(ссылка) and источник.startswith(
        ("own-site", "enrich", "mass", "panel-run", "recheck", "zenno"))

    if not имя:
        счёт["без имени (и раньше здоровались безлично)"] += 1
        continue
    счёт["имя в карточке есть"] += 1
    if not _polnoe_imya(имя):
        счёт["имя неполное - резалось и ДО правки"] += 1
        пример("неполное имя", f"{имя!r} -> {почта}")
        continue
    счёт["имя полное"] += 1
    согласуется = _imya_soglasuetsya_s_yashchikom(имя, почта)
    if согласуется:
        счёт["ящик подтверждает имя - приветствие остаётся"] += 1
        пример("ящик подтверждает", f"{имя!r} -> {почта}")
        continue
    if свой_сайт_путь:
        счёт["ящик молчит, но спасает свой сайт со ссылкой"] += 1
        пример("спасает сайт", f"{имя!r} -> {почта} | {ссылка[:60]}")
        continue
    if роль in ОБЩИЕ_РОЛИ:
        счёт["ящик молчит, но роль общая - резалось и ДО правки"] += 1
        пример("общая роль", f"{имя!r} -> {почта} | роль {роль}")
        continue
    счёт["ЦЕНА ПРАВКИ: имя срежется только из-за ящика"] += 1
    пример("срежется", f"{имя!r} -> {почта} | роль {роль or 'нет'}")

п("# Сверка имени с ящиком: цена правила в письмах")
п()
п(f"Группа «{ГРУППА}», считано по той же цепочке, что в генерации.")
п()
for k, n in счёт.most_common():
    п(f"- {k}: **{n}**")
п()
цена = счёт["ЦЕНА ПРАВКИ: имя срежется только из-за ящика"]
оставим = счёт["ящик подтверждает имя - приветствие остаётся"] + счёт[
    "ящик молчит, но спасает свой сайт со ссылкой"]
п(f"Итого именных приветствий: было бы **{оставим + цена}**, "
  f"останется **{оставим}**, срежется **{цена}**.")
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
    rq = __import__("urllib.request", fromlist=["request"]).Request(
        os.environ["DROP_URL"].rstrip("/") + "/" + ИМЯ,
        data=текст.encode("utf-8"), method="PUT",
        headers={"X-Drop-Token": os.environ["DROP_TOKEN"]})
    with __import__("urllib.request", fromlist=["request"]).urlopen(
            rq, timeout=120) as rp:
        rp.read()
    print(f"отчёт на дропе: {ИМЯ}")
except Exception as ex:                                         # noqa: BLE001
    print("отчёт на дроп не уехал:", str(ex)[:200])

for k, n in счёт.most_common():
    print(f"  {k:<52} {n}")
print(f"именных приветствий: было бы {оставим + цена}, останется {оставим}, "
      f"срежется {цена}")
