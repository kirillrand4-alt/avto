#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Слияние двух словарей компрессорного оборудования в один.

Вход (три файла с дропа):
  1. PARK-SLOVAR-PROKOMPRESSOR.csv      — каталог владельца (brend;model;istochnik).
     Это то, что владелец ПРОДАЁТ: импорт и новая техника. Поле model — полное
     торговое название («Винтовой компрессор ABAC FORMULA 11-10»), а не голое
     обозначение, поэтому обозначение из него ВЫРЕЗАЕТСЯ (см. obozn_iz_modeli).
  2. PARK-SLOVAR-SERII-3S.csv           — серии из разбора документов (ЭПБ, закупки).
  3. PARK-SLOVAR-SERII-PROVERIT-3S.csv  — то же, но вид машины не установлен.
     Это то, что у заводов СТОИТ.

Выход: PARK-SLOVAR-EDINYY.csv, колонки
  oboznachenie;vid_zapisi;brend;princip;vid_mashiny;istochnik;vstrech;innov;ssylok
  vid_zapisi = «модель каталога» | «серия из документов».

Плюс отчёт о пересечении: нормализованное сравнение (верхний регистр, без
пробелов, дефисов и кавычек), 10 примеров совпавших пар в исходном виде.

Запуск:
  python3 p25_slovar_sliyanie.py --katalog PARK-SLOVAR-PROKOMPRESSOR.csv \
      --serii PARK-SLOVAR-SERII-3S.csv --proverit PARK-SLOVAR-SERII-PROVERIT-3S.csv \
      --vyhod PARK-SLOVAR-EDINYY.csv
"""

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict

VYHOD_POLYA = [
    "oboznachenie", "vid_zapisi", "brend", "princip",
    "vid_mashiny", "istochnik", "vstrech", "innov", "ssylok",
]

# --- лексикон ведущих слов-типов каталога (только кириллица, без цифр) -------
# Собран по частотам первых слов в поле model: это описание ТИПА машины,
# а не обозначение. Вырезается только с НАЧАЛА строки и только по белому списку.
TIPOVYE_SLOVA = {
    "компрессор", "компрессорная", "компрессорный", "станция", "винтовой", "винтовая",
    "поршневой", "поршневая", "спиральный", "спиральная", "дизельный", "дизельная",
    "бензиновый", "электрический", "роторная", "роторный", "двухступенчатый",
    "двухступенчатая", "одноступенчатый", "безмасляный", "безмасляная", "масляный",
    "передвижной", "передвижная", "стационарный", "стационарная", "воздуходувка",
    "осушитель", "осушительный", "рефрижераторный", "рефрижераторная", "адсорбционный",
    "адсорбционная", "фильтр", "фильтра", "фильтрующий", "магистральный",
    "магистрального", "магистральная", "воздушный", "воздушного", "картридж",
    "сепаратор", "сепарационный", "циклонный", "циклонная", "центробежный",
    "центробежная", "влагомаслоотделитель", "масловлагоотделитель",
    "масловлагоразделитель", "влагоотделитель", "влагосепаратор", "ресивер",
    "вертикальный", "горизонтальный", "угольная", "угольный", "колонна", "концевой",
    "охладитель", "доохладитель", "модуль", "очистки", "сжатого", "воздуха", "воздух",
    "бустер", "дожимной", "дожимная", "высокого", "низкого", "среднего", "давления",
    "конденсатоотводчик", "блок", "комплект", "элемент", "корпус", "высокотемпературный",
    "резьбовой", "фланцевый", "теплообменник", "маслоотделитель", "маслоохладитель",
    "генератор", "азота", "кислорода", "мембранный", "адсорбер", "приёмный", "приемный",
}

# --- бренды: псевдонимы, которые надо срезать перед обозначением -------------
# Берутся из колонки brend (slug -> слова) плюс ручные кириллические написания
# и написания, встречающиеся в чужих строках (в строке abac бывает "DALGAKIRAN").
RUCHNYE_BRENDY = [
    "abac", "adicomp", "airman", "airpol", "airrus", "almig", "alup", "ariacom",
    "atlas copco", "atlascopco", "atmos", "atom", "ats", "baysar", "berg", "boge",
    "ceccato", "chicago pneumatic", "coaire", "comaro", "comprag", "cross air",
    "crossair", "dali", "dalgakiran", "das", "dnt", "ekomak", "enger", "et",
    "et compressors", "fiac", "fini", "fubag", "gardner denver", "gc", "global",
    "habe", "hansmann", "harrison", "hori", "ingersoll rand", "ingersoll-rand",
    "ingro", "ironmac", "kaeser", "kraftmachine", "kraftmann", "lupamat", "magnus",
    "mark", "master blast", "omi", "ozen", "paramina", "pneumatech", "remeza",
    "renner", "robuschi", "rkz", "sotras", "souair", "spitzenreiter", "sullair",
    "tamsan", "ultratech", "xeleron", "zammer", "zega", "zif",
    # кириллические написания брендов из поля model
    "абак", "аирпол", "алмиг", "атлас копко", "бежецк", "бежецкий",
    "евразкомпрессор", "зиф", "комаро", "компраг", "ремеза", "ркз", "ркз, airrus",
    "ркз airrus", "айррус", "экомак", "энгер", "озен", "далгакиран",
]

# хвосты, которые не входят в обозначение
HVOST_BAR = re.compile(r"[\s,]*\b\d+(?:[.,]\d+)?\s*бар\b\s*$", re.I)
HVOST_KVT = re.compile(r"[\s,]*\b\d+(?:[.,]\d+)?\s*квт\b\s*$", re.I)
SKOBKI_ORIG = re.compile(r"\(\s*ориг[^)]*\)?\s*$", re.I)
PROBELY = re.compile(r"\s+")


def podgotovit_brendy(katalog_brendy):
    """Множество псевдонимов брендов (в нижнем регистре, по словам)."""
    aliasy = set(RUCHNYE_BRENDY)
    for slug in katalog_brendy:
        aliasy.add(slug.replace("_", " ").lower())
        for kus in slug.split("_"):
            if len(kus) > 2:
                aliasy.add(kus.lower())
    return aliasy


def chistyy_token(t):
    return t.strip(' "\'«»,;:()').lower()


def obozn_iz_modeli(model, aliasy_brendov):
    """Вырезать обозначение из торгового названия каталога.

    Срезается ведущее описание типа (по белому списку кириллических слов),
    затем ведущее имя бренда (по списку псевдонимов, до 3 слов подряд),
    затем хвосты «N бар», «N кВт», «(оригинал…)».
    """
    s = model.strip()
    s = SKOBKI_ORIG.sub("", s).strip()
    s = HVOST_BAR.sub("", s).strip()
    s = HVOST_KVT.sub("", s).strip()

    tokeny = s.split()
    # 1) ведущие слова-типы
    i = 0
    while i < len(tokeny):
        t = chistyy_token(tokeny[i])
        if t in TIPOVYE_SLOVA or t in {"в", "с", "на", "для", "без", "и"}:
            i += 1
            continue
        break
    tokeny = tokeny[i:]

    # 2) ведущее имя бренда (жадно: сначала три слова, потом два, потом одно)
    menyalos = True
    while menyalos and tokeny:
        menyalos = False
        for n in (3, 2, 1):
            if len(tokeny) > n:  # не съедать строку целиком
                kandidat = " ".join(chistyy_token(x) for x in tokeny[:n]).strip()
                if kandidat in aliasy_brendov:
                    tokeny = tokeny[n:]
                    menyalos = True
                    break

    # 3) снова слова-типы (бывает «Pneumatech фильтр магистральный PMH …»)
    i = 0
    while i < len(tokeny) - 1:
        if chistyy_token(tokeny[i]) in TIPOVYE_SLOVA:
            i += 1
            continue
        break
    tokeny = tokeny[i:]

    rez = PROBELY.sub(" ", " ".join(tokeny)).strip(' "\'«»,;:')
    return rez if rez else model.strip()


def vid_iz_modeli(model):
    """Вид машины по торговому названию каталога (грубо, по ключевым словам)."""
    m = model.lower()
    pary = [
        ("воздуходувка", "воздуходувка"),
        ("осушител", "осушитель"),
        ("картридж", "картридж фильтра"),
        ("фильтр", "фильтр"),
        ("сепаратор", "сепаратор"),
        ("влагомаслоотделител", "влагомаслоотделитель"),
        ("масловлагоотделител", "влагомаслоотделитель"),
        ("масловлагоразделител", "влагомаслоотделитель"),
        ("влагосепаратор", "сепаратор"),
        ("ресивер", "ресивер"),
        ("колонна", "адсорбционная колонна"),
        ("охладител", "охладитель"),
        ("конденсатоотводчик", "конденсатоотводчик"),
        ("компрессор", "компрессор"),
        ("бустер", "компрессор"),
        ("генератор азота", "генератор азота"),
        ("генератор кислорода", "генератор кислорода"),
    ]
    for klyuch, vid in pary:
        if klyuch in m:
            return vid
    return "не установлен"


def princip_iz_modeli(model):
    """Принцип действия по торговому названию каталога."""
    m = model.lower()
    if "центробежн" in m or "циклонн" in m:
        # у сепараторов «центробежный» — это принцип отделения, не тип машины,
        # но принцип он и есть принцип; помечаем честно.
        return "центробежный"
    for klyuch, znach in (
        ("винтов", "винтовой"), ("поршнев", "поршневой"),
        ("спиральн", "спиральный"), ("роторн", "роторный"),
        ("мембранн", "мембранный"), ("адсорбцион", "адсорбционный"),
    ):
        if klyuch in m:
            return znach
    return "не установлен"


def normalizovat(s):
    """Ключ сравнения: верхний регистр, без пробелов, дефисов, кавычек и точек-разделителей."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.upper()
    s = re.sub(r"[\s\-–—_«»\"'`’]+", "", s)
    return s


# кириллица -> латиница для омоглифов (вторая, справочная нормализация)
OMOGLIFY = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")


def normalizovat_omo(s):
    return normalizovat(s).translate(OMOGLIFY)


def chitat(put, polya=None):
    with open(put, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--katalog", default="PARK-SLOVAR-PROKOMPRESSOR.csv")
    p.add_argument("--serii", default="PARK-SLOVAR-SERII-3S.csv")
    p.add_argument("--proverit", default="PARK-SLOVAR-SERII-PROVERIT-3S.csv")
    p.add_argument("--vyhod", default="PARK-SLOVAR-EDINYY.csv")
    p.add_argument("--primerov", type=int, default=10)
    args = p.parse_args()

    katalog = chitat(args.katalog)
    serii = chitat(args.serii)
    proverit = chitat(args.proverit)

    aliasy = podgotovit_brendy({r["brend"] for r in katalog})

    stroki = []
    # --- каталог ---------------------------------------------------------
    for r in katalog:
        model = (r.get("model") or "").strip()
        ob = obozn_iz_modeli(model, aliasy)
        stroki.append({
            "oboznachenie": ob,
            "vid_zapisi": "модель каталога",
            "brend": (r.get("brend") or "").strip(),
            "princip": princip_iz_modeli(model),
            "vid_mashiny": vid_iz_modeli(model),
            "istochnik": (r.get("istochnik") or "").strip(),
            "vstrech": "",
            "innov": "",
            "ssylok": "",
            "_ishod": model,
        })

    # --- серии из документов ---------------------------------------------
    for nabor, imya in ((serii, args.serii), (proverit, args.proverit)):
        for r in nabor:
            ser = (r.get("seriya") or "").strip()
            stroki.append({
                "oboznachenie": ser,
                "vid_zapisi": "серия из документов",
                "brend": "",
                "princip": (r.get("princip") or "").strip(),
                "vid_mashiny": (r.get("vid") or "").strip(),
                "istochnik": "разбор документов 3С (%s)" % imya.split("/")[-1],
                "vstrech": (r.get("vstrech") or "").strip(),
                "innov": (r.get("innov") or "").strip(),
                "ssylok": (r.get("ssylok") or "").strip(),
                "_ishod": ser,
            })

    with open(args.vyhod, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=VYHOD_POLYA, delimiter=";",
                           extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for s in stroki:
            w.writerow(s)

    # --- пересечение ------------------------------------------------------
    kat_klyuchi = defaultdict(list)
    dok_klyuchi = defaultdict(list)
    for s in stroki:
        k = normalizovat(s["oboznachenie"])
        if not k:
            continue
        (kat_klyuchi if s["vid_zapisi"] == "модель каталога" else dok_klyuchi)[k].append(s)

    obshchie = sorted(set(kat_klyuchi) & set(dok_klyuchi))
    tolko_kat = set(kat_klyuchi) - set(dok_klyuchi)
    tolko_dok = set(dok_klyuchi) - set(kat_klyuchi)

    # справочно: то же с приведением кириллических омоглифов к латинице
    kat_omo = {normalizovat_omo(s["oboznachenie"]) for s in stroki
               if s["vid_zapisi"] == "модель каталога" and s["oboznachenie"]}
    dok_omo = {normalizovat_omo(s["oboznachenie"]) for s in stroki
               if s["vid_zapisi"] == "серия из документов" and s["oboznachenie"]}
    obshchie_omo = kat_omo & dok_omo

    out = sys.stdout
    p_ = lambda *a: print(*a, file=out)
    p_("=== ЕДИНЫЙ СЛОВАРЬ ===")
    p_("файл:", args.vyhod)
    p_("строк всего:", len(stroki))
    p_("  модели каталога:", sum(1 for s in stroki if s["vid_zapisi"] == "модель каталога"))
    p_("  серии из документов:", sum(1 for s in stroki if s["vid_zapisi"] == "серия из документов"),
       "(%d из %s + %d из %s)" % (len(serii), args.serii.split("/")[-1],
                                  len(proverit), args.proverit.split("/")[-1]))
    p_()
    p_("=== ПЕРЕСЕЧЕНИЕ (нормализовано: верхний регистр, без пробелов/дефисов) ===")
    p_("уникальных обозначений в каталоге:   ", len(kat_klyuchi))
    p_("уникальных обозначений в документах: ", len(dok_klyuchi))
    p_("в ОБОИХ списках:                     ", len(obshchie))
    p_("только в каталоге:                   ", len(tolko_kat))
    p_("только в документах:                 ", len(tolko_dok))
    if kat_klyuchi:
        p_("доля пересечения от каталога:   %.2f%%" % (100.0 * len(obshchie) / len(kat_klyuchi)))
    if dok_klyuchi:
        p_("доля пересечения от документов: %.2f%%" % (100.0 * len(obshchie) / len(dok_klyuchi)))
    p_("справочно, с приведением кириллических омоглифов к латинице: %d общих" % len(obshchie_omo))
    p_()
    p_("=== ПРИМЕРЫ СОВПАДЕНИЙ (исходный вид) ===")
    # показываем самые «весомые» совпадения: у которых больше встреч в документах
    def ves(k):
        try:
            return max(int(x["vstrech"] or 0) for x in dok_klyuchi[k])
        except ValueError:
            return 0
    for k in sorted(obshchie, key=ves, reverse=True)[:args.primerov]:
        kat = kat_klyuchi[k][0]
        dok = dok_klyuchi[k][0]
        p_("ключ %-16s | каталог: %-38s (из «%s», бренд %s)" %
           (k, kat["oboznachenie"], kat["_ishod"], kat["brend"]))
        p_("%22s | документы: %-36s (вид: %s, принцип: %s, встреч: %s)" %
           ("", dok["oboznachenie"], dok["vid_mashiny"], dok["princip"], dok["vstrech"]))
    p_()

    # --- проверка прибора: дубли и подозрительно короткие ключи -----------
    p_("=== ПРОВЕРКА ПРИБОРА ===")
    korotkie = [k for k in obshchie if len(k) <= 3]
    p_("совпадений с ключом короче 4 символов (риск ложного совпадения):", len(korotkie),
       sorted(korotkie)[:20])
    dubli_kat = sum(len(v) - 1 for v in kat_klyuchi.values() if len(v) > 1)
    dubli_dok = sum(len(v) - 1 for v in dok_klyuchi.values() if len(v) > 1)
    p_("дублей обозначений внутри каталога:", dubli_kat,
       "| внутри документов:", dubli_dok)
    dlinnye = [s for s in stroki if s["vid_zapisi"] == "модель каталога"
               and len(s["oboznachenie"]) > 40]
    p_("моделей каталога с обозначением длиннее 40 знаков (плохо вырезано):", len(dlinnye))
    for s in dlinnye[:5]:
        p_("   ", s["oboznachenie"][:90])
    kirill = [s for s in stroki if s["vid_zapisi"] == "модель каталога"
              and re.search(r"[а-яё]", s["oboznachenie"], re.I)]
    p_("моделей каталога, где в обозначении осталась кириллица:", len(kirill))
    for s in kirill[:5]:
        p_("   ", s["oboznachenie"], " <- ", s["_ishod"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
