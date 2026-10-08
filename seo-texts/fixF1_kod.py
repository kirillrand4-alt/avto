# -*- coding: utf-8 -*-
"""fixF1 (08.10, повторная проверка панели Meyer): доводка кода очереди, фильтров и статистики.

1. Перезвон не прыгает наверх. _queue_rank: перезвон, срок которого наступил (сегодня или
   просрочен, по Москве), – наверх по сроку; новые – по баллу очереди, будущий перезвон стоит
   на своём месте по баллу; обработанные (вкладки) – по сроку перезвона, затем по баллу. Тот же
   порядок у CSV директора и очереди продавца в статистике (они берут _queue_rank).
2. Числа у пунктов фильтров главной – по тому же набору, что и список: с учётом вкладки,
   скрытых и прочих выбранных фильтров (число = сколько строк покажет список с этим пунктом).
3. Скрытые компании и статистика: директору в отборах по результату (вкладка, «Результат
   звонка», отметки за период, причина, событие) скрытые видны с пометкой «скрыта» – цифры их
   считают (сделанная работа остаётся сделанной), ссылка с цифры их показывает. Очередь – без
   скрытых. «По результатам звонка» – только ИНН каталога (их можно открыть списком).
4. Регионы: у продавца – только регионы с его компаниями в текущем отборе, у директора – все;
   рядом число компаний.
5. Вид: плавающие «К результату звонка ↓» и «⚙ Вид» на ноутбуке – в правом поле, не поверх
   карточек; балл компании с пометкой – «в конце: пометка …» вместо числа (число – в подсказке,
   сортировка прежняя); «тот же ЛПР, что у №… » – один номер ЛПР наверху у нескольких компаний.

Порядок (OBSHCHEE.md): замок → перечитать файлы → правки по якорям (идемпотентно) → проверка в
отдельном venv-процессе на КОПИЯХ баз → провал: вернуть свои файлы из своей копии → успех:
перезапуск → отдать замок.

    python3 zapusk_na_servere.py fixF1_kod.py
    python3 fixF1_kod.py --lokalno <папка app>      # те же правки в локальную копию кода
"""
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'

F_RCS = ('api', 'routes_centro_sales.py')
F_SP = ('templates', '_ochered_spisok.html')
F_C = ('templates', 'centro.html')
F_ST = ('templates', 'centro_stats.html')

# ============================================================================ код в конец routes
RCS_KOD = r'''


# ================================================================ fixF1 (08.10, повторная проверка)
# 1. Числа у пунктов фильтров главной – по тому же набору, что и список (вкладка, скрытые, прочие
#    выбранные фильтры): число у пункта = сколько строк покажет список, если выбрать этот пункт
#    и оставить остальное. Раньше считалось по всем компаниям пользователя, а «Вся очередь»
#    обработанные скрывает – после первых отметок числа расходились со списком.
# 2. Регионы с числом: у продавца – только регионы, где у него есть компании в этом отборе; у
#    директора – все регионы каталога.
# 3. Скрытые компании директору видны с пометкой «скрыта» в отборах по результату (вкладка,
#    «Результат звонка», отметки за период, причина, событие): статистика их считает – сделанная
#    работа остаётся сделанной, – и список по ссылке с цифры обязан их показать. «Вся очередь» и
#    очередь продавца – без скрытых, как раньше.
# 4. «Тот же ЛПР, что у …»: один и тот же номер ЛПР (строка ЛПР в списке) у нескольких компаний
#    одной очереди – продавец звонит человеку один раз.
import threading as _thr_f1

_FIXF1_LOK = _thr_f1.local()
_FIXF1_NE_FILTRY = ("page", "size", "inn", "skrytye", "sort")
_FIXF1_OTBOR_REZ = ("call_status", "ot", "do", "prichina", "bez_poyasneniya", "rez_p", "kto_p", "sob")


class _FixF1Zapros:
    """Для _matches: те же правила отбора, но с другим набором параметров."""

    def __init__(self, params: dict):
        self.query_params = params


def _fixF1_s_skrytymi(params, user, skrytye) -> bool:
    """Директор смотрит отбор по результату – скрытые показываются (с пометкой)."""
    if (user or {}).get("role") != "admin" or skrytye:
        return False
    return any(str(params.get(k) or "").strip() for k in _FIXF1_OTBOR_REZ)


def _fixF1_pometit_skrytye(spisok, hidden_co) -> None:
    for c in spisok:
        c["skryta"] = (hidden_co or {}).get(str(c.get("inn") or "")) or None


# Кэш на время одного запроса (поток): счётчики зовут _matches по разу на группу фильтров, и без
# кэша каждый вызов заново читал бы журнал отметок и индекс поиска по контактам. Вне счётчиков
# кэш выключен – функции работают как прежде.
_fixF1_sobytiya_bez_kesha = _sobytiya
_fixF1_sobytiya_zvonka_bez_kesha = _sobytiya_zvonka
_fixF1_indeks_bez_kesha = _indeks_poiska


def _fixF1_kesh(klyuch, fn):
    kesh = getattr(_FIXF1_LOK, "kesh", None)
    if kesh is None:
        return fn()
    if klyuch not in kesh:
        kesh[klyuch] = fn()
    return kesh[klyuch]


def _sobytiya(conn, ot=None, do=None, vse_deystviya=False):  # noqa: F811 – fixF1: с кэшем запроса
    return _fixF1_kesh(("sobytiya", ot, do, bool(vse_deystviya)),
                       lambda: _fixF1_sobytiya_bez_kesha(conn, ot, do, vse_deystviya))


def _sobytiya_zvonka(conn, ot=None, do=None, inn=None):  # noqa: F811
    return _fixF1_kesh(("zvonka", ot, do, inn),
                       lambda: _fixF1_sobytiya_zvonka_bez_kesha(conn, ot, do, inn))


def _indeks_poiska():  # noqa: F811
    return _fixF1_kesh(("indeks",), _fixF1_indeks_bez_kesha)


def _fixF1_schetchiki(choices, vidimye, request, user, companies, assignments) -> list:
    P = {k: request.query_params.get(k) for k in request.query_params.keys()
         if k not in _FIXF1_NE_FILTRY}
    _FIXF1_LOK.kesh = {}
    try:
        return _fixF1_schetchiki_(choices, vidimye, P, user, companies, assignments)
    finally:
        _FIXF1_LOK.kesh = None


def _fixF1_schetchiki_(choices, vidimye, P, user, companies, assignments) -> list:
    def nabor(*bez, **est):
        p = {k: v for k, v in P.items() if k not in bez}
        p.update(est)
        return _matches(vidimye, _FixF1Zapros(p))

    def schet(spisok, znacheniya) -> dict:
        sch: dict = {}
        for c in spisok:
            for z in set(znacheniya(c)):
                if z:
                    sch[z] = sch.get(z, 0) + 1
        return sch

    def vybran(k) -> str:
        return str(P.get(k) or "").strip()

    # --- регионы
    sch = schet(nabor("region"), lambda c: [str(c.get("region") or "")])
    if user["role"] == "admin":
        vse = {str(c.get("region") or "") for c in companies}
    else:
        vse = {r for r, n in sch.items() if n}
    if vybran("region"):
        vse.add(vybran("region"))
    regiony = [(r, sch.get(r, 0)) for r in sorted((x for x in vse if x), key=str.casefold)]
    # --- сегмент (с галочкой «+ доп. ОКВЭД» – и по доп.)
    dop = P.get("segment_dop") == "1"
    sch = schet(nabor("segment"), lambda c: _segmenty(c, dop))
    univ = [s for s, _n in (choices.get("segment") or [])]
    if vybran("segment") and vybran("segment") not in univ:
        univ.append(vybran("segment"))
    choices["segment"] = [(s, sch.get(s, 0)) for s in sorted(univ)]
    # --- отрасль, роль ЛПР – по убыванию числа
    sch = schet(nabor("otrasl"), lambda c: [str(c.get("otrasl") or "")])
    univ = [o for o, _n in (choices.get("otrasl") or [])]
    if vybran("otrasl") and vybran("otrasl") not in univ:
        univ.append(vybran("otrasl"))
    choices["otrasl"] = sorted(((o, sch.get(o, 0)) for o in univ), key=lambda x: (-x[1], x[0]))
    sch = schet(nabor("rol_lpr"), lambda c: [r.strip() for r in str(c.get("lpr_roli") or "").split(",")])
    univ = [o for o, _n in (choices.get("rol_lpr") or [])]
    if vybran("rol_lpr") and vybran("rol_lpr") not in univ:
        univ.append(vybran("rol_lpr"))
    choices["rol_lpr"] = sorted(((o, sch.get(o, 0)) for o in univ), key=lambda x: (-x[1], x[0]))
    # --- источник базы
    sch = schet(nabor("baza"), lambda c: [b.strip() for b in str(c.get("bazy") or "").split("|")])
    choices["baza"] = [(b, sch.get(b, 0), op) for b, _n, op in (choices.get("baza") or [])]
    # --- пометка очереди
    if choices.get("pometka_vybor"):
        rr = nabor("pometka_och")
        choices["pometka_vybor"] = [(k, nz, sum(1 for c in rr if _pometka_sovpala(c, k)))
                                    for k, nz, _n in choices["pometka_vybor"]]
    # --- галочки
    for kl, pole, f in (("has_tech", "has_tech_n", lambda c: c.get("has_tech")),
                        ("lpr_mobilnyy", "lpr_mobilnyy_n", lambda c: c.get("lpr_mobilnyy")),
                        ("lpr_fio", "lpr_fio_n", lambda c: c.get("lpr_s_fio")),
                        ("bitrix", "bitrix_n", lambda c: c.get("bitrix_kc")),
                        ("klient_sc", "klient_sc_n", _klient_sc),
                        ("rabochee", "rabochee_n", _rabochee_vremya)):
        choices[pole] = sum(1 for c in nabor(kl) if f(c))
    if choices.get("pod_zamenu_n"):
        n = sum(1 for c in nabor("pod_zamenu") if c.get("pod_zamenu"))
        if n or not P.get("pod_zamenu"):
            choices["pod_zamenu_n"] = n
    # --- состояние машины и приговор (есть только у баз с фактами по машинам)
    if choices.get("sostoyanie"):
        sch = schet(nabor("sostoyanie"), lambda c: list(c.get("sostoyaniya_mashin") or ()))
        choices["sostoyanie"] = sorted(((s, sch.get(s, 0)) for s, _n in choices["sostoyanie"]),
                                       key=lambda x: -x[1])
    if choices.get("verdikt"):
        sch = schet(nabor("verdikt"), lambda c: [c.get("verdikt") or ""])
        choices["verdikt"] = [(v, sch.get(v, 0)) for v, _n in choices["verdikt"]]
    # --- перезвон: выбор перезвона ищет по всем вкладкам – так и считаем
    choices["perezvon_segodnya_n"] = len(nabor(perezvon="segodnya"))
    choices["perezvon_prosrocheno_n"] = len(nabor(perezvon="prosrocheno"))
    # --- строка директора
    if user["role"] == "admin":
        choices["prichiny"] = [(p, len(nabor(prichina=p))) for p, _n in (choices.get("prichiny") or [])]
        choices["dubl_n"] = len(nabor(prichina="dubl"))
        choices["bez_poyasneniya_n"] = len(nabor(bez_poyasneniya="1"))
        net = []
        for c in companies:
            if c["inn"] in assignments:
                continue
            d = dict(c)
            d["assigned_user"] = ""
            d["assignment_score"] = 0
            net.append(d)
        p = {k: v for k, v in P.items()}
        p["assigned_user"] = "__net__"
        choices["bez_prodavca_n"] = len(_matches(net, _FixF1Zapros(p))) if net else 0
    return regiony


def _fixF1_klyuch_lpr(kratko) -> str:
    """Номер ЛПР из строки ЛПР списка («ФИО · должность · +7 …») – цифрами, с добавочным."""
    s = str(kratko or "").strip()
    if not s or s.startswith("ЛПР не найден") or "без номера" in s:
        return ""
    for chast in s.split(" · "):
        d = re.sub(r"\D", "", re.sub(r"\(\s*\+\s*ещё.*?\)", "", chast))
        if len(d) >= 10:
            if len(d) >= 11 and d[0] == "8":
                d = "7" + d[1:]
            elif len(d) == 10:
                d = "7" + d
            return d
    return ""


def _fixF1_tot_zhe_lpr(vse, spisok) -> None:
    """Один номер ЛПР у нескольких компаний одной очереди -> строке «тот же ЛПР, что у …»."""
    poz = {c["inn"]: i + 1 for i, c in enumerate(spisok)}
    gruppy: dict = {}
    for c in vse:
        k = _fixF1_klyuch_lpr(c.get("lpr_kratko"))
        if k:
            gruppy.setdefault((c.get("assigned_user") or "", k), []).append(c)
    for chleny in gruppy.values():
        if len(chleny) < 2:
            continue
        chleny = sorted(chleny, key=lambda d: poz.get(d["inn"], 10 ** 6))
        for c in chleny:
            c["tot_zhe_lpr"] = [{"inn": d["inn"], "poz": poz.get(d["inn"]),
                                 "nazv": d.get("predpriyatie") or d.get("name_short") or d["inn"]}
                                for d in chleny if d is not c][:6]


def _fixF1_po_rezultatu(conn, obshchee, imena) -> None:
    """«По результатам звонка» – только ИНН каталога: их и показывает список по ссылке."""
    if not imena:
        return
    po: dict = {}
    for inn, rez in conn.execute(
            "SELECT a.inn, COALESCE(s.call_result,'new') FROM company_assignment a "
            "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username"):
        if str(inn) in imena:
            po[str(rez)] = po.get(str(rez), 0) + 1
    obshchee["po_rezultatu"] = po


def _fixF1_skryta_csv(c, skr) -> str:
    h = (skr or {}).get(str(c.get("inn") or ""))
    if not h:
        return ""
    return ("скрыта" + ((": " + _fio_dlya_shablona(h.get("username"))) if h.get("username") else "")
            + ((" – " + str(h.get("reason"))) if h.get("reason") else ""))
'''

# ============================================================================ правки по якорям
QR_STARO = '''def _queue_rank(company: dict) -> tuple:
    result = company.get("call_result") or "new"
    next_contact = company.get("next_contact_at") or "9999-12-31T23:59"
    if result == "new":
        bucket = 0
    elif result in {"callback", "interested", "proposal"}:
        bucket = 1
    elif result in {"no_answer", "contacted", "wrong_number"}:
        bucket = 2
    else:
        bucket = 3
    return (
        bucket,
        next_contact,
        -float(company.get("assignment_score") or 0),
        company.get("inn") or "",
    )
'''
QR_NOVO = '''def _queue_rank(company: dict) -> tuple:
    # fixF1 (08.10, повторная проверка): перезвон, срок которого НЕ наступил, не обгоняет очередь.
    # Раньше новая компания с перезвоном на завтра сразу вставала на 1-е место «Всей очереди»:
    # срок «2026-10-09» меньше заглушки «9999-…» у всех остальных. Теперь:
    #   1) срок перезвона наступил (сегодня или просрочен, по Москве) – наверх, по сроку;
    #   2) новые – по баллу очереди; будущий перезвон стоит на своём месте по баллу;
    #   3) обработанные (вкладки) – по сроку перезвона, затем по баллу.
    result = company.get("call_result") or "new"
    next_contact = str(company.get("next_contact_at") or "").strip()
    if result == "new":
        bucket = 0
    elif result in {"callback", "interested", "proposal"}:
        bucket = 1
    elif result in {"no_answer", "contacted", "wrong_number"}:
        bucket = 2
    else:
        bucket = 3
    ball = -float(company.get("assignment_score") or 0)
    inn = company.get("inn") or ""
    if next_contact and (_perezvon_sovpal(company, "segodnya")
                         or _perezvon_sovpal(company, "prosrocheno")):
        return (0, next_contact, bucket, ball, inn)
    if bucket == 0:
        return (1, "", 0, ball, inn)
    return (1 + bucket, next_contact or "9999-12-31T23:59", 0, ball, inn)
'''

SKR_STARO = '''    hidden_co = sales.hidden_companies()
    companies_all = companies
    if hidden_co and not skrytye:
'''
SKR_NOVO = '''    hidden_co = sales.hidden_companies()
    companies_all = companies
    # fixF1: директору в отборах по результату скрытые видны (с пометкой «скрыта») – их считает статистика
    if hidden_co and not skrytye and not _fixF1_s_skrytymi(request.query_params, user, skrytye):
'''
POM_STARO = '''    _prikrepit_sobytiya(visible)        # fixB: попытки «не дозвонился» и номера ЛПР – к строкам
'''
POM_NOVO = '''    _prikrepit_sobytiya(visible)        # fixB: попытки «не дозвонился» и номера ЛПР – к строкам
    _fixF1_pometit_skrytye(visible, hidden_co)   # fixF1: пометка «скрыта» в строке
'''
TZ_STARO = '''    _sortirovat_dir(visible, request.query_params.get("sort", ""))   # fixB: только с ?sort=
'''
TZ_NOVO = '''    _sortirovat_dir(visible, request.query_params.get("sort", ""))   # fixB: только с ?sort=
    _fixF1_tot_zhe_lpr(vidimye_vladeltsu, visible)    # fixF1: один ЛПР у нескольких компаний очереди
'''
SCH_STARO = '''        choices.update(_direktor_vybor(companies, vidimye_vladeltsu, assignments))
'''
SCH_NOVO = '''        choices.update(_direktor_vybor(companies, vidimye_vladeltsu, assignments))
    # fixF1: числа у пунктов – по тому же набору, что и список; регионы – с числом
    regiony_n = _fixF1_schetchiki(choices, vidimye_vladeltsu, request, user, companies, assignments)
'''
REG_STARO = '''            "regions": all_regions,
'''
REG_NOVO = '''            "regions": all_regions,
            "regiony_n": regiony_n,          # fixF1: регионы с числом компаний
'''
VYG_STARO = '''    skrytye = str(request.query_params.get("skrytye") or "0") not in ("", "0")
    if hidden_co and not skrytye:
'''
VYG_NOVO = '''    skrytye = str(request.query_params.get("skrytye") or "0") not in ("", "0")
    if hidden_co and not skrytye and not _fixF1_s_skrytymi(request.query_params, user, skrytye):   # fixF1
'''
CSV1_STARO = '''"Базы", "Пометка очереди", "Клиент СЦ"])'''
CSV1_NOVO = '''"Базы", "Пометка очереди", "Клиент СЦ", "Скрыта"])'''
CSV2_STARO = '''    for i, c in enumerate(spisok, 1):
'''
CSV2_NOVO = '''    _f1_skr = sales.hidden_companies()      # fixF1: скрытые – отдельной колонкой, как пометка в списке
    for i, c in enumerate(spisok, 1):
'''
CSV3_STARO = '''            "да" if _klient_sc(c) else ""])'''
CSV3_NOVO = '''            "да" if _klient_sc(c) else "", _fixF1_skryta_csv(c, _f1_skr)])'''
DS_STARO = '''    # считаются компании, которые можно открыть списком: в каталоге и не скрытые
    vidimye = set(katalog) - skrytye
'''
DS_NOVO = '''    # fixF1: отметки считаются по всем компаниям каталога, в том числе скрытым позже (сделанная работа
    # остаётся сделанной); список по ссылке с цифры показывает директору и скрытые – с пометкой
    # «скрыта». Очередь («в очереди сейчас») – без скрытых: их не обзванивают.
    vidimye = set(katalog)
    vidimye_ochered = set(katalog) - skrytye
'''
DSO_STARO = '''        if str(r["inn"]) in vidimye and r["r"] not in sales.CALL_RESULT_CHOICES:'''
DSO_NOVO = '''        if str(r["inn"]) in vidimye_ochered and r["r"] not in sales.CALL_RESULT_CHOICES:'''
LEN_STARO = '''                {"inn": z["inn"]}, **({"call_status": tekushchiy}
                                      if tekushchiy in sales.CALL_RESULT_CHOICES else {}))))'''
LEN_NOVO = '''                {"inn": z["inn"]}, **({"call_status": tekushchiy}
                                      if tekushchiy in sales.CALL_RESULT_CHOICES
                                      else ({"call_status": "new"} if z["inn"] in skrytye else {})))))'''
SS_STARO = '''    vidimye -= {str(r[0]) for r in conn.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
'''
SS_NOVO = '''    # fixF1: скрытые позже не вычитаются – номер ЛПР и недозвон по ним остаются работой продавца;
    # список по ссылке показывает их директору с пометкой «скрыта»
'''
PR_STARO = '''        obshchee = _stats_obshchee(conn)
'''
PR_NOVO = '''        obshchee = _stats_obshchee(conn)
        _fixF1_po_rezultatu(conn, obshchee, imena)     # fixF1: только ИНН каталога – как список по ссылке
'''

# --- шаблоны
SP_POR_STARO = 'порядок – как у очереди: сначала новые, внутри по баллу очереди'
SP_POR_NOVO = ('порядок – как у очереди: наверху перезвоны на сегодня и просроченные, '
               'дальше по баллу очереди (перезвон на будущий день – на своём месте)')
SP_ST_STARO = '''<span class="st-metka st-{{ _st }}">{{ call_results.get(_st, _st) }}</span>'''
SP_ST_NOVO = ('''<span class="st-metka st-{{ _st }}">{{ call_results.get(_st, _st) }}</span>'''
              '''{% if c.skryta %} <span class="och-tag net f1-skryta" title="Скрыта целиком{% if c.skryta.username %}: '''
              '''{{ c.skryta.username|fio }}{% endif %}{% if c.skryta.reason %} – {{ c.skryta.reason }}{% endif %}. '''
              '''В очереди продавца её нет; директору видна в отборах по результату: отметка по ней '''
              '''считается в статистике">скрыта</span>{% endif %}''')
SP_BALL_STARO = '''<td class="chislo tiho och-ball"{% if c.prioritet_pochemu %} title="{{ c.prioritet_pochemu }}"{% endif %}>{{ '%.1f'|format(c.assignment_score or 0) }}</td>'''
SP_BALL_NOVO = ('''{% set _f1k = c.get('pometka_ocheredi') or (c.assignment_score or 0) < 0 %}'''
                '''<td class="chislo tiho och-ball"{% if c.prioritet_pochemu or _f1k %} title="{% if _f1k %}Балл очереди '''
                '''{{ '%.1f'|format(c.assignment_score or 0) }} – только для порядка: компания в конце очереди. '''
                '''{% endif %}{{ c.prioritet_pochemu or '' }}"{% endif %}>{% if c.get('pometka_ocheredi') %}'''
                '''<span class="f1-konec">в конце: пометка «{{ (c.get('pometka_ocheredi')|string).split(':')[0]|trim }}»</span>'''
                '''{% elif _f1k %}<span class="f1-konec">в конце очереди</span>'''
                '''{% else %}{{ '%.1f'|format(c.assignment_score or 0) }}{% endif %}</td>''')
SP_LPR_STARO = '''{% endif %}{% endif %}</td>
        <td>{% set _st = c.call_result or 'new' %}'''
SP_LPR_NOVO = ('''{% endif %}{% endif %}'''
               '''{% if c.tot_zhe_lpr %}<span class="f1-tot-zhe" title="Этот номер ЛПР стоит первым и у других '''
               '''компаний вашей очереди – это один человек: договаривайтесь за все компании одним звонком">'''
               '''тот же ЛПР, что у {% for d in c.tot_zhe_lpr %}{% if d.poz %}№{{ d.poz }} {% endif %}«{{ d.nazv }}»'''
               '''{% if not loop.last %}, {% endif %}{% endfor %}</span>{% endif %}</td>
        <td>{% set _st = c.call_result or 'new' %}''')
SP_CSS_STARO = '''<main class="ochered-wrap">'''
SP_CSS_NOVO = '''<style id="fixF1-spisok">
/* fixF1 08.10: балл компании с пометкой, «тот же ЛПР», «скрыта» */
.f1-konec{display:inline-block;white-space:normal;max-width:120px;text-align:right;font-size:11px;line-height:1.3;color:#8a5300}
.f1-tot-zhe{display:block;margin-top:5px;padding:2px 6px;border-radius:4px;background:#fff4e0;border:1px solid #f3d39b;
  color:#8a5300;font-size:11px;line-height:1.3;white-space:normal}
.f1-skryta{margin-left:4px}
@media(max-width:760px){.f1-konec{text-align:left;max-width:none}}
</style>
<main class="ochered-wrap">'''

C_REG1_STARO = '''    {% for value in regions %}<option value="{{ value }}" {% if request.query_params.get('region') == value %}selected{% endif %}>{{ value }}</option>{% endfor %}
  </select>'''
C_REG1_NOVO = '''    {% if regiony_n %}{% for value, n in regiony_n %}<option value="{{ value }}" {% if request.query_params.get('region') == value %}selected{% endif %}>{{ value }} · {{ n }}</option>{% endfor %}{% else %}{% for value in regions %}<option value="{{ value }}" {% if request.query_params.get('region') == value %}selected{% endif %}>{{ value }}</option>{% endfor %}{% endif %}
  </select>'''
C_REG2_STARO = '''<label>Регион<select name="region"><option value="">Любой</option>{% for value in regions %}<option value="{{ value }}" {% if request.query_params.get('region') == value %}selected{% endif %}>{{ value }}</option>{% endfor %}</select></label>'''
C_REG2_NOVO = '''<label>Регион<select name="region"><option value="">Любой</option>{% if regiony_n %}{% for value, n in regiony_n %}<option value="{{ value }}" {% if request.query_params.get('region') == value %}selected{% endif %}>{{ value }} · {{ n }}</option>{% endfor %}{% else %}{% for value in regions %}<option value="{{ value }}" {% if request.query_params.get('region') == value %}selected{% endif %}>{{ value }}</option>{% endfor %}{% endif %}</select></label>'''
C_BALL_STARO = '''<b>Балл очереди</b> {{ '%.1f'|format(company.assignment_score|float) if company.assignment_score is not none else '–' }}</span>'''
C_BALL_NOVO = ('''<b>Балл очереди</b> {% if company.get('pometka_ocheredi') %}в конце: пометка «{{ (company.get('pometka_ocheredi')|string).split(':')[0]|trim }}»'''
               '''<span class="f1-chislo"> (число {{ '%.1f'|format(company.assignment_score|float) if company.assignment_score is not none else '–' }} – только для порядка)</span>'''
               '''{% elif company.assignment_score is not none and company.assignment_score|float < 0 %}в конце очереди'''
               '''<span class="f1-chislo"> (число {{ '%.1f'|format(company.assignment_score|float) }} – только для порядка)</span>'''
               '''{% else %}{{ '%.1f'|format(company.assignment_score|float) if company.assignment_score is not none else '–' }}{% endif %}</span>''')
C_SKR_STARO = '''{% set _st = company.call_result or 'new' %}<span class="st-metka st-{{ _st }}" title="Результат звонка – как в списке">'''
C_SKR_NOVO = ('''{% if company.skryta %}<span class="tag tag-egrul-net" title="Скрыта целиком{% if company.skryta.username %}: '''
              '''{{ company.skryta.username|fio }}{% endif %}{% if company.skryta.reason %} – {{ company.skryta.reason }}{% endif %}. '''
              '''В очереди продавца её нет">скрыта</span>{% endif %}'''
              '''{% set _st = company.call_result or 'new' %}<span class="st-metka st-{{ _st }}" title="Результат звонка – как в списке">''')
C_CSS_STARO = '''</style>
</body>
</html>'''
C_CSS_NOVO = '''</style>
<style id="fixF1-vid">
/* fixF1 08.10: на ноутбуке (1366×768) плавающие «К результату звонка ↓» и «⚙ Вид» закрывали низ
   первых карточек контактов. Теперь у карточки компании справа поле, и кнопки стоят в нём
   вертикальными ярлыками – поверх контактов ничего нет. На телефоне – как было (внизу). */
.f1-chislo{color:var(--muted);font-weight:400;font-size:12px}
@media(min-width:761px){
  body.v-kartochke main.page-wrap{padding-right:64px}
  body.v-kartochke #kRezultatu,body.v-kartochke #vidBtn{left:auto;right:10px;writing-mode:vertical-rl;
    padding:14px 9px;border-radius:999px;font-size:13px;line-height:1.15;letter-spacing:.02em}
  body.v-kartochke #vidBtn{bottom:18px}
  body.v-kartochke #kRezultatu{bottom:104px}
  body.v-kartochke #vidPanel{right:60px;bottom:18px}
  body.v-kartochke{padding-bottom:0}
}
</style>
</body>
</html>'''

ST_POR_STARO = '''  <p class="pometka">Порядок тот же, что у продавца: сначала новые, затем перезвоны по
    сроку, внутри – по убыванию балла очереди.'''
ST_POR_NOVO = '''  <p class="pometka">Порядок тот же, что у продавца: наверху – перезвоны, срок которых наступил
    (сегодня и просроченные); дальше сначала новые, затем перезвоны по сроку (перезвон новой компании
    на будущий день стоит на своём месте по баллу), внутри – по убыванию балла очереди.'''
ST_REZ_STARO = '''  <h3>По результатам звонка</h3>
'''
ST_REZ_NOVO = '''  <h3>По результатам звонка</h3>
  <p class="pometka">Компании каталога, назначенные продавцам. Скрытые продавцом позже входят в цифры
    (работа по ним сделана); список по ссылке показывает их директору с пометкой «скрыта». Очередь
    («в очереди») – без скрытых: их не обзванивают.</p>
'''
ST_BALL_STARO = '''<td>{{ '%.1f'|format(z.assignment_score or 0) }}</td>'''
ST_BALL_NOVO = ('''<td{% if (z.assignment_score or 0) < 0 %} title="Балл {{ '%.1f'|format(z.assignment_score) }} – только для порядка"{% endif %}>'''
                '''{% if (z.assignment_score or 0) < 0 %}в конце очереди (пометка){% else %}{{ '%.1f'|format(z.assignment_score or 0) }}{% endif %}</td>''')

PRAVKI = [
    # (файл, имя, якорь, замена, признак «уже сделано»)
    (F_RCS, '_queue_rank: будущий перезвон не наверху', QR_STARO, QR_NOVO, 'fixF1 (08.10, повторная проверка): перезвон'),
    (F_RCS, 'главная: скрытые директору в отборах по результату', SKR_STARO, SKR_NOVO, 'not _fixF1_s_skrytymi(request.query_params, user, skrytye):\n        companies'),
    (F_RCS, 'главная: пометка «скрыта»', POM_STARO, POM_NOVO, '_fixF1_pometit_skrytye(visible, hidden_co)'),
    (F_RCS, 'главная: «тот же ЛПР»', TZ_STARO, TZ_NOVO, '_fixF1_tot_zhe_lpr(vidimye_vladeltsu, visible)'),
    (F_RCS, 'главная: счётчики фильтров', SCH_STARO, SCH_NOVO, 'regiony_n = _fixF1_schetchiki('),
    (F_RCS, 'главная: регионы в шаблон', REG_STARO, REG_NOVO, '"regiony_n": regiony_n,'),
    (F_RCS, 'CSV: скрытые как в списке', VYG_STARO, VYG_NOVO, 'skrytye and not _fixF1_s_skrytymi(request.query_params, user, skrytye):   # fixF1'),
    (F_RCS, 'CSV: колонка «Скрыта» (заголовок)', CSV1_STARO, CSV1_NOVO, '"Клиент СЦ", "Скрыта"]'),
    (F_RCS, 'CSV: скрытые (выборка)', CSV2_STARO, CSV2_NOVO, '_f1_skr = sales.hidden_companies()'),
    (F_RCS, 'CSV: колонка «Скрыта» (строка)', CSV3_STARO, CSV3_NOVO, '_fixF1_skryta_csv(c, _f1_skr)'),
    (F_RCS, 'статистика директора: скрытые в отметках', DS_STARO, DS_NOVO, 'vidimye_ochered = set(katalog) - skrytye'),
    (F_RCS, 'статистика директора: очередь без скрытых', DSO_STARO, DSO_NOVO, 'in vidimye_ochered and r["r"]'),
    (F_RCS, 'лента: ссылка на скрытую', LEN_STARO, LEN_NOVO, '({"call_status": "new"} if z["inn"] in skrytye else {})'),
    (F_RCS, 'номера ЛПР / недозвоны: скрытые не вычитаются', SS_STARO, SS_NOVO, 'fixF1: скрытые позже не вычитаются'),
    (F_RCS, '«По результатам звонка»: только каталог', PR_STARO, PR_NOVO, '_fixF1_po_rezultatu(conn, obshchee, imena)     # fixF1'),
    (F_SP, 'список: подпись порядка', SP_POR_STARO, SP_POR_NOVO, 'наверху перезвоны на сегодня и просроченные'),
    (F_SP, 'список: пометка «скрыта»', SP_ST_STARO, SP_ST_NOVO, 'f1-skryta'),
    (F_SP, 'список: балл компании с пометкой', SP_BALL_STARO, SP_BALL_NOVO, 'f1-konec">в конце'),
    (F_SP, 'список: «тот же ЛПР»', SP_LPR_STARO, SP_LPR_NOVO, 'f1-tot-zhe" title'),
    (F_SP, 'список: стили', SP_CSS_STARO, SP_CSS_NOVO, 'id="fixF1-spisok"'),
    (F_C, 'фильтры: регионы с числом (строка)', C_REG1_STARO, C_REG1_NOVO, '{{ value }} · {{ n }}</option>{% endfor %}{% else %}{% for value in regions %}<option value="{{ value }}" {% if request.query_params.get(\'region\') == value %}selected{% endif %}>{{ value }}</option>{% endfor %}{% endif %}\n  </select>'),
    (F_C, 'фильтры: регионы с числом (диалог)', C_REG2_STARO, C_REG2_NOVO, '<label>Регион<select name="region"><option value="">Любой</option>{% if regiony_n %}'),
    (F_C, 'карточка: балл компании с пометкой', C_BALL_STARO, C_BALL_NOVO, 'f1-chislo"> (число'),
    (F_C, 'карточка: пометка «скрыта»', C_SKR_STARO, C_SKR_NOVO, '{% if company.skryta %}'),
    (F_C, 'карточка: плавающие кнопки в правом поле', C_CSS_STARO, C_CSS_NOVO, 'id="fixF1-vid"'),
    (F_ST, 'статистика: подпись порядка очереди', ST_POR_STARO, ST_POR_NOVO, 'наверху – перезвоны, срок которых наступил'),
    (F_ST, 'статистика: пояснение про скрытые', ST_REZ_STARO, ST_REZ_NOVO, 'Скрытые продавцом позже входят в цифры'),
    (F_ST, 'статистика: балл компании с пометкой', ST_BALL_STARO, ST_BALL_NOVO, 'в конце очереди (пометка)'),
]
PRIZNAK_KODA = 'def _fixF1_schetchiki('


def chitat(p):
    """Текст файла с \n и признак CRLF: файлы на сервере – с CRLF, его и сохраняем."""
    syroe = io.open(p, encoding='utf-8', newline='').read()
    return syroe.replace('\r\n', '\n'), '\r\n' in syroe


def zapisat(p, t, crlf):
    io.open(p, 'w', encoding='utf-8', newline='').write(t.replace('\n', '\r\n') if crlf else t)


def primenit(app_dir, bekap_dir=None, izmeneny=None, log=None):
    """Все правки в папке app_dir. Возвращает (сделано, надо). Идемпотентно."""
    log = log if log is not None else []
    izmeneny = izmeneny if izmeneny is not None else {}
    nado = sdelano = 0

    def sohranit_kopiyu(p):
        if bekap_dir is None:
            return
        b = os.path.join(bekap_dir, os.path.basename(p))
        if not os.path.exists(b):
            shutil.copy2(p, b)
            izmeneny[os.path.basename(p)] = p
    # код в конец routes – первым: правки ниже на него ссылаются
    p = os.path.join(app_dir, *F_RCS)
    nado += 1
    t, crlf = chitat(p)
    if PRIZNAK_KODA in t:
        sdelano += 1
        log.append('[уже] функции fixF1 в routes_centro_sales.py')
    else:
        sohranit_kopiyu(p)
        zapisat(p, t.rstrip('\n') + '\n' + RCS_KOD, crlf)
        sdelano += 1
        log.append('[ок] функции fixF1 в routes_centro_sales.py')
    for f, imya, staro, novo, priznak in PRAVKI:
        nado += 1
        p = os.path.join(app_dir, *f)
        t, crlf = chitat(p)
        if priznak in t:
            sdelano += 1
            log.append('[уже] ' + imya)
            continue
        n = t.count(staro)
        if n != 1:
            log.append('[ЯКОРЬ: %d] %s – не правлю' % (n, imya))
            continue
        sohranit_kopiyu(p)
        zapisat(p, t.replace(staro, novo, 1), crlf)
        sdelano += 1
        log.append('[ок] ' + imya)
    return sdelano, nado


if '--lokalno' in sys.argv:
    papka = sys.argv[sys.argv.index('--lokalno') + 1]
    lg = []
    s, n = primenit(papka, log=lg)
    print('\n'.join(lg))
    print('правок: %d из %d' % (s, n))
    raise SystemExit(0 if s == n else 1)


# ====================================================================== ПРОВЕРКА (venv, копии баз)
def proverka(test_sales, test_kat):
    import warnings
    warnings.filterwarnings('ignore')
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    logging.disable(logging.CRITICAL)
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = test_sales
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = test_kat
    import app
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    ok(os.path.abspath(app.__file__).lower().startswith(APP.lower()), 'код из %s' % APP)
    ok(str(catalog.db_path()) == test_kat and str(sales.sales_db_path()) == test_sales, 'базы – временные копии')
    ok(hasattr(rcs, '_fixF1_schetchiki') and hasattr(rcs, '_fixF1_tot_zhe_lpr'), 'в коде есть функции fixF1')
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 2, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    vnutr.dependency_overrides[rcs._same_origin] = lambda: None
    b = sqlite3.connect(test_sales)
    b.row_factory = sqlite3.Row
    A = [r['inn'] for r in b.execute("SELECT inn FROM company_assignment WHERE username='meyer2' "
                                     "ORDER BY assignment_score DESC")]

    def chislo(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1
    with TestClient(vnutr) as kl:
        def poluchit(u, kak=ADMIN, **kw):
            kto['u'] = kak
            return kl.get(PUT + u, **kw)
        for nazv, u, kak, kod in (('главная, админ', '/centro', ADMIN, 200),
                                  ('главная, админ, вкладка', '/centro?call_status=v_rabote', ADMIN, 200),
                                  ('карточка, админ', '/centro?inn=' + A[0], ADMIN, 200),
                                  ('статистика, админ', '/centro/stats', ADMIN, 200),
                                  ('статистика, админ, продавец', '/centro/stats?user=meyer2', ADMIN, 200),
                                  ('CSV, админ', '/centro/vygruzka.csv', ADMIN, 200),
                                  ('главная, продавец', '/centro', PROD, 200),
                                  ('карточка, продавец', '/centro?inn=' + A[0], PROD, 200),
                                  ('карточка ГКЗ, продавец', '/centro?inn=1829013726', PROD, 200),
                                  ('статистика, продавец', '/centro/stats', PROD, 403)):
            t0 = time.time()
            o = poluchit(u, kak)
            ok(o.status_code == kod, '%s: %s (%.2f с)' % (nazv, o.status_code, time.time() - t0))
        t = poluchit('/centro', PROD).text
        ok('наверху перезвоны на сегодня' in t and 'id="fixF1-spisok"' in t, 'список: подпись порядка и стили fixF1')
        reg = re.search(r'<select name="region">(.*?)</select>', t, re.S)
        opc = re.findall(r'<option value="([^"]+)"[^>]*>[^<]*· (\d+)</option>', reg.group(1)) if reg else []
        ok(opc and all(int(n) > 0 for _, n in opc), 'регионы продавца: %d, у каждого число > 0' % len(opc))
        plohie = []
        for v, n in opc[:6]:
            nn = chislo(poluchit('/centro', PROD, params={'region': v}).text)
            if nn != int(n):
                plohie.append((v, n, nn))
        ok(not plohie, 'регион продавца: число = строк списка (первые 6) %s' % plohie)
        t = poluchit('/centro', ADMIN).text
        reg = re.search(r'<select name="region">(.*?)</select>', t, re.S)
        opc_a = re.findall(r'<option value="([^"]+)"[^>]*>[^<]*· (\d+)</option>', reg.group(1)) if reg else []
        ok(len(opc_a) >= len(opc), 'регионы директора: %d (все, с числами)' % len(opc_a))
        t = poluchit('/centro?inn=1829013726', PROD).text
        ok('id="fixF1-vid"' in t, 'карточка: стили плавающих кнопок fixF1')
        t = poluchit('/centro/stats?user=meyer2', ADMIN).text
        ok('наверху – перезвоны, срок которых наступил' in t, 'статистика: подпись порядка')
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    raise SystemExit(1 if proverka(sys.argv[i + 1], sys.argv[i + 2]) else 0)


# ====================================================================== ПРАВКИ ПОД ЗАМКОМ
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


def kopiya(src_put, dst_put):
    src = sqlite3.connect('file:%s?mode=ro' % src_put, uri=True)
    dst = sqlite3.connect(dst_put)
    src.backup(dst)
    dst.close()
    src.close()


VREMYA = time.strftime('%Y%m%d-%H%M%S')
BEKAP = os.path.join(KOREN, '_bekap', 'fixF1-kod-' + VREMYA)
IZMENENY = {}


def vernut():
    for imya, kuda in IZMENENY.items():
        shutil.copy2(os.path.join(BEKAP, imya), kuda)


vzyat_zamok('fixF1')
try:
    os.makedirs(BEKAP, exist_ok=True)
    log = []
    sdelano, nado = primenit(APP, BEKAP, IZMENENY, log)
    for x in log:
        print('   ' + x)
    print('правок: %d из %d; бэкап своих файлов: %s' % (sdelano, nado, BEKAP))
    if sdelano != nado:
        vernut()
        print('НЕ ВСЕ ПРАВКИ ВНЕСЕНЫ – %d файлов возвращены из своей копии, перезапуска нет' % len(IZMENENY))
        raise SystemExit(1)
    if not IZMENENY:
        print('всё уже было сделано – перезапуск не нужен')
        raise SystemExit(0)
    ts, tk = os.path.join(BEKAP, 'test_sales.db'), os.path.join(BEKAP, 'test_kat.db')
    kopiya(os.path.join(KOREN, 'data', 'centro_sales_meyer1.db'), ts)
    kopiya(os.path.join(KOREN, 'data', 'meyer_baza1.db'), tk)
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True,
                       timeout=900, cwd=KOREN, env=sreda)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-4000:]
    for f in (ts, tk):
        try:
            os.remove(f)
        except OSError:
            pass
    io.open(os.path.join(DROP, 'fixF1-kod-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(vyvod)
    uspeh = r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod
    if uspeh and 'routes_centro_sales.py' in IZMENENY:
        p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
        for l in p.stdout.decode('cp866', 'replace').splitlines():
            if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
                subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
        time.sleep(2)
        lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
        lg.write('\n===== перезапуск: fixF1 очередь, фильтры, статистика %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
        lg.flush()
        subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                         stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                         close_fds=True, env=sreda)
        time.sleep(10)
        import urllib.request
        kod = ''
        for _ in range(6):
            try:
                kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
                break
            except Exception as e:  # noqa: BLE001
                kod = str(e)[:80]
                time.sleep(5)
        print('перезапущено, вход: %s' % kod)
    elif not uspeh:
        vernut()
        print('ПРОВЕРКА НЕ ПРОШЛА – %d своих файлов возвращены из копии, процесс не перезапускался' % len(IZMENENY))
    print('===== ПРОВЕРКА (полностью: fixF1-kod-proverka-%s.txt на дропе) =====' % VREMYA)
    sys.stdout.write(vyvod[-4000:])
finally:
    otdat_zamok()
