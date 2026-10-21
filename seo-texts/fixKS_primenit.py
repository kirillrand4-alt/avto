# -*- coding: utf-8 -*-
r"""fixKS (21.10): статистика админа в панели КЦ (/obzvon/centro/stats) – перенос со страницы Meyer.

Что меняет в C:\seostat\app (больше ничего):
  * app\api\routes_centro_sales.py – в конец дописан блок fixKS: маршрут GET /centro/stats (админ – 200,
    продавец – 403) и функции _fixKS_*; всё только читает базы (sqlite mode=ro);
  * app\templates\fixKS_stats.html – новый шаблон, его рендерит только этот маршрут;
  * app\templates\centro.html – в шапке у админа ссылка «Статистика» в той же строке, что «Распределение»,
    под условием `fixKS_stats_est is defined`: глобал ставит только новый код, поэтому процесс со старым
    Python (8014 /p25 без перезапуска) рендерит шапку байт в байт как раньше.

Проверка (TestClient, копии баз в C:\seostat\_stage\fixKS-<время>\db): три варианта кода – «до», «после» и
«смесь» (старый Python + новые шаблоны = 8014 до перезапуска), два набора баз (КЦ /obzvon и p25 /p25). Под admin,
user1, user2, user3: главная, вкладки, карточки, статистика; действия продавцов (сохранить звонок, скрыть
компанию) на своей копии базы и дамп базы после них. «Смесь» = «до» байт в байт; «после» = «до» везде, кроме
ссылки «Статистика» у админа; статистика – 404 до, 200 админу и 403 продавцу после. На странице статистики:
очередь менеджера = «N компаний» его главной и тот же порядок первой страницы; каждая цифра-ссылка = числу
строк своего списка; карточки по ссылкам открываются.

    python3 zapusk_na_servere.py fixKS_primenit.py --suho      # только stage и проверки
    python3 zapusk_na_servere.py fixKS_primenit.py --primenit  # замок C:\seostat\_zamok.txt, копии, запись, nssm restart obzvon
Откат: файлы из C:\seostat\_bekap\fixKS-<время>\app (fixKS_stats.html удалить) и `nssm restart obzvon`.
"""


# ======================================================================== код: routes_centro_sales
RCS_KOD = r'''


# ===================================================================== fixKS (21.10): статистика админа
# Владелец 21.10: «сделай статистику так же, как у Meyer» – страница /centro/stats панели Meyer
# (C:\centro2) перенесена в панель КЦ. Всё только читает (sqlite mode=ro). Блоков, для которых в данных
# КЦ нет полей (вердикт «покупатель Meyer», метки Битрикса, руководители, базы, сегменты, причины
# отказа), здесь нет. Очередь считается так же, как её строит главная: компания есть в каталоге, не
# скрыта, не перенесена во вкладки («Взял в работу», «Не понравилась», «Дубль»), порядок – тот же
# _queue_rank. ОДНА ФУНКЦИЯ НА ЦИФРУ И НА СПИСОК: каждая цифра-ссылка считается как длина списка
# _fixKS_otbor(), который она открывает, поэтому число и строки по ссылке совпадают по построению.
import datetime as _ks_dt
import json as _ks_json
import math as _ks_math
import re as _ks_re
import sqlite3 as _ks_sq

# Шапка (centro.html) показывает «Статистика» только процессу, в котором этот маршрут есть: шаблоны
# общие у 8012 и 8014, а код процесс подхватывает лишь после перезапуска.
templates.env.globals["fixKS_stats_est"] = True

_KS_MSK = _ks_dt.timedelta(hours=3)
_KS_VKLADKI = tuple(sales.CALL_RESULT_CHOICES)          # v_rabote, ne_ponravilas, dubl
_KS_NEDOZVON = ("no_answer", "ne_dozvonilsya")           # попытка без исхода (в данных КЦ пока нет)
_KS_SKRYTIE = (
    ("tv", "только турбовоздуходувка", r"турбовоздуходувк"),
    ("mertv", "недействующее юрлицо", r"мёртв|мертв|ликвидир|исключ|прекращ|банкрот|недейству"),
    ("neprof", "непрофильное по ОКВЭД", r"непрофильн|непроизводств|оквэд|образовани|здравоохран|нецелев"),
    ("pusto", "не осталось видимых фактов", r"пусто|не осталось ни одного видимого|оказались мусором|нет фактов|фактов не было"),
    ("necentr", "центробежная машина не подтверждена",
     r"центробеж|садов|инструмент|бытов|марки в фактах|суд моделей|не машина|не компрессор|поршнев|винтов"),
)
_KS_SKRYTIE_NAZV = dict([(k, n) for k, n, _p in _KS_SKRYTIE] + [("bez", "без причины"), ("drugoe", "другая причина")])
_KS_RAZREZY = (("region", "Регион"), ("verdikt", "Вердикт по центробежной машине"),
               ("kontakty", "Кто есть в контактах"))
_KS_RAZREZ_NAZV = dict(_KS_RAZREZY)
_KS_VID_NAZV = {"kat": "в каталоге", "och": "показывается в «Вся очередь»", "vkl": "во вкладках",
                "skr": "скрыта", "vne": "нет в каталоге"}
_KS_REZ_NAZV = {"bez_komm": "не понравилась без комментария", "prochee": "другие отметки"}


def _fixKS_msk(znach):
    """UTC ISO из базы -> наивное московское datetime (или None)."""
    if not znach:
        return None
    try:
        dt = _ks_dt.datetime.fromisoformat(str(znach).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_ks_dt.timezone.utc).replace(tzinfo=None)
    return dt + _KS_MSK


def _fixKS_segodnya():
    return (_ks_dt.datetime.now(_ks_dt.timezone.utc).replace(tzinfo=None) + _KS_MSK).date()


def _fixKS_data(z):
    z = str(z or "").strip()
    if not z:
        return None, ""
    try:
        return _ks_dt.date.fromisoformat(z), ""
    except ValueError:
        return None, z


def _fixKS_period(params, pervyy) -> dict:
    """Период [ot, do] по Москве. Перевёрнутые, будущие и нераспознанные даты не подменяются молча."""
    segodnya = _fixKS_segodnya()
    soob = []
    vse = params.get("stat_vse") == "1"
    ot, plokh_ot = _fixKS_data(params.get("stat_ot"))
    do, plokh_do = _fixKS_data(params.get("stat_data"))
    for p in (plokh_ot, plokh_do):
        if p:
            soob.append("Дата «%s» не распознана – взят день по умолчанию." % p[:20])
    if vse:
        ot, do = min(pervyy or segodnya, segodnya), segodnya
    else:
        do = do or segodnya
        if do > segodnya:
            soob.append("Конец периода %s ещё не наступил – взято сегодня." % do.strftime("%d.%m.%Y"))
            do = segodnya
        ot = ot or do
        if ot > segodnya:
            soob.append("Начало периода %s ещё не наступило – взято сегодня." % ot.strftime("%d.%m.%Y"))
            ot = segodnya
        if ot > do:
            soob.append("Начало периода позже конца – даты переставлены местами.")
            ot, do = do, ot
    return {"ot": ot, "do": do, "vse": vse, "soob": soob, "segodnya": segodnya}


def _fixKS_period_ru(ot, do) -> str:
    if ot == do:
        return "за %s" % do.strftime("%d.%m.%Y")
    return "с %s по %s" % (ot.strftime("%d.%m.%Y"), do.strftime("%d.%m.%Y"))


def _fixKS_skrytie_gruppa(reason) -> str:
    r = str(reason or "").strip()
    if not r:
        return "bez"
    for kod, _n, pat in _KS_SKRYTIE:
        if _ks_re.search(pat, r, _ks_re.I):
            return kod
    return "drugoe"


def _fixKS_tabl(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except _ks_sq.OperationalError:          # таблицы ещё нет – значит, и данных нет
        return []


def _fixKS_dannye(params) -> dict:
    """Всё, из чего считается страница: каталог, назначения, статусы, скрытые, журнал. Только чтение."""
    kat: dict = {}
    try:
        for row in catalog.list_companies():
            inn = sales.normalize_inn(row.get("inn"))
            if inn and inn not in kat:
                kat[inn] = {"nazv": str(row.get("predpriyatie") or row.get("name") or row.get("nazvanie") or inn),
                            "region": str(row.get("region") or "").strip()}
    except catalog.CentroDbUnavailable:
        pass
    conn = _ks_sq.connect(sales.sales_db_path().resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = _ks_sq.Row
    try:
        lyudi = {r["username"]: {"role": r["role"], "aktiven": bool(r["is_active"])}
                 for r in conn.execute("SELECT username, role, is_active FROM users")}
        naznach = {str(r["inn"]): dict(r) for r in conn.execute("SELECT * FROM company_assignment")}
        sost = {(str(r["inn"]), r["username"]): dict(r) for r in conn.execute("SELECT * FROM company_state")}
        skryt = {str(r["inn"]): {"reason": r["reason"] or "", "kto": r["username"] or ""} for r in _fixKS_tabl(
            conn, "SELECT inn, reason, username FROM hidden_item WHERE kind='company'")}
        komm = {(str(r["inn"]), r["username"], r["created_at"]): r["body"] or ""
                for r in conn.execute("SELECT inn, username, body, created_at FROM company_comment")}
        kommentariev = conn.execute("SELECT COUNT(*) FROM company_comment").fetchone()[0]
        verd = {str(r[0]): str(r[1] or "") for r in _fixKS_tabl(conn, "SELECT inn, verdikt FROM sud_verdikt")}
        zhurnal = [dict(r) for r in conn.execute(
            "SELECT id, inn, username, action, payload_json, created_at FROM activity_log ORDER BY created_at, id")]
    finally:
        conn.close()
    prodavcy = sorted(u for u, x in lyudi.items() if x["role"] == "sales" and x["aktiven"])

    sob = []
    for r in zhurnal:
        kogda = _fixKS_msk(r["created_at"])
        if kogda is None:
            continue
        try:
            pl = _ks_json.loads(r["payload_json"] or "{}")
        except ValueError:
            pl = {}
        if not isinstance(pl, dict):
            pl = {}
        inn = str(r["inn"] or "")
        d = r["action"]
        kto = pl.get("state_user") or pl.get("to") or pl.get("komu") or pl.get("stalo") or r["username"]
        rez = str(pl.get("result") or "") if d == "call_saved" else (d if d in _KS_NEDOZVON else "")
        sob.append({"id": r["id"], "inn": inn, "deystvie": d, "deystvoval": r["username"] or "",
                    "kto": str(kto or ""), "rez": rez, "kogda": kogda, "den": kogda.date(),
                    "sled": str(pl.get("next_contact") or ""), "pl": pl,
                    "tekst": komm.get((inn, r["username"], r["created_at"]), "") if d == "call_saved" else ""})
    pervyy = min((z["den"] for z in sob if z["deystvie"] == "call_saved"), default=None)
    per = _fixKS_period(params, pervyy)
    ot, do = per["ot"], per["do"]

    # назначения: что с каждой компанией сейчас и видна ли она менеджеру
    stroki: dict = {}
    for inn, a in naznach.items():
        u = a["username"]
        st = sost.get((inn, u)) or {}
        rez = st.get("call_result") or "new"
        if inn not in kat:
            vid = "vne"
        elif inn in skryt:
            vid = "skr"
        elif rez in _KS_VKLADKI:
            vid = "vkl"
        else:
            vid = "och"
        nz = _fixKS_msk(a.get("assigned_at"))
        sk = skryt.get(inn) or {}
        stroki[inn] = {"inn": inn, "u": u, "rez": rez, "vid": vid, "v_kat": inn in kat,
                       "skr": inn in skryt, "skr_gr": _fixKS_skrytie_gruppa(sk.get("reason")) if sk else "",
                       "skr_reason": sk.get("reason", ""), "skr_kto": sk.get("kto", ""),
                       "score": float(a.get("assignment_score") or 0), "has_phone": a.get("has_phone"),
                       "has_tech": a.get("has_tech"), "has_purchaser": a.get("has_purchaser"),
                       "naznacheno_den": nz.date() if nz else None,
                       "call_result": st.get("call_result"), "last_contact_at": st.get("last_contact_at"),
                       "next_contact_at": st.get("next_contact_at"),
                       "nazv": (kat.get(inn) or {}).get("nazv", ""), "region": (kat.get(inn) or {}).get("region", "")}

    # последняя отметка компании за период (компании каталога, в том числе скрытые позже)
    posl: dict = {}
    for z in sob:
        if z["deystvie"] == "call_saved" and z["inn"] in kat and ot <= z["den"] <= do:
            n = posl[z["inn"]]["n"] + 1 if z["inn"] in posl else 1
            posl[z["inn"]] = dict(z, n=n)

    # очередь на конец периода: видна сейчас, назначена к концу периода и к концу периода не перенесена
    posl_do: dict = {}
    est_sob = set()
    for z in sob:
        if z["deystvie"] == "call_saved":
            est_sob.add((z["inn"], z["kto"]))
            if z["den"] <= do:
                posl_do[(z["inn"], z["kto"])] = z["rez"]
    ochk = set()
    for inn, s in stroki.items():
        if not s["v_kat"] or s["skr"] or (s["naznacheno_den"] and s["naznacheno_den"] > do):
            continue
        k = (inn, s["u"])
        if k in posl_do:
            r_k = posl_do[k]
        elif k in est_sob:
            r_k = "new"
        else:
            lc = _fixKS_msk(s["last_contact_at"])
            r_k = s["rez"] if (lc is None or lc.date() <= do) else "new"
        if r_k not in _KS_VKLADKI:
            ochk.add(inn)
    return {"kat": kat, "lyudi": lyudi, "prodavcy": prodavcy, "naznach": naznach, "sost": sost,
            "skryt": skryt, "verd": verd, "sob": sob, "stroki": stroki, "posl": posl, "ochk": ochk,
            "kommentariev": kommentariev, "pervyy": pervyy, "per": per, "ot": ot, "do": do,
            "nedozvonov_vsego": sum(1 for z in sob if z["rez"] in _KS_NEDOZVON)}


def _fixKS_znach(pole, inn, D) -> str:
    if pole == "region":
        return (D["kat"].get(inn) or {}).get("region") or "не указан"
    if pole == "verdikt":
        return D["verd"].get(inn) or "вердикта нет"
    s = D["stroki"].get(inn) or {}
    t, z = bool(s.get("has_tech")), bool(s.get("has_purchaser"))
    return ("технический и закупщик" if t and z else "только технический" if t
            else "только закупщик" if z else "ни технического, ни закупщика")


def _fixKS_otbor(D, sp) -> list:
    """Компании за цифрой. sp: вид (per – последняя отметка за период, ochk – очередь на конец периода,
    nazn – назначения сейчас, nedozv – попытки без исхода), kto, rez, vid, pole/zn, gr."""
    kto, rez = sp.get("kto", ""), sp.get("rez", "")
    vid = sp.get("sp")
    out = []
    if vid == "per":
        for inn, o in D["posl"].items():
            if kto and o["kto"] != kto:
                continue
            if rez == "bez_komm":
                if o["rez"] != "ne_ponravilas" or o["tekst"].strip():
                    continue
            elif rez == "prochee":
                if o["rez"] in _KS_VKLADKI:
                    continue
            elif rez and o["rez"] != rez:
                continue
            if sp.get("pole") and _fixKS_znach(sp["pole"], inn, D) != sp.get("zn"):
                continue
            out.append(dict(D["stroki"].get(inn) or {"inn": inn, "u": "", "rez": "new", "vid": "",
                                                      "nazv": D["kat"].get(inn, {}).get("nazv", "")},
                            otmetka=o))
        out.sort(key=lambda x: x["otmetka"]["kogda"], reverse=True)
    elif vid == "ochk":
        out = [s for inn, s in D["stroki"].items() if inn in D["ochk"] and (not kto or s["u"] == kto)]
        out.sort(key=_fixKS_rang)
    elif vid == "nazn":
        v = sp.get("vid", "")
        for inn, s in D["stroki"].items():
            if kto and s["u"] != kto:
                continue
            if v == "kat":
                if not s["v_kat"]:
                    continue
            elif v and s["vid"] != v:
                continue
            if rez == "prochee":
                if s["rez"] in _KS_VKLADKI or s["rez"] == "new":
                    continue
            elif rez and s["rez"] != rez:
                continue
            if sp.get("gr") and s["skr_gr"] != sp["gr"]:
                continue
            out.append(s)
        out.sort(key=_fixKS_rang)
    elif vid == "nedozv":
        for z in D["sob"]:
            if z["rez"] in _KS_NEDOZVON and D["ot"] <= z["den"] <= D["do"] and (not kto or z["kto"] == kto):
                out.append(dict(D["stroki"].get(z["inn"]) or {"inn": z["inn"], "u": z["kto"], "rez": "new", "vid": "",
                                                               "nazv": D["kat"].get(z["inn"], {}).get("nazv", "")},
                                otmetka=z))
        out.sort(key=lambda x: x["otmetka"]["kogda"], reverse=True)
    return out


def _fixKS_rang(s) -> tuple:
    """Порядок очереди – ровно функция главной (_queue_rank) на тех же полях."""
    return _queue_rank({"call_result": s.get("call_result"), "next_contact_at": s.get("next_contact_at"),
                        "assignment_score": s.get("score", 0), "inn": s.get("inn", "")})


def _fixKS_karta(inn, D) -> str:
    """Ссылка на карточку: с вкладкой, если компания перенесена, и со «скрытыми», если скрыта."""
    if inn not in D["kat"]:
        return ""
    q = {"inn": inn}
    s = D["stroki"].get(inn) or {}
    if s.get("rez") in _KS_VKLADKI:
        q["call_status"] = s["rez"]
    if inn in D["skryt"]:
        q["skrytye"] = "1"
    return "%s/centro?%s" % (BP, urlencode(q))


def _fixKS_opis(sp, D) -> str:
    chasti = []
    vid = sp.get("sp")
    chasti.append({"per": "последняя отметка %s" % _fixKS_period_ru(D["ot"], D["do"]),
                   "ochk": "в очереди на конец периода (%s)" % D["do"].strftime("%d.%m.%Y"),
                   "nazn": "назначены сейчас",
                   "nedozv": "попытки без исхода %s" % _fixKS_period_ru(D["ot"], D["do"])}.get(vid, vid))
    if sp.get("kto"):
        chasti.append("менеджер %s" % sp["kto"])
    if sp.get("vid"):
        chasti.append(_KS_VID_NAZV.get(sp["vid"], sp["vid"]))
    if sp.get("rez"):
        chasti.append(_KS_REZ_NAZV.get(sp["rez"]) or sales.CALL_RESULT_LABELS.get(sp["rez"], sp["rez"]))
    if sp.get("gr"):
        chasti.append("скрыта: " + _KS_SKRYTIE_NAZV.get(sp["gr"], sp["gr"]))
    if sp.get("pole"):
        chasti.append("%s: %s" % (_KS_RAZREZ_NAZV.get(sp["pole"], sp["pole"]), sp.get("zn", "")))
    return " · ".join(chasti)


@router.get("/centro/stats")
def fixKS_stats_page(request: Request, user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    P = request.query_params
    D = _fixKS_dannye(P)
    ot, do, per = D["ot"], D["do"], D["per"]
    prodavcy = D["prodavcy"]
    kto = (P.get("stat_user") or "").strip()
    if kto not in prodavcy:
        kto = ""
    vybrannyy = (P.get("user") or "").strip()
    if vybrannyy not in D["lyudi"]:
        vybrannyy = ""
    pokaz = [kto] if kto else prodavcy
    stat_ot = ot.isoformat() if (ot != do and not per["vse"]) else ""
    stat_data = do.isoformat() if (do != per["segodnya"] and not per["vse"]) else ""

    def ssylka(**kw):
        d = {"stat_ot": stat_ot, "stat_data": stat_data, "stat_vse": "1" if per["vse"] else "",
             "stat_user": kto, "user": vybrannyy}
        d.update(kw)
        d = {k: v for k, v in d.items() if v}
        return "%s/centro/stats%s" % (BP, ("?" + urlencode(d)) if d else "")

    def yach(**sp):
        n = len(_fixKS_otbor(D, sp))
        q = {"sp_" + k if k != "sp" else "sp": v for k, v in sp.items() if v}
        return {"n": n, "url": (ssylka(**q) + "#spisok") if n else ""}

    stroki = D["stroki"]
    # ---- по менеджерам: за период и за всё время
    est_nedozv = D["nedozvonov_vsego"] > 0
    statblok = []
    for u in pokaz + ([""] if len(pokaz) > 1 else []):
        statblok.append({
            "u": u, "itog": u == "",
            "per": {r: yach(sp="per", kto=u, rez=r) for r in _KS_VKLADKI},
            "per_och": yach(sp="ochk", kto=u),
            "per_nedozv": yach(sp="nedozv", kto=u) if est_nedozv else None,
            "vse": {r: yach(sp="nazn", vid="kat", kto=u, rez=r) for r in _KS_VKLADKI},
            "vse_och": yach(sp="nazn", vid="och", kto=u),
            "vse_prochee": yach(sp="nazn", vid="kat", kto=u, rez="prochee"),
        })
    # ---- итоги за период и темп
    dney = (do - ot).days + 1
    itogi, temp = [], []
    for u in pokaz + ([""] if len(pokaz) > 1 else []):
        dni, posled = set(), None
        for z in D["sob"]:
            if (z["deystvie"] == "call_saved" and z["inn"] in D["kat"] and ot <= z["den"] <= do
                    and (z["kto"] == u if u else z["kto"] in pokaz)):
                dni.add(z["den"])
                posled = z["kogda"] if posled is None or z["kogda"] > posled else posled
        otm = yach(sp="per", kto=u)
        if not u and kto:
            otm = yach(sp="per", kto=kto)
        itogi.append({"u": u, "itog": u == "", "otmecheno": otm,
                      "v_rabote": yach(sp="per", kto=u or kto, rez="v_rabote"),
                      "ne_ponravilas": yach(sp="per", kto=u or kto, rez="ne_ponravilas"),
                      "bez_komm": yach(sp="per", kto=u or kto, rez="bez_komm"),
                      "dubl": yach(sp="per", kto=u or kto, rez="dubl"),
                      "prochee": yach(sp="per", kto=u or kto, rez="prochee"),
                      "dney": len(dni), "posled": posled.strftime("%d.%m %H:%M") if posled else ""})
        och = yach(sp="nazn", vid="och", kto=u or kto)
        v_den = otm["n"] / len(dni) if dni else 0.0
        temp.append({"u": u, "itog": u == "", "otmecheno": otm, "dney_rab": len(dni), "v_den_rab": v_den,
                     "v_den_kal": otm["n"] / dney, "ochered": och,
                     "prognoz": _ks_math.ceil(och["n"] / v_den) if v_den and och["n"] else None,
                     "posled": posled.strftime("%d.%m %H:%M") if posled else ""})
    # ---- где берут в работу
    razrezy = []
    for pole, nazv in _KS_RAZREZY:
        sch: dict = {}
        for inn, o in D["posl"].items():
            if kto and o["kto"] != kto:
                continue
            zn = _fixKS_znach(pole, inn, D)
            s = sch.setdefault(zn, {"otmecheno": 0, "v_rabote": 0})
            s["otmecheno"] += 1
            s["v_rabote"] += o["rez"] == "v_rabote"
        rows = []
        for zn, s in sorted(sch.items(), key=lambda x: (-x[1]["otmecheno"], x[0]))[:20]:
            rows.append({"zn": zn, "otmecheno": yach(sp="per", kto=kto, pole=pole, zn=zn),
                         "v_rabote": yach(sp="per", kto=kto, pole=pole, zn=zn, rez="v_rabote"),
                         "ne_ponravilas": yach(sp="per", kto=kto, pole=pole, zn=zn, rez="ne_ponravilas"),
                         "dubl": yach(sp="per", kto=kto, pole=pole, zn=zn, rez="dubl"),
                         "dolya": 100.0 * s["v_rabote"] / s["otmecheno"] if s["otmecheno"] else 0.0})
        razrezy.append({"nazv": nazv, "stroki": rows, "vsego": len(sch)})
    # ---- активность по часам (Москва), считается тот, кто нажал
    chasy_po: dict = {}
    for z in D["sob"]:
        if z["deystvie"] != "call_saved" and z["rez"] not in _KS_NEDOZVON:
            continue
        if not (ot <= z["den"] <= do) or (kto and z["deystvoval"] != kto):
            continue
        h = chasy_po.setdefault(z["deystvoval"], {})
        h[z["kogda"].hour] = h.get(z["kogda"].hour, 0) + 1
    vse_ch = [h for d in chasy_po.values() for h in d]
    kolonki_ch = list(range(min([8] + vse_ch), max([20] + vse_ch) + 1))
    chasy = [{"u": u, "po_chasam": [chasy_po[u].get(h, 0) for h in kolonki_ch], "vsego": sum(chasy_po[u].values())}
             for u in sorted(chasy_po)]
    if len(chasy) > 1:
        chasy.append({"u": "", "itog": True, "vsego": sum(s["vsego"] for s in chasy),
                      "po_chasam": [sum(chasy_po[u].get(h, 0) for u in chasy_po) for h in kolonki_ch]})
    chasy_max = max([1] + [n for s in chasy if not s.get("itog") for n in s["po_chasam"]])
    # ---- лента действий
    lenta_vse = [z for z in reversed(D["sob"]) if ot <= z["den"] <= do
                 and (not kto or z["kto"] == kto or z["deystvoval"] == kto)]
    lenta = []
    for z in lenta_vse[:300]:
        d = z["deystvie"]
        if d == "call_saved":
            chto = sales.CALL_RESULT_LABELS.get(z["rez"], z["rez"] or "отметка")
        elif d == "reassigned":
            chto = "передал компанию: %s → %s" % (z["pl"].get("from") or "", z["pl"].get("to") or "")
        elif d == "comment_edited":
            chto = "изменил комментарий"
        elif d == "park_v_obzvon":
            chto = "из «Парка» в обзвон: %s" % (z["pl"].get("komu") or "")
        elif d == "park_perenaznachenie":
            chto = "переназначил из «Парка»: %s → %s" % (z["pl"].get("bylo") or "", z["pl"].get("stalo") or "")
        elif d in _KS_NEDOZVON:
            chto = "не дозвонился"
        else:
            chto = d
        lenta.append({"vremya": z["kogda"].strftime("%H:%M" if ot == do else "%d.%m %H:%M"), "kto": z["kto"],
                      "deystvoval": z["deystvoval"], "nazv": (D["kat"].get(z["inn"]) or {}).get("nazv") or z["inn"],
                      "url": _fixKS_karta(z["inn"], D), "chto": chto, "rez": z["rez"], "tekst": z["tekst"],
                      "sled": z["sled"].replace("T", " ")[:16]})
    # ---- общая статистика
    kat_set, nazn_set = set(D["kat"]), set(D["naznach"])
    seychas = sales.utcnow()
    aktivnost = {}
    teper = _ks_dt.datetime.now(_ks_dt.timezone.utc).replace(tzinfo=None) + _KS_MSK
    for n_d in (1, 7, 30):
        porog = teper - _ks_dt.timedelta(days=n_d)
        aktivnost[n_d] = sum(1 for z in D["sob"] if z["kogda"] >= porog)
    posl_d = max((z["kogda"] for z in D["sob"]), default=None)
    po_rez: dict = {}
    for s in stroki.values():
        if s["v_kat"]:
            po_rez[s["rez"]] = po_rez.get(s["rez"], 0) + 1
    obshchee = {
        "v_kataloge": len(kat_set), "naznacheno": len(D["naznach"]),
        "kompaniy_naznacheno": len(kat_set & nazn_set), "ne_naznacheno": len(kat_set - nazn_set),
        "vne_kataloga": yach(sp="nazn", vid="vne"),
        "obrabotano": yach(sp="nazn", vid="kat", rez="prochee")["n"] + sum(
            yach(sp="nazn", vid="kat", rez=r)["n"] for r in _KS_VKLADKI),
        "prosrocheno": sum(1 for s in D["sost"].values()
                           if s.get("next_contact_at") and str(s["next_contact_at"]) < seychas),
        "kommentariev": D["kommentariev"], "skryto": len(D["skryt"]),
        "skryto_naznachennyh": yach(sp="nazn", vid="skr"),
        "aktivnost": aktivnost, "vsego_deystviy": len(D["sob"]),
        "poslednee": posl_d.strftime("%d.%m.%Y %H:%M") if posl_d else "",
        "nedozvonov": D["nedozvonov_vsego"],
        "po_rezultatu": [{"kod": r, "n": n, "yach": yach(sp="nazn", vid="kat", rez=r)}
                         for r, n in sorted(po_rez.items(), key=lambda x: -x[1])],
    }
    # ---- по менеджерам и почему назначено больше, чем показывается
    gruppy = [g for g in [k for k, _n, _p in _KS_SKRYTIE] + ["drugoe", "bez"]
              if any(s["skr_gr"] == g and s["vid"] == "skr" for s in stroki.values())]
    vse_users = prodavcy + sorted(u for u in {s["u"] for s in stroki.values()} if u not in prodavcy)
    po_men, pochemu = [], []
    poslednee_po = {}
    for z in D["sob"]:
        poslednee_po[z["deystvoval"]] = z["kogda"]
    for u in vse_users:
        moi = [s for s in stroki.values() if s["u"] == u]
        rez_u: dict = {}
        for s in moi:
            rez_u[s["rez"]] = rez_u.get(s["rez"], 0) + 1
        x = D["lyudi"].get(u) or {}
        po_men.append({"u": u, "role": x.get("role", "нет в users"), "aktiven": x.get("aktiven", False),
                       "naznacheno": len(moi), "obrabotano": sum(1 for s in moi if s["rez"] != "new"),
                       "vidno": sum(1 for s in moi if s["vid"] in ("och", "vkl")),
                       "ochered": yach(sp="nazn", vid="och", kto=u),
                       "prosrocheno": sum(1 for s in moi if s["next_contact_at"] and str(s["next_contact_at"]) < seychas),
                       "ball_summa": sum(s["score"] for s in moi),
                       "ball_sredniy": (sum(s["score"] for s in moi) / len(moi)) if moi else 0.0,
                       "posled": poslednee_po[u].strftime("%d.%m.%Y %H:%M") if u in poslednee_po else "",
                       "po_rezultatu": sorted(rez_u.items(), key=lambda t: -t[1])})
    for u in vse_users + [""]:
        moi = [s for s in stroki.values() if (s["u"] == u or not u)]
        kem: dict = {}
        for s in moi:
            if s["vid"] == "skr":
                k = ("админ" if (D["lyudi"].get(s["skr_kto"]) or {}).get("role") == "admin"
                     else "автоотсев (system)" if s["skr_kto"] == "system"
                     else "сам менеджер" if s["skr_kto"] == s["u"] else (s["skr_kto"] or "неизвестно"))
                kem[k] = kem.get(k, 0) + 1
        pochemu.append({"u": u, "itog": not u, "naznacheno": len(moi),
                        "vne": yach(sp="nazn", vid="vne", kto=u), "skr": yach(sp="nazn", vid="skr", kto=u),
                        "gruppy": [yach(sp="nazn", vid="skr", kto=u, gr=g) for g in gruppy],
                        "vkl": {r: yach(sp="nazn", vid="vkl", kto=u, rez=r) for r in _KS_VKLADKI},
                        "och": yach(sp="nazn", vid="och", kto=u),
                        "kem": sorted(kem.items(), key=lambda t: -t[1])})
    # ---- очередь выбранного менеджера и список за цифрой
    ochered = _fixKS_otbor(D, {"sp": "nazn", "vid": "och", "kto": vybrannyy}) if vybrannyy else []
    sp = {k: (P.get("sp_" + k) or "").strip() for k in ("kto", "rez", "vid", "pole", "zn", "gr")}
    sp["sp"] = (P.get("sp") or "").strip()
    spisok = None
    if sp["sp"] in ("per", "ochk", "nazn", "nedozv"):
        sp = {k: v for k, v in sp.items() if v}
        rows = _fixKS_otbor(D, sp)
        spisok = {"opis": _fixKS_opis(sp, D), "rows": rows[:2000], "vsego": len(rows),
                  "zakryt": ssylka(), "est_otmetka": sp["sp"] in ("per", "nedozv")}
    segodnya = per["segodnya"]
    d1 = _ks_dt.timedelta(days=1)
    bystrye = []
    for nazv, a, b in (("сегодня", segodnya, segodnya), ("вчера", segodnya - d1, segodnya - d1),
                       ("7 дней", segodnya - 6 * d1, segodnya), ("30 дней", segodnya - 29 * d1, segodnya)):
        bystrye.append({"nazv": nazv, "aktiven": (not per["vse"]) and (a, b) == (ot, do),
                        "url": ssylka(stat_ot=a.isoformat() if a != b else "",
                                      stat_data=b.isoformat() if b != segodnya else "", stat_vse="")})
    bystrye.append({"nazv": "всё время", "aktiven": per["vse"], "url": ssylka(stat_ot="", stat_data="", stat_vse="1")})
    posl_den = max((z["den"] for z in D["sob"] if z["deystvie"] == "call_saved"), default=None)
    return templates.TemplateResponse(
        request,
        "fixKS_stats.html",
        {
            "user": user, "base_path": BP, "metki": sales.CALL_RESULT_LABELS, "vkladki": _KS_VKLADKI,
            "period_ru": ("за всё время (с %s)" % ot.strftime("%d.%m.%Y")) if per["vse"] else _fixKS_period_ru(ot, do),
            "ot_iso": ot.isoformat(), "do_iso": do.isoformat(), "segodnya_iso": segodnya.isoformat(),
            "vse": per["vse"], "soobshcheniya": per["soob"], "bystrye": bystrye, "dney": dney,
            "posl_den": posl_den, "posl_den_url": ssylka(stat_ot="", stat_data=posl_den.isoformat(), stat_vse="")
            if posl_den and posl_den != do else "",
            "prodavcy": prodavcy, "kto": kto, "vybrannyy": vybrannyy, "est_nedozv": est_nedozv,
            "statblok": statblok, "itogi": itogi, "temp": temp, "razrezy": razrezy,
            "chasy": chasy, "chasy_kolonki": kolonki_ch, "chasy_max": chasy_max,
            "lenta": lenta, "lenta_vsego": len(lenta_vse), "obshchee": obshchee,
            "po_men": po_men, "pochemu": pochemu, "gruppy_nazv": [_KS_SKRYTIE_NAZV[g] for g in gruppy],
            "ochered": ochered, "spisok": spisok, "karta": lambda inn: _fixKS_karta(inn, D),
            "ssylka": ssylka, "stat_forma": "%s/centro/stats" % BP,
        },
    )
# ===================================================================== /fixKS
'''

# ======================================================================== шапка главной и карточки
SHAPKA_YAKOR = '''    {% if user.role == 'admin' %}<a href="{{ base_path }}/centro/admin">Распределение</a>{% endif %}
'''
SHAPKA_NOVOE = SHAPKA_YAKOR.rstrip('\n') + '''{% if user.role == 'admin' and fixKS_stats_est is defined %}<a href="{{ base_path }}/centro/stats">Статистика</a>{% endif %}
'''
SHAPKA_PRIZNAK = 'fixKS_stats_est is defined'

# ======================================================================== шаблон страницы
SHABLON = r'''<!doctype html>
{# fixKS (21.10): статистика админа панели КЦ – перенос страницы статистики панели Meyer. Рендерит только
   маршрут /centro/stats (fixKS_stats_page); другие страницы этот файл не подключают. #}
<html lang="ru" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Статистика – Центробежные</title>
  <link rel="stylesheet" href="{{ base_path }}/static/css/centro.css">
  <style>
    main.ks{padding:16px 22px;max-width:1500px;margin:0 auto}
    main.ks h2{font-size:19px;margin:26px 0 6px;color:#2b2e35}
    main.ks h3{font-size:15px;margin:10px 0 4px}
    .stat-setka{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}
    .plitka{border:1px solid #d7dde5;border-radius:8px;padding:10px 14px;min-width:min(150px,100%);background:#fff}
    .plitka b{display:block;font-size:22px;line-height:1.1}
    .plitka span{color:#5a6472;font-size:12px}
    table.stat{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px;background:#fff}
    table.stat th,table.stat td{border:1px solid #dde3ea;padding:5px 8px;text-align:left;vertical-align:top}
    table.stat th{background:#2f5496;color:#fff;font-weight:600}
    table.stat tr:nth-child(even) td{background:#f6f8fb}
    table.stat a{color:#4f46e5;font-weight:600}
    table.stat tr.itog td{font-weight:700;background:#eef1f7}
    table.stat td.razd,table.stat th.razd{border-left:2px solid #9aa8bd}
    .prosr{color:#b4232a;font-weight:600}
    .nead{color:#8a94a0}
    .pometka{color:#5a6472;font-size:12px;margin:4px 0 14px;max-width:1100px}
    .period-metka{font-size:14px;font-weight:400;color:#5a6472}
    .razrezy{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr));gap:14px}
    .razrezy>section{min-width:0}
    table.chasy td,table.chasy th{padding:4px 6px}
    .st-ne_ponravilas{color:#9b1c1c;font-weight:600}
    .st-v_rabote{color:#17663a;font-weight:600}
    .ks-forma{display:flex;gap:12px;align-items:end;flex-wrap:wrap;font-size:12px;color:var(--muted);
      background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
    .ks-forma label{display:grid;gap:3px}
    .ks-forma input,.ks-forma select{padding:6px 8px;border:1px solid #ced0d5;border-radius:6px;background:#fff;color:#33373e}
    .bystrye a,.bystrye b{margin:0 2px;font-size:13px}
    .bystrye b{color:var(--navy)}
    .period-oshibka{background:#fff4e0;border:1px solid #f3d39b;color:#8a5300;border-radius:6px;padding:6px 10px;font-size:13px;margin:8px 0}
    .spisok{border:2px solid #4f46e5;border-radius:8px;padding:8px 12px;background:#fbfbff;margin:14px 0}
    .topbar nav a.aktiv{text-decoration:underline;font-weight:700}
    .tabl-obol{overflow-x:auto;max-width:100%}
    @media(max-width:760px){main.ks{padding:10px 8px}.stat-setka>.plitka{flex:1 1 140px;padding:8px 10px}}
  </style>
</head>
<body>
{% macro ch(c) %}{% if c and c.n and c.url %}<a href="{{ c.url }}">{{ c.n }}</a>{% elif c %}{{ c.n }}{% else %}–{% endif %}{% endmacro %}
<header class="topbar">
  <div class="brand-block">
    <strong>Центробежные</strong>
    <span>база продаж по компрессорному оборудованию</span>
  </div>
  <nav>
    <a href="{{ base_path }}/centro">Вся очередь</a>
    <a href="{{ base_path }}/centro?call_status=v_rabote">Взял в работу</a>
    <a href="{{ base_path }}/centro?call_status=ne_ponravilas">Компания не понравилась</a>
    <a href="{{ base_path }}/centro?call_status=dubl">Дубль — уже работают</a>
    <a href="{{ base_path }}/centro/spisok">Список компаний</a>
    <a href="{{ base_path }}/centro/park">Парк машин</a>
    <a href="{{ base_path }}/centro/admin">Распределение</a>
    <a class="aktiv" href="{{ base_path }}/centro/stats">Статистика</a>
  </nav>
  <div class="user-block">
    <span>{{ user.username }} · администратор</span>
    <form method="post" action="{{ base_path }}/centro/logout"><button class="link-button">Выйти</button></form>
  </div>
</header>
<main class="ks" id="fixKS-stats">

  <form class="ks-forma" method="get" action="{{ stat_forma }}">
    {% if vybrannyy %}<input type="hidden" name="user" value="{{ vybrannyy }}">{% endif %}
    <label>С <input type="date" name="stat_ot" value="{{ ot_iso }}" max="{{ segodnya_iso }}"></label>
    <label>по <input type="date" name="stat_data" value="{{ do_iso }}" max="{{ segodnya_iso }}"></label>
    <label>Менеджер
      <select name="stat_user">
        <option value="">все менеджеры</option>
        {% for u in prodavcy %}<option value="{{ u }}" {% if u == kto %}selected{% endif %}>{{ u }}</option>{% endfor %}
      </select>
    </label>
    <button class="action-button" type="submit">Показать</button>
    <span class="bystrye">{% for b in bystrye %}{% if b.aktiven %}<b>{{ b.nazv }}</b>{% else %}<a href="{{ b.url }}">{{ b.nazv }}</a>{% endif %}{% if not loop.last %} · {% endif %}{% endfor %}</span>
    {% if posl_den_url %}<span>последний день с отметками: <a href="{{ posl_den_url }}">{{ posl_den.strftime('%d.%m.%Y') }}</a></span>{% endif %}
  </form>
  {% if soobshcheniya %}<div class="period-oshibka" role="alert">{% for s in soobshcheniya %}<div>{{ s }}</div>{% endfor %}</div>{% endif %}
  <p class="pometka">Период: <b>{{ period_ru }}</b>{% if kto %}, менеджер <b>{{ kto }}</b>{% endif %}. Дни – по Москве. Менеджеры показаны логином: ФИО в панели не заведены. Каждая цифра-ссылка открывает компании за ней списком (над таблицами), название в списке – карточку.</p>

  {% if spisok %}
  <section class="spisok" id="spisok">
    <h2 style="margin-top:4px">{{ spisok.vsego }} {{ 'компания' if spisok.vsego % 10 == 1 and spisok.vsego % 100 != 11 else 'компаний' }}: {{ spisok.opis }} <span class="period-metka"><a href="{{ spisok.zakryt }}">закрыть</a></span></h2>
    {% if spisok.vsego > spisok.rows|length %}<p class="pometka">Показаны первые {{ spisok.rows|length }}.</p>{% endif %}
    <div class="tabl-obol"><table class="stat">
      <thead><tr><th>№</th><th>Компания</th><th>ИНН</th><th>Менеджер</th><th>Результат сейчас</th><th>Видна менеджеру</th>{% if spisok.est_otmetka %}<th>Отметка</th><th>Комментарий</th>{% endif %}</tr></thead>
      <tbody>
      {% for z in spisok.rows %}
        <tr><td>{{ loop.index }}</td>
          <td>{% set url = karta(z.inn) %}{% if url %}<a href="{{ url }}">{{ z.nazv or z.inn }}</a>{% else %}{{ z.nazv or '–' }}{% endif %}</td>
          <td>{{ z.inn }}</td><td>{{ z.u or '–' }}</td>
          <td>{{ metki.get(z.rez, z.rez) }}</td>
          <td>{% if z.vid == 'och' %}в «Вся очередь»{% elif z.vid == 'vkl' %}во вкладке{% elif z.vid == 'skr' %}<span class="prosr">скрыта</span>: {{ z.skr_reason or 'без причины' }} <span class="nead">({{ z.skr_kto }})</span>{% elif z.vid == 'vne' %}<span class="prosr">нет в каталоге</span>{% else %}–{% endif %}</td>
          {% if spisok.est_otmetka %}<td style="white-space:nowrap">{{ z.otmetka.kogda.strftime('%d.%m %H:%M') }} · <span class="st-{{ z.otmetka.rez }}">{{ metki.get(z.otmetka.rez, z.otmetka.rez) }}</span>{% if z.otmetka.kto != z.otmetka.deystvoval %} <span class="nead">(нажал {{ z.otmetka.deystvoval }})</span>{% endif %}{% if z.otmetka.n and z.otmetka.n > 1 %} <span class="nead">({{ z.otmetka.n }} отметки за период)</span>{% endif %}</td><td>{{ z.otmetka.tekst }}</td>{% endif %}
        </tr>
      {% else %}<tr><td colspan="8">Компаний нет.</td></tr>{% endfor %}
      </tbody>
    </table></div>
  </section>
  {% endif %}

  <h2>По менеджерам: за период и за всё время</h2>
  <div class="tabl-obol"><table class="stat">
    <thead>
      <tr><th rowspan="2">Менеджер</th><th class="razd" colspan="{{ 5 if est_nedozv else 4 }}">{{ period_ru }}</th><th class="razd" colspan="4">за всё время (нынешний статус)</th></tr>
      <tr><th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди на конец периода</th>{% if est_nedozv %}<th>не дозвонился</th>{% endif %}
        <th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди сейчас</th></tr>
    </thead>
    <tbody>
    {% for z in statblok %}
      <tr{% if z.itog %} class="itog"{% endif %}><td>{{ 'Все менеджеры' if z.itog else z.u }}</td>
        <td class="razd">{{ ch(z.per.v_rabote) }}</td><td>{{ ch(z.per.ne_ponravilas) }}</td><td>{{ ch(z.per.dubl) }}</td><td>{{ ch(z.per_och) }}</td>{% if est_nedozv %}<td>{{ ch(z.per_nedozv) }}</td>{% endif %}
        <td class="razd">{{ ch(z.vse.v_rabote) }}</td><td>{{ ch(z.vse.ne_ponravilas) }}</td><td>{{ ch(z.vse.dubl) }}</td><td>{{ ch(z.vse_och) }}</td></tr>
    {% else %}<tr><td colspan="10">Менеджеров нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>
  <p class="pometka">За период – по последней отметке компании в периоде; отметка засчитывается менеджеру, за которым компания (даже если нажал админ). Очередь на конец периода – компании, которые к концу периода были назначены, видны менеджеру и ещё не перенесены во вкладки. За всё время – нынешний статус компаний каталога, в том числе скрытых позже (сделанная работа остаётся сделанной); «в очереди сейчас» – ровно то, что менеджер видит в «Вся очередь».{% set pr = statblok[-1].vse_prochee if statblok else none %}{% if pr and pr.n %} Из них со старым статусом вне трёх вкладок (например «Связались») – {{ ch(pr) }}: такие компании остаются в очереди.{% endif %}{% if not est_nedozv %} Попыток «не дозвонился» в данных панели КЦ нет (такой кнопки в ней нет), поэтому колонки и блока недозвонов здесь нет.{% endif %}</p>

  <h2>Итоги за период по менеджерам <span class="period-metka">{{ period_ru }}</span></h2>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>Менеджер</th><th>Отмечено компаний</th><th>Взял в работу</th><th>Не понравилась</th><th>из них без комментария</th><th>Дубль – уже работают</th><th>Другие отметки</th><th>Дней с отметками</th><th>Последняя отметка</th></tr></thead>
    <tbody>
    {% for s in itogi %}
      <tr{% if s.itog %} class="itog"{% endif %}><td>{{ 'Все менеджеры' if s.itog else s.u }}</td><td>{{ ch(s.otmecheno) }}</td><td>{{ ch(s.v_rabote) }}</td><td>{{ ch(s.ne_ponravilas) }}</td><td>{{ ch(s.bez_komm) }}</td><td>{{ ch(s.dubl) }}</td><td>{{ ch(s.prochee) }}</td><td>{{ s.dney }}</td><td>{{ s.posled or '–' }}</td></tr>
    {% endfor %}
    </tbody>
  </table></div>
  <p class="pometka">Причин отказа в панели КЦ нет (у кнопки «Компания не понравилась» нет выбора причины), поэтому вместо разбивки по причинам – «без комментария»: отказ, к которому менеджер не написал ни слова.</p>

  <h2>Темп и прогноз <span class="period-metka">{{ period_ru }}</span></h2>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>Менеджер</th><th>Отмечено</th><th>Дней с отметками</th><th>В день работы</th><th>В календарный день</th><th>В очереди сейчас</th><th>Хватит очереди</th><th>Последняя отметка</th></tr></thead>
    <tbody>
    {% for t in temp %}
      <tr{% if t.itog %} class="itog"{% endif %}><td>{{ 'Все менеджеры' if t.itog else t.u }}</td><td>{{ ch(t.otmecheno) }}</td><td>{{ t.dney_rab }}</td><td>{{ ('%.1f'|format(t.v_den_rab)).replace('.', ',') if t.dney_rab else '–' }}</td><td>{{ ('%.1f'|format(t.v_den_kal)).replace('.', ',') }}</td><td>{{ ch(t.ochered) }}</td><td>{% if t.prognoz is not none %}≈ {{ t.prognoz }} раб. дн.{% elif t.ochered.n %}<span class="prosr">темпа нет</span>{% else %}очередь пуста{% endif %}</td><td>{{ t.posled or '–' }}</td></tr>
    {% endfor %}
    </tbody>
  </table></div>
  <p class="pometka">«В день работы» – на день, когда были отметки; «в календарный день» – на {{ dney }} дн. периода. Прогноз – на сколько рабочих дней хватит нынешней очереди при темпе «в день работы».</p>

  <h2>Где берут в работу <span class="period-metka">{{ period_ru }}</span></h2>
  <p class="pometka">Доля «Взял в работу» среди компаний, отмеченных за период. Сегментов, баз и меток Битрикса в каталоге КЦ нет – разрезы по тому, что в нём есть: регион, вердикт по центробежной машине, кто есть в контактах.</p>
  <div class="razrezy">
  {% for r in razrezy %}
    <section>
      <h3>{{ r.nazv }}{% if r.vsego > r.stroki|length %} <span class="period-metka">(первые {{ r.stroki|length }} из {{ r.vsego }})</span>{% endif %}</h3>
      <div class="tabl-obol"><table class="stat">
        <thead><tr><th>{{ r.nazv }}</th><th>Отмечено</th><th>Взял в работу</th><th>Не понр.</th><th>Дубль</th><th>Доля в работу</th></tr></thead>
        <tbody>
        {% for z in r.stroki %}<tr><td>{{ z.zn }}</td><td>{{ ch(z.otmecheno) }}</td><td>{{ ch(z.v_rabote) }}</td><td>{{ ch(z.ne_ponravilas) }}</td><td>{{ ch(z.dubl) }}</td><td>{{ '%.0f'|format(z.dolya) }} %</td></tr>
        {% else %}<tr><td colspan="6">за период отметок нет</td></tr>{% endfor %}
        </tbody>
      </table></div>
    </section>
  {% endfor %}
  </div>

  <h2>Активность по часам <span class="period-metka">{{ period_ru }}, время московское</span></h2>
  <p class="pometka">Сколько отметок звонка сохранено в каждый час. Считается тот, кто нажал кнопку.</p>
  <div class="tabl-obol"><table class="stat chasy">
    <thead><tr><th>Кто</th>{% for h in chasy_kolonki %}<th>{{ h }}</th>{% endfor %}<th>Всего</th></tr></thead>
    <tbody>
    {% for s in chasy %}
      <tr{% if s.itog %} class="itog"{% endif %}><td>{{ 'Все' if s.itog else s.u }}</td>{% for n in s.po_chasam %}<td style="text-align:center;{% if n and not s.itog %}background:rgba(79,70,229,{{ '%.2f'|format(0.12 + 0.55 * n / chasy_max) }});{% endif %}">{{ n or '' }}</td>{% endfor %}<td>{{ s.vsego }}</td></tr>
    {% else %}<tr><td colspan="{{ chasy_kolonki|length + 2 }}">За период отметок нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>

  <h2>Лента действий <span class="period-metka">{{ period_ru }}</span></h2>
  <p class="pometka">{% if lenta_vsego > lenta|length %}Показаны последние {{ lenta|length }} из {{ lenta_vsego }}.{% else %}Всего действий: {{ lenta_vsego }}.{% endif %} Время московское, новые сверху. Название открывает карточку.</p>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>Время</th><th>Менеджер</th><th>Компания</th><th>Что сделал</th><th>Комментарий</th><th>Следующий контакт</th></tr></thead>
    <tbody>
    {% for e in lenta %}
      <tr><td style="white-space:nowrap">{{ e.vremya }}</td>
        <td>{{ e.kto }}{% if e.deystvoval != e.kto %} <span class="nead">(нажал {{ e.deystvoval }})</span>{% endif %}</td>
        <td>{% if e.url %}<a href="{{ e.url }}">{{ e.nazv }}</a>{% else %}{{ e.nazv }}{% endif %}</td>
        <td><span class="st-{{ e.rez }}">{{ e.chto }}</span></td><td>{{ e.tekst }}</td><td style="white-space:nowrap">{{ e.sled or '' }}</td></tr>
    {% else %}<tr><td colspan="6">За период действий нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>

  <h2>Общая статистика</h2>
  <div class="stat-setka">
    <div class="plitka"><b>{{ obshchee.v_kataloge }}</b><span>компаний в каталоге</span></div>
    <div class="plitka"><b>{{ obshchee.naznacheno }}</b><span>назначений всего</span></div>
    <div class="plitka"><b>{{ obshchee.kompaniy_naznacheno }}</b><span>компаний каталога назначено</span></div>
    <div class="plitka"><b>{{ obshchee.ne_naznacheno }}</b><span>компаний без менеджера</span></div>
    <div class="plitka"><b class="{% if obshchee.vne_kataloga.n %}prosr{% endif %}">{{ ch(obshchee.vne_kataloga) }}</b><span>назначений на ИНН вне каталога</span></div>
    <div class="plitka"><b>{{ obshchee.skryto }}</b><span>скрыто компаний (из них назначено и не видно менеджеру: {{ ch(obshchee.skryto_naznachennyh) }})</span></div>
    <div class="plitka"><b>{{ obshchee.obrabotano }}</b><span>обработано (компании каталога)</span></div>
    <div class="plitka"><b class="{% if obshchee.prosrocheno %}prosr{% endif %}">{{ obshchee.prosrocheno }}</b><span>просрочен следующий контакт</span></div>
    <div class="plitka"><b>{{ obshchee.kommentariev }}</b><span>комментариев</span></div>
    <div class="plitka"><b>{{ obshchee.aktivnost.get(1, 0) }} / {{ obshchee.aktivnost.get(7, 0) }} / {{ obshchee.aktivnost.get(30, 0) }}</b><span>действий за сутки / 7 дней / 30 дней</span></div>
    <div class="plitka"><b>{{ obshchee.vsego_deystviy }}</b><span>действий в журнале всего, последнее {{ obshchee.poslednee or '–' }}</span></div>
  </div>

  <h3>По результатам звонка</h3>
  <p class="pometka">Компании каталога, назначенные менеджерам, по нынешнему статусу; скрытые позже входят в цифры (работа по ним сделана).</p>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>Результат</th><th>Компаний</th><th>Доля</th></tr></thead>
    <tbody>
    {% for r in obshchee.po_rezultatu %}
      <tr><td>{{ metki.get(r.kod, r.kod) }}</td><td>{{ ch(r.yach) }}</td><td>{% if obshchee.kompaniy_naznacheno %}{{ ('%.1f'|format(100.0 * r.n / obshchee.kompaniy_naznacheno)).replace('.', ',') }} %{% else %}–{% endif %}</td></tr>
    {% else %}<tr><td colspan="3">Назначений нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>

  <h2 id="naznacheno-pokazano">Назначено → показывается в очереди</h2>
  <p class="pometka">Почему у менеджера назначено больше компаний, чем он видит. Главная показывает менеджеру только компании, которые есть в каталоге и не скрыты; отмеченные «Взял в работу», «Компания не понравилась» и «Дубль» уходят из «Вся очередь» в свои вкладки. Строка складывается: назначено = нет в каталоге + скрыто + во вкладках + показывается. Скрытые разложены по причине скрытия (из текста причины), кто скрыл – под строкой.</p>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>Менеджер</th><th>Назначено</th><th class="razd">Нет в каталоге</th><th class="razd">Скрыто всего</th>{% for g in gruppy_nazv %}<th>{{ g }}</th>{% endfor %}<th class="razd">Взял в работу</th><th>Не понравилась</th><th>Дубль</th><th class="razd">Показывается в «Вся очередь»</th></tr></thead>
    <tbody>
    {% for p in pochemu %}
      <tr{% if p.itog %} class="itog"{% endif %}><td>{{ 'Все' if p.itog else p.u }}</td><td>{{ p.naznacheno }}</td><td class="razd">{{ ch(p.vne) }}</td><td class="razd">{{ ch(p.skr) }}</td>{% for g in p.gruppy %}<td>{{ ch(g) }}</td>{% endfor %}<td class="razd">{{ ch(p.vkl.v_rabote) }}</td><td>{{ ch(p.vkl.ne_ponravilas) }}</td><td>{{ ch(p.vkl.dubl) }}</td><td class="razd"><b>{{ ch(p.och) }}</b></td></tr>
      {% if p.kem %}<tr><td colspan="{{ 9 + gruppy_nazv|length }}" style="font-size:12px;color:#5a6472">скрыл: {% for k, n in p.kem %}{{ k }} {{ n }}{% if not loop.last %} · {% endif %}{% endfor %}</td></tr>{% endif %}
    {% endfor %}
    </tbody>
  </table></div>

  <h2>По менеджерам</h2>
  <p class="pometka">Нажмите на логин, чтобы увидеть очередь менеджера в том же порядке, в каком её видит он сам.</p>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>Менеджер</th><th>Роль</th><th>Назначено</th><th>Обработано</th><th>Видно менеджеру</th><th>В очереди</th><th>Просрочено</th><th>Сумма балла очереди</th><th>Средний балл очереди</th><th>Последнее действие</th></tr></thead>
    <tbody>
    {% for p in po_men %}
      <tr{% if not p.aktiven %} class="nead"{% endif %}>
        <td><a href="{{ ssylka(user=p.u) }}#ochered-prodavca">{{ p.u }}</a>{% if not p.aktiven %} (отключён){% endif %}</td>
        <td>{{ p.role }}</td><td>{{ p.naznacheno }}</td><td>{{ p.obrabotano }}</td><td>{{ p.vidno }}</td><td>{{ ch(p.ochered) }}</td>
        <td{% if p.prosrocheno %} class="prosr"{% endif %}>{{ p.prosrocheno }}</td>
        <td>{{ ('%.1f'|format(p.ball_summa)).replace('.', ',') }}</td><td>{{ ('%.2f'|format(p.ball_sredniy)).replace('.', ',') }}</td><td>{{ p.posled or '–' }}</td>
      </tr>
      <tr><td colspan="10" style="font-size:12px;color:#5a6472">{% for kod, n in p.po_rezultatu %}{{ metki.get(kod, kod) }}: {{ n }}{% if not loop.last %} · {% endif %}{% endfor %}</td></tr>
    {% else %}<tr><td colspan="10">Пользователей нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>
  <p class="pometka">«Видно менеджеру» – есть в каталоге и не скрыто (очередь и вкладки); «В очереди» – то, что он видит в «Вся очередь».</p>

  {% if vybrannyy %}
  <h2 id="ochered-prodavca">Очередь менеджера {{ vybrannyy }} – {{ ochered|length }} компаний</h2>
  <p class="pometka">Ровно «Вся очередь» менеджера и в том же порядке (та же функция сортировки, что у главной): сначала новые, затем перезвоны по сроку, внутри – по убыванию балла. Скрытые, перенесённые во вкладки и ИНН вне каталога не показываются: менеджер их тоже не видит. <a href="{{ ssylka(user='') }}">закрыть</a></p>
  <div class="tabl-obol"><table class="stat">
    <thead><tr><th>№</th><th>Компания</th><th>ИНН</th><th>Регион</th><th>Балл очереди</th><th>Результат</th><th>Последний контакт</th><th>Следующий контакт</th><th>Телефон</th><th>Тех / Закуп</th></tr></thead>
    <tbody>
    {% for z in ochered %}
      <tr><td>{{ loop.index }}</td><td><a href="{{ karta(z.inn) }}">{{ z.nazv or '–' }}</a></td><td>{{ z.inn }}</td><td>{{ z.region or '–' }}</td>
        <td>{{ ('%.1f'|format(z.score or 0)).replace('.', ',') }}</td><td>{{ metki.get(z.rez, z.rez) }}</td>
        <td>{{ (z.last_contact_at or '')[:16].replace('T', ' ') or '–' }}</td><td>{{ (z.next_contact_at or '')[:16].replace('T', ' ') or '–' }}</td>
        <td>{{ 'да' if z.has_phone else '–' }}</td>
        <td>{{ 'тех' if z.has_tech else '' }}{% if z.has_tech and z.has_purchaser %} / {% endif %}{{ 'закуп' if z.has_purchaser else '' }}{% if not z.has_tech and not z.has_purchaser %}–{% endif %}</td></tr>
    {% else %}<tr><td colspan="10">Очередь пуста.</td></tr>{% endfor %}
    </tbody>
  </table></div>
  {% endif %}

</main>
</body>
</html>
'''


# ======================================================================== логика прогона
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

LOK = os.environ.get('FIXKS_LOKALNO')        # проверка в песочнице: каталог с kod/ и db/
VENV = sys.executable if LOK else r'C:\seostat\.venv\Scripts\python.exe'
KOREN = os.path.join(LOK, 'kod', 'seostat') if LOK else r'C:\seostat'
APP = os.path.join(KOREN, 'app')
DATA = os.path.join(LOK, 'db') if LOK else os.path.join(KOREN, 'data')
BAZY = ({'kc': ('fixKS-sales.db', 'fixKS-kat.db')} if LOK else
        {'kc': ('centro_sales.db', 'centrifugal.db'), 'p25': ('p25_sales.db', 'p25.db')})
PUT = {'kc': '/obzvon', 'p25': '/p25'}
PORT = {'kc': 8012, 'p25': 8014}
DROP = os.path.join(LOK, 'drop') if LOK else r'C:\seostat\drop\drop-storage'
ZAMOK = os.path.join(KOREN, '_zamok.txt')
T = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(LOK or KOREN, '_stage', 'fixKS-' + T)
BEKAP = os.path.join(KOREN, '_bekap', 'fixKS-' + T)
RCS_REL = os.path.join('app', 'api', 'routes_centro_sales.py')
CEN_REL = os.path.join('app', 'templates', 'centro.html')
SHB_REL = os.path.join('app', 'templates', 'fixKS_stats.html')
RCS_PRIZNAK = '# ===================================================================== fixKS (21.10): статистика админа'
SSYLKA_RE = r'<a href="%s/centro/stats">Статистика</a>'
log = []


def p(*a):
    s = ' '.join(str(x) for x in a)
    log.append(s)
    print(s, flush=True)


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode('utf-8')).hexdigest()[:16]


def chitat(put):
    return io.open(put, encoding='utf-8', newline='').read() if os.path.exists(put) else None


def pisat(put, t):
    with io.open(put, 'w', encoding='utf-8', newline='') as f:
        f.write(t)


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)                      # брошенный (старше 25 мин)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def pravki(koren) -> list:
    """Правки по якорям, идемпотентно. Возвращает, что сделано."""
    sd = []
    rcs = os.path.join(koren, RCS_REL)
    t = chitat(rcs)
    if RCS_PRIZNAK in t:
        sd.append('routes_centro_sales: уже есть')
    else:
        pisat(rcs, t + RCS_KOD)
        sd.append('routes_centro_sales: дописан блок fixKS')
    c = os.path.join(koren, CEN_REL)
    t = chitat(c)
    if SHAPKA_PRIZNAK in t:
        sd.append('centro.html: уже есть')
    else:
        if t.count(SHAPKA_YAKOR) != 1:
            raise SystemExit('centro.html: якорь шапки найден %d раз' % t.count(SHAPKA_YAKOR))
        pisat(c, t.replace(SHAPKA_YAKOR, SHAPKA_NOVOE))
        sd.append('centro.html: ссылка «Статистика»')
    s = os.path.join(koren, SHB_REL)
    if chitat(s) == SHABLON:
        sd.append('fixKS_stats.html: уже есть')
    else:
        if os.path.exists(s):
            raise SystemExit('fixKS_stats.html уже есть и отличается – чужой файл?')
        pisat(s, SHABLON)
        sd.append('fixKS_stats.html: новый шаблон')
    return sd


def kopiya_bazy(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True, timeout=30)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ---------------------------------------------------------------- проверка в отдельном процессе (venv)
NORM = [(re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:\d{2}|Z)?'), '<ВРЕМЯ>'),
        (re.compile(r'\d{2}\.\d{2}(\.\d{4})?,? \d{2}:\d{2}'), '<ВРЕМЯ>')]


def norm(t):
    for r, z in NORM:
        t = r.sub(z, t)
    return t


def proverka(var_koren, konf, vyhod):
    """Импорт приложения варианта, рендер страниц под admin/продавцами, действия продавцов на своей копии
    базы. Пишет JSON: {ключ: [код, sha нормализованного текста]} + дампы базы + тела для сравнения."""
    sys.path.insert(0, var_koren)
    os.chdir(var_koren)
    from fastapi.testclient import TestClient
    from app.obzvon import create_app
    from app.api import routes_centro_sales as rcs
    vn = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    bp = PUT[konf]
    s = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    lyudi = [(r[0], r[1]) for r in s.execute('SELECT username, role FROM users WHERE is_active=1 ORDER BY username')]
    s.close()
    if not any(r == 'admin' for _u, r in lyudi):
        lyudi = [('admin', 'admin')] + lyudi
    res, tela = {}, {}

    def kak(u, rol):
        vn.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': u, 'role': rol, 'is_active': 1}
        return TestClient(vn, follow_redirects=False)

    def get(u, rol, url, klyuch=None):
        r = kak(u, rol).get(bp + url)
        k = klyuch or '%s GET %s' % (u, url)
        res[k] = [r.status_code, sha(norm(r.text)), len(r.text)]
        tela[k] = r.text
        return r

    for u, rol in lyudi:
        g = get(u, rol, '/centro')
        inns = re.findall(r'centro\?inn=(\d{10,12})', g.text.split('class="queue-list"', 1)[-1])
        for st in ('v_rabote', 'ne_ponravilas', 'dubl'):
            get(u, rol, '/centro?call_status=' + st)
        for inn in inns[:2]:
            get(u, rol, '/centro?inn=' + inn, '%s GET карточка %d' % (u, inns.index(inn)))
        get(u, rol, '/centro/stats')
        if rol == 'admin':
            get(u, rol, '/centro/admin')
            get(u, rol, '/centro?assigned_user=' + next((x for x, r in lyudi if r == 'sales'), ''))
    stat = {}
    if konf == 'kc' and os.path.exists(os.path.join(var_koren, SHB_REL)) and RCS_PRIZNAK in chitat(os.path.join(var_koren, RCS_REL)):
        stat = proverka_statistiki(kak, bp, lyudi, tela)
    # действия продавцов – в том же порядке во всех вариантах, на своей копии базы
    for u, rol in lyudi:
        if rol != 'sales':
            continue
        g = kak(u, rol).get(bp + '/centro')
        inns = re.findall(r'centro\?inn=(\d{10,12})', g.text.split('class="queue-list"', 1)[-1])
        if len(inns) < 2:
            continue
        r = kak(u, rol).post(bp + '/centro/save', data={'inn': inns[0], 'call_result': 'v_rabote',
                                                        'comment': 'fixKS проверка', 'next_contact_at': '', 'return_query': ''})
        res['%s POST save' % u] = [r.status_code, r.headers.get('location', ''), 0]
        r = kak(u, rol).post(bp + '/centro/hide', data={'inn': inns[1], 'kind': 'company', 'value': inns[1],
                                                        'reason': 'fixKS проверка'})
        res['%s POST hide' % u] = [r.status_code, r.headers.get('location', ''), 0]
        get(u, rol, '/centro', '%s GET главная после действий' % u)
    s = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    dump = {}
    for tabl, kol in (('company_state', 'inn, username, status, call_result, next_contact_at'),
                      ('company_comment', 'inn, username, body'), ('activity_log', 'inn, username, action, payload_json'),
                      ('hidden_item', 'inn, kind, value, reason, username'), ('company_assignment', 'inn, username, assignment_score')):
        dump[tabl] = sha(json.dumps(sorted(map(list, s.execute('SELECT %s FROM %s' % (kol, tabl)).fetchall())), ensure_ascii=False))
    s.close()
    io.open(vyhod, 'w', encoding='utf-8').write(json.dumps({'res': res, 'dump': dump, 'stat': stat}, ensure_ascii=False))
    io.open(vyhod + '.tela', 'w', encoding='utf-8').write(json.dumps(tela, ensure_ascii=False))


def proverka_statistiki(kak, bp, lyudi, tela) -> dict:
    """Только для варианта «после», до действий продавцов (база та же, что у главной в tela)."""
    plokh, ok = [], 0
    prod = [u for u, r in lyudi if r == 'sales']
    stranicy = {}
    for url in ('', '?stat_vse=1', '?stat_ot=2026-08-01&stat_data=2026-08-31', '?stat_data=2026-10-19',
                '?stat_ot=2026-13-01&stat_data=2030-01-01', '?stat_ot=2026-10-19&stat_data=2026-08-01') + tuple(
            '?stat_vse=1&stat_user=' + u for u in prod) + tuple('?user=' + u for u in prod):
        r = kak('admin', 'admin').get(bp + '/centro/stats' + url)
        stranicy[url] = r.text
        if r.status_code != 200 or 'id="fixKS-stats"' not in r.text:
            plokh.append('страница %s: %s' % (url, r.status_code))
        else:
            ok += 1
    for u in prod:   # продавцу – 403
        r = kak(u, 'sales').get(bp + '/centro/stats')
        if r.status_code != 403:
            plokh.append('продавцу %s статистика отдала %s' % (u, r.status_code))
        else:
            ok += 1
    # очередь на странице = «Вся очередь» продавца: число и порядок первой страницы
    ochered = {}
    for u in prod:
        t = stranicy['?user=' + u]
        m = re.search(r'Очередь менеджера %s – (\d+) компаний' % re.escape(u), t)
        glav = tela.get('%s GET /centro' % u, '')
        g = re.search(r'class="total-count">(\d+) компаний', glav)
        n_st, n_gl = int(m.group(1)) if m else -1, int(g.group(1)) if g else -2
        blok = t.split('id="ochered-prodavca"', 1)[-1]
        inn_st = re.findall(r'<td>(\d{10,12})</td>', blok)[:20]
        inn_gl = re.findall(r'centro\?inn=(\d{10,12})', glav.split('class="queue-list"', 1)[-1].split('</div>', 1)[0])
        ochered[u] = {'stat': n_st, 'glavnaya': n_gl, 'poryadok_20': inn_st == inn_gl[:20]}
        if n_st != n_gl or inn_st != inn_gl[:20] or len(inn_st) != min(20, n_gl):
            plokh.append('очередь %s: статистика %s, главная %s, порядок %s' % (u, n_st, n_gl, inn_st == inn_gl[:20]))
        else:
            ok += 1
        # то же число – в таблице «Назначено → показывается»
        m2 = re.search(r'<tr><td>%s</td><td>(\d+)</td>.*?<td class="razd"><b>(?:<a href="[^"]*">)?(\d+)' % re.escape(u),
                       stranicy[''].split('id="naznacheno-pokazano"', 1)[-1], re.S)
        if not m2 or int(m2.group(2)) != n_gl:
            plokh.append('«назначено → показывается» %s: %s при главной %s' % (u, m2.groups() if m2 else None, n_gl))
        else:
            ok += 1
            ochered[u]['naznacheno'] = int(m2.group(1))
    # каждая цифра-ссылка = число строк её списка
    ssylki = {}
    for t in stranicy.values():
        for href, n in re.findall(r'<a href="([^"]*(?:\?|&amp;)sp=[^"]*)">(\d+)</a>', t):
            ssylki.setdefault(href.replace('&amp;', '&'), set()).add(int(n))
    proshlo = 0
    t0 = time.time()
    for href, nn in sorted(ssylki.items()):
        if time.time() - t0 > 600:
            if proshlo < 200:
                plokh.append('ссылки: не успела проверить %d из %d' % (len(ssylki) - proshlo, len(ssylki)))
            break
        r = kak('admin', 'admin').get(href.split('#')[0])
        blok = r.text.split('id="spisok"', 1)[-1].split('</section>', 1)[0]
        m = re.search(r'<h2[^>]*>(\d+) компани', blok)
        strok = len(re.findall(r'<tr><td>\d+</td>', blok))
        if r.status_code != 200 or not m or len(nn) != 1 or int(m.group(1)) != list(nn)[0] or strok != list(nn)[0]:
            plokh.append('ссылка %s: цифра %s, заголовок %s, строк %s, код %s' % (href[:120], nn, m.group(1) if m else None, strok, r.status_code))
        proshlo += 1
    # карточки по ссылкам со статистики открываются админу
    kartochki = sorted({h.replace('&amp;', '&') for t in stranicy.values() for h in re.findall(r'href="(%s/centro\?inn=[^"]+)"' % re.escape(bp), t)})
    shag = max(1, len(kartochki) // 25)
    kart_plokh = 0
    for h in kartochki[::shag]:
        r = kak('admin', 'admin').get(h)
        if r.status_code != 200:
            kart_plokh += 1
            plokh.append('карточка %s: %s' % (h, r.status_code))
    for imya, url in (('fixKS-stats-admin.html', ''), ('fixKS-stats-vse.html', '?stat_vse=1'), ('fixKS-stats-user2.html', '?user=user2')):
        if url in stranicy:
            io.open(os.path.join(DROP, imya), 'w', encoding='utf-8').write(stranicy[url])
    return {'plokh': plokh, 'ok': ok, 'ochered': ochered, 'ssylok': len(ssylki), 'ssylok_provereno': proshlo,
            'kartochek': len(kartochki[::shag]), 'kartochek_plokh': kart_plokh,
            'soobshcheniya': re.findall(r'role="alert"><div>(.*?)</div>', stranicy['?stat_ot=2026-13-01&stat_data=2030-01-01'])}


# ---------------------------------------------------------------- стадия: три варианта и сравнение
def stadiya() -> bool:
    os.makedirs(os.path.join(STAGE, 'db'), exist_ok=True)
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    do_k = os.path.join(STAGE, 'do')
    shutil.copytree(APP, os.path.join(do_k, 'app'), ignore=ign)
    posle_k = os.path.join(STAGE, 'posle')
    shutil.copytree(os.path.join(do_k, 'app'), os.path.join(posle_k, 'app'))
    p('правки в stage:', pravki(posle_k))
    smes_k = os.path.join(STAGE, 'smes')        # старый Python + новые шаблоны = 8014 без перезапуска
    shutil.copytree(os.path.join(do_k, 'app'), os.path.join(smes_k, 'app'))
    shutil.copytree(os.path.join(posle_k, 'app', 'templates'), os.path.join(smes_k, 'app', 'templates'), dirs_exist_ok=True)
    varianty = {'do': do_k, 'posle': posle_k, 'smes': smes_k}
    procy = []
    for konf, (sdb, kdb) in BAZY.items():
        snimok = os.path.join(STAGE, 'db', '%s-sales-snimok.db' % konf)
        kat = os.path.join(STAGE, 'db', '%s-kat.db' % konf)
        kopiya_bazy(os.path.join(DATA, sdb), snimok)
        kopiya_bazy(os.path.join(DATA, kdb), kat)
        for imya, k in varianty.items():
            sd = os.path.join(STAGE, 'db', '%s-sales-%s.db' % (konf, imya))
            shutil.copy(snimok, sd)
            env = {x: v for x, v in os.environ.items() if not x.startswith(('CENTRO', 'PARK_', 'OBZVON', 'CENTRIFUGAL'))}
            env.update(PYTHONIOENCODING='utf-8', PYTHONPATH=k, OBZVON_ROOT_PATH=PUT[konf], CENTRO_SALES_DB=sd,
                       CENTRIFUGAL_DB=kat, CENTRO_DB=kat, PARK_OCHERED_SALES_DB=sd, PARK_OCHERED_DB=kat,
                       PARK_PANEL_DB=os.path.join(STAGE, 'db', 'net-park.db'), CENTRO_SESSION_SECRET='x' * 40)
            vyh = os.path.join(STAGE, '%s-%s.json' % (konf, imya))
            procy.append((konf, imya, vyh, subprocess.Popen(
                [VENV, os.path.abspath(__file__), '--proverka', k, konf, vyh], cwd=k, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)))
    rez = {}
    for konf, imya, vyh, pr in procy:
        out = pr.communicate(timeout=1300)[0].decode('utf-8', 'replace')
        if pr.returncode or not os.path.exists(vyh):
            p('ПРОВЕРКА %s/%s УПАЛА rc=%s:\n%s' % (konf, imya, pr.returncode, out[-2500:]))
            return False
        rez[(konf, imya)] = json.load(io.open(vyh, encoding='utf-8'))
        rez[(konf, imya)]['tela'] = json.load(io.open(vyh + '.tela', encoding='utf-8'))
    plokh = 0
    for konf in BAZY:
        do, smes, posle = rez[(konf, 'do')], rez[(konf, 'smes')], rez[(konf, 'posle')]
        ssylka = SSYLKA_RE % PUT[konf]
        for k, v in sorted(do['res'].items()):
            # «старый код + новые шаблоны» (8014 до перезапуска) – байт в байт как до правки
            if smes['res'].get(k) != v:
                plokh += 1
                p('РАСХОЖДЕНИЕ %s smes %s: было %s, стало %s' % (konf, k, v, smes['res'].get(k)))
            pv = posle['res'].get(k)
            if k.endswith('GET /centro/stats'):
                ozh = 200 if k.startswith('admin ') else 403
                if v[0] != 404 or pv is None or pv[0] != ozh:
                    plokh += 1
                    p('СТАТИСТИКА %s %s: до %s, после %s (ждём 404 → %s)' % (konf, k, v[0], pv and pv[0], ozh))
                continue
            tp = posle['tela'].get(k)
            if tp is not None and k.startswith('admin ') and v[0] == 200 and '/centro/admin' not in k:
                if tp.count(ssylka) != 1:
                    plokh += 1
                    p('ШАПКА %s %s: ссылка «Статистика» %d раз' % (konf, k, tp.count(ssylka)))
                tp = tp.replace(ssylka, '')
            if tp is not None:
                pv = [pv[0], sha(norm(tp)), len(tp)]
            if pv != v:
                plokh += 1
                p('РАСХОЖДЕНИЕ %s posle %s: было %s, стало %s' % (konf, k, v, pv))
                if tp is not None and k in do['tela']:
                    import difflib
                    for l in list(difflib.unified_diff(norm(do['tela'][k]).splitlines(), norm(tp).splitlines(), lineterm='', n=0))[:12]:
                        p('      ' + l[:200])
        for imya in ('smes', 'posle'):
            if rez[(konf, imya)]['dump'] != do['dump']:
                plokh += 1
                p('БАЗА после действий %s/%s отличается: %s / %s' % (konf, imya, do['dump'], rez[(konf, imya)]['dump']))
        p('%s: запросов %d, расхождений по вариантам – см. выше; дампы баз после действий: %s' % (
            konf, len(do['res']), 'совпали' if all(rez[(konf, i)]['dump'] == do['dump'] for i in ('smes', 'posle')) else 'НЕТ'))
        p('   коды до: %s' % sorted({(k.split(' ', 1)[1].split('?')[0], v[0]) for k, v in do['res'].items()}))
    st = rez[('kc', 'posle')]['stat']
    p('статистика: проверок ok %s, ссылок-цифр %s (проверено %s), карточек %s (плохих %s)' % (
        st.get('ok'), st.get('ssylok'), st.get('ssylok_provereno'), st.get('kartochek'), st.get('kartochek_plokh')))
    p('   очередь: %s' % st.get('ochered'))
    p('   сообщения о датах: %s' % st.get('soobshcheniya'))
    for x in st.get('plokh') or []:
        p('   ПЛОХО: ' + x)
    plokh += len(st.get('plokh') or []) + (0 if st else 1)
    p('ПЛОХИХ ПРОВЕРОК: %d' % plokh)
    return plokh == 0


def http(port, url):
    try:
        r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:%d%s' % (port, url)), timeout=30)
        return [r.status, sha(norm(r.read().decode('utf-8', 'replace')))]
    except urllib.error.HTTPError as e:
        return [e.code, '']
    except Exception as e:  # noqa: BLE001
        return [str(e)[:60], '']


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


urllib.request.install_opener(urllib.request.build_opener(BezRedirekta))
ZHIVYE = [(8012, '/obzvon/centro/login'), (8012, '/obzvon/centro/stats'), (8014, '/p25/centro/login'),
          (8014, '/p25/centro/stats'), (8011, '/'), (8011, '/stat/')]


def nssm_restart(svc):
    for exe in (r'C:\Windows\System32\nssm.exe', r'C:\nssm.exe'):
        if os.path.exists(exe):
            r = subprocess.run([exe, 'restart', svc], capture_output=True, timeout=120)
            return (r.stdout + r.stderr).decode('utf-16-le' if b'\x00' in r.stdout + r.stderr else 'cp866', 'replace').replace('\x00', '').strip()
    return 'nssm не найден'


def zhdat_vhod(port, url):
    for _ in range(30):
        time.sleep(2)
        k = http(port, url)
        if k[0] == 200:
            return k
    return k


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else '--suho'
    if rezhim == '--proverka':
        return proverka(sys.argv[2], sys.argv[3], sys.argv[4])
    os.makedirs(DROP, exist_ok=True)
    p('fixKS %s, %s' % (rezhim, T))
    zamok = rezhim == '--primenit'
    if zamok:
        vzyat_zamok('fixKS (KS: статистика панели КЦ)')
    try:
        if not LOK:
            do_zhivye = {'%d %s' % k: http(*k) for k in ZHIVYE}
            p('живые до:', do_zhivye)
        ok = stadiya()
        if rezhim != '--primenit':
            p('сухой прогон: живые файлы не трогались')
            return
        if not ok:
            p('ПРОВЕРКА НЕ ПРОШЛА – живые файлы не трогались')
            raise SystemExit(1)
        # запись: копии прежних файлов, правки по якорям (файлы перечитаны под замком), сверка со stage
        os.makedirs(os.path.join(BEKAP, 'app', 'api'), exist_ok=True)
        os.makedirs(os.path.join(BEKAP, 'app', 'templates'), exist_ok=True)
        for rel in (RCS_REL, CEN_REL):
            shutil.copy2(os.path.join(KOREN, rel), os.path.join(BEKAP, rel))
            if sha(chitat(os.path.join(KOREN, rel))) != sha(chitat(os.path.join(STAGE, 'do', rel))):
                p('ЖИВОЙ ФАЙЛ ИЗМЕНИЛСЯ ПОСЛЕ КОПИИ В STAGE: %s – запись отменена' % rel)
                raise SystemExit(1)
        sdelano = pravki(KOREN)
        p('записано:', sdelano, ' копии прежних:', BEKAP)
        sovp = all(sha(chitat(os.path.join(KOREN, r))) == sha(chitat(os.path.join(STAGE, 'posle', r))) for r in (RCS_REL, CEN_REL, SHB_REL))
        p('живые файлы = проверенный stage:', sovp)
        if not sovp:
            raise RuntimeError('живые файлы не совпали с проверенным stage')
        p('перезапуск obzvon (8012):', nssm_restart('obzvon'))
        p('8012 вход:', zhdat_vhod(8012, '/obzvon/centro/login'))
        posle = {'%d %s' % k: http(*k) for k in ZHIVYE}
        p('живые после:', posle)
        if posle['8012 /obzvon/centro/login'][0] != 200 or posle['8012 /obzvon/centro/stats'][0] != 303:
            raise RuntimeError('8012 после перезапуска: вход %s, статистика %s (ждём 200 и 303)' % (
                posle['8012 /obzvon/centro/login'][0], posle['8012 /obzvon/centro/stats'][0]))
        for k, v in posle.items():
            if not k.startswith('8012 /obzvon/centro/stats') and v[0] != do_zhivye[k][0]:
                p('ВНИМАНИЕ: %s код был %s, стал %s' % (k, do_zhivye[k][0], v[0]))
            elif k.endswith('/login') and v != do_zhivye[k]:
                p('ВНИМАНИЕ: %s страница входа изменилась' % k)
        p('ГОТОВО')
    except RuntimeError as e:
        p('ОШИБКА ПОСЛЕ ЗАПИСИ: %s – возвращаю свои файлы из %s' % (e, BEKAP))
        for rel in (RCS_REL, CEN_REL):
            shutil.copy2(os.path.join(BEKAP, rel), os.path.join(KOREN, rel))
        try:
            os.remove(os.path.join(KOREN, SHB_REL))
        except OSError:
            pass
        p('перезапуск obzvon после отката:', nssm_restart('obzvon'), zhdat_vhod(8012, '/obzvon/centro/login'))
        raise SystemExit(1)
    finally:
        if zamok:
            otdat_zamok()
        io.open(os.path.join(DROP, 'fixKS-%s-%s.txt' % (rezhim.strip('-'), T)), 'w', encoding='utf-8').write('\n'.join(log))
        if os.path.isdir(STAGE) and not LOK:
            shutil.rmtree(os.path.join(STAGE, 'db'), ignore_errors=True)     # копии баз не копим
            if 'ГОТОВО' in log[-1:] or rezhim != '--primenit':
                shutil.rmtree(STAGE, ignore_errors=True)


if __name__ == '__main__':
    main()
