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
    "сборе", "ременным", "клиноременным", "прямым", "приводом", "поплавковый",
    "таймерный", "электронный", "шасси", "раме", "салазках", "тормозами", "тормозов",
}

# служебные предлоги/союзы, которые встречаются внутри ведущего описания
SLUZHEBNYE = {"в", "с", "на", "и", "для", "без", "из", "по"}

# латинские омоглифы -> кириллица (для распознавания слов вида «Cепаратор» с
# латинской C — в каталоге такие есть, 14 строк)
LAT_V_KIR = str.maketrans("ABEKMHOPCTYXaeopcyx", "АВЕКМНОРСТУХаеорсух")

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
    # ABAC в каталоге местами набран кириллическими омоглифами: «АВАС»
    "авас", "авас,", "abac,",
]

# хвосты, которые не входят в обозначение
HVOST_BAR = re.compile(r"[\s,]*\b\d+(?:[.,]\d+)?\s*бар\b\s*$", re.I)
HVOST_KVT = re.compile(r"[\s,]*\b\d+(?:[.,]\d+)?\s*квт\b\s*$", re.I)
SKOBKI_HVOST = re.compile(r"\s*\([^()]*\)?\s*$")
PROBELY = re.compile(r"\s+")

# скобочный хвост режем, только если внутри пояснение, а не часть обозначения
POYASNENIE = re.compile(
    r"ориг|шасси|помещ|сбор|регенерац|осушител|стационар|фикс|высота|тормоз|"
    r"раме|салазк|мкм|мг/м|л/мин|м3/|компл|исполн|двигател|кожух|лючк|класс",
    re.I,
)


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


def tipovoe(t):
    """Слово-тип? Латинские омоглифы приводятся к кириллице («Cепаратор»).

    Дефисные составные («Фильтр-элемент», «Влаго-маслоотделитель») считаются
    типовыми, если типовые ВСЕ их части.
    """
    t = chistyy_token(t)
    for v in (t, t.translate(LAT_V_KIR)):
        if v in TIPOVYE_SLOVA:
            return True
        chasti = [c for c in v.split("-") if c]
        if len(chasti) > 1 and all(c in TIPOVYE_SLOVA for c in chasti):
            return True
    return False


def obozn_iz_modeli(model, aliasy_brendov):
    """Вырезать обозначение из торгового названия каталога.

    Срезается ведущее описание типа (по белому списку кириллических слов),
    затем ведущее имя бренда (по списку псевдонимов, до 3 слов подряд),
    затем хвосты «N бар», «N кВт», «(оригинал…)».
    """
    s = model.strip()
    # хвостовые пояснения в скобках и «N бар» / «N кВт» — срезаем по кругу
    for _ in range(4):
        do = s
        m = SKOBKI_HVOST.search(s)
        if m and POYASNENIE.search(m.group(0)):
            s = s[: m.start()].strip()
        s = HVOST_BAR.sub("", s).strip()
        s = HVOST_KVT.sub("", s).strip()
        if s == do:
            break

    tokeny = s.split()
    # 1) ведущие слова-типы
    i = 0
    while i < len(tokeny):
        if tipovoe(tokeny[i]) or chistyy_token(tokeny[i]) in SLUZHEBNYE:
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
        if tipovoe(tokeny[i]) or chistyy_token(tokeny[i]) in SLUZHEBNYE:
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
    if obshchie:
        p_("=== ПРИМЕРЫ СОВПАДЕНИЙ (исходный вид) ===")
        # самые «весомые» совпадения: у которых больше встреч в документах
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
    else:
        p_("=== СОВПАДЕНИЙ НЕТ. БЛИЖАЙШИЕ ПАРЫ (исходный вид) ===")
        p_("(показываем %d самых похожих пар, чтобы пустое пересечение можно было "
           "проверить глазами)" % args.primerov)
        import difflib
        kat_spisok = list(kat_klyuchi)
        pary = []
        for dk in dok_klyuchi:
            blizh = difflib.get_close_matches(dk, kat_spisok, n=1, cutoff=0.72)
            if blizh:
                r = difflib.SequenceMatcher(None, dk, blizh[0]).ratio()
                pary.append((r, dk, blizh[0]))
        pary.sort(reverse=True)
        for r, dk, kk in pary[:args.primerov]:
            dok = dok_klyuchi[dk][0]
            kat = kat_klyuchi[kk][0]
            p_("похожесть %.2f | документы: %-18s | каталог: %-24s <- «%s»" %
               (r, dok["oboznachenie"], kat["oboznachenie"], kat["_ishod"]))
        p_("всего пар с похожестью >= 0.72:", len(pary))
    p_()

    # --- проверка прибора --------------------------------------------------
    p_("=== ПРОВЕРКА ПРИБОРА ===")
    # (а) контроль, не зависящий от вырезания обозначения: сравниваем серию
    #     с ПОЛНЫМ торговым названием каталога.
    polnye = {normalizovat(s["_ishod"]) for s in stroki if s["vid_zapisi"] == "модель каталога"}
    tochno_polnye = [k for k in dok_klyuchi if k in polnye]
    p_("контроль без вырезания (серия == полное название модели):", len(tochno_polnye))

    # (б) контроль на максимум полноты: серия ПОДСТРОКОЙ в названии модели.
    #     Даёт ложные срабатывания (после снятия дефисов «К-601» лезет в «BK60-1,5»),
    #     поэтому печатаем примеры — их видно глазами.
    polnye_spisok = [(normalizovat(s["_ishod"]), s) for s in stroki
                     if s["vid_zapisi"] == "модель каталога"]
    podstroki = []
    for dk in dok_klyuchi:
        if len(dk) < 4:
            continue
        for pk, s in polnye_spisok:
            if dk in pk:
                podstroki.append((dok_klyuchi[dk][0]["oboznachenie"], s["_ishod"]))
                break
    p_("контроль подстрокой (серия внутри названия модели):", len(podstroki))
    for a, b in podstroki[:8]:
        p_("    %-12s внутри  %s" % (a, b))

    # (в) кириллица/латиница
    p_("контроль омоглифов (кир. АВЕКМНОРСТУХ -> лат.):", len(obshchie_omo),
       sorted(obshchie_omo)[:10])

    korotkie = [k for k in obshchie if len(k) <= 3]
    p_("совпадений с ключом короче 4 символов (риск ложного совпадения):", len(korotkie),
       sorted(korotkie)[:20])
    dubli_kat = sum(len(v) - 1 for v in kat_klyuchi.values() if len(v) > 1)
    dubli_dok = sum(len(v) - 1 for v in dok_klyuchi.values() if len(v) > 1)
    p_("дублей обозначений внутри каталога:", dubli_kat,
       "| внутри документов:", dubli_dok, "(в документах это варианты написания: ЦК-135/8 и ЦК135/8)")
    dlinnye = [s for s in stroki if s["vid_zapisi"] == "модель каталога"
               and len(s["oboznachenie"]) > 40]
    p_("моделей каталога с обозначением длиннее 40 знаков (плохо вырезано):", len(dlinnye))
    for s in dlinnye[:5]:
        p_("   ", s["oboznachenie"][:90])
    slova = [s for s in stroki if s["vid_zapisi"] == "модель каталога"
             and re.search(r"[а-яё]{4,}", s["oboznachenie"], re.I)]
    p_("моделей каталога, где в обозначении осталось русское СЛОВО (>=4 букв):", len(slova))
    for s in slova[:6]:
        p_("    %-46s <- %s" % (s["oboznachenie"][:46], s["_ishod"][:70]))
    pusto_dok = [s for s in stroki if s["vid_zapisi"] == "серия из документов"
                 and s["vid_mashiny"] == "не установлен"]
    nepon_dok = [s for s in stroki if s["vid_zapisi"] == "серия из документов"
                 and s["princip"] == "не установлен"]
    p_("серий, у которых вид машины не установлен:", len(pusto_dok),
       "| принцип не установлен:", len(nepon_dok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
