# -*- coding: utf-8 -*-
"""Админская статистика в КОПИИ панели: общая сводка, разрез по продавцам, очередь юзера.

Правится ТОЛЬКО C:\\centro2. Боевой C:\\seostat\\app не трогается ни одной строкой:
продавцы работают на 8012 прямо сейчас.

ЧТО ДОБАВЛЯЕТСЯ
  маршрут  GET /centro/stats            общая статистика + разрез по продавцам
  маршрут  GET /centro/stats?user=имя   плюс очередь этого продавца, как он её видит
  шаблон   centro_stats.html
  ссылка   со страницы /centro/admin на новую статистику

ПОЧЕМУ ОЧЕРЕДЬ СЧИТАЕТСЯ ТЕМ ЖЕ ПОРЯДКОМ, ЧТО И У ПРОДАВЦА
В панели порядок задаёт _queue_rank: корзина по результату звонка, затем срок следующего
контакта, затем балл. Если на админской странице отсортировать иначе, админ увидит НЕ ТУ
очередь, которую видит продавец, и разговор будет про разные списки. Поэтому здесь
вызывается ровно та же функция, а не похожая.
"""
import io
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

KOREN = r'C:\centro2'
ROUTES = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
SHABLON = os.path.join(KOREN, 'app', 'templates', 'centro_stats.html')
ADMIN_HTML = os.path.join(KOREN, 'app', 'templates', 'centro_admin.html')
VENV = r'C:\seostat\.venv\Scripts\python.exe'
PORT = 8016

ishodnik = io.open(ROUTES, encoding='utf-8').read()
print('routes_centro_sales.py копии: %d знаков' % len(ishodnik))
if '/centro/stats' in ishodnik:
    print('  маршрут уже есть — выхожу, повторно не добавляю')
    raise SystemExit(0)

# Каким параметром список ищет компанию — чтобы ссылка из статистики открывала карточку,
# а не пустой поиск. Не угадываю: смотрю, что читает сам маршрут /centro.
m = re.search(r'def centro\((.*?)\):', ishodnik, re.S)
podpis = m.group(1) if m else ''
param = 'q'
for kand in ('q', 'search', 'inn', 'poisk'):
    if re.search(r'\b%s\s*:\s*str' % kand, podpis):
        param = kand
        break
print('  параметр поиска в /centro: %s' % param)

KOD = '''

# ---------------------------------------------------------------- статистика для админа
# Добавлено в КОПИИ панели. Владелец: «у админа возможность просматривать статистику по
# всем пользователям и всем компаниям, как общая статистика, так и видеть очереди юзеров».
_STATS_POISK = "%(param)s"


def _stats_obshchee(conn) -> dict:
    """Общие числа. Считаются одним проходом по назначениям, а не запросом на пользователя."""
    itog: dict = {}
    itog["naznacheno"] = conn.execute(
        "SELECT COUNT(*) FROM company_assignment").fetchone()[0]
    po_rezultatu = {}
    for rezultat, n in conn.execute(
        "SELECT COALESCE(s.call_result,'new'), COUNT(*) "
        "FROM company_assignment a "
        "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username "
        "GROUP BY 1"
    ):
        po_rezultatu[str(rezultat)] = n
    itog["po_rezultatu"] = po_rezultatu
    itog["obrabotano"] = sum(n for r, n in po_rezultatu.items() if r != "new")
    itog["kommentariev"] = conn.execute(
        "SELECT COUNT(*) FROM company_comment").fetchone()[0]
    try:
        itog["skryto"] = conn.execute(
            "SELECT COUNT(*) FROM hidden_item WHERE kind='company'").fetchone()[0]
    except Exception:  # noqa: BLE001
        itog["skryto"] = 0
    seychas = sales.utcnow()
    itog["prosrocheno"] = conn.execute(
        "SELECT COUNT(*) FROM company_state "
        "WHERE next_contact_at IS NOT NULL AND next_contact_at <> '' "
        "AND next_contact_at < ?", (seychas,)).fetchone()[0]
    aktivnost = {}
    for dney in (1, 7, 30):
        porog = (datetime.datetime.utcnow()
                 - datetime.timedelta(days=dney)).strftime("%%Y-%%m-%%dT%%H:%%M:%%S")
        try:
            aktivnost[dney] = conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE created_at >= ?",
                (porog,)).fetchone()[0]
        except Exception:  # noqa: BLE001
            aktivnost[dney] = 0
    itog["aktivnost"] = aktivnost
    return itog


def _stats_po_prodavcam(conn) -> list[dict]:
    """Разрез по продавцам. Пользователи берутся из users, а не из назначений:
    иначе сотрудник без единого назначения просто исчезнет из отчёта, и это будет
    выглядеть как «такого нет», а не как «ему ничего не досталось»."""
    seychas = sales.utcnow()
    stroki = {}
    for row in conn.execute(
        "SELECT username, role, is_active FROM users ORDER BY username"
    ):
        stroki[row["username"]] = {
            "username": row["username"], "role": row["role"],
            "aktiven": bool(row["is_active"]), "naznacheno": 0, "obrabotano": 0,
            "ball_summa": 0.0, "ball_sredniy": 0.0, "prosrocheno": 0,
            "po_rezultatu": {}, "poslednyaya_aktivnost": "",
        }
    for row in conn.execute(
        "SELECT a.username, COUNT(*) n, COALESCE(SUM(a.assignment_score),0) summa, "
        "COALESCE(AVG(a.assignment_score),0) sredniy "
        "FROM company_assignment a GROUP BY a.username"
    ):
        z = stroki.setdefault(row["username"], {
            "username": row["username"], "role": "?", "aktiven": False,
            "naznacheno": 0, "obrabotano": 0, "ball_summa": 0.0, "ball_sredniy": 0.0,
            "prosrocheno": 0, "po_rezultatu": {}, "poslednyaya_aktivnost": ""})
        z["naznacheno"] = row["n"]
        z["ball_summa"] = float(row["summa"] or 0)
        z["ball_sredniy"] = float(row["sredniy"] or 0)
    for row in conn.execute(
        "SELECT a.username, COALESCE(s.call_result,'new') r, COUNT(*) n "
        "FROM company_assignment a "
        "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username "
        "GROUP BY a.username, 2"
    ):
        z = stroki.get(row["username"])
        if not z:
            continue
        z["po_rezultatu"][str(row["r"])] = row["n"]
        if str(row["r"]) != "new":
            z["obrabotano"] += row["n"]
    for row in conn.execute(
        "SELECT username, COUNT(*) n FROM company_state "
        "WHERE next_contact_at IS NOT NULL AND next_contact_at <> '' "
        "AND next_contact_at < ? GROUP BY username", (seychas,)
    ):
        if row["username"] in stroki:
            stroki[row["username"]]["prosrocheno"] = row["n"]
    try:
        for row in conn.execute(
            "SELECT username, MAX(created_at) p FROM activity_log GROUP BY username"
        ):
            if row["username"] in stroki:
                stroki[row["username"]]["poslednyaya_aktivnost"] = row["p"] or ""
    except Exception:  # noqa: BLE001
        pass
    for z in stroki.values():
        z["ostalos"] = z["naznacheno"] - z["obrabotano"]
    return sorted(stroki.values(), key=lambda z: (-z["naznacheno"], z["username"]))


def _stats_ochered(conn, username: str, imena: dict) -> list[dict]:
    """Очередь продавца ровно в том порядке, в каком её видит он сам: _queue_rank."""
    stroki = []
    for row in conn.execute(
        "SELECT a.inn, a.assignment_score, a.has_phone, a.has_tech, a.has_purchaser, "
        "COALESCE(s.call_result,'new') call_result, s.last_contact_at, s.next_contact_at "
        "FROM company_assignment a "
        "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username "
        "WHERE a.username=?", (username,)
    ):
        d = dict(row)
        d["nazvanie"] = imena.get(str(d["inn"]), "")
        stroki.append(d)
    stroki.sort(key=_queue_rank)
    return stroki


@router.get("/centro/stats")
def stats_page(request: Request, user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    vybrannyy = (request.query_params.get("user") or "").strip()
    imena: dict = {}
    vsego_v_kataloge = 0
    try:
        for row in catalog.list_companies():
            inn = str(row.get("inn") or "").strip()
            if not inn:
                continue
            vsego_v_kataloge += 1
            imena[inn] = (row.get("predpriyatie") or row.get("name")
                          or row.get("nazvanie") or "")
    except catalog.CentroDbUnavailable:
        pass
    with sales.connect() as conn:
        obshchee = _stats_obshchee(conn)
        prodavcy = _stats_po_prodavcam(conn)
        ochered = _stats_ochered(conn, vybrannyy, imena) if vybrannyy else []
    obshchee["v_kataloge"] = vsego_v_kataloge
    obshchee["ne_naznacheno"] = max(0, vsego_v_kataloge - obshchee["naznacheno"])
    return templates.TemplateResponse(
        request,
        "centro_stats.html",
        {
            "user": user,
            "obshchee": obshchee,
            "prodavcy": prodavcy,
            "ochered": ochered,
            "vybrannyy": vybrannyy,
            "metki": sales.CALL_RESULT_LABELS,
            "poisk_param": _STATS_POISK,
            "base_path": BP,
        },
    )
''' % {'param': param}

# datetime нужен для окон активности — добавляю импорт, если его нет
if not re.search(r'^import datetime', ishodnik, re.M):
    ishodnik = ishodnik.replace('import hashlib', 'import datetime\nimport hashlib', 1)
    print('  добавлен import datetime')

io.open(ROUTES, 'w', encoding='utf-8').write(ishodnik + KOD)
print('  маршрут /centro/stats дописан (%d знаков)' % len(KOD))
print('ГОТОВО: код статистики записан. Шаблон пишется вторым шагом.')
