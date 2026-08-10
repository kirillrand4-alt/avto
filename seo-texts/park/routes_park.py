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
import sqlite3
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

from app.api.routes_centro_sales import current_user
from app.config import get_settings
from app.web import templates

router = APIRouter(tags=["park"], include_in_schema=False)
BP = get_settings().obzvon_path
BAZA = os.environ.get("PARK_PANEL_DB", r"C:\seostat\data\park_panel.db")

SORTIROVKI = {
    "vyruchka": "coalesce(vyruchka, -1) desc, rang_mashiny desc",
    "rang": "rang_mashiny desc, coalesce(vyruchka, -1) desc",
    "faktov": "faktov desc, coalesce(vyruchka, -1) desc",
    "nazvanie": "nazvanie asc",
}
NA_STRANICE = 100


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect("file:%s?mode=ro" % BAZA, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _okvedy(conn: sqlite3.Connection) -> list[dict]:
    """Список ОКВЭД для фильтра: код, сколько предприятий, есть ли выручка."""
    out = []
    for r in conn.execute(
        "select okved, count(*) n, sum(case when vyruchka is not null then 1 else 0 end) v "
        "from predpriyatie where coalesce(okved,'')<>'' group by okved "
        "order by n desc limit 60"
    ):
        out.append({"kod": r["okved"], "shtuk": r["n"], "s_vyruchkoy": r["v"]})
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
    poisk = (p.get("q") or "").strip()
    try:
        stranica = max(1, int(p.get("str") or 1))
    except ValueError:
        stranica = 1

    gde, znach = ["1=1"], []
    if okved:
        # префикс кода: 28.13 покажет и 28.13.28
        gde.append("okved like ?")
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
    if poisk:
        gde.append("(nazvanie like ? or inn like ?)")
        znach += ["%" + poisk + "%", poisk + "%"]
    usloviye = " and ".join(gde)

    with _conn() as conn:
        vsego = conn.execute(
            "select count(*) from predpriyatie where " + usloviye, znach
        ).fetchone()[0]
        svod = conn.execute(
            "select count(*) vsego, sum(case when vyruchka is not null then 1 else 0 end) s_vyr,"
            " sum(case when krug<=2 then 1 else 0 end) s_teh,"
            " sum(case when coalesce(telefon,'')<>'' then 1 else 0 end) s_tel,"
            " sum(coalesce(vyruchka,0)) summa_vyr"
            " from predpriyatie where " + usloviye, znach
        ).fetchone()
        stroki = conn.execute(
            "select * from predpriyatie where " + usloviye
            + " order by " + SORTIROVKI[sort]
            + " limit ? offset ?", znach + [NA_STRANICE, (stranica - 1) * NA_STRANICE]
        ).fetchall()
        okvedy = _okvedy(conn)
        regiony = [r[0] for r in conn.execute(
            "select region, count(*) n from predpriyatie where coalesce(region,'')<>''"
            " group by region order by n desc limit 40")]

    def ssylka(**kw):
        d = {k: v for k, v in {
            "sort": sort, "okved": okved, "region": region, "os": os_,
            "teh": "1" if tolko_teh else "", "est_vyruchka": "1" if tolko_vyruchka else "",
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
            "stranica": stranica, "stranic": max(1, (vsego + NA_STRANICE - 1) // NA_STRANICE),
            "ssylka": ssylka,
        },
    )


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
