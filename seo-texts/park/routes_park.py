"""Панель ПАРКА компрессорного оборудования: 4 589 предприятий с доказанной машиной.

Отдельная страница внутри того же приложения обзвона, поэтому вход и сессия общие —
кто зашёл в /obzvon/centro, тот видит и /obzvon/park.

Что показывает и почему именно так:
  * адрес /obzvon/centro/park — под общей сессией продавца;
  * сортировка ПО ВЫРУЧКЕ (по умолчанию) — прямая просьба владельца; выручка собрана
    из серверных источников и у каждого числа записано, откуда оно взято;
  * фильтр ПО ОКВЭД — список кодов с числом предприятий, выбор одним щелчком;
  * ранг машины и «чем ранг доказан» — правило владельца «выше тот, у кого машина дороже»;
  * колонка «доказано» — предприятия без открываемой ссылки названы своим именем,
    их 10 из 4 589, и они не прячутся;
  * ссылки на доказательство машины и на контакт — открываются, это требование
    «каждый факт и контакт доказывается ссылкой».

Данные лежат в отдельной компактной базе C:\\seostat\\data\\park_panel.db (9.5 МБ):
полная park.db весит 338 МБ, и панели она не нужна.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.api.routes_centro_sales import current_user
from app.config import get_settings
from app.web import templates

router = APIRouter(tags=["park"], include_in_schema=False)
BP = get_settings().obzvon_path
BAZA = os.environ.get("PARK_PANEL_DB", r"C:\seostat\data\park_panel.db")

# ЦЕНТРОБЕЖНЫЕ — ВСЕГДА СВЕРХУ. Владелец назвал списком модели, по которым звонят в первую
# очередь («К-250, К-350, К-500, ЦТК-275… а у этих брендов поищи, как обозначаются
# центробежники»), и попросил вывести их вверху. Поэтому `prioritet_modeli` стоит ПЕРВЫМ
# ключом в каждой сортировке: 2 — отечественные центробежные, 1 — центробежные серии
# импортных брендов, 0 — остальные. Выбранная сортировка работает внутри этих групп.
_SVERHU = "coalesce(prioritet_modeli, 0) desc, "
SORTIROVKI = {
    "vyruchka": _SVERHU + "coalesce(vyruchka, -1) desc, rang_mashiny desc",
    "rang": _SVERHU + "rang_mashiny desc, coalesce(vyruchka, -1) desc",
    "faktov": _SVERHU + "faktov desc, coalesce(vyruchka, -1) desc",
    "nazvanie": _SVERHU + "nazvanie asc",
}
NA_STRANICE = 100


# Очередь обзвона и скрытие живут в базе ПРОДАЖ (`centro_sales.db`), а не в park_panel.db.
# Это принципиально: park_panel.db я пересобираю в песочнице и кладу на сервер целиком, любая
# отметка внутри неё была бы стёрта следующей выкладкой. centro_sales.db — серверная, её
# никто не перезаписывает, и в ней уже есть и `company_assignment`, и `hidden_item`
# (25 389 записей) — беру существующие таблицы, а не завожу свои.
# ВСЕГДА «Центробежные», а не база той панели, на которой нажали кнопку.
# Владелец сказал буквально: «убрать в очередь базы обзвон центробежные». Панель парка
# открыта из-под ДВУХ служб, и у p25 своя база продаж, где заведён один user3 (491
# назначение), а в «Центробежных» — user1 (695), user2 (697), user3 (223). Пока путь брался
# из окружения службы, на p25 в выборе стоял один человек, и предприятие ушло бы в очередь
# p25, а не туда, куда просили. Поэтому путь задан прямо; переменные оставлены на случай
# переноса, но они СВОИ, а не CENTRO_SALES_DB службы.
SALES_DB_PUT = os.environ.get("PARK_OCHERED_SALES_DB", r"C:\seostat\data\centro_sales.db")
OCHERED_DB = os.environ.get("PARK_OCHERED_DB", r"C:\seostat\data\centrifugal.db")
SKRYTO_VIDY = ("park_musor", "park_v_obzvon")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect("file:%s?mode=ro" % BAZA, uri=True)
    conn.row_factory = sqlite3.Row
    if os.path.exists(SALES_DB_PUT):
        try:
            conn.execute("attach database ? as sales", ("file:%s?mode=ro" % SALES_DB_PUT,))
        except sqlite3.OperationalError:
            pass
    return conn


def _sales() -> sqlite3.Connection:
    """На запись: сюда кладём назначение продавцу и отметку «мусор»."""
    conn = sqlite3.connect(SALES_DB_PUT, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _prodavcy(conn: sqlite3.Connection) -> list[str]:
    """Кому можно отдать: действующие продавцы из users, а не те, у кого уже есть строки."""
    try:
        return [r[0] for r in conn.execute(
            "select username from sales.users where coalesce(is_active,1)=1"
            " and username <> 'admin' order by username")]
    except sqlite3.OperationalError:
        return []


def _est_sales(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("select 1 from sales.hidden_item limit 1")
        return True
    except sqlite3.OperationalError:
        return False


def _modeli(conn: sqlite3.Connection, skolko: int = 60) -> list[tuple]:
    """Ходовые модели для выпадающего списка фильтра.

    Марки хранятся строкой через « | » («ГА160 | ЦК135/8 | ГПА-16»), поэтому список
    собирается разбором, а не group by. Показываем самые частые: по ним и звонят.
    Одиночные и совсем короткие обозначения выкидываем — они чаще позиция, чем модель
    (класс «в поле марки лежит номер позиции» разобран в журнале, записи 111 и 116).
    """
    schet: dict[str, int] = {}
    for (m,) in conn.execute("select marki from predpriyatie where coalesce(marki,'')<>''"):
        for kusok in str(m).split("|"):
            k = " ".join(kusok.split())
            # «К-250-61-5 К-250-61-5» — марка записана дважды подряд, схлопываем
            polovina = len(k) // 2
            if len(k) % 2 == 1 and k[:polovina] == k[polovina + 1:]:
                k = k[:polovina]
            if len(k) >= 4:
                schet[k] = schet.get(k, 0) + 1
    return sorted(((k, n) for k, n in schet.items() if n >= 2),
                  key=lambda x: -x[1])[:skolko]


def _okvedy(conn: sqlite3.Connection) -> list[dict]:
    """Список ОКВЭД для фильтра: код, название, сколько НАЙДЁТ ОТБОР, из них по основному.

    Число берётся из свода `okved_svod`, который считает предприятия ПО ВСЕМ КОДАМ — так же,
    как ищет фильтр. Владелец спросил: «это фильтр только основных ОКВЭД или дополнительные
    тоже ищет?» Искал только основной; теперь ищет по всем, и число в списке обязано считаться
    так же, иначе список врёт ровно там, где выбирают, кому звонить.
    """
    try:
        rows = conn.execute(
            "select kod, imya, shtuk, s_vyruchkoy, osnovnoy from okved_svod "
            "order by shtuk desc limit 80"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if rows:
        return [{"kod": r["kod"], "imya": r["imya"] or "", "shtuk": r["shtuk"],
                 "s_vyruchkoy": r["s_vyruchkoy"], "osnovnoy": r["osnovnoy"]} for r in rows]
    out = []           # запасной путь: база собрана старой сборкой, свода в ней нет
    for r in conn.execute(
        "select okved, count(*) n, sum(case when vyruchka is not null then 1 else 0 end) v "
        "from predpriyatie where coalesce(okved,'')<>'' group by okved "
        "order by n desc limit 60"
    ):
        kod, _, imya = (r["okved"] or "").strip().partition(" ")
        out.append({"kod": kod, "imya": imya.strip(), "shtuk": r["n"], "s_vyruchkoy": r["v"],
                    "osnovnoy": r["n"]})
    return out


@router.get("/centro/park")
def park(request: Request, user: dict = Depends(current_user)):
    p = request.query_params
    sort = p.get("sort") if p.get("sort") in SORTIROVKI else "vyruchka"
    okved = (p.get("okved") or "").strip()
    region = (p.get("region") or "").strip()
    os_ = (p.get("os") or "").strip()
    tolko_teh = p.get("teh") == "1"
    tolko_vyruchka = p.get("est_vyruchka") == "1"
    # Три фильтра по просьбе владельца: выбрать МОДЕЛЬ, по которой звонить; только с
    # телефоном; только те, где личный номер ДОКАЗАН СНИМКОМ (на картинке видно номер,
    # должность и ФИО). Модель ищется по полю marki — там марки через « | ».
    model = (p.get("model") or "").strip()
    tolko_telefon = p.get("est_telefon") == "1"
    tolko_snimok = p.get("nomer_snimok") == "1"
    tolko_lichnyy = p.get("lichnyy_mobilnyy") == "1"
    tolko_centro = p.get("centro") == "1"
    poisk = (p.get("q") or "").strip()
    try:
        stranica = max(1, int(p.get("str") or 1))
    except ValueError:
        stranica = 1

    gde, znach = ["1=1"], []
    if okved:
        # префикс кода: 28.13 покажет и 28.13.28
        # по ВСЕМ кодам предприятия, а не только по основному: okved_kody хранится
        # строкой « 35.11.3 20.11 33.13 » с пробелами по краям, поэтому « + код» ловит код
        # целиком с начала, а не кусок середины другого кода
        gde.append("(okved_kody like ? or okved like ?)")
        znach.append("% " + okved + "%")
        znach.append(okved + "%")
    if region:
        gde.append("region = ?")
        znach.append(region)
    if os_:
        gde.append("os = ?")
        znach.append(os_)
    if tolko_teh:
        gde.append("krug <= 2")
    if tolko_vyruchka:
        gde.append("vyruchka is not null")
    if model:
        # Марки лежат строкой «ГА160 | ЦК-201 | ГПА-16». Проба показала: запрос «ЦК135»
        # давал НОЛЬ, потому что в базе написано «ЦК-135/8» — с дефисом. Поэтому сравнение
        # идёт по строке, из которой убраны дефисы, пробелы и точки: тогда «цк135» находит
        # и «ЦК-135/8», и «ЦК 135». Ищем и в марках, и в ТИПЕ машины — по типу («МКС»,
        # «ГПА», «воздуходувка») звонят так же, как по конкретной модели.
        # сравниваем с заранее нормализованным полем: SQLite lower() не трогает кириллицу,
        # поэтому нормализация сделана на сборке панели, средствами Python
        # то же приведение, что на сборке: убрать разделители и свести похожие буквы
        # латиницы к кириллице — иначе «K-101» латиницей даёт ноль при девяти «К-101»
        _karta = str.maketrans('ABCEHKMOPTXYaceopxy', 'АВСЕНКМОРТХУасеорху')
        gde.append("poisk_mashina like ?")
        znach.append("%" + re.sub(r"[-\s.,/()«»\'\"]", "", model.lower()).translate(_karta) + "%")
    if tolko_telefon:
        gde.append("coalesce(telefon,'') <> ''")
    if tolko_snimok:
        gde.append("coalesce(nomer_snimok,'') <> ''")
    if tolko_lichnyy:
        # вид номера от 3-й сессии; доказанность — отдельное поле, их не смешиваем
        gde.append("coalesce(vid_nomera,'') like 'ЛИЧНЫЙ%'")
    if tolko_centro:
        gde.append("coalesce(prioritet_modeli, 0) > 0")
    if poisk:
        gde.append("(nazvanie like ? or inn like ?)")
        znach += ["%" + poisk + "%", poisk + "%"]
    with _conn() as conn:
        # Убранное руками владельца: «мусор» и «забрал в свою очередь». Условие ставится
        # ЗДЕСЬ, а не в списке выше, потому что оно есть только когда база продаж
        # присоединилась — иначе панель падала бы на «no such table: sales.hidden_item».
        if _est_sales(conn):
            gde.append("inn not in (select inn from sales.hidden_item where kind in (%s))"
                       % ",".join("?" * len(SKRYTO_VIDY)))
            znach += list(SKRYTO_VIDY)
        usloviye = " and ".join(gde)
        vsego = conn.execute(
            "select count(*) from predpriyatie where " + usloviye, znach
        ).fetchone()[0]
        svod = conn.execute(
            "select count(*) vsego, sum(case when vyruchka is not null then 1 else 0 end) s_vyr,"
            " sum(case when krug<=2 then 1 else 0 end) s_teh,"
            " sum(case when coalesce(telefon,'')<>'' then 1 else 0 end) s_tel,"
            " sum(case when coalesce(nomer_snimok,'')<>'' then 1 else 0 end) s_snim,"
            " sum(case when coalesce(vid_nomera,'') like 'ЛИЧНЫЙ%' then 1 else 0 end) s_lich,"
            " sum(case when coalesce(prioritet_modeli,0)>0 then 1 else 0 end) s_centro,"
            " sum(coalesce(vyruchka,0)) summa_vyr"
            " from predpriyatie where " + usloviye, znach
        ).fetchone()
        stroki = conn.execute(
            "select * from predpriyatie where " + usloviye
            + " order by " + SORTIROVKI[sort]
            + " limit ? offset ?", znach + [NA_STRANICE, (stranica - 1) * NA_STRANICE]
        ).fetchall()
        okvedy = _okvedy(conn)
        modeli = _modeli(conn)
        prodavcy = _prodavcy(conn)
        regiony = [r[0] for r in conn.execute(
            "select region, count(*) n from predpriyatie where coalesce(region,'')<>''"
            " group by region order by n desc limit 40")]

    def ssylka(**kw):
        d = {k: v for k, v in {
            "sort": sort, "okved": okved, "region": region, "os": os_,
            "teh": "1" if tolko_teh else "", "est_vyruchka": "1" if tolko_vyruchka else "",
            "model": model, "est_telefon": "1" if tolko_telefon else "",
            "nomer_snimok": "1" if tolko_snimok else "",
            "lichnyy_mobilnyy": "1" if tolko_lichnyy else "",
            "centro": "1" if tolko_centro else "",
            "q": poisk, **kw}.items() if v}
        return "%s/centro/park?%s" % (BP, urlencode(d))

    return templates.TemplateResponse(
        request,
        "park.html",
        {
            "user": user, "bp": BP,
            "stroki": stroki, "vsego": vsego, "svod": svod,
            "okvedy": okvedy, "regiony": regiony,
            "sort": sort, "okved": okved, "region": region, "os": os_,
            "teh": tolko_teh, "est_vyruchka": tolko_vyruchka, "q": poisk,
            "model": model, "est_telefon": tolko_telefon, "nomer_snimok": tolko_snimok,
            "lichnyy_mobilnyy": tolko_lichnyy, "centro": tolko_centro,
            "modeli": modeli, "prodavcy": prodavcy,
            "stranica": stranica, "stranic": max(1, (vsego + NA_STRANICE - 1) // NA_STRANICE),
            "ssylka": ssylka,
        },
    )


def _kartochka_iz_parka(conn, inn: str, kto: str) -> dict | None:
    """Собрать ПОЛНУЮ карточку для базы обзвона: факты со ссылками, цитаты, люди, счётчики.

    Владелец забрал компанию и написал: «почему когда в очередь забираем, все факты слетают?»
    Не слетают — не переносились. Карточка в базе обзвона держит СВОЙ снимок фактов и
    контактов в отдельных полях (`ssylki_na_istochniki`, `citaty_dokazatelstv`, `daty_faktov`,
    `lyudi_moi_podrobno`, `n_facts`, `n_phones` …), а кнопка заводила её из шести полей —
    ИНН, название, регион, ОКВЭД, выручка, типы машин. Всё остальное оставалось нулями, и
    продавец видел компанию без единого доказательства.

    Собирается из park_panel.db, той же базы, по которой показан парк, — чтобы в очереди
    лежало ровно то, что владелец видел, когда нажимал кнопку.
    """
    r = conn.execute(
        "select inn, nazvanie, region, okved, okved_vse, vyruchka, ssch, status_egrul,"
        "       rang_mashiny, chem_rang, tipy, marki, faktov, ssylok, chelovek, dolzhnost,"
        "       krug, telefon, pochta, nomer_snimok"
        "  from predpriyatie where inn = ?", (inn,)).fetchone()
    if r is None:
        return None
    fakty = conn.execute(
        "select f.id, coalesce(f.tip,''), coalesce(f.marka,''), coalesce(f.model,''),"
        "       coalesce(f.sostoyanie,''), coalesce(f.data_fakta,''), coalesce(f.chto_naydeno,'')"
        "  from fakt f where f.inn = ? order by coalesce(f.sila,0) desc limit 60", (inn,)).fetchall()
    ids = [str(x[0]) for x in fakty]
    ssylki = []
    if ids:
        # СИЛЬНЫЕ ССЫЛКИ ВПЕРЁД. Первый прогон отдал в карточку «НОВАТЭКа» ссылку на
        # вакансию hh.ru — она в базе есть, но доказывает слабее закупки, а продавец
        # смотрит первую. Порядок: первоисточник, потом площадка закупок, потом прочее.
        ssylki = [x[0] for x in conn.execute(
            "select url from fakt_ssylka where fakt_id in (%s) and url like 'http%%'"
            " order by coalesce(pervoistochnik,0) desc,"
            "          case when url like '%%zakupki.gov.ru%%' or url like '%%tektorg%%'"
            "                 or url like '%%roseltorg%%' or url like '%%etpgpb%%'"
            "                 or url like '%%fabrikant%%' or url like '%%tender.pro%%'"
            "               then 0 when url like '%%hh.ru%%' then 2 else 1 end"
            " limit 60" % ",".join("?" * len(ids)), ids)]
    lyudi = conn.execute(
        "select coalesce(person,''), coalesce(dolzhnost,''), coalesce(vid,''),"
        "       coalesce(znachenie,''), coalesce(krug,9), coalesce(ssylka,'')"
        "  from kontakt where inn = ? order by coalesce(krug,9) limit 40", (inn,)).fetchall()
    telefony = [x[3] for x in lyudi if x[2] == "telefon"]
    pochty = [x[3] for x in lyudi if x[2] == "email"]
    s_imenem = [x for x in lyudi if x[0]]
    teh = [x for x in s_imenem if x[4] <= 2]

    def skleit(znacheniya, skolko=25):
        vidno, itog = set(), []
        for z in znacheniya:
            z = (z or "").strip()
            if z and z not in vidno:
                vidno.add(z)
                itog.append(z)
            if len(itog) >= skolko:
                break
        return " | ".join(itog)

    return {
        "inn": inn, "predpriyatie": r["nazvanie"], "region": r["region"],
        "okved": r["okved"], "okvedy_vse": r["okved_vse"], "vyruchka_rub": r["vyruchka"],
        "ssch": r["ssch"], "status_egrul": r["status_egrul"],
        "tipy_mashin": r["tipy"], "marki": r["marki"],
        "marki_iz_faktov": skleit([("%s %s" % (x[2], x[3])).strip() for x in fakty]),
        "sostoyaniya_po_faktam": skleit([x[4] for x in fakty]),
        "daty_faktov": skleit([x[5] for x in fakty]),
        "citaty_dokazatelstv": skleit([x[6] for x in fakty], 20),
        "ssylki_na_istochniki": skleit(ssylki, 30),
        "faktov_centrobezhnyh": r["faktov"], "n_facts": r["faktov"],
        "telefony_predpriyatiya": skleit(telefony, 12),
        "telefony_iz_bazy": skleit(telefony, 12),
        "pochta": r["pochta"] or (pochty[0] if pochty else None),
        "pochty_checko": skleit(pochty, 10),
        "lyudi_moi_podrobno": skleit(
            ["%s — %s: %s%s" % (x[0], x[1] or "должность не названа", x[3],
                                (" · " + x[5]) if x[5].startswith("http") else "")
             for x in s_imenem], 20),
        "lyudi_moi_vsego": len(s_imenem), "lyudej_vsego_svedeno": len(s_imenem),
        "lyudej_s_nomerom": len([x for x in s_imenem if x[2] == "telefon"]),
        "tehnicheskih_s_nomerom": len([x for x in teh if x[2] == "telefon"]),
        "tehnicheskie_lyudi": skleit(["%s — %s" % (x[0], x[1]) for x in teh], 12),
        "n_phones": len(telefony), "n_tech": len(teh),
        "has_phone": 1 if telefony else 0, "has_tech": 1 if teh else 0,
        "ball_prioriteta": float(r["rang_mashiny"] or 0),
        "prioritet_pochemu": (r["chem_rang"] or "")[:200],
        "sostoyanie_potverzhdeno_faktom": 1 if ssylki else 0,
        "ssylka_sostoyaniya": ssylki[0] if ssylki else None,
        "istochnik_dopolneniya": "парк компрессорного оборудования, забрал %s" % kto,
        "pometka": "из парка компрессорного оборудования, забрал %s" % kto,
        "chego_ne_hvataet": ", ".join(
            [x for x in (("телефон" if not telefony else ""),
                         ("технический контакт" if not teh else ""),
                         ("доказательство номера снимком" if not r["nomer_snimok"] else ""))
             if x]) or None,
        "search_blob": " ".join(str(x or "") for x in
                                (inn, r["nazvanie"], r["marki"], r["tipy"], r["chelovek"])),
    }


@router.post("/centro/park/{inn}/v-obzvon")
def park_v_obzvon(inn: str, request: Request, username: str = Form(""),
                  nazad: str = Form(""), user: dict = Depends(current_user)):
    """Забрать предприятие из парка в очередь обзвона «Центробежные», на выбранного продавца.

    Владелец: «нужна кнопка „убрать в очередь базы обзвон центробежные“ и выбор, под какого
    юзера убрать». Делается ровно то, что делает сама база обзвона:

        1. карточка предприятия заводится в `centrifugal.company`, если её там ещё нет —
           иначе строка назначения будет ссылаться в пустоту и список обзвона её не покажет;
        2. ставится назначение в `company_assignment` на выбранного продавца;
        3. предприятие прячется из ПАРКА через `hidden_item(kind='park_v_obzvon')` — чтобы
           не звонить дважды и чтобы владелец видел парк как «ещё не разобранное».

        4. карточка сразу ставится «Взял в работу» (`company_state`), а балл очереди —
           выше максимума этого продавца: владелец забрал её руками, это самый сильный
           сигнал важности, и в хвосте очереди ей делать нечего.

    Ничего не удаляется: отметку видно в hidden_item, назначение — в company_assignment.
    """
    kto = (user or {}).get("username") or "?"
    komu = (username or "").strip() or kto
    with _conn() as conn:
        r = conn.execute(
            "select telefon, chelovek from predpriyatie where inn = ?", (inn,)).fetchone()
        gotovo = _kartochka_iz_parka(conn, inn, kto)
    sales = _sales()
    try:
        sales.execute("attach database ? as centro", (OCHERED_DB,))
        est = sales.execute(
            "select coalesce(pometka,'') from centro.company where inn = ?", (inn,)).fetchone()
        if gotovo is not None:
            kolonki = [x[1] for x in sales.execute("pragma centro.table_info(company)")]
            polya = [k for k in gotovo if k in kolonki]
            if not est:
                sales.execute("insert into centro.company (%s) values (%s)"
                              % (",".join(polya), ",".join("?" * len(polya))),
                              [gotovo[k] for k in polya])
            elif "из парка" in (est[0] or ""):
                # карточка заведена парком — обновляем целиком, она наша
                bez_inn = [k for k in polya if k != "inn"]
                sales.execute("update centro.company set %s where inn = ?"
                              % ",".join("%s=?" % k for k in bez_inn),
                              [gotovo[k] for k in bez_inn] + [inn])
            else:
                # РОДНАЯ карточка базы обзвона: её данные не трогаем, но пустые поля
                # дозаполняем. У Газпрома стояло 49 фактов и НИ ОДНОЙ ссылки — парк такие
                # места закрывает, а перетирать заполненное нельзя: там своя работа.
                bez_inn = [k for k in polya if k != "inn" and gotovo[k] not in (None, "", 0)]
                if bez_inn:
                    sales.execute(
                        "update centro.company set %s where inn = ?"
                        % ",".join("%s = case when coalesce(%s,'')='' then ? else %s end"
                                   % (k, k, k) for k in bez_inn),
                        [gotovo[k] for k in bez_inn] + [inn])
        # БАЛЛ ОЧЕРЕДИ. Владелец забрал компанию РУКАМИ — это самый сильный сигнал важности,
        # какой вообще бывает, и она обязана встать первой. С баллом 0 «НОВАТЭК» встал 696-м
        # из 697: очередь сортируется по баллу, а у остальных он 2000+. Поэтому берём
        # максимум по этому продавцу и добавляем единицу.
        bylo_max = sales.execute(
            "select coalesce(max(assignment_score), 0) from company_assignment"
            " where username = ?", (komu,)).fetchone()[0]
        ball = float(bylo_max or 0) + 1.0
        # Ключ таблицы — ОДИН ИНН, один продавец. Если компания уже назначена другому,
        # переназначение отбирает её у него, и это должно оставить след, а не пройти молча:
        # своей пробой я так затёр прежнего продавца Газпрома и восстановить его не смог.
        prezhniy = sales.execute(
            "select username from company_assignment where inn = ?", (inn,)).fetchone()
        if prezhniy and prezhniy[0] != komu:
            sales.execute(
                "insert into activity_log (inn, username, action, payload_json, created_at)"
                " values (?,?,?,?,?)",
                (inn, kto, "park_perenaznachenie",
                 '{"bylo": "%s", "stalo": "%s"}' % (prezhniy[0], komu),
                 datetime.now(timezone.utc).isoformat()))
        sales.execute(
            "insert or replace into company_assignment"
            " (inn, username, assignment_score, has_phone, has_purchaser, has_tech,"
            "  has_signal, assigned_at, source_version, assigned_by)"
            " values (?,?,?,?,?,?,?,?,?,?)",
            (inn, komu, ball, 1 if (r and r["telefon"]) else 0, 0,
             1 if (r and r["chelovek"]) else 0, 0,
             datetime.now(timezone.utc).isoformat(), "park", kto))
        # СРАЗУ В РАБОТУ, а не в конец очереди. Владелец: «она должна сразу в работу
        # уходить». В базе обзвона это `company_state` со status='processed' и
        # call_result='v_rabote' — та самая вкладка «Взял в работу»; ключ (инн, продавец).
        sales.execute(
            "insert or replace into company_state"
            " (inn, username, status, last_contact_at, next_contact_at, call_result, updated_at)"
            " values (?,?,?,?,?,?,?)",
            (inn, komu, "processed", None, None, "v_rabote",
             datetime.now(timezone.utc).isoformat()))
        sales.execute(
            # у hidden_item уникальный ключ (инн, вид, значение): повторное нажатие кнопки
            # роняло ВСЮ транзакцию, и карточка не успевала обновиться —
            # владелец видел «факты слетают», хотя дело было в этой строке
            "insert or replace into hidden_item"
            " (inn, kind, value, reason, username, created_at)"
            " values (?,?,?,?,?,?)",
            (inn, "park_v_obzvon", inn, "забрано в очередь обзвона на %s" % komu, kto,
             datetime.now(timezone.utc).isoformat()))
        sales.execute(
            "insert into activity_log (inn, username, action, payload_json, created_at)"
            " values (?,?,?,?,?)",
            (inn, kto, "park_v_obzvon", '{"komu": "%s"}' % komu,
             datetime.now(timezone.utc).isoformat()))
        sales.commit()
    finally:
        sales.close()
    return RedirectResponse(nazad or ("%s/centro/park" % BP), status_code=303)


@router.post("/centro/park/{inn}/musor")
def park_musor(inn: str, request: Request, prichina: str = Form(""),
               nazad: str = Form(""), user: dict = Depends(current_user)):
    """Убрать мусорную компанию из списка парка совсем.

    Владелец: «нужна кнопка, которая удаляет просто мусорную компанию, в принципе из списка,
    так как много мусора сейчас».

    Строка НЕ удаляется из базы, а прячется через тот же `hidden_item`, которым база обзвона
    уже прячет 25 389 записей. Причина: удаление необратимо и стирает доказательства, а
    отметка — обратима и хранит, КТО и ПОЧЕМУ убрал. При следующей пересборке парка эти
    отметки переживут выкладку, потому что лежат в серверной базе продаж, а не в park_panel.db.
    """
    kto = (user or {}).get("username") or "?"
    sales = _sales()
    try:
        sales.execute(
            # у hidden_item уникальный ключ (инн, вид, значение): повторное нажатие кнопки
            # роняло ВСЮ транзакцию, и карточка не успевала обновиться —
            # владелец видел «факты слетают», хотя дело было в этой строке
            "insert or replace into hidden_item"
            " (inn, kind, value, reason, username, created_at)"
            " values (?,?,?,?,?,?)",
            (inn, "park_musor", inn, (prichina or "").strip() or "мусор, убрано из парка",
             kto, datetime.now(timezone.utc).isoformat()))
        sales.execute(
            "insert into activity_log (inn, username, action, payload_json, created_at)"
            " values (?,?,?,?,?)",
            (inn, kto, "park_musor", "{}", datetime.now(timezone.utc).isoformat()))
        sales.commit()
    finally:
        sales.close()
    return RedirectResponse(nazad or ("%s/centro/park" % BP), status_code=303)


@router.get("/centro/park/{inn}")
def park_karta(inn: str, request: Request, user: dict = Depends(current_user)):
    """Карточка предприятия: реквизиты, ВСЕ факты про машины со своими ссылками, контакты.

    Факты добавлены после прямого вопроса владельца на карточке КАМАЗа: «а где все факты
    про машины то? как понять что это не выдуманное». До этого карточка показывала список
    моделей и ОДНУ ссылку — и та оказалась вакансией hh.ru, хотя в базе у предприятия
    13 фактов и 85 ссылок, у каждой модели свой тендер. Список моделей без источника
    действительно неотличим от выдуманного; теперь под каждым фактом лежат его адреса.
    """
    with _conn() as conn:
        p = conn.execute("select * from predpriyatie where inn=?", (inn,)).fetchone()
        if p is None:
            # В парке нет — почти всегда потому, что предприятие УЖЕ показано продавцам в
            # базе обзвона: такие из парка убраны (517 штук), чтобы не звать на одну компанию
            # дважды. Раньше шаблон падал на этом с 500 («'None' has no attribute
            # 'rang_mashiny'») — пустая страница вместо ответа, да ещё пугающая. Теперь
            # отвечаем словами и сразу даём переход туда, где карточка есть.
            est_v_obzvone = conn.execute(
                "select 1 from predpriyatie limit 1").fetchone() is not None
            return templates.TemplateResponse(
                request, "park_net.html",
                {"user": user, "bp": BP, "inn": inn, "baza_zhiva": est_v_obzvone},
                status_code=404,
            )
        kont = conn.execute(
            "select * from kontakt where inn=? order by coalesce(krug,9), lichnyy desc,"
            " mobilnyy desc, ssylok desc", (inn,)
        ).fetchall()
        # сильные факты выше: сначала «машина», потом узел/расходник; внутри — по силе
        fakty = [dict(r) for r in conn.execute(
            "select * from fakt where inn=? order by"
            " case vid_fakta when 'машина' then 1 when 'узел' then 2"
            "      when 'расходник' then 3 when 'газ' then 4 else 5 end,"
            " sila, data_fakta desc", (inn,))]
        # ссылок несколько — строк несколько: правило владельца, поэтому берём ВСЕ
        for f in fakty:
            f["ssylki"] = [dict(x) for x in conn.execute(
                "select url, istochnik, pervoistochnik from fakt_ssylka where fakt_id=?"
                " order by pervoistochnik desc", (f["id"],))]
    return templates.TemplateResponse(
        request,
        "park_card.html",
        {"user": user, "bp": BP, "p": p, "kont": kont, "fakty": fakty},
    )


# ---------------------------------------------------------------------------
# СПИСОК КОМПАНИЙ ОБЗВОНА — просьба владельца: «в общей панели сделай возможность
# смотреть списком компании, чтобы была в списке обязательно выручка и основной
# ОКВЭД». Карточка обзвона показывает по одному предприятию; здесь та же база,
# но целиком, с сортировкой и фильтрами. Ничего в обзвоне не меняем — только
# добавляем страницу.
# ---------------------------------------------------------------------------
SALES_DB = os.environ.get("CENTRO_SALES_DB", r"C:\seostat\data\centro_sales.db")
CENTRO_DB = os.environ.get("CENTRO_DB", r"C:\seostat\data\centrifugal.db")

SORT_SPISOK = {
    "vyruchka": "coalesce(c.vyruchka_rub, -1) desc, coalesce(c.ball_prioriteta,0) desc",
    "prioritet": "coalesce(c.ball_prioriteta,0) desc, coalesce(c.vyruchka_rub,-1) desc",
    "nazvanie": "c.predpriyatie asc",
}


@router.get("/centro/spisok")
def centro_spisok(request: Request, user: dict = Depends(current_user)):
    p = request.query_params
    sort = p.get("sort") if p.get("sort") in SORT_SPISOK else "vyruchka"
    okved = (p.get("okved") or "").strip()
    region = (p.get("region") or "").strip()
    kto = (p.get("kto") or "").strip()
    sost = (p.get("sost") or "").strip()
    poisk = (p.get("q") or "").strip()
    tolko_vyr = p.get("est_vyruchka") == "1"
    tolko_teh = p.get("teh") == "1"
    try:
        stranica = max(1, int(p.get("str") or 1))
    except ValueError:
        stranica = 1

    conn = sqlite3.connect("file:%s?mode=ro" % SALES_DB, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("attach database ? as centro", ("file:%s?mode=ro" % CENTRO_DB,))

    # продавец видит своё, админ — всё; это то же правило, что в карточке обзвона
    gde = ["a.inn not in (select inn from hidden_item where kind='company')"]
    znach: list = []
    if user.get("role") != "admin":
        gde.append("a.username = ?")
        znach.append(user["username"])
    elif kto:
        gde.append("a.username = ?")
        znach.append(kto)
    if okved:
        gde.append("c.okved like ?")
        znach.append(okved + "%")
    if region:
        gde.append("c.region = ?")
        znach.append(region)
    if tolko_vyr:
        gde.append("c.vyruchka_rub is not null and c.vyruchka_rub > 0")
    if tolko_teh:
        gde.append("coalesce(c.n_tech,0) > 0")
    if sost == "rabota":
        gde.append("s.status is not null")
    elif sost == "ochered":
        gde.append("s.status is null")
    if poisk:
        gde.append("(c.predpriyatie like ? or a.inn like ?)")
        znach += ["%" + poisk + "%", poisk + "%"]
    usl = " and ".join(gde)

    OSNOVA = (" from company_assignment a"
              " join centro.company c on c.inn = a.inn"
              " left join company_state s on s.inn = a.inn"
              " where " + usl)
    vsego = conn.execute("select count(*)" + OSNOVA, znach).fetchone()[0]
    svod = conn.execute(
        "select sum(case when c.vyruchka_rub>0 then 1 else 0 end) s_vyr,"
        " sum(case when coalesce(c.n_tech,0)>0 then 1 else 0 end) s_teh,"
        " sum(case when s.status is not null then 1 else 0 end) s_rabota,"
        " sum(coalesce(c.vyruchka_rub,0)) summa_vyr" + OSNOVA, znach).fetchone()
    stroki = conn.execute(
        "select a.inn, a.username, c.predpriyatie, c.region, c.okved, c.vyruchka_rub,"
        " c.ball_prioriteta, c.tipy_mashin, c.marki, c.n_phones, c.n_tech, c.n_facts,"
        " s.status, s.call_result, s.last_contact_at" + OSNOVA
        + " order by " + SORT_SPISOK[sort] + " limit ? offset ?",
        znach + [NA_STRANICE, (stranica - 1) * NA_STRANICE]).fetchall()
    okvedy = [{"kod": r[0], "shtuk": r[1]} for r in conn.execute(
        "select c.okved, count(*) n from company_assignment a"
        " join centro.company c on c.inn=a.inn"
        " where coalesce(c.okved,'')<>'' group by c.okved order by n desc limit 60")]
    regiony = [r[0] for r in conn.execute(
        "select c.region, count(*) n from company_assignment a"
        " join centro.company c on c.inn=a.inn"
        " where coalesce(c.region,'')<>'' group by c.region order by n desc limit 40")]
    prodavcy = [r[0] for r in conn.execute(
        "select distinct username from company_assignment order by 1")]
    conn.close()

    def ssylka(**kw):
        d = {k: v for k, v in {
            "sort": sort, "okved": okved, "region": region, "kto": kto, "sost": sost,
            "q": poisk, "est_vyruchka": "1" if tolko_vyr else "",
            "teh": "1" if tolko_teh else "", **kw}.items() if v}
        return "%s/centro/spisok?%s" % (BP, urlencode(d))

    return templates.TemplateResponse(
        request, "spisok.html",
        {"user": user, "bp": BP, "stroki": stroki, "vsego": vsego, "svod": svod,
         "okvedy": okvedy, "regiony": regiony, "prodavcy": prodavcy,
         "sort": sort, "okved": okved, "region": region, "kto": kto, "sost": sost,
         "q": poisk, "est_vyruchka": tolko_vyr, "teh": tolko_teh,
         "stranica": stranica, "stranic": max(1, (vsego + NA_STRANICE - 1) // NA_STRANICE),
         "ssylka": ssylka},
    )
