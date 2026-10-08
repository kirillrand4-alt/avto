# -*- coding: utf-8 -*-
"""Фильтры и статистика для директора по продажам (админ панели Meyer).

Владелец 08.10: «админ – директор по продажам, он не будет звонить, он будет анализировать
работу продажников». Выбрано: 1, 2, 3 (в т.ч. очередь «дубль»), 6, 8, 9, 10, 11, 13, 14.

ГЛАВНАЯ (строка «Директор» под фильтрами, только у админа):
  1. Продавец в основной строке + «без продавца».
  2. «Отметки с … по …» – компании, отмеченные продавцами в период (журнал call_saved).
  3. Причина отказа – четыре причины «не понравилась» + «Дубль – уже работают».
  6. «Отказ без пояснения» – «не понравилась», а текста от человека нет.
  Заодно: строка фильтров больше не теряет вкладку (call_status) при «Найти».

СТАТИСТИКА:
  8.  Период «с … по …» и кнопки: сегодня, вчера, 7 дней, 30 дней, всё время.
  9.  Причины отказов × продавец.
  10. Темп и прогноз: отмечено, дней с отметками, в день, очередь, на сколько дней хватит.
  11. Где берут в работу: доля «взял в работу» по сегменту, источнику базы, региону, роли
      ЛПР, «есть в битриксе», откуда номер.
  13. Лента действий за период; каждая цифра на странице – ссылка на список компаний.
  14. Активность по часам (Москва).

ОДИН ИСТОЧНИК ДЛЯ ЦИФР И ДЛЯ СПИСКА: и таблицы статистики, и фильтр главной берут
отметки из _sobytiya() / _poslednie() – последняя отметка компании в периоде, её
владелец, результат, причина. Проверка ниже открывает КАЖДУЮ ссылку-цифру страницы
статистики и сверяет число строк списка с цифрой.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
T = os.path.join(APP, 'templates')
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
RP = os.path.join(APP, 'api', 'routes_park.py')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
TEST_DB = os.path.join(KOREN, '_bekap', 'direktor-test.db')
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('direktor-%Y%m%d-%H%M%S'))

# ====================================================================== код: routes_centro_sales
RCS_KOD = r'''


# ================================================================ для директора по продажам
# Владелец 08.10: админ – директор по продажам, сам не звонит, анализирует работу
# продавцов. Главная: продавец (+ «без продавца»), отметки с … по …, причина отказа
# (+ «дубль»), отказ без пояснения. Статистика: период, причины × продавец, темп и
# прогноз, где берут в работу, лента действий, часы; каждая цифра – ссылка на список.
#
# ОДИН ИСТОЧНИК ДЛЯ ЦИФР И ДЛЯ СПИСКА. И таблицы статистики, и фильтр главной берут
# отметки из _sobytiya(): последняя отметка компании в периоде, её владелец, результат
# и причина. Иначе цифра в статистике и число строк по её ссылке разошлись бы на первой
# же компании, которую в периоде отметили дважды.
import json as _json_dir
import math as _math_dir

_MSK_DIR = datetime.timedelta(hours=3)
_DIR_PARAMY = ("ot", "do", "prichina", "bez_poyasneniya", "rez_p", "kto_p")


def _msk_vremya(znach):
    """UTC ISO из базы -> наивное московское datetime (или None)."""
    if not znach:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(znach).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt + _MSK_DIR


def _segodnya_msk():
    return (datetime.datetime.utcnow() + _MSK_DIR).date()


def _data_param(znach):
    try:
        return datetime.date.fromisoformat(str(znach or "").strip()) if znach else None
    except ValueError:
        return None


def _sobytiya(conn, ot=None, do=None, vse_deystviya=False) -> list[dict]:
    """Отметки продавцов из журнала за период [ot, do] (дни по Москве, включительно;
    None – без границы), по времени. kto – владелец компании на момент отметки
    (state_user), deystvoval – кто нажал. Причина и текст – из комментария, сохранённого
    той же кнопкой (тот же ИНН, автор и время). vse_deystviya – ещё правки комментариев
    и передачи компаний (для ленты)."""
    komm = {}
    for r in conn.execute("SELECT inn, username, body, created_at FROM company_comment"):
        komm[(str(r["inn"]), r["username"], r["created_at"])] = r["body"]
    vidy = ("call_saved", "comment_edited", "reassigned") if vse_deystviya else ("call_saved",)
    out = []
    for r in conn.execute(
            "SELECT id, inn, username, action, payload_json, created_at FROM activity_log "
            "WHERE action IN (%s) ORDER BY created_at, id" % ",".join("?" * len(vidy)), vidy):
        kogda = _msk_vremya(r["created_at"])
        if kogda is None:
            continue
        den = kogda.date()
        if (ot and den < ot) or (do and den > do):
            continue
        try:
            pl = _json_dir.loads(r["payload_json"] or "{}")
        except ValueError:
            pl = {}
        inn = str(r["inn"] or "")
        z = {"id": r["id"], "inn": inn, "deystvie": r["action"], "deystvoval": r["username"],
             "kto": pl.get("state_user") or r["username"], "rez": str(pl.get("result") or ""),
             "kogda": kogda, "den": den, "sled": str(pl.get("next_contact") or ""),
             "prichina": "", "tekst": "", "pl": pl}
        if r["action"] == "call_saved":
            body = komm.get((inn, r["username"], r["created_at"]))
            if body is not None:
                rk = _razbor_kommentariya(body)
                z["prichina"], z["tekst"] = rk["prichina"], rk["tekst"]
        elif r["action"] == "reassigned":
            z["kto"] = pl.get("to") or r["username"]
        out.append(z)
    return out


def _poslednie(sobytiya) -> dict:
    """ИНН -> ПОСЛЕДНЯЯ отметка (call_saved) из набора, n – сколько их было."""
    out: dict = {}
    for z in sobytiya:
        if z["deystvie"] == "call_saved":
            out[z["inn"]] = dict(z, n=out.get(z["inn"], {}).get("n", 0) + 1)
    return out


def _direktor_predikat(params):
    """Фильтры директора для списка. None – ни один не задан (список как был).
    С периодом (ot/do/rez_p/kto_p) всё решает ПОСЛЕДНЯЯ отметка компании в периоде;
    без периода причина и «без пояснения» – по нынешнему статусу и последней отметке."""
    ot, do = _data_param(params.get("ot")), _data_param(params.get("do"))
    prichina = (params.get("prichina") or "").strip()
    bez = params.get("bez_poyasneniya") == "1"
    rez_p = (params.get("rez_p") or "").strip()
    kto_p = (params.get("kto_p") or "").strip()
    po_periodu = bool(ot or do or rez_p or kto_p)
    if not (po_periodu or prichina or bez):
        return None
    with sales.connect() as conn:
        posl = _poslednie(_sobytiya(conn, ot, do))

    def pred(company) -> bool:
        o = posl.get(str(company.get("inn") or ""))
        if po_periodu:
            if not o:
                return False
            if kto_p and o["kto"] != kto_p:
                return False
            if rez_p and o["rez"] != rez_p:
                return False
            rez = o["rez"]
        else:
            rez = company.get("call_result") or "new"
        if prichina:
            if prichina == "dubl":
                if rez != "dubl":
                    return False
            elif rez != "ne_ponravilas":
                return False
            elif prichina == "bez_prichiny":
                if o and o["prichina"]:
                    return False
            elif not o or o["prichina"] != prichina:
                return False
        if bez and (rez != "ne_ponravilas" or (o and o["tekst"])):
            return False
        return True
    return pred


def _period_ru(ot, do) -> str:
    if ot and do and ot == do:
        return "за " + do.strftime("%d.%m.%Y")
    return " ".join(x for x in (("с " + ot.strftime("%d.%m.%Y")) if ot else "",
                                ("по " + do.strftime("%d.%m.%Y")) if do else "") if x)


_PRICHINA_NAZV = {"dubl": "Дубль – уже работают", "bez_prichiny": "без причины"}


def _dir_opis(params) -> str:
    """Человеческое описание отбора директора – строкой над списком."""
    chasti = []
    ot, do = _data_param(params.get("ot")), _data_param(params.get("do"))
    if ot or do:
        chasti.append("отметки " + _period_ru(ot, do))
    if params.get("kto_p"):
        chasti.append("продавец: " + _fio_dlya_shablona(params.get("kto_p")))
    if params.get("rez_p"):
        chasti.append("последняя отметка: " + sales.CALL_RESULT_LABELS.get(
            params.get("rez_p"), params.get("rez_p")))
    if params.get("prichina"):
        chasti.append("причина: " + _PRICHINA_NAZV.get(params.get("prichina"), params.get("prichina")))
    if params.get("bez_poyasneniya") == "1":
        chasti.append("отказ без пояснения")
    return " · ".join(chasti)


def _ssylka_spiska(**kw) -> str:
    d = {k: v for k, v in kw.items() if v not in (None, "")}
    return "%s/centro%s" % (BP, ("?" + urlencode(d)) if d else "")


def _direktor_vybor(companies_vse, vidimye, assignments) -> dict:
    """Счётчики у фильтров директора – по нынешнему статусу компаний, которые сейчас
    видит админ (с учётом выбранного продавца)."""
    with sales.connect() as conn:
        posl = _poslednie(_sobytiya(conn))
    pr: dict = {}
    dubl = bez = 0
    for c in vidimye:
        rez = c.get("call_result") or "new"
        o = posl.get(str(c.get("inn") or "")) or {}
        if rez == "dubl":
            dubl += 1
        elif rez == "ne_ponravilas":
            p = o.get("prichina") or "bez_prichiny"
            pr[p] = pr.get(p, 0) + 1
            if not o.get("tekst"):
                bez += 1
    spisok = [(p, pr.get(p, 0)) for p in PRICHINY_NE_PONRAVILAS]
    spisok += [(p, n) for p, n in sorted(pr.items())
               if p not in PRICHINY_NE_PONRAVILAS and p != "bez_prichiny"]
    if pr.get("bez_prichiny"):
        spisok.append(("bez_prichiny", pr["bez_prichiny"]))
    return {"prichiny": spisok, "dubl_n": dubl, "bez_poyasneniya_n": bez,
            "bez_prodavca_n": sum(1 for c in companies_vse if c["inn"] not in assignments)}


def _statblok_ssylki(statblok, ot, do) -> None:
    """Ссылки на список у цифр календарного блока (только на странице статистики)."""
    per = {"ot": ot.isoformat(), "do": do.isoformat()}

    def ss(u):
        k = {"kto_p": u} if u else {}
        a = {"assigned_user": u} if u else {}
        den = {r: _ssylka_spiska(**per, rez_p=r, **k) for r in ("v_rabote", "ne_ponravilas", "dubl")}
        # очередь «на конец дня» за прошлый день списком не показать – только сегодняшняя
        den["ochered"] = _ssylka_spiska(**a) if do == _segodnya_msk() else ""
        vse = {r: _ssylka_spiska(call_status=r, **a) for r in ("v_rabote", "ne_ponravilas", "dubl")}
        vse["ochered"] = _ssylka_spiska(**a)
        return den, vse
    for z in statblok.get("stroki") or []:
        z["ss_den"], z["ss_vse"] = ss(z["username"])
    statblok["itog_ss_den"], statblok["itog_ss_vse"] = ss("")


def _bystrye_periody(ssylka, pervyy, ot, do) -> list[dict]:
    segodnya = _segodnya_msk()
    d1 = datetime.timedelta(days=1)
    pervyy_den = (_msk_vremya(pervyy).date() if _msk_vremya(pervyy) else segodnya)
    pervyy_den = min(pervyy_den, segodnya)
    out = []
    for nazv, a, b in (("сегодня", segodnya, segodnya), ("вчера", segodnya - d1, segodnya - d1),
                       ("7 дней", segodnya - 6 * d1, segodnya),
                       ("30 дней", segodnya - 29 * d1, segodnya),
                       ("всё время", pervyy_den, segodnya)):
        out.append({"nazv": nazv, "aktiven": (a, b) == (ot, do),
                    "url": ssylka(stat_ot=a.isoformat() if a != b else "",
                                  stat_data=b.isoformat() if b != segodnya else "")})
    return out


_RAZREZY = (("segment", "Сегмент", "segment"), ("bazy", "Источник базы", "baza"),
            ("region", "Регион", "region"), ("lpr_roli", "Роль ЛПР", "rol_lpr"),
            ("bitrix", "Есть номер в битриксе", "bitrix"), ("istochnik", "Откуда номер", ""))


def _direktor_svodka(conn, ot, do, kto: str) -> dict:
    """Блоки статистики директора за период [ot, do] (дни по Москве)."""
    from app.web import _vid_istochnika
    katalog: dict = {}
    try:
        for row in catalog.list_companies():
            inn = sales.normalize_inn(row.get("inn"))
            if inn and inn not in katalog:
                katalog[inn] = row
    except catalog.CentroDbUnavailable:
        pass
    skrytye = {str(r[0]) for r in conn.execute(
        "SELECT inn FROM hidden_item WHERE kind='company'")}
    # считаются компании, которые можно открыть списком: в каталоге и не скрытые
    vidimye = set(katalog) - skrytye
    lyudi = {r["username"]: dict(r) for r in conn.execute(
        "SELECT username, role, is_active FROM users")}
    prodavcy = sorted((u for u, r in lyudi.items() if r["role"] == "sales" and r["is_active"]),
                      key=lambda u: _fio_dlya_shablona(u).lower())
    if kto:
        prodavcy = [kto]
    per = {"ot": ot.isoformat(), "do": do.isoformat()}
    sobytiya = _sobytiya(conn, ot, do, vse_deystviya=True)
    zvonki = [z for z in sobytiya if z["deystvie"] == "call_saved"]
    posl = {inn: o for inn, o in _poslednie(zvonki).items()
            if inn in vidimye and (not kto or o["kto"] == kto)}

    def yach(n, **kw):
        return {"n": n, "url": _ssylka_spiska(**per, **kw) if n else ""}

    # ---- 9. причины × продавец
    drugie = sorted({o["prichina"] for o in posl.values() if o["rez"] == "ne_ponravilas"
                     and o["prichina"] and o["prichina"] not in PRICHINY_NE_PONRAVILAS})
    kolonki = list(PRICHINY_NE_PONRAVILAS) + drugie + ["bez_prichiny"]

    def pustaya():
        return {"otmecheno": 0, "v_rabote": 0, "otkazov": 0, "dubl": 0, "bez_poyasn": 0,
                "pr": {p: 0 for p in kolonki}, "dni": set(), "posled": None}
    po = {u: pustaya() for u in prodavcy}
    for inn, o in posl.items():
        s = po.setdefault(o["kto"], pustaya())
        s["otmecheno"] += 1
        if o["rez"] == "v_rabote":
            s["v_rabote"] += 1
        elif o["rez"] == "dubl":
            s["dubl"] += 1
        elif o["rez"] == "ne_ponravilas":
            s["otkazov"] += 1
            s["pr"][o["prichina"] or "bez_prichiny"] += 1
            if not o["tekst"]:
                s["bez_poyasn"] += 1
    for z in zvonki:
        if z["inn"] in vidimye and z["kto"] in po and (not kto or z["kto"] == kto):
            po[z["kto"]]["dni"].add(z["den"])
            if po[z["kto"]]["posled"] is None or z["kogda"] > po[z["kto"]]["posled"]:
                po[z["kto"]]["posled"] = z["kogda"]

    def stroka_prichin(u, s, itog=False):
        k = {} if (itog and not kto) else {"kto_p": u or kto}
        return {"kto": u, "itog": itog,
                "otmecheno": yach(s["otmecheno"], **k),
                "v_rabote": yach(s["v_rabote"], rez_p="v_rabote", **k),
                "pr": [yach(s["pr"][p], rez_p="ne_ponravilas", prichina=p, **k) for p in kolonki],
                "otkazov": yach(s["otkazov"], rez_p="ne_ponravilas", **k),
                "bez_poyasn": yach(s["bez_poyasn"], rez_p="ne_ponravilas", bez_poyasneniya="1", **k),
                "dubl": yach(s["dubl"], rez_p="dubl", **k)}
    poryadok = prodavcy + sorted(u for u in po if u not in prodavcy)
    prichiny = [stroka_prichin(u, po[u]) for u in poryadok]
    itog = pustaya()
    for u in poryadok:
        for kl in ("otmecheno", "v_rabote", "otkazov", "dubl", "bez_poyasn"):
            itog[kl] += po[u][kl]
        for p in kolonki:
            itog["pr"][p] += po[u]["pr"][p]
        itog["dni"] |= po[u]["dni"]
        if po[u]["posled"] and (itog["posled"] is None or po[u]["posled"] > itog["posled"]):
            itog["posled"] = po[u]["posled"]
    if len(poryadok) > 1:
        prichiny.append(stroka_prichin("", itog, itog=True))

    # ---- 10. темп и прогноз
    ochered: dict = {}
    for r in conn.execute(
            "SELECT a.username u, a.inn inn, COALESCE(s.call_result,'new') r FROM company_assignment a "
            "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username"):
        if str(r["inn"]) in vidimye and r["r"] not in sales.CALL_RESULT_CHOICES:
            ochered[r["u"]] = ochered.get(r["u"], 0) + 1
    dney = (do - ot).days + 1

    def stroka_tempa(u, s, och, itog=False):
        dni = len(s["dni"])
        v_den = s["otmecheno"] / dni if dni else 0.0
        a = {} if itog and not kto else {"assigned_user": u or kto}
        return {"kto": u, "itog": itog,
                "otmecheno": yach(s["otmecheno"], **({} if itog and not kto else {"kto_p": u or kto})),
                "dney_rab": dni, "v_den_rab": v_den, "v_den_kal": s["otmecheno"] / dney,
                "ochered": {"n": och, "url": _ssylka_spiska(**a) if och else ""},
                "prognoz": _math_dir.ceil(och / v_den) if v_den and och else None,
                "posled": s["posled"].strftime("%d.%m %H:%M") if s["posled"] else ""}
    temp = [stroka_tempa(u, po[u], ochered.get(u, 0)) for u in poryadok]
    if len(poryadok) > 1:
        temp.append(stroka_tempa("", itog, sum(ochered.get(u, 0) for u in poryadok), itog=True))

    # ---- 11. где берут в работу
    istochniki: dict = {}
    try:
        kc = catalog.connect()
        try:
            for r in kc.execute("SELECT inn, source_url, source FROM contact"):
                inn = str(r["inn"])
                row = katalog.get(inn) or {}
                v = _vid_istochnika(r["source_url"], r["source"], row.get("sayt") or row.get("website") or "")
                istochniki.setdefault(inn, set()).add(v["vid"] or "без ссылки")
        finally:
            kc.close()
    except Exception:  # noqa: BLE001 – нет таблицы contact: срез просто пустой
        istochniki = {}

    def znacheniya(pole, row, inn):
        if pole == "segment":
            v = [s.strip() for s in str(row.get("segment") or "").split("|") if s.strip()]
        elif pole == "bazy":
            v = [s.strip() for s in str(row.get("bazy") or "").split("|") if s.strip()]
        elif pole == "region":
            v = [str(row.get("region") or "").strip()] if str(row.get("region") or "").strip() else []
        elif pole == "lpr_roli":
            v = [s.strip() for s in str(row.get("lpr_roli") or "").split(",") if s.strip()]
        elif pole == "bitrix":
            v = ["да" if row.get("bitrix_kc") else "нет"]
        else:
            v = sorted(istochniki.get(inn) or [])
        return v or ["не указан"]
    razrezy = []
    for pole, nazv, param in _RAZREZY:
        sch: dict = {}
        for inn, o in posl.items():
            for zn in znacheniya(pole, katalog.get(inn) or {}, inn):
                s = sch.setdefault(zn, {"otmecheno": 0, "v_rabote": 0, "ne_ponravilas": 0, "dubl": 0})
                s["otmecheno"] += 1
                if o["rez"] in ("v_rabote", "ne_ponravilas", "dubl"):
                    s[o["rez"]] += 1
        stroki = []
        for zn, s in sorted(sch.items(), key=lambda x: (-x[1]["otmecheno"], x[0])):
            if not param or zn == "не указан" or (param == "bitrix" and zn != "да"):
                f = None                    # такого фильтра в списке нет – цифра без ссылки
            else:
                f = {param: "1" if param == "bitrix" else zn}
            k = dict(f or {}, **({"kto_p": kto} if kto else {}))

            def y(n, **kw):
                return yach(n, **k, **kw) if f is not None else {"n": n, "url": ""}
            stroki.append({"znach": zn, "otmecheno": y(s["otmecheno"]),
                           "v_rabote": y(s["v_rabote"], rez_p="v_rabote"),
                           "ne_ponravilas": y(s["ne_ponravilas"], rez_p="ne_ponravilas"),
                           "dubl": y(s["dubl"], rez_p="dubl"),
                           "dolya": 100.0 * s["v_rabote"] / s["otmecheno"] if s["otmecheno"] else 0.0})
        razrezy.append({"nazv": nazv, "stroki": stroki[:20], "vsego_znacheniy": len(stroki)})

    # ---- 14. часы (Москва): кто нажал кнопку
    chasy_po: dict = {}
    for z in zvonki:
        if kto and z["deystvoval"] != kto:
            continue
        chasy_po.setdefault(z["deystvoval"], {})
        chasy_po[z["deystvoval"]][z["kogda"].hour] = chasy_po[z["deystvoval"]].get(z["kogda"].hour, 0) + 1
    vse_chasy = [h for d in chasy_po.values() for h in d]
    ch_ot = min([8] + vse_chasy)
    ch_do = max([20] + vse_chasy)
    kolonki_ch = list(range(ch_ot, ch_do + 1))
    chasy = []
    for u in sorted(chasy_po, key=lambda u: _fio_dlya_shablona(u).lower()):
        chasy.append({"kto": u, "po_chasam": [chasy_po[u].get(h, 0) for h in kolonki_ch],
                      "vsego": sum(chasy_po[u].values())})
    if len(chasy) > 1:
        chasy.append({"kto": "", "itog": True,
                      "po_chasam": [sum(chasy_po[u].get(h, 0) for u in chasy_po) for h in kolonki_ch],
                      "vsego": sum(sum(d.values()) for d in chasy_po.values())})
    chasy_max = max([1] + [n for s in chasy if not s.get("itog") for n in s["po_chasam"]])

    # ---- 13. лента действий
    tek = {str(r[0]): r[1] for r in conn.execute(
        "SELECT a.inn, COALESCE(s.call_result,'new') FROM company_assignment a "
        "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username")}
    odin_den = ot == do
    lenta_vse = [z for z in reversed(sobytiya)
                 if not kto or z["kto"] == kto or z["deystvoval"] == kto]
    lenta = []
    for z in lenta_vse[:300]:
        row = katalog.get(z["inn"]) or {}
        tekushchiy = tek.get(z["inn"], "new")
        url = ""
        if z["inn"] in vidimye:
            url = "%s/centro?%s" % (BP, urlencode(dict(
                {"inn": z["inn"]}, **({"call_status": tekushchiy}
                                      if tekushchiy in sales.CALL_RESULT_CHOICES else {}))))
        if z["deystvie"] == "call_saved":
            chto = sales.CALL_RESULT_LABELS.get(z["rez"], z["rez"] or "отметка")
        elif z["deystvie"] == "reassigned":
            chto = "передал компанию: %s → %s" % (_fio_dlya_shablona(z["pl"].get("from") or ""),
                                                  _fio_dlya_shablona(z["pl"].get("to") or ""))
        else:
            chto = "изменил комментарий"
        lenta.append({"vremya": z["kogda"].strftime("%H:%M" if odin_den else "%d.%m %H:%M"),
                      "kto": z["kto"], "deystvoval": z["deystvoval"],
                      "nazvanie": row.get("predpriyatie") or row.get("name_short") or z["inn"],
                      "url": url, "chto": chto, "prichina": z["prichina"], "tekst": z["tekst"],
                      "sled": z["sled"].replace("T", " ")[:16], "rez": z["rez"]})
    return {"period_ru": _period_ru(ot, do), "kto": kto, "dney": dney,
            "kolonki": kolonki, "kolonki_nazv": [_PRICHINA_NAZV.get(p, p) for p in kolonki],
            "prichiny": prichiny, "temp": temp, "razrezy": razrezy,
            "chasy": chasy, "chasy_kolonki": kolonki_ch, "chasy_max": chasy_max,
            "lenta": lenta, "lenta_vsego": len(lenta_vse),
            "otmecheno_vsego": len(posl)}
'''

# ====================================================================== шаблоны
FILTR_DIREKTORA = '''  {% if user.role == 'admin' %}{# Строка директора (владелец 08.10): продавец, отметки за период,
     причина отказа (+ «дубль»), отказ без пояснения. Числа – по нынешнему статусу. #}
  <div class="direktor-ryad">
    <span class="direktor-metka">Директор:</span>
    <select name="assigned_user" title="За кем сейчас компания">
      <option value="">Все продавцы</option>
      {% for value in sales_users %}<option value="{{ value }}" {% if request.query_params.get('assigned_user') == value %}selected{% endif %}>{{ value|fio }}</option>{% endfor %}
      <option value="__net__" {% if request.query_params.get('assigned_user') == '__net__' %}selected{% endif %}>Без продавца · {{ choices.bez_prodavca_n }}</option>
    </select>
    <label class="direktor-period" title="Компании, по которым продавцы ставили отметку в эти дни (по Москве). Статус в списке – нынешний">Отметки с <input type="date" name="ot" value="{{ request.query_params.get('ot','') }}"> по <input type="date" name="do" value="{{ request.query_params.get('do','') }}"></label>
    <select name="prichina" title="Причина «Компания не понравилась» или очередь «Дубль». Числа – по нынешнему статусу">
      <option value="">Причина отказа: любая</option>
      {% for p, n in choices.prichiny %}<option value="{{ p }}" {% if request.query_params.get('prichina') == p %}selected{% endif %}>{{ 'без причины' if p == 'bez_prichiny' else p }} · {{ n }}</option>{% endfor %}
      <option value="dubl" {% if request.query_params.get('prichina') == 'dubl' %}selected{% endif %}>Дубль – уже работают · {{ choices.dubl_n }}</option>
    </select>
    <label class="check" title="«Компания не понравилась», а от продавца ни слова кроме причины"><input type="checkbox" name="bez_poyasneniya" value="1" {% if request.query_params.get('bez_poyasneniya') == '1' %}checked{% endif %}> Отказ без пояснения · {{ choices.bez_poyasneniya_n }}</label>
    {% for k in ('rez_p', 'kto_p') %}{% if request.query_params.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.query_params.get(k) }}">{% endif %}{% endfor %}
    <button type="submit">Показать</button>
  </div>
  {% endif %}
'''

STAT_BLOKI = r'''
  {# ======== для директора (владелец 08.10): все блоки – за период календаря выше #}
  {% set d = direktor %}
  {% macro ch(c) %}{% if c.n and c.url %}<a href="{{ c.url }}">{{ c.n }}</a>{% else %}{{ c.n }}{% endif %}{% endmacro %}

  <h2>Причины отказов по продавцам <span class="period-metka">{{ d.period_ru }}</span></h2>
  <p class="pometka">По последней отметке компании за период{% if d.kto %}, продавец {{ d.kto|fio }}{% endif %}. Каждая цифра открывает эти компании списком.</p>
  <div style="overflow-x:auto"><table class="stat">
    <thead><tr><th>Продавец</th><th>Отмечено компаний</th><th>Взял в работу</th>{% for nz in d.kolonki_nazv %}<th>{{ nz }}</th>{% endfor %}<th>Не понравилась, всего</th><th>из них без пояснения</th><th>Дубль – уже работают</th></tr></thead>
    <tbody>
    {% for s in d.prichiny %}
      <tr{% if s.itog %} class="itog"{% endif %}><td>{% if s.itog %}Все продавцы{% else %}{{ s.kto|fio }}{% endif %}</td><td>{{ ch(s.otmecheno) }}</td><td>{{ ch(s.v_rabote) }}</td>{% for c in s.pr %}<td>{{ ch(c) }}</td>{% endfor %}<td>{{ ch(s.otkazov) }}</td><td>{{ ch(s.bez_poyasn) }}</td><td>{{ ch(s.dubl) }}</td></tr>
    {% else %}<tr><td colspan="9">Продавцов нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>

  <h2>Темп и прогноз <span class="period-metka">{{ d.period_ru }}</span></h2>
  <p class="pometka">Отмечено – компании, у которых последняя отметка за период у этого продавца. «В день работы» – на день, когда были отметки; «в календарный день» – на {{ d.dney }} дн. периода. Прогноз – на сколько рабочих дней хватит нынешней очереди при темпе «в день работы».</p>
  <table class="stat">
    <thead><tr><th>Продавец</th><th>Отмечено</th><th>Дней с отметками</th><th>В день работы</th><th>В календарный день</th><th>В очереди сейчас</th><th>Хватит очереди</th><th>Последняя отметка</th></tr></thead>
    <tbody>
    {% for t in d.temp %}
      <tr{% if t.itog %} class="itog"{% endif %}><td>{% if t.itog %}Все продавцы{% else %}{{ t.kto|fio }}{% endif %}</td><td>{{ ch(t.otmecheno) }}</td><td>{{ t.dney_rab }}</td><td>{{ ('%.1f'|format(t.v_den_rab)).replace('.', ',') if t.dney_rab else '–' }}</td><td>{{ ('%.1f'|format(t.v_den_kal)).replace('.', ',') }}</td><td>{{ ch(t.ochered) }}</td><td>{% if t.prognoz is not none %}≈ {{ t.prognoz }} раб. дн.{% elif t.ochered.n %}<span class="prosr">темпа нет</span>{% else %}очередь пуста{% endif %}</td><td>{{ t.posled or '–' }}</td></tr>
    {% endfor %}
    </tbody>
  </table>

  <h2>Где берут в работу <span class="period-metka">{{ d.period_ru }}</span></h2>
  <p class="pometka">Доля «Взял в работу» среди компаний, отмеченных за период. Компания с двумя сегментами (ролями, источниками номера) считается в каждом. У «нет в битриксе» и «откуда номер» такого фильтра в списке нет – там цифры без ссылки.</p>
  <div class="razrezy">
  {% for r in d.razrezy %}
    <section>
      <h3>{{ r.nazv }}{% if r.vsego_znacheniy > r.stroki|length %} <span class="pometka">(первые {{ r.stroki|length }} из {{ r.vsego_znacheniy }})</span>{% endif %}</h3>
      <table class="stat">
        <thead><tr><th>{{ r.nazv }}</th><th>Отмечено</th><th>Взял в работу</th><th>Не понр.</th><th>Дубль</th><th>Доля в работу</th></tr></thead>
        <tbody>
        {% for z in r.stroki %}<tr><td>{{ z.znach }}</td><td>{{ ch(z.otmecheno) }}</td><td>{{ ch(z.v_rabote) }}</td><td>{{ ch(z.ne_ponravilas) }}</td><td>{{ ch(z.dubl) }}</td><td>{{ '%.0f'|format(z.dolya) }} %</td></tr>
        {% else %}<tr><td colspan="6">за период отметок нет</td></tr>{% endfor %}
        </tbody>
      </table>
    </section>
  {% endfor %}
  </div>

  <h2>Активность по часам <span class="period-metka">{{ d.period_ru }}, время московское</span></h2>
  <p class="pometka">Сколько отметок поставлено в каждый час. Считается тот, кто нажал кнопку.</p>
  <div style="overflow-x:auto"><table class="stat chasy">
    <thead><tr><th>Кто</th>{% for h in d.chasy_kolonki %}<th>{{ h }}</th>{% endfor %}<th>Всего</th></tr></thead>
    <tbody>
    {% for s in d.chasy %}
      <tr{% if s.itog %} class="itog"{% endif %}><td>{% if s.itog %}Все{% else %}{{ s.kto|fio }}{% endif %}</td>{% for n in s.po_chasam %}<td style="text-align:center;{% if n and not s.itog %}background:rgba(79,70,229,{{ '%.2f'|format(0.12 + 0.55 * n / d.chasy_max) }});{% endif %}">{{ n or '' }}</td>{% endfor %}<td>{{ s.vsego }}</td></tr>
    {% else %}<tr><td colspan="{{ d.chasy_kolonki|length + 2 }}">За период отметок нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>

  <h2>Лента действий <span class="period-metka">{{ d.period_ru }}</span></h2>
  <p class="pometka">{% if d.lenta_vsego > d.lenta|length %}Показаны последние {{ d.lenta|length }} из {{ d.lenta_vsego }}.{% else %}Всего действий: {{ d.lenta_vsego }}.{% endif %} Время московское, новые сверху. Название открывает карточку.</p>
  <div style="overflow-x:auto"><table class="stat lenta">
    <thead><tr><th>Время</th><th>Продавец</th><th>Компания</th><th>Что сделал</th><th>Комментарий</th><th>Следующий контакт</th></tr></thead>
    <tbody>
    {% for e in d.lenta %}
      <tr><td style="white-space:nowrap">{{ e.vremya }}</td>
        <td>{{ e.kto|fio }}{% if e.deystvoval != e.kto %} <span class="nead">(нажал {{ e.deystvoval|fio }})</span>{% endif %}</td>
        <td>{% if e.url %}<a href="{{ e.url }}">{{ e.nazvanie }}</a>{% else %}{{ e.nazvanie }}{% endif %}</td>
        <td><span class="st-l st-{{ e.rez }}">{{ e.chto }}</span>{% if e.prichina %}<br><span class="prosr">причина: {{ e.prichina }}</span>{% endif %}</td>
        <td>{{ e.tekst }}</td><td style="white-space:nowrap">{{ e.sled or '' }}</td></tr>
    {% else %}<tr><td colspan="6">За период действий нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>
'''

STAT_STILI = '''    .period-metka{font-size:14px;font-weight:400;color:#5a6472}
    table.stat a{color:#4f46e5;font-weight:600}
    table.stat tr.itog td{font-weight:700;background:#eef1f7}
    .razrezy{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:14px}
    .razrezy h3{margin:8px 0 0}
    table.chasy td,table.chasy th{padding:4px 6px}
    .st-l.st-ne_ponravilas{color:#9b1c1c;font-weight:600}
    .st-l.st-v_rabote{color:#17663a;font-weight:600}
    .bystrye a,.bystrye b{margin:0 2px}
    .bystrye b{color:var(--navy)}
'''

# ---------------------------------------------------------------------- проверка
if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import datetime as dt
    import json
    import logging
    import sqlite3
    import warnings
    from html import unescape
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    ZHIVAYA = os.environ['CENTRO_SALES_DB']
    shutil.copy2(ZHIVAYA, TEST_DB)
    os.environ['CENTRO_SALES_DB'] = TEST_DB          # всё ниже пишет только во временную копию
    os.environ['PARK_OCHERED_SALES_DB'] = TEST_DB
    zh = sqlite3.connect(ZHIVAYA)
    zh_do = (zh.execute('select count(*) from activity_log').fetchone()[0],
             zh.execute('select count(*) from company_state').fetchone()[0],
             zh.execute('select count(*) from company_comment').fetchone()[0])
    zh.close()

    from app.api import routes_centro_sales as rcs
    from app.api import routes_park as rp
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    proverit(rp.SALES_DB == TEST_DB, 'статистика читает временную копию')
    # ---------- синтетические отметки во временной копии
    b = sqlite3.connect(TEST_DB)
    b.row_factory = sqlite3.Row
    segodnya = (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()
    zanyatye = {str(r[0]) for r in b.execute('select inn from company_state')}
    po_prod = {}
    for r in b.execute('select username, inn from company_assignment order by assignment_score desc'):
        if str(r['inn']) not in zanyatye:
            po_prod.setdefault(r['username'], []).append(str(r['inn']))
    A, B_, C = po_prod['meyer1'], po_prod['meyer2'], po_prod['meyer3']
    PR = rcs.PRICHINY_NE_PONRAVILAS

    def zapis(inn, kto, rez, nazad, chas, minut, prichina=None, tekst='', deystvoval=None):
        msk = dt.datetime.combine(segodnya - dt.timedelta(days=nazad), dt.time(chas, minut))
        iso = (msk - dt.timedelta(hours=3)).replace(tzinfo=dt.timezone.utc).isoformat(timespec='seconds')
        a = deystvoval or kto
        body = ('Причина: %s' % prichina + ('. %s' % tekst if tekst else '')) if prichina else tekst
        if body:
            b.execute('insert into company_comment(inn,username,body,created_at,updated_at) values(?,?,?,?,?)',
                      (inn, a, body, iso, iso))
        b.execute('insert into activity_log(inn,username,action,payload_json,created_at) values(?,?,?,?,?)',
                  (inn, a, 'call_saved', json.dumps({'result': rez, 'next_contact': '', 'state_user': kto}), iso))
        b.execute('insert into company_state(inn,username,status,last_contact_at,next_contact_at,call_result,updated_at) '
                  'values(?,?,?,?,?,?,?) on conflict(inn,username) do update set status=excluded.status,'
                  'last_contact_at=excluded.last_contact_at,call_result=excluded.call_result,updated_at=excluded.updated_at',
                  (inn, kto, 'processed', iso, None, rez, iso))
    # по времени: сначала старые
    zapis(A[5], 'meyer1', 'v_rabote', 20, 13, 0, tekst='давно взял')
    zapis(A[4], 'meyer1', 'dubl', 8, 12, 0, tekst='уже работает Петров')
    zapis(C[1], 'meyer3', 'ne_ponravilas', 5, 14, 0, PR[1], 'только холодильники')
    zapis(B_[3], 'meyer2', 'ne_ponravilas', 3, 18, 45)                    # старая отметка без причины
    zapis(B_[1], 'meyer2', 'ne_ponravilas', 2, 10, 0, PR[2], 'звонил 3 раза. Писал.')
    zapis(B_[2], 'meyer2', 'v_rabote', 2, 10, 30)
    zapis(A[2], 'meyer1', 'ne_ponravilas', 1, 15, 5, PR[0], 'номер не существует')
    zapis(A[3], 'meyer1', 'ne_ponravilas', 1, 15, 30, PR[3])
    zapis(A[3], 'meyer1', 'v_rabote', 0, 7, 10, tekst='передумали, ждут КП')   # повторная отметка
    zapis(A[0], 'meyer1', 'ne_ponravilas', 0, 7, 15, PR[1])                   # без пояснения
    zapis(A[1], 'meyer1', 'v_rabote', 0, 7, 40, tekst='договорились на КП')
    zapis(B_[0], 'meyer2', 'dubl', 0, 7, 20)
    zapis(C[0], 'meyer3', 'v_rabote', 0, 7, 50, deystvoval='meyer_admin')  # админ за продавца
    b.commit()

    # ---------- независимый расчёт (своим кодом, не функциями панели)
    RX = re.compile(r'^Причина: (%s)(?:\.\s*(.*))?$' % '|'.join(re.escape(p) for p in PR + ['дубль']), re.S)

    def nezav(ot, do):
        posl = {}
        for r in b.execute("select id, inn, username, payload_json, created_at from activity_log "
                           "where action='call_saved' order by created_at, id"):
            msk = dt.datetime.fromisoformat(r['created_at']).astimezone(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=3)
            if not (ot <= msk.date() <= do):
                continue
            pl = json.loads(r['payload_json'])
            kom = b.execute('select body from company_comment where inn=? and username=? and created_at=?',
                            (r['inn'], r['username'], r['created_at'])).fetchone()
            m = RX.match(kom[0]) if kom else None
            posl[str(r['inn'])] = {'kto': pl.get('state_user') or r['username'], 'rez': pl['result'],
                                   'prichina': m.group(1) if m else '',
                                   'tekst': ((m.group(2) or '') if m else (kom[0] if kom else '')).strip()}
        po = {}
        for o in posl.values():
            s = po.setdefault(o['kto'], {'otmecheno': 0, 'v_rabote': 0, 'otkazov': 0, 'dubl': 0, 'bez': 0, 'pr': {}})
            s['otmecheno'] += 1
            if o['rez'] == 'v_rabote':
                s['v_rabote'] += 1
            if o['rez'] == 'dubl':
                s['dubl'] += 1
            if o['rez'] == 'ne_ponravilas':
                s['otkazov'] += 1
                s['pr'][o['prichina'] or 'bez_prichiny'] = s['pr'].get(o['prichina'] or 'bez_prichiny', 0) + 1
                if not o['tekst']:
                    s['bez'] += 1
        return po
    ot7 = segodnya - dt.timedelta(days=6)
    nz = nezav(ot7, segodnya)
    with rcs.sales.connect() as conn:
        sv = rcs._direktor_svodka(conn, ot7, segodnya, '')
    for s in sv['prichiny']:
        if s['itog']:
            continue
        n = nz.get(s['kto'], {'otmecheno': 0, 'v_rabote': 0, 'otkazov': 0, 'dubl': 0, 'bez': 0, 'pr': {}})
        moi = {'otmecheno': s['otmecheno']['n'], 'v_rabote': s['v_rabote']['n'], 'otkazov': s['otkazov']['n'],
               'dubl': s['dubl']['n'], 'bez': s['bez_poyasn']['n'],
               'pr': {p: c['n'] for p, c in zip(sv['kolonki'], s['pr']) if c['n']}}
        proverit(moi == n, '7 дней, %s: панель %s = независимо %s' % (s['kto'], moi, n))
    # ожидаемое руками (синтетика + отметка владельца, если она у meyer1)
    m3 = next(s for s in sv['prichiny'] if s['kto'] == 'meyer3')
    proverit(m3['otmecheno']['n'] == 2 and m3['v_rabote']['n'] == 1,
             'отметка админа за продавца засчитана продавцу (meyer3: отмечено 2, в работу 1)')
    m2 = next(s for s in sv['prichiny'] if s['kto'] == 'meyer2')
    proverit(m2['pr'][sv['kolonki'].index('bez_prichiny')]['n'] == 1 and m2['bez_poyasn']['n'] == 1,
             'старая отметка без причины: «без причины» 1 и «без пояснения» 1 у meyer2')
    m1 = next(s for s in sv['prichiny'] if s['kto'] == 'meyer1')
    proverit(m1['pr'][3]['n'] == 0, 'повторная отметка: «купили у конкурентов» сменилось на «в работу» и не считается')
    vsego_sob = sum(1 for r in b.execute("select created_at from activity_log where action='call_saved'")
                    if ot7 <= (dt.datetime.fromisoformat(r[0]).astimezone(dt.timezone.utc).replace(tzinfo=None)
                               + dt.timedelta(hours=3)).date() <= segodnya)
    itog_ch = next((s for s in sv['chasy'] if s.get('itog')), sv['chasy'][0] if sv['chasy'] else {'vsego': 0})
    proverit(itog_ch['vsego'] == vsego_sob, 'часы: всего %d = отметок в журнале за 7 дней %d' % (itog_ch['vsego'], vsego_sob))
    proverit(sv['lenta_vsego'] == vsego_sob, 'лента: %d действий = %d' % (sv['lenta_vsego'], vsego_sob))
    m4 = next(t for t in sv['temp'] if t['kto'] == 'meyer4')
    och4 = sum(1 for r in b.execute("select a.inn, coalesce(s.call_result,'new') from company_assignment a left join "
                                    "company_state s on s.inn=a.inn and s.username=a.username where a.username='meyer4'")
               if r[1] not in ('v_rabote', 'ne_ponravilas', 'dubl'))
    proverit(m4['ochered']['n'] == och4 and m4['prognoz'] is None, 'темп meyer4: очередь %d, без отметок – прогноза нет' % och4)
    t1 = next(t for t in sv['temp'] if t['kto'] == 'meyer1')
    print('      темп meyer1: отмечено %d, дней %d, в день %.1f, очередь %d, прогноз %s' % (
        t1['otmecheno']['n'], t1['dney_rab'], t1['v_den_rab'], t1['ochered']['n'], t1['prognoz']))

    # ---------- страницы
    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    vnutr.dependency_overrides[rcs.current_user] = lambda: ADMIN

    def chislo_strok(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1
    with TestClient(vnutr) as k:
        o = k.get(PUT + '/centro/stats?stat_ot=' + ot7.isoformat())
        st = o.text
        proverit(o.status_code == 200, 'статистика за 7 дней: %s' % o.status_code)
        io.open(os.path.join(DROP, 'centro2-dir-stats.html'), 'w', encoding='utf-8').write(st)
        for nado in ('Причины отказов по продавцам', 'Темп и прогноз', 'Где берут в работу',
                     'Активность по часам', 'Лента действий', 'name="stat_ot"', 'class="bystrye"'):
            proverit(nado in st, 'на странице: %s' % nado)
        ssylki = [(unescape(u), int(n)) for u, n in re.findall(r'<a href="(%s/centro\?[^"]*|%s/centro)">(\d+)</a>' % (PUT, PUT), st)]
        ssylki = list(dict.fromkeys(ssylki))
        neravny = []
        for u, n in ssylki:
            t = k.get(u).text
            if chislo_strok(t) != n:
                neravny.append((u, n, chislo_strok(t)))
        proverit(len(ssylki) >= 25 and not neravny,
                 'ссылки-цифры статистики: %d, число строк списка совпало у всех (расхождения: %s)' % (len(ssylki), neravny[:5]))
        # быстрые периоды открываются
        for nazv, u in re.findall(r'<a href="([^"]*stats[^"]*)">(сегодня|вчера|7 дней|30 дней|всё время)</a>', st)[:0]:
            pass
        for u, nazv in re.findall(r'<a href="([^"]*/centro/stats[^"]*)">(сегодня|вчера|7 дней|30 дней|всё время)</a>', st):
            proverit(k.get(unescape(u)).status_code == 200, 'быстрый период «%s» открывается' % nazv)
        # главная: строка директора и фильтры
        t = k.get(PUT + '/centro').text
        proverit('class="direktor-ryad"' in t, 'у админа строка «Директор» есть')
        t = k.get(PUT + '/centro?assigned_user=__net__')
        proverit(t.status_code == 200 and chislo_strok(t.text) == 0, '«без продавца»: 200, компаний %d' % chislo_strok(t.text))
        och2 = sum(1 for r in b.execute("select a.inn, coalesce(s.call_result,'new') from company_assignment a left join "
                                        "company_state s on s.inn=a.inn and s.username=a.username where a.username='meyer2'")
                   if r[1] not in ('v_rabote', 'ne_ponravilas', 'dubl'))
        proverit(chislo_strok(k.get(PUT + '/centro?assigned_user=meyer2').text) == och2,
                 'продавец meyer2 во «Всей очереди»: %d' % och2)
        # причина без периода – по нынешнему статусу, независимо
        sost = {str(r[0]): r[1] for r in b.execute('select inn, call_result from company_state')}
        nz_vse = {}
        for r in b.execute("select inn, username, created_at from activity_log where action='call_saved' order by created_at, id"):
            kom = b.execute('select body from company_comment where inn=? and username=? and created_at=?', tuple(r)).fetchone()
            m = RX.match(kom[0]) if kom else None
            nz_vse[str(r[0])] = (m.group(1) if m else '', ((m.group(2) or '') if m else (kom[0] if kom else '')).strip())
        for p in PR:
            ozh = sum(1 for inn, rez in sost.items() if rez == 'ne_ponravilas' and nz_vse.get(inn, ('', ''))[0] == p)
            n = chislo_strok(k.get(PUT + '/centro', params={'prichina': p}).text)
            proverit(n == ozh, 'причина «%s»: список %d = независимо %d' % (p[:28], n, ozh))
        ozh = sum(1 for rez in sost.values() if rez == 'dubl')
        proverit(chislo_strok(k.get(PUT + '/centro?prichina=dubl').text) == ozh, '«Дубль» в причинах: %d' % ozh)
        ozh = sum(1 for inn, rez in sost.items() if rez == 'ne_ponravilas' and not nz_vse.get(inn, ('', ''))[1])
        proverit(chislo_strok(k.get(PUT + '/centro?bez_poyasneniya=1').text) == ozh, 'отказ без пояснения: %d' % ozh)
        t = k.get(PUT + '/centro?call_status=v_rabote').text
        proverit('<input type="hidden" name="call_status" value="v_rabote">' in t, 'строка фильтров помнит вкладку')
        t = k.get(PUT + '/centro', params={'ot': ot7.isoformat(), 'do': segodnya.isoformat(), 'rez_p': 'v_rabote'}).text
        proverit('Отбор:' in t and 'последняя отметка: Взял в работу' in t, 'над списком написано, что отобрано')
        io.open(os.path.join(DROP, 'centro2-dir-glavnaya.html'), 'w', encoding='utf-8').write(
            k.get(PUT + '/centro', params={'prichina': PR[1]}).text)
        proverit(k.get(PUT + '/centro/spisok').status_code == 200, '«Список компаний» (общий блок статистики) открывается')
        o = k.get(PUT + '/centro/stats?stat_data=' + segodnya.isoformat())
        proverit(o.status_code == 200 and 'за ' + segodnya.strftime('%d.%m.%Y') in o.text, 'старая ссылка stat_data (один день) работает')
    # продавец
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 1, 'username': 'meyer1', 'role': 'sales', 'is_active': 1}
    with TestClient(vnutr) as k:
        t = k.get(PUT + '/centro').text
        proverit('class="direktor-ryad"' not in t, 'у продавца строки «Директор» нет')
        proverit(k.get(PUT + '/centro/stats').status_code == 403, 'статистика продавцу – 403')
    b.close()
    zh = sqlite3.connect(ZHIVAYA)
    zh_posle = (zh.execute('select count(*) from activity_log').fetchone()[0],
                zh.execute('select count(*) from company_state').fetchone()[0],
                zh.execute('select count(*) from company_comment').fetchone()[0])
    zh.close()
    proverit(zh_do == zh_posle, 'рабочая база продаж не тронута: %s = %s' % (zh_do, zh_posle))
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ---------------------------------------------------------------------- правки
os.makedirs(BEKAP, exist_ok=True)
log = []
nado = sdelano = 0
IZMENENY = {}          # имя бэкапа -> файл: откат, если проверка не прошла


def pravka(p, staro, novo, imya, priznak):
    global nado, sdelano
    nado += 1
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    n = t.count(staro)
    if n != 1:
        log.append('[ЯКОРЬ: %d] %s – не правлю' % (n, imya))
        return
    b = os.path.join(BEKAP, os.path.basename(p))
    if not os.path.exists(b):
        shutil.copy2(p, b)
        IZMENENY[os.path.basename(p)] = p
    io.open(p, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    sdelano += 1
    log.append('[ок] ' + imya)


# --- routes_centro_sales: код директора в конец файла
nado += 1
t = io.open(RCS, encoding='utf-8').read()
if '_direktor_svodka' in t:
    sdelano += 1
    log.append('[уже] код директора')
else:
    shutil.copy2(RCS, os.path.join(BEKAP, 'routes_centro_sales.py'))
    IZMENENY['routes_centro_sales.py'] = RCS
    io.open(RCS, 'w', encoding='utf-8').write(t.rstrip('\n') + '\n' + RCS_KOD)
    sdelano += 1
    log.append('[ок] код директора')

pravka(RCS, '''        if requested_owner and (
            not assignment or assignment["username"] != requested_owner
        ):
            continue
''', '''        if requested_owner == "__net__":            # директор: «без продавца»
            if assignment:
                continue
        elif requested_owner and (
            not assignment or assignment["username"] != requested_owner
        ):
            continue
''', 'centro(): «без продавца»', 'requested_owner == "__net__"')
pravka(RCS, '''    out: list[dict] = []
    for company in rows:
        if exact_inn:''', '''    dir_pred = _direktor_predikat(params)          # фильтры директора (None – не заданы)
    out: list[dict] = []
    for company in rows:
        if exact_inn:''', '_matches: предикат директора', 'dir_pred = _direktor_predikat(params)')
pravka(RCS, '''        if assigned_user and company.get("assigned_user") != assigned_user:
            continue
''', '''        if assigned_user == "__net__":
            if company.get("assigned_user"):
                continue
        elif assigned_user and company.get("assigned_user") != assigned_user:
            continue
        if dir_pred is not None and not dir_pred(company):
            continue
''', '_matches: без продавца и фильтры директора', 'if dir_pred is not None and not dir_pred(company)')
pravka(RCS, '        if not call_status and not perezvon and company.get("call_result") in sales.CALL_RESULT_CHOICES:',
       '        # с фильтрами директора обработанные видны: он и ищет отмеченные\n'
       '        if not call_status and not perezvon and dir_pred is None and company.get("call_result") in sales.CALL_RESULT_CHOICES:',
       '_matches: «Вся очередь» не прячет отмеченные при отборе директора', 'and dir_pred is None and company.get')
pravka(RCS, '''    choices["est_oborudovanie"] = bool(choices.get("model") or choices.get("equipment")
                                       or choices.get("sostoyanie") or choices.get("medium"))
''', '''    choices["est_oborudovanie"] = bool(choices.get("model") or choices.get("equipment")
                                       or choices.get("sostoyanie") or choices.get("medium"))
    if user["role"] == "admin":
        choices.update(_direktor_vybor(companies, vidimye_vladeltsu, assignments))
''', 'centro(): счётчики у фильтров директора', 'choices.update(_direktor_vybor(')
pravka(RCS, '            "kommentarii": kommentarii,\n',
       '            "kommentarii": kommentarii,\n            "dir_opis": _dir_opis(request.query_params),\n',
       'centro(): описание отбора', '"dir_opis": _dir_opis(')
# --- статистика
pravka(RCS, '''    stat_user = (request.query_params.get("stat_user") or "").strip()
    sc = _sq_st.connect(''', '''    stat_user = (request.query_params.get("stat_user") or "").strip()
    stat_ot_param = (request.query_params.get("stat_ot") or "").strip()
    stat_ot_d = _data_param(stat_ot_param)
    if stat_ot_d is None:
        stat_ot_param = ""
    sc = _sq_st.connect(''', 'stats: параметр stat_ot', 'stat_ot_param = (request.query_params.get("stat_ot")')
pravka(RCS, '        statblok = _rp._statblok(sc, user, stat_den, stat_user)\n',
       '        statblok = _rp._statblok(sc, user, stat_den, stat_user, den_ot=stat_ot_d)\n',
       'stats: период в календарный блок', '_rp._statblok(sc, user, stat_den, stat_user, den_ot=stat_ot_d)')
pravka(RCS, '''        d = {k: v for k, v in {"stat_data": stat_data_param, "stat_user": stat_user,
                               "user": vybrannyy, **kw}.items() if v}''',
       '''        d = {k: v for k, v in {"stat_ot": stat_ot_param, "stat_data": stat_data_param,
                               "stat_user": stat_user, "user": vybrannyy, **kw}.items() if v}''',
       'stats: stat_ot в ссылках', '{"stat_ot": stat_ot_param, "stat_data": stat_data_param,')
pravka(RCS, '''        return "%s/centro/stats%s" % (BP, ("?" + _urlenc_st(d)) if d else "")
    return templates.TemplateResponse(
        request,
        "centro_stats.html",''', '''        return "%s/centro/stats%s" % (BP, ("?" + _urlenc_st(d)) if d else "")
    # --- для директора: всё за тот же период, что календарный блок
    d_ot = datetime.date.fromisoformat(statblok["ot_iso"])
    d_do = datetime.date.fromisoformat(statblok["den_iso"])
    with sales.connect() as conn_d:
        direktor = _direktor_svodka(conn_d, d_ot, d_do, stat_user)
        pervyy = conn_d.execute(
            "SELECT MIN(created_at) FROM activity_log WHERE action='call_saved'").fetchone()[0]
    _statblok_ssylki(statblok, d_ot, d_do)
    statblok["period_mozhno"] = True
    statblok["bystrye"] = _bystrye_periody(stat_ssylka, pervyy, d_ot, d_do)
    return templates.TemplateResponse(
        request,
        "centro_stats.html",''', 'stats: расчёт блоков директора', 'direktor = _direktor_svodka(conn_d')
pravka(RCS, '            "statblok": statblok,\n            "sohranit": {"user": vybrannyy} if vybrannyy else {},',
       '            "statblok": statblok,\n            "direktor": direktor,\n            "sohranit": {"user": vybrannyy} if vybrannyy else {},',
       'stats: direktor в шаблон', '"direktor": direktor,')

# --- routes_park._statblok: период
pravka(RP, 'def _statblok(conn, user: dict, den, kto: str) -> dict:',
       'def _statblok(conn, user: dict, den, kto: str, den_ot=None) -> dict:', '_statblok: параметр den_ot', 'kto: str, den_ot=None)')
pravka(RP, '    den = den or segodnya\n',
       '    den = den or segodnya\n'
       '    # период для директора (страница статистики): [ot, den]; без den_ot – один день, как было\n'
       '    ot = den_ot if (den_ot is not None and den_ot <= den) else den\n',
       '_statblok: начало периода', 'ot = den_ot if (den_ot is not None and den_ot <= den) else den')
pravka(RP, '        if d == den:\n            za_den[kl] = str(pl.get("result") or "")',
       '        if ot <= d <= den:\n            za_den[kl] = str(pl.get("result") or "")',
       '_statblok: отметки за период', 'if ot <= d <= den:')
pravka(RP, '        "den_iso": den.isoformat(), "den_ru": den.strftime("%d.%m.%Y"),\n',
       '        "den_iso": den.isoformat(), "den_ru": den.strftime("%d.%m.%Y"),\n'
       '        "ot_iso": ot.isoformat(), "ot_ru": ot.strftime("%d.%m.%Y"), "period": ot != den,\n',
       '_statblok: границы периода в ответе', '"ot_iso": ot.isoformat()')

# --- шаблон календарного блока
SB = os.path.join(T, '_statblok.html')
pravka(SB, '''    {% macro chetyre(d) %}<td class="razd">{{ d.v_rabote }}</td><td>{{ d.ne_ponravilas }}</td><td>{{ d.dubl }}</td><td>{{ d.ochered }}</td>{% endmacro %}''',
       '''    {% macro yach(n, url) %}{% if n and url %}<a href="{{ url }}">{{ n }}</a>{% else %}{{ n }}{% endif %}{% endmacro %}
    {# ссылки у цифр – только на странице статистики (там их кладёт маршрут) #}
    {% macro chetyre(d, ss=none) %}<td class="razd">{{ yach(d.v_rabote, ss.v_rabote if ss else '') }}</td><td>{{ yach(d.ne_ponravilas, ss.ne_ponravilas if ss else '') }}</td><td>{{ yach(d.dubl, ss.dubl if ss else '') }}</td><td>{{ yach(d.ochered, ss.ochered if ss else '') }}</td>{% endmacro %}''',
       'календарь: цифры-ссылки', '{% macro yach(n, url) %}')
pravka(SB, '''          <tr class="itog"><td>Все продавцы</td>{{ chetyre(statblok.itog.den) }}{{ chetyre(statblok.itog.vse) }}</tr>''',
       '''          <tr class="itog"><td>Все продавцы</td>{{ chetyre(statblok.itog.den, statblok.itog_ss_den) }}{{ chetyre(statblok.itog.vse, statblok.itog_ss_vse) }}</tr>''',
       'календарь: ссылки в итоге', 'statblok.itog_ss_den')
pravka(SB, '''{{ chetyre(z.den) }}{{ chetyre(z.vse) }}</tr>''',
       '''{{ chetyre(z.den, z.ss_den) }}{{ chetyre(z.vse, z.ss_vse) }}</tr>''', 'календарь: ссылки в строках', 'chetyre(z.den, z.ss_den)')
pravka(SB, '''        <label>Дата
          <input type="date" name="stat_data" value="{{ statblok.den_iso }}" max="{{ statblok.segodnya_iso }}" onchange="this.form.submit()">
        </label>''', '''        {% if statblok.period_mozhno %}
        <label>С
          <input type="date" name="stat_ot" value="{{ statblok.ot_iso }}" max="{{ statblok.segodnya_iso }}" onchange="this.form.submit()">
        </label>
        <label>по
          <input type="date" name="stat_data" value="{{ statblok.den_iso }}" max="{{ statblok.segodnya_iso }}" onchange="this.form.submit()">
        </label>
        {% else %}
        <label>Дата
          <input type="date" name="stat_data" value="{{ statblok.den_iso }}" max="{{ statblok.segodnya_iso }}" onchange="this.form.submit()">
        </label>
        {% endif %}''', 'календарь: «с … по …»', 'name="stat_ot"')
pravka(SB, '''        <span>
          {% if not statblok.eto_segodnya %}''', '''        {% if statblok.bystrye %}<span class="bystrye">{% for b in statblok.bystrye %}{% if b.aktiven %}<b>{{ b.nazv }}</b>{% else %}<a href="{{ b.url }}">{{ b.nazv }}</a>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}</span>{% endif %}
        <span>
          {% if statblok.bystrye %}{% elif not statblok.eto_segodnya %}''', 'календарь: быстрые периоды', 'class="bystrye"')
pravka(SB, '''{% if statblok.eto_segodnya %} (сегодня){% endif %}</th>''',
       '''{% if statblok.eto_segodnya and not statblok.period %} (сегодня){% endif %}</th>''',
       'календарь: «(сегодня)» только для одного дня', 'and not statblok.period %} (сегодня)')
pravka(SB, '''<th class="gr razd" colspan="4">за {{ statblok.den_ru }}''',
       '''<th class="gr razd" colspan="4">{% if statblok.period %}с {{ statblok.ot_ru }} по {{ statblok.den_ru }}{% else %}за {{ statblok.den_ru }}{% endif %}''',
       'календарь: заголовок периода', 'с {{ statblok.ot_ru }} по {{ statblok.den_ru }}')
pravka(SB, '''        За день – последняя отметка по компании за этот день по Москве; очередь – на конец дня.''',
       '''        {% if statblok.period %}За период – последняя отметка по компании за период по Москве; очередь – на конец последнего дня.{% else %}За день – последняя отметка по компании за этот день по Москве; очередь – на конец дня.{% endif %}''',
       'календарь: пояснение периода', 'За период – последняя отметка')

# --- страница статистики
CS = os.path.join(T, 'centro_stats.html')
pravka(CS, '''  {% include "_statblok.html" %}
''', '''  {% include "_statblok.html" %}
''' + STAT_BLOKI, 'статистика: блоки директора', 'Причины отказов по продавцам')
pravka(CS, '''    .pometka{color:#5a6472;font-size:12px;margin:4px 0 14px}
''', '''    .pometka{color:#5a6472;font-size:12px;margin:4px 0 14px}
''' + STAT_STILI, 'статистика: стили', '.period-metka{')
pravka(CS, '''  <h2>По продавцам: за день и за всё время</h2>''',
       '''  <h2>По продавцам: за период и за всё время</h2>''', 'статистика: заголовок', 'По продавцам: за период и за всё время')
pravka(CS, '''        <td>{{ metki.get(kod, kod) }}</td>
        <td>{{ n }}</td>''', '''        <td>{{ metki.get(kod, kod) }}</td>
        <td><a href="{{ base_path }}/centro?call_status={{ kod }}">{{ n }}</a></td>''',
       'статистика: «по результатам звонка» – ссылки', 'centro?call_status={{ kod }}">{{ n }}</a>')
pravka(CS, '''        <td>{{ p.vidno }}</td><td>{{ p.vidno_ochered }}</td>''',
       '''        <td>{{ p.vidno }}</td><td>{% if p.vidno_ochered %}<a href="{{ base_path }}/centro?assigned_user={{ p.username }}">{{ p.vidno_ochered }}</a>{% else %}0{% endif %}</td>''',
       'статистика: «в очереди» – ссылка', 'centro?assigned_user={{ p.username }}">{{ p.vidno_ochered }}')

# --- главная
C = os.path.join(T, 'centro.html')
pravka(C, '''<form class="filterbar" method="get">
''', '''<form class="filterbar" method="get">
  {# вкладка («Взял в работу» и т. п.) – часть отбора: без этого «Найти» выбрасывал на «Всю очередь» #}
  {% if request.query_params.get('call_status') %}<input type="hidden" name="call_status" value="{{ request.query_params.get('call_status') }}">{% endif %}
''', 'главная: строка фильтров помнит вкладку', 'без этого «Найти» выбрасывал на «Всю очередь»')
pravka(C, '''  <b class="total-count">{{ total }} компаний</b>
</form>''', '''  <b class="total-count">{{ total }} компаний</b>
''' + FILTR_DIREKTORA + '''</form>''', 'главная: строка «Директор»', 'class="direktor-ryad"')
pravka(C, '''  <form method="get" class="dialog-form">
''', '''  <form method="get" class="dialog-form">
    {# отбор директора не теряется при «Применить» в расширенных фильтрах #}
    {% for k in ('ot', 'do', 'prichina', 'bez_poyasneniya', 'rez_p', 'kto_p') %}{% if request.query_params.get(k) %}<input type="hidden" name="{{ k }}" value="{{ request.query_params.get(k) }}">{% endif %}{% endfor %}
''', 'расширенные фильтры: отбор директора не теряется', "for k in ('ot', 'do', 'prichina'")
pravka(C, '.hide-company{margin:8px 0 0;',
       '.direktor-ryad{flex-basis:100%;display:flex;flex-wrap:wrap;gap:9px;align-items:center;'
       'padding-top:8px;border-top:1px dashed var(--line)}\n'
       '.direktor-metka{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}\n'
       '.direktor-period{display:flex;gap:6px;align-items:center;font-size:13px;color:#33373e}\n'
       '.direktor-period input{padding:7px 8px}\n'
       '.hide-company{margin:8px 0 0;', 'главная: стили строки директора', '.direktor-ryad{')
L = os.path.join(T, '_ochered_spisok.html')
pravka(L, '''    <b>{% if total %}Компании {{ ot }}–{{ do }} из {{ total }}{% else %}Компании не найдены{% endif %}</b>
''', '''    <b>{% if total %}Компании {{ ot }}–{{ do }} из {{ total }}{% else %}Компании не найдены{% endif %}</b>
    {% if dir_opis %}<span class="dir-opis">Отбор: {{ dir_opis }} · <a href="{{ base_path }}/centro">сбросить</a></span>{% endif %}
''', 'список: «Отбор: …»', 'class="dir-opis"')
pravka(L, '.komp-yach{display:flex;',
       '.dir-opis{color:var(--navy);background:#eef1fb;border:1px solid #d5daf3;border-radius:6px;padding:3px 9px}\n'
       '.komp-yach{display:flex;', 'список: стиль «Отбор»', '.dir-opis{')

for x in log:
    print('   ' + x)
print('правок внесено: %d из %d' % (sdelano, nado))
print('бэкап: %s' % BEKAP)
if sdelano != nado:
    for imya, kuda in IZMENENY.items():
        shutil.copy2(os.path.join(BEKAP, imya), kuda)
    print('НЕ ВСЕ ПРАВКИ ВНЕСЕНЫ – %d файлов возвращены из бэкапа, перезапуска нет' % len(IZMENENY))
    raise SystemExit(1)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=1200, cwd=KOREN, env=sreda)
vyvod = r.stdout.decode('utf-8', 'replace')
if r.returncode:
    vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-4000:]
try:
    os.remove(TEST_DB)
except OSError as e:
    vyvod += '\nвременная копия не удалена: %s' % e
io.open(os.path.join(DROP, 'centro2-direktor-proverka.txt'), 'w', encoding='utf-8').write(vyvod)
ok = (r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod)
if ok:
    p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in p.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
    time.sleep(2)
    lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    lg.write('\n===== перезапуск: фильтры и статистика директора %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
    lg.flush()
    subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                     stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                     close_fds=True, env=sreda)
    time.sleep(10)
    import urllib.request
    try:
        kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
    except Exception as e:  # noqa: BLE001
        kod = str(e)[:80]
    print('перезапущено, вход: %s' % kod)
else:
    # Шаблоны боевой процесс перечитывает сам, а код – только после перезапуска: оставить
    # новые шаблоны при старом коде нельзя. Возвращаю ВСЕ файлы из бэкапа.
    for imya, kuda in IZMENENY.items():
        shutil.copy2(os.path.join(BEKAP, imya), kuda)
    print('ПРОВЕРКА НЕ ПРОШЛА – все %d файлов возвращены из бэкапа, процесс не перезапускался' % len(IZMENENY))
print()
print('===== ПРОВЕРКА (полностью: centro2-direktor-proverka.txt на дропе) =====')
sys.stdout.write(vyvod[-4500:])
