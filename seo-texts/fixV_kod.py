# -*- coding: utf-8 -*-
r"""fixV 14.10: роль «руководитель отдела продаж» (rop) в панели Meyer + сегменты по номеру.

Владелец 14.10: «сделай ещё доступы вроде админского для руководителей отдела продаж: Погорелый
Александр – Барнаул; Шамшев Вячеслав – Воронеж; Ершов Михаил – Краснодар. У них должен быть доступ к
статистике такой же, как у админа, но только по своим менеджерам продаж».
Координатор (14.10, тем же прогоном): сегменты во всех списках выбора и разбивках – по номеру в начале
названия («2 семеноводы» раньше «10 соль»), без номера – в конце по алфавиту.

Что меняется (по уникальным якорям, чтение-правка-запись под замком C:\centro2\_zamok.txt):
  services/centro_sales.py – роль rop (ROLES, CHECK в SCHEMA для новых баз); KOMANDA (contextvar) и
      zatenit(): на странице руководителя connect() накрывает users / company_assignment /
      company_state / zvonok_sobytie временными представлениями «только команда»; connect(bez_teni=True).
  api/routes_centro_sales.py – fixV-блок: current_user добавляет руководителю город и команду
      (действующие role='sales' того же users.gorod), любой не-GET руководителя – 403; обёртка
      _fixV_obertka на «/centro», «/centro/stats», «/centro/vygruzka.csv»: админский код, база продаж –
      по команде, чужой менеджер в параметрах – 404; без раздачи (assign_new) и без компаний вне
      команды; журнал (activity_log) не накрывается – отбор по последней отметке компании, как у админа
      (строки менеджеров = строкам админа); плитки комментариев/скрытых/действий – по команде;
      кэш ФИО – всегда по всем; сегменты – по номеру (_fixV_segm_klyuch).
  api/routes_park.py – блок «за день / за всё время»: у руководителя строки и выбор – только команда.
  templates/_shapka.html – «ФИО · Руководитель отдела продаж · Город», ссылка «Статистика», формы
      действий у руководителя скрыты (сервер их и так не примет).
  templates/centro.html – «Руководитель:» вместо «Директор:», без пункта «Без менеджера».
  templates/centro_stats.html – у руководителя нет плиток «компаний в каталоге» и «без менеджера».
  База продаж (только --primenit): CHECK(role IN ('admin','sales','rop')) – правка текста схемы
      (writable_schema, документированный способ SQLite), до записи – копия базы.

    python3 zapusk_na_servere.py fixV_kod.py --suho       # stage-копия кода, копии баз, синтетика; живое не трогается
    python3 zapusk_na_servere.py fixV_kod.py --primenit   # под замком: stage -> CHECK в базе -> запись -> перезапуск -> проверка
"""
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
PORT = 8016
ZAMOK = r'C:\centro2\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_bekap', 'fixV-stage')
PRODAVCY = ['meyer%d' % i for i in range(1, 10)]
ROPS = [('meyer_rop_barnaul', 'Погорелый Александр', 'Барнаул'),
        ('meyer_rop_voronezh', 'Шамшев Вячеслав', 'Воронеж'),
        ('meyer_rop_krasnodar', 'Ершов Михаил', 'Краснодар')]
FAJLY = {'S': 'services/centro_sales.py', 'R': 'api/routes_centro_sales.py', 'P': 'api/routes_park.py',
         'H': 'templates/_shapka.html', 'C': 'templates/centro.html', 'T': 'templates/centro_stats.html'}
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')

# ====================================================================== правки
S1_STARO = 'ROLES = {"admin", "sales"}\n'
S1_NOVO = 'ROLES = {"admin", "sales", "rop"}   # fixV: rop – руководитель отдела продаж (только просмотр своей команды)\n'
S2_STARO = " role TEXT NOT NULL CHECK(role IN ('admin','sales')),\n"
S2_NOVO = " role TEXT NOT NULL CHECK(role IN ('admin','sales','rop')),\n"
S3_STARO = '''def connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path or sales_db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn
'''
S3_NOVO = '''# fixV (14.10): руководитель отдела продаж (роль rop) видит базу продаж только по своей команде.
# Страница руководителя кладёт в KOMANDA логины его менеджеров на время запроса, и connect()
# накрывает четыре таблицы временными представлениями с тем же именем (в SQLite temp-схема ищется
# раньше main): users (продавцы – только команда; админ и руководители остаются), company_assignment
# и company_state (владелец из команды), zvonok_sobytie (засчитано менеджеру команды). Журнал,
# комментарии и скрытые не накрываются – отбор по ним в коде страниц (отметка компании засчитывается
# по её последней отметке, как у админа). Представления только для чтения: записать через такое
# соединение нельзя. Вне страниц руководителя KOMANDA = None, и всё как было.
import contextvars as _contextvars_fixV

KOMANDA: _contextvars_fixV.ContextVar = _contextvars_fixV.ContextVar("centro_komanda", default=None)
_TENI_FIXV = (("users", "role<>'sales' OR username IN (%s)"),
              ("company_assignment", "username IN (%s)"),
              ("company_state", "username IN (%s)"),
              ("zvonok_sobytie", "state_user IN (%s)"))


def zatenit(conn: sqlite3.Connection, komanda=None) -> None:
    """Накрыть таблицы базы продаж представлениями «только команда» (fixV). Без команды – ничего."""
    komanda = KOMANDA.get() if komanda is None else komanda
    if komanda is None:
        return
    spisok = ",".join("'%s'" % str(u).replace("'", "''") for u in sorted(komanda))
    for imya, uslovie in _TENI_FIXV:
        if conn.execute("SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                        (imya,)).fetchone():
            conn.execute("CREATE TEMP VIEW IF NOT EXISTS %s AS SELECT * FROM main.%s WHERE %s"
                         % (imya, imya, uslovie % spisok))


def connect(path: str | Path | None = None, *, bez_teni: bool = False) -> sqlite3.Connection:
    target = Path(path or sales_db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    if not bez_teni and KOMANDA.get() is not None:
        zatenit(conn)              # fixV: страница руководителя – только его команда
    return conn
'''

R1_STARO = '''        if row and row["is_active"]:
            return dict(row)
'''
R1_NOVO = '''        if row and row["is_active"]:
            return _fixV_polzovatel(dict(row), request)   # fixV: руководителю – город, команда; только GET
'''
R2_STARO = '''@router.get("/centro/login")
def login_page('''
R2_NOVO = '''# ===================================================================== fixV-блок (14.10)
# Руководитель отдела продаж (владелец 14.10: «доступ к статистике такой же, как у админа, но только
# по своим менеджерам продаж»). Роль rop в users, город – users.gorod. Команда – действующие
# менеджеры (role='sales') того же города: новый менеджер города попадает в неё сам.
# Главная, карточки, статистика и выгрузка CSV – админским кодом, но база продаж видна только по
# команде (centro_sales.KOMANDA + временные представления). Никаких действий: любой не-GET запрос
# руководителя – 403 (звонок, комментарий, скрытие, переназначение, «Парк»); «Распределение» – 403
# (там проверка role == 'admin'). Чужой менеджер в параметрах страницы – 404, чужая компания – 404.
import functools as _functools_fixV
import json as _json_fixV

_FIXV_PARAMY_LYUDEY = ("user", "stat_user", "assigned_user", "kto_p", "kto")


def _fixV_komanda(gorod: str) -> list:
    """Логины действующих менеджеров по продажам (role='sales') города руководителя."""
    g = (gorod or "").strip().casefold()
    if not g:
        return []
    with sales.connect(bez_teni=True) as conn:
        return sorted(str(r[0]) for r in conn.execute(
            "SELECT username, COALESCE(gorod,'') FROM users WHERE role='sales' AND is_active=1")
            if str(r[1] or "").strip().casefold() == g)


def _fixV_polzovatel(u: dict, request: Request) -> dict:
    if u.get("role") != "rop":
        return u
    if request.method not in ("GET", "HEAD"):
        raise HTTPException(403, "Руководителю отдела продаж – только просмотр")
    with sales.connect(bez_teni=True) as conn:
        r = conn.execute("SELECT COALESCE(gorod,'') FROM users WHERE username=?",
                         (u["username"],)).fetchone()
    u["rop"] = True
    u["rop_gorod"] = str(r[0] if r else "").strip()
    u["komanda"] = _fixV_komanda(u["rop_gorod"])
    return u


def _fixV_kom():
    """Команда руководителя на время его запроса (frozenset логинов) или None."""
    return sales.KOMANDA.get()


def _fixV_obertka(fn):
    """Страница для руководителя: админский код, база продаж – только его команда. Админ и
    менеджер по продажам проходят без изменений."""
    @_functools_fixV.wraps(fn)
    def obertka(*a, **kw):
        u = kw.get("user")
        if not (isinstance(u, dict) and u.get("rop")):
            return fn(*a, **kw)
        komanda = frozenset(u.get("komanda") or ())
        zapros = kw.get("request")
        if zapros is not None:
            for k in _FIXV_PARAMY_LYUDEY:
                z = (zapros.query_params.get(k) or "").strip()
                if z and z not in komanda:
                    raise HTTPException(404, "Менеджер по продажам не из вашей команды")
        kw["user"] = dict(u, role="admin")
        metka = sales.KOMANDA.set(komanda)
        try:
            return fn(*a, **kw)
        finally:
            sales.KOMANDA.reset(metka)
    return obertka


def _fixV_obshchee(obshchee: dict, komanda) -> None:
    """Плитки статистики не по назначениям – у руководителя по команде: комментарии её менеджеров,
    скрытые из её компаний, действия её менеджеров и действия за них (state_user)."""
    kom = set(komanda)
    with sales.connect(bez_teni=True) as conn:
        inn_kom = {str(r[0]) for r in conn.execute("SELECT inn, username FROM company_assignment")
                   if r[1] in kom}
        obshchee["kommentariev"] = sum(1 for r in conn.execute("SELECT username FROM company_comment")
                                       if r[0] in kom)
        try:
            obshchee["skryto"] = sum(1 for r in conn.execute(
                "SELECT inn FROM hidden_item WHERE kind='company'") if str(r[0]) in inn_kom)
        except Exception:  # noqa: BLE001
            obshchee["skryto"] = 0
        kogda = []
        for r in conn.execute("SELECT username, payload_json, created_at FROM activity_log"):
            try:
                pl = _json_fixV.loads(r[1] or "{}")
            except ValueError:
                pl = {}
            za = str(pl.get("state_user") or "") if isinstance(pl, dict) else ""
            if r[0] in kom or za in kom:
                kogda.append(str(r[2] or ""))
    akt = {}
    for dney in (1, 7, 30):
        porog = (datetime.datetime.utcnow()
                 - datetime.timedelta(days=dney)).strftime("%Y-%m-%dT%H:%M:%S")
        akt[dney] = sum(1 for k in kogda if k >= porog)
    obshchee["aktivnost"] = akt
    obshchee["vsego_deystviy"] = len(kogda)
    obshchee["poslednee_deystvie"] = (max(kogda) if kogda else "")[:16].replace("T", " ")


def _fixV_segm_klyuch(s) -> tuple:
    """Сегменты по номеру в начале названия («2 семеноводы» раньше «10 соль»), без номера – в конце."""
    t = str(s or "").strip()
    m = re.match(r"(\\d+)", t)
    return (0, int(m.group(1)), t.casefold()) if m else (1, 0, t.casefold())


@router.get("/centro/login")
def login_page('''
R3_STARO = '''@router.get("/centro")
def centro('''
R3_NOVO = '''@router.get("/centro")
@_fixV_obertka   # fixV: руководителю – админский вид по своей команде
def centro('''
R4_STARO = '''    if sales_users and companies:
'''
R4_NOVO = '''    if sales_users and companies and _fixV_kom() is None:   # fixV: страница руководителя ничего не раздаёт
'''
R5_STARO = '''        if user["role"] != "admin" and (
            not assignment or assignment["username"] != user["username"]
        ):
            continue
'''
R5_NOVO = R5_STARO + '''        if not assignment and _fixV_kom() is not None:   # fixV: руководителю – только компании команды
            continue
'''
R6_STARO = '''        if user["role"] == "admin" or v.get("username") == user["username"]
    }'''
R6_NOVO = '''        if (user["role"] == "admin" and (_fixV_kom() is None or и in assignments))   # fixV: руководителю – скрытые его команды
        or v.get("username") == user["username"]
    }'''
R7_STARO = '''@router.get("/centro/stats")
def stats_page('''
R7_NOVO = '''@router.get("/centro/stats")
@_fixV_obertka   # fixV: руководителю – статистика админа по своей команде
def stats_page('''
R8_STARO = '''    sc.row_factory = _sq_st.Row
'''
R8_NOVO = '''    sc.row_factory = _sq_st.Row
    sales.zatenit(sc)          # fixV: у руководителя – только его команда (вне его страницы ничего не делает)
'''
R9_STARO = '''    return templates.TemplateResponse(
        request,
        "centro_stats.html",'''
R9_NOVO = '''    if _fixV_kom() is not None:   # fixV: плитки не по назначениям – по команде руководителя
        _fixV_obshchee(obshchee, _fixV_kom())
''' + R9_STARO
R10_STARO = '''            if inn in vidimye and (not kto or o["kto"] == kto)}'''
R10_NOVO = '''            if inn in vidimye and (not kto or o["kto"] == kto)
            and (_fixV_kom() is None or o["kto"] in _fixV_kom())}   # fixV: только команда руководителя'''
R11_STARO = '''        if kto and z["deystvoval"] != kto:
            continue
'''
R11_NOVO = R11_STARO + '''        if _fixV_kom() is not None and z["deystvoval"] not in _fixV_kom():   # fixV: часы – только команда
            continue
'''
R12_STARO = '''                 if not kto or z["kto"] == kto or z["deystvoval"] == kto]'''
R12_NOVO = '''                 if (not kto or z["kto"] == kto or z["deystvoval"] == kto)
                 and (_fixV_kom() is None or z["kto"] in _fixV_kom() or z["deystvoval"] in _fixV_kom())]   # fixV'''
R13_STARO = '''    if user["role"] == "admin":
        vse = {str(c.get("region") or "") for c in companies}'''
R13_NOVO = '''    if user["role"] == "admin" and _fixV_kom() is None:   # fixV: руководителю – регионы его команды
        vse = {str(c.get("region") or "") for c in companies}'''
R14_STARO = '''            if c["inn"] in assignments:
                continue
'''
R14_NOVO = '''            if c["inn"] in assignments or _fixV_kom() is not None:   # fixV: «без менеджера» руководителю не считается
                continue
'''
R15_STARO = '''@router.get("/centro/vygruzka.csv")
def vygruzka_csv('''
R15_NOVO = '''@router.get("/centro/vygruzka.csv")
@_fixV_obertka   # fixV: руководителю – выгрузка только его команды
def vygruzka_csv('''
R16_STARO = '''        if user["role"] != "admin" and (not a or a["username"] != user["username"]):
            continue
'''
R16_NOVO = R16_STARO + '''        if not a and _fixV_kom() is not None:   # fixV: руководителю – только компании команды
            continue
'''
R17_STARO = '''    if seychas - _FIO_KESH["t"] > 30:
        try:
            with sales.connect() as conn:'''
R17_NOVO = '''    if seychas - _FIO_KESH["t"] > 30:
        try:
            with sales.connect(bez_teni=True) as conn:   # fixV: кэш ФИО общий – всегда по всем'''
R18_STARO = '''    choices["segment"] = sorted(счёт_сегм.items())
'''
R18_NOVO = '''    choices["segment"] = sorted(счёт_сегм.items(), key=lambda x: _fixV_segm_klyuch(x[0]))   # fixV: по номеру
'''
R19_STARO = '''        choices["segment"] = sorted(sch.items())
'''
R19_NOVO = '''        choices["segment"] = sorted(sch.items(), key=lambda x: _fixV_segm_klyuch(x[0]))   # fixV: по номеру
'''
R20_STARO = '''    choices["segment"] = [(s, sch.get(s, 0)) for s in sorted(univ)]
'''
R20_NOVO = '''    choices["segment"] = [(s, sch.get(s, 0)) for s in sorted(univ, key=_fixV_segm_klyuch)]   # fixV: по номеру
'''
R21_STARO = '''        for zn, s in sorted(sch.items(), key=lambda x: (-x[1]["otmecheno"], x[0])):
'''
R21_NOVO = '''        for zn, s in sorted(sch.items(), key=((lambda x: _fixV_segm_klyuch(x[0])) if pole == "segment"   # fixV
                                              else (lambda x: (-x[1]["otmecheno"], x[0])))):
'''
P1_STARO = '''    vse_stroki = [z for z in po.values() if z["aktiven"]]
'''
P1_NOVO = P1_STARO + '''    from app.services import centro_sales as _cs_fixV     # fixV: у руководителя – только его команда
    if _cs_fixV.KOMANDA.get() is not None:
        vse_stroki = [z for z in vse_stroki if z["username"] in _cs_fixV.KOMANDA.get()]
'''
H1_STARO = '''    {% if user is defined and user and user.role == 'admin' %}<a href="{{ _bp }}/centro/stats"'''
H1_NOVO = '''    {% if user is defined and user and (user.role == 'admin' or user.rop) %}<a href="{{ _bp }}/centro/stats"'''
H2_STARO = '''    <span>{{ user.username|fio }} · {{ 'администратор' if user.role == 'admin' else 'менеджер по продажам' }}</span>'''
H2_NOVO = '''    <span>{{ user.username|fio }} · {% if user.rop %}Руководитель отдела продаж{% if user.rop_gorod %} · {{ user.rop_gorod }}{% endif %}{% else %}{{ 'администратор' if user.role == 'admin' else 'менеджер по продажам' }}{% endif %}</span>'''
H3_STARO = '''<style>.topbar nav a.active{font-weight:700;text-decoration:underline;text-underline-offset:5px}</style>
'''
H3_NOVO = H3_STARO + '''{% if user is defined and user and user.rop %}<style id="fixV-rop">{# руководитель отдела продаж только смотрит: формы действий скрыты, сервер их всё равно не примет (403) #}.dir-forma,.ubrat-pred,form[method="post"]:not([action$="/logout"]){display:none!important}</style>{% endif %}
'''
C1_STARO = '''<span class="direktor-metka">Директор:</span>'''
C1_NOVO = '''<span class="direktor-metka">{{ 'Руководитель:' if user.rop else 'Директор:' }}</span>'''
C2_STARO = '''      <option value="__net__" {% if request.query_params.get('assigned_user') == '__net__' %}selected{% endif %}>Без менеджера по продажам · {{ choices.bez_prodavca_n }}</option>'''
C2_NOVO = '''      {% if not user.rop %}<option value="__net__" {% if request.query_params.get('assigned_user') == '__net__' %}selected{% endif %}>Без менеджера по продажам · {{ choices.bez_prodavca_n }}</option>{% endif %}'''
T1_STARO = '''    <div class="plitka"><b>{{ obshchee.v_kataloge }}</b><span>компаний в каталоге</span></div>'''
T1_NOVO = '''    {% if not user.rop %}<div class="plitka"><b>{{ obshchee.v_kataloge }}</b><span>компаний в каталоге</span></div>{% endif %}'''
T2_STARO = '''    <div class="plitka"><b>{{ obshchee.ne_naznacheno }}</b><span>компаний без менеджера по продажам</span></div>'''
T2_NOVO = '''    {% if not user.rop %}<div class="plitka"><b>{{ obshchee.ne_naznacheno }}</b><span>компаний без менеджера по продажам</span></div>{% endif %}'''

# (файл, название, было, стало, признак «уже сделано» – подстрока нового текста)
PRAVKI = [
    ('S', 'роль rop', S1_STARO, S1_NOVO, 'fixV'),
    ('S', 'CHECK роли в схеме новых баз', S2_STARO, S2_NOVO, "'rop'"),
    ('S', 'connect: команда руководителя', S3_STARO, S3_NOVO, 'fixV'),
    ('R', 'current_user: руководитель', R1_STARO, R1_NOVO, 'fixV'),
    ('R', 'fixV-блок', R2_STARO, R2_NOVO, 'fixV'),
    ('R', 'главная: обёртка', R3_STARO, R3_NOVO, 'fixV'),
    ('R', 'главная: без раздачи', R4_STARO, R4_NOVO, 'fixV'),
    ('R', 'главная: только команда', R5_STARO, R5_NOVO, 'fixV'),
    ('R', 'главная: скрытые команды', R6_STARO, R6_NOVO, 'fixV'),
    ('R', 'статистика: обёртка', R7_STARO, R7_NOVO, 'fixV'),
    ('R', 'статистика: блок дня по команде', R8_STARO, R8_NOVO, 'fixV'),
    ('R', 'статистика: плитки по команде', R9_STARO, R9_NOVO, 'fixV'),
    ('R', 'директор: отметки команды', R10_STARO, R10_NOVO, 'fixV'),
    ('R', 'директор: часы команды', R11_STARO, R11_NOVO, 'fixV'),
    ('R', 'директор: лента команды', R12_STARO, R12_NOVO, 'fixV'),
    ('R', 'счётчики: регионы команды', R13_STARO, R13_NOVO, 'fixV'),
    ('R', 'счётчики: без менеджера', R14_STARO, R14_NOVO, 'fixV'),
    ('R', 'выгрузка: обёртка', R15_STARO, R15_NOVO, 'fixV'),
    ('R', 'выгрузка: только команда', R16_STARO, R16_NOVO, 'fixV'),
    ('R', 'кэш ФИО по всем', R17_STARO, R17_NOVO, 'fixV'),
    ('R', 'сегменты по номеру (главная)', R18_STARO, R18_NOVO, 'fixV'),
    ('R', 'сегменты по номеру (доп. ОКВЭД)', R19_STARO, R19_NOVO, 'fixV'),
    ('R', 'сегменты по номеру (счётчики)', R20_STARO, R20_NOVO, 'fixV'),
    ('R', 'сегменты по номеру (статистика)', R21_STARO, R21_NOVO, 'fixV'),
    ('P', 'блок дня: строки команды', P1_STARO, P1_NOVO, 'fixV'),
    ('H', 'шапка: ссылка Статистика', H1_STARO, H1_NOVO, 'user.rop'),
    ('H', 'шапка: подпись руководителя', H2_STARO, H2_NOVO, 'user.rop'),
    ('H', 'шапка: формы действий скрыты', H3_STARO, H3_NOVO, 'fixV'),
    ('C', 'строка «Руководитель:»', C1_STARO, C1_NOVO, 'user.rop'),
    ('C', 'без пункта «Без менеджера»', C2_STARO, C2_NOVO, 'user.rop'),
    ('T', 'плитка «в каталоге»', T1_STARO, T1_NOVO, 'user.rop'),
    ('T', 'плитка «без менеджера»', T2_STARO, T2_NOVO, 'user.rop'),
]


def nl_kak_v(t, x):
    return x.replace('\n', '\r\n') if t.count('\r\n') * 2 > t.count('\n') else x


def nalozhit(teksty):
    novye = dict(teksty)
    zh, ok = [], True
    for kl, imya, staro, novo, priznak in PRAVKI:
        t = novye[kl]
        st, nv = nl_kak_v(t, staro), nl_kak_v(t, novo)
        if t.count(nv) == 1 and priznak in nv:
            zh.append('[уже] ' + imya)
            continue
        n = t.count(st)
        if n != 1:
            zh.append('[ЯКОРЬ НАЙДЕН %d РАЗ] %s' % (n, imya))
            ok = False
            continue
        novye[kl] = t.replace(st, nv, 1)
        zh.append('[ок] ' + imya)
    return novye, zh, ok


def prochitat(koren_app):
    return {k: io.open(os.path.join(koren_app, *p.split('/')), encoding='utf-8', newline='').read()
            for k, p in FAJLY.items()}


def zapisat(koren_app, teksty, klyuchi):
    for k in klyuchi:
        p = os.path.join(koren_app, *FAJLY[k].split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, 'w', encoding='utf-8', newline='') as f:
            f.write(teksty[k])


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


def migraciya_check(put_bazy):
    """CHECK(role IN ('admin','sales')) -> ('admin','sales','rop') в тексте схемы users. Документированный
    способ SQLite для ослабления CHECK (writable_schema + schema_version+1): данные не переписываются."""
    c = sqlite3.connect(put_bazy, timeout=30)
    c.isolation_level = None
    try:
        sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
        if "'rop'" in sql:
            return 'уже'
        staro = "CHECK(role IN ('admin','sales'))"
        if sql.count(staro) != 1:
            raise SystemExit('CHECK роли не найден в схеме users: %r' % sql[:300])
        novo = sql.replace(staro, "CHECK(role IN ('admin','sales','rop'))")
        c.execute('BEGIN IMMEDIATE')
        try:
            v = c.execute('PRAGMA schema_version').fetchone()[0]
            c.execute('PRAGMA writable_schema=ON')
            c.execute("UPDATE sqlite_master SET sql=? WHERE type='table' AND name='users'", (novo,))
            c.execute('PRAGMA schema_version=%d' % (v + 1))
            c.execute('PRAGMA writable_schema=OFF')
            c.execute('COMMIT')
        except Exception:
            c.execute('ROLLBACK')
            raise
    finally:
        c.close()
    c = sqlite3.connect(put_bazy, timeout=30)
    try:
        ic = c.execute('PRAGMA integrity_check').fetchone()[0]
        sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
        n = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    finally:
        c.close()
    if ic != 'ok' or "'rop'" not in sql:
        raise SystemExit('ПОСЛЕ ПРАВКИ CHECK: integrity=%s, rop в схеме=%s' % (ic, "'rop'" in sql))
    return 'сделано (integrity ok, пользователей %d)' % n


# ====================================================================== venv: подготовка копий, снимки, проверки
def okruzhenie(koren_app, kat, sales_db):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    sys.path.insert(0, koren_app)
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = sales_db
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        if os.path.normcase(os.path.abspath(os.environ.get(k, '') or 'x')) == os.path.normcase(KAT):
            os.environ[k] = kat
    from app import web
    from app.services import centro_catalog as cat
    assert os.path.normcase(os.path.dirname(web.__file__)).startswith(os.path.normcase(koren_app)), web.__file__
    assert os.path.normcase(str(cat.db_path())) == os.path.normcase(kat), str(cat.db_path())
    from app.services import centro_sales as sales
    assert os.path.normcase(str(sales.sales_db_path())) == os.path.normcase(sales_db), str(sales.sales_db_path())
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides.clear()
    return web, sales, rcs, vnutr


def prep(koren_app, kat, sales_db):
    """На КОПИИ базы продаж: три руководителя (случайный пароль, хеш) и синтетические действия менеджеров
    живым кодом (отметки трёх результатов, «не дозвонился», отметка админа за менеджера, переход компании
    в другой город с новой отметкой, скрытие компании)."""
    import secrets
    import datetime
    web, sales, rcs, vnutr = okruzhenie(koren_app, kat, sales_db)
    from fastapi.testclient import TestClient
    c = sqlite3.connect(sales_db)
    c.row_factory = sqlite3.Row
    for login, fio, gorod in ROPS:
        if not c.execute('SELECT 1 FROM users WHERE username=?', (login,)).fetchone():
            now = sales.utcnow()
            c.execute("INSERT INTO users(username,password_hash,role,is_active,created_at,updated_at,fio,gorod) "
                      "VALUES(?,?,'rop',1,?,?,?,?)", (login, sales.password_hash(secrets.token_urlsafe(18)),
                                                       now, now, fio, gorod))
    c.commit()
    kat_c = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
    v_kat = {str(r[0]) for r in kat_c.execute('SELECT inn FROM company')}
    kat_c.close()
    skr = {str(r[0]) for r in c.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
    otm = {str(r[0]) for r in c.execute("SELECT inn FROM company_state WHERE call_result<>'new'")}
    vl = {}
    for r in c.execute('SELECT inn, username FROM company_assignment ORDER BY inn'):
        if str(r[0]) in v_kat and str(r[0]) not in skr and str(r[0]) not in otm:
            vl.setdefault(r[1], []).append(str(r[0]))
    c.close()
    USERS = {'meyer_admin': {'id': 5, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY, 6):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    vchera = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    kody = []
    with TestClient(vnutr) as kl:
        kl.get(PUT + '/centro', follow_redirects=False)          # раздача новых (как у админа) – до снимков

        def post(u, put, data):
            kto['u'] = USERS[u]
            o = kl.post(PUT + put, data=data, follow_redirects=False)
            kody.append('%s %s %s' % (u, put.split('/')[-1], o.status_code))
            return o
        pr = rcs.PRICHINY_NE_PONRAVILAS
        for i, u in enumerate(PRODAVCY):
            ii = vl.get(u) or []
            if len(ii) < 7:
                kody.append('%s: мало компаний (%d)' % (u, len(ii)))
                continue
            post(u, '/centro/save', {'inn': ii[0], 'call_result': 'v_rabote', 'comment': 'тест fixV',
                                     'next_contact_at': vchera})
            post(u, '/centro/save', {'inn': ii[1], 'call_result': 'ne_ponravilas', 'prichina': pr[i % len(pr)],
                                     'comment': '' if i % 2 else 'тест fixV'})
            post(u, '/centro/save', {'inn': ii[2], 'call_result': 'dubl', 'comment': 'тест fixV'})
            post(u, '/centro/save', {'inn': ii[3], 'call_result': 'ne_dozvonilsya', 'comment': 'тест fixV'})
        i1 = vl['meyer1'][4]                  # Барнаул -> Краснодар: последняя отметка уже не барнаульская
        post('meyer1', '/centro/save', {'inn': i1, 'call_result': 'v_rabote', 'comment': 'тест fixV'})
        post('meyer_admin', '/centro/reassign', {'inn': i1, 'username': 'meyer2'})
        post('meyer2', '/centro/save', {'inn': i1, 'call_result': 'ne_ponravilas', 'prichina': pr[0],
                                        'comment': 'тест fixV'})
        post('meyer_admin', '/centro/save', {'inn': vl['meyer5'][4], 'call_result': 'v_rabote',
                                             'comment': 'тест fixV: админ за менеджера'})
        post('meyer3', '/centro/hide', {'inn': vl['meyer3'][5], 'kind': 'company', 'value': vl['meyer3'][5],
                                        'reason': 'тест fixV'})
    vnutr.dependency_overrides.clear()
    plohie = [k for k in kody if not k.endswith(' 303')]
    print('синтетика: действий %d, не 303: %s' % (len(kody), plohie))
    return 0 if not plohie else 1


def chisto(x):
    import datetime
    if isinstance(x, dict):
        return {str(k): chisto(v) for k, v in x.items() if not callable(v)}
    if isinstance(x, (list, tuple)):
        return [chisto(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((chisto(v) for v in x), key=str)
    if isinstance(x, (datetime.date, datetime.datetime)):
        return x.isoformat()
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    return str(x)


STATS_KL = ('obshchee', 'prodavcy', 'statblok', 'direktor', 'sobytiya_dir', 'ochered')


def snimok(koren_app, kat, sales_db, metka, rop):
    import csv
    import re
    t0 = time.time()
    web, sales, rcs, vnutr = okruzhenie(koren_app, kat, sales_db)
    from fastapi.testclient import TestClient
    ZH = {}
    orig = web.templates.TemplateResponse

    def tr(*a, **kw):
        try:
            ZH[a[1] if len(a) > 1 else kw.get('name')] = a[2] if len(a) > 2 else kw.get('context')
        except Exception:  # noqa: BLE001
            pass
        return orig(*a, **kw)
    web.templates.TemplateResponse = tr
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    c = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
    c.row_factory = sqlite3.Row
    lyudi = {r['username']: dict(r) for r in c.execute('SELECT username, role, is_active, fio, gorod FROM users')}
    vl = {str(r[0]): r[1] for r in c.execute('SELECT inn, username FROM company_assignment')}
    c.close()
    fio = {u: (r['fio'] or u) for u, r in lyudi.items()}
    sn = {'admin': {}, 'sales': {}}
    with TestClient(vnutr) as kl:
        def zapros(login, put, metod='get', data=None, **params):
            h = {'Cookie': '%s=%s' % (rcs.COOKIE, rcs._token(login, int(time.time()) + 3600))}
            ZH.clear()
            if metod == 'post':
                o = kl.post(PUT + put, data=data or {}, headers=h, follow_redirects=False)
            else:
                o = kl.get(PUT + put, params=params, headers=h, follow_redirects=False)
            return o, dict(ZH)

        # для сравнения «до/после» порядок сегментов не важен (его и меняем): сортируется одинаково
        def stats_sn(z):
            s = z.get('centro_stats.html') or {}
            sn_ = chisto({k: s.get(k) for k in STATS_KL})
            for r in (sn_.get('direktor') or {}).get('razrezy') or []:
                if r.get('nazv') == 'Сегмент':
                    r['stroki'] = sorted(r['stroki'], key=lambda x: str(x.get('znach')))
            return sn_

        def glavn_sn(z):
            s = z.get('centro.html') or {}
            sn_ = chisto({'total': s.get('total'), 'inn': [r['inn'] for r in s.get('rows') or []],
                          'choices': s.get('choices'), 'sales_users': s.get('sales_users')})
            if isinstance((sn_.get('choices') or {}).get('segment'), list):
                sn_['choices']['segment'] = sorted(sn_['choices']['segment'], key=str)
            return sn_
        # ---------------- админ
        o, z = zapros('meyer_admin', '/centro/stats')
        ok(o.status_code == 200, 'админ: статистика %s' % o.status_code)
        sn['admin']['stats'] = stats_sn(z)
        A = z.get('centro_stats.html') or {}
        o, z = zapros('meyer_admin', '/centro/stats', stat_vse='1')
        ok(o.status_code == 200, 'админ: статистика за всё время %s' % o.status_code)
        sn['admin']['stats_vse'] = stats_sn(z)
        A_vse = z.get('centro_stats.html') or {}
        o, z = zapros('meyer_admin', '/centro')
        ok(o.status_code == 200, 'админ: главная %s (компаний %s)' % (o.status_code, (z.get('centro.html') or {}).get('total')))
        sn['admin']['glavnaya'] = glavn_sn(z)
        segm_admin = list((z.get('centro.html') or {}).get('choices', {}).get('segment') or [])
        o, z = zapros('meyer_admin', '/centro', call_status='v_rabote')
        sn['admin']['v_rabote'] = glavn_sn(z)
        o, _ = zapros('meyer_admin', '/centro/vygruzka.csv')
        stroki_adm = list(csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))[1:] if o.status_code == 200 else []
        ok(o.status_code == 200, 'админ: выгрузка CSV %s (строк %d)' % (o.status_code, len(stroki_adm)))
        sn['admin']['csv_n'] = len(stroki_adm)
        o, _ = zapros('meyer_admin', '/centro/admin')
        ok(o.status_code == 200, 'админ: распределение %s' % o.status_code)
        # ---------------- продавцы
        for p in PRODAVCY:
            o, z = zapros(p, '/centro')
            g = glavn_sn(z)
            o2, _ = zapros(p, '/centro/stats')
            moi = [i for i, u in vl.items() if u == p]
            o3, _ = zapros(p, '/centro', inn=(g['inn'] or [''])[0]) if g['inn'] else (None, None)
            ok(o.status_code == 200 and o2.status_code == 403 and (o3 is None or o3.status_code == 200),
               '%s: главная %s (компаний %s из назначенных %d), статистика %s, своя карточка %s'
               % (p, o.status_code, g['total'], len(moi), o2.status_code, o3.status_code if o3 else '-'))
            sn['sales'][p] = {'glavnaya': g, 'stats': o2.status_code}
        # сегменты: порядок и число = строкам (админ – все, продавец – три)
        def nomer(s):
            m = re.match(r'\s*(\d+)', s)
            return (0, int(m.group(1)), s.casefold()) if m else (1, 0, s.casefold())
        imena = [s for s, _n in segm_admin]
        print('   сегменты у админа: %s' % ' | '.join('%s – %s' % (s, n) for s, n in segm_admin))
        if rop:
            ok(imena == sorted(imena, key=nomer), 'админ: сегменты по номеру, без номера в конце')
            for s, n in segm_admin:
                o, z = zapros('meyer_admin', '/centro', segment=s)
                t = (z.get('centro.html') or {}).get('total')
                ok(o.status_code == 200 and t == n, 'админ: сегмент «%s» – %s, строк %s = %s' % (s, o.status_code, t, n))
            o, z = zapros('meyer1', '/centro')
            seg1 = list((z.get('centro.html') or {}).get('choices', {}).get('segment') or [])
            ok([s for s, _ in seg1] == sorted([s for s, _ in seg1], key=nomer), 'meyer1: сегменты по номеру (%d)' % len(seg1))
            for s, n in seg1[:3] + seg1[-2:]:
                o, z = zapros('meyer1', '/centro', segment=s)
                t = (z.get('centro.html') or {}).get('total')
                ok(o.status_code == 200 and t == n, 'meyer1: сегмент «%s» – %s, строк %s = %s' % (s, o.status_code, t, n))
            for st_, nazv in ((A, 'период'), (A_vse, 'всё время')):
                rz = [r for r in (st_.get('direktor') or {}).get('razrezy') or [] if r['nazv'] == 'Сегмент']
                zn = [x['znach'] for x in (rz[0]['stroki'] if rz else [])]
                ok(zn == sorted(zn, key=nomer), 'статистика (%s): разбивка по сегменту по номеру: %s' % (nazv, zn[:8]))
        io.open(os.path.join(os.path.dirname(sales_db), 'fixV-snimok-%s.json' % metka), 'w', encoding='utf-8').write(
            json.dumps(sn, ensure_ascii=False, sort_keys=True))
        print('   снимок %s записан (%.0f с)' % (metka, time.time() - t0))
        if not rop:
            print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
            return plohih[0]
        # ================================================================ руководители
        adm_tot = {}
        adm_vr = {}
        for u in PRODAVCY:
            o, z = zapros('meyer_admin', '/centro', assigned_user=u)
            adm_tot[u] = (z.get('centro.html') or {}).get('total')
            o, z = zapros('meyer_admin', '/centro', assigned_user=u, call_status='v_rabote')
            adm_vr[u] = (z.get('centro.html') or {}).get('total')
        print('   админ: компаний по менеджерам %s' % adm_tot)

        def po_kto(spisok):
            return {r['kto']: r for r in spisok or [] if not r.get('itog')}

        def itog_iz(spisok):
            it = [r for r in spisok or [] if r.get('itog')]
            return it[0] if it else None

        def sverit_prichiny(R, Ad, kom, nazv):
            dr, da = R.get('direktor') or {}, Ad.get('direktor') or {}
            kr, ka = dr.get('kolonki') or [], da.get('kolonki') or []
            rr, ra = po_kto(dr.get('prichiny')), po_kto(da.get('prichiny'))
            ok(set(rr) <= set(kom), '%s: причины × менеджер – строки только команды %s' % (nazv, sorted(rr)))
            plohie = []
            for u, r in rr.items():
                a_ = ra.get(u)
                if a_ is None:
                    plohie.append(u)
                    continue
                r1 = {k: v for k, v in chisto(r).items() if k != 'pr'}
                a1 = {k: v for k, v in chisto(a_).items() if k != 'pr'}
                pr_r = dict(zip(kr, chisto(r['pr'])))
                pr_a = dict(zip(ka, chisto(a_['pr'])))
                if r1 != a1 or any(pr_r[k] != pr_a.get(k, {'n': 0, 'url': ''}) for k in kr) \
                        or any(pr_a[k]['n'] for k in ka if k not in kr):
                    plohie.append(u)
            ok(not plohie, '%s: строки причин = строкам админа (расхождения: %s)' % (nazv, plohie))
            it = itog_iz(dr.get('prichiny'))
            if len(rr) > 1:
                sm = {k: sum(r[k]['n'] for r in rr.values()) for k in ('otmecheno', 'v_rabote', 'otkazov', 'dubl', 'bez_poyasn')}
                ok(it is not None and all(it[k]['n'] == v for k, v in sm.items()),
                   '%s: итог причин = сумме команды %s' % (nazv, sm))
            tr_, ta = po_kto(dr.get('temp')), po_kto(da.get('temp'))
            ok(set(tr_) <= set(kom) and all(chisto(r) == chisto(ta.get(u)) for u, r in tr_.items()),
               '%s: темп и прогноз – строки команды = строкам админа' % nazv)
            it = itog_iz(dr.get('temp'))
            if len(tr_) > 1:
                ok(it is not None and it['otmecheno']['n'] == sum(r['otmecheno']['n'] for r in tr_.values())
                   and it['ochered']['n'] == sum(r['ochered']['n'] for r in tr_.values()),
                   '%s: итог темпа = сумме (отмечено %s, очередь %s)' % (nazv, it and it['otmecheno']['n'], it and it['ochered']['n']))
            chr_ = {r['kto']: r['vsego'] for r in dr.get('chasy') or [] if not r.get('itog')}
            cha = {r['kto']: r['vsego'] for r in da.get('chasy') or [] if not r.get('itog')}
            ok(set(chr_) <= set(kom) and all(cha.get(u) == v for u, v in chr_.items()),
               '%s: часы – только команда, как у админа %s' % (nazv, chr_))
            lr = dr.get('lenta') or []
            la = [x for x in da.get('lenta') or [] if x['kto'] in kom or x['deystvoval'] in kom]
            ok(all(x['kto'] in kom or x['deystvoval'] in kom for x in lr)
               and (da.get('lenta_vsego', 0) > 300 or len(lr) == len(la)),
               '%s: лента – только команда (%d, у админа по команде %d)' % (nazv, len(lr), len(la)))
            ok(all(r['kompaniy'] == dr.get('otmecheno_vsego') for r in dr.get('razrezy') or []),
               '%s: разбивки «где берут в работу» – по %s компаниям команды' % (nazv, dr.get('otmecheno_vsego')))
            sr, sa = po_kto((R.get('sobytiya_dir') or {}).get('stroki')), po_kto((Ad.get('sobytiya_dir') or {}).get('stroki'))
            ok(set(sr) <= set(kom) and all(chisto(r) == chisto(sa.get(u)) for u, r in sr.items()),
               '%s: недозвоны – строки команды = строкам админа' % nazv)
            it = (R.get('sobytiya_dir') or {}).get('itog') or {}
            ok(it.get('nedozvon') == sum(r['nedozvon'] for r in sr.values()), '%s: итог недозвонов = сумме (%s)' % (nazv, it.get('nedozvon')))
            sb, sa_ = R.get('statblok') or {}, {s['username']: s for s in (Ad.get('statblok') or {}).get('stroki') or []}
            ok(sorted(s['username'] for s in sb.get('stroki') or []) == kom
               and sorted(s['username'] for s in sb.get('vybor') or []) == kom,
               '%s: блок «за день / всё время» – строки и выбор = команда' % nazv)
            ok(all(chisto(s) == chisto(sa_.get(s['username'])) for s in sb.get('stroki') or []),
               '%s: блок дня – строки = строкам админа' % nazv)
            itg = {ch: {k: sum(s[ch][k] for s in sb.get('stroki') or []) for k in (sb.get('itog') or {}).get(ch, {})}
                   for ch in ('den', 'vse')}
            ok(chisto(itg) == chisto(sb.get('itog')), '%s: итог блока дня = сумме %s' % (nazv, sb.get('itog')))

        c = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
        kom_po_gorodu = {}
        for u, r in lyudi.items():
            if r['role'] == 'sales' and r['is_active']:
                kom_po_gorodu.setdefault((r['gorod'] or '').strip(), []).append(u)
        kat_c = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
        v_kat = {str(r[0]) for r in kat_c.execute('SELECT inn FROM company')}
        kat_c.close()

        def kolvo(c_):
            return [c_.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0] for t in
                    ('activity_log', 'company_state', 'company_comment', 'hidden_item', 'company_assignment', 'zvonok_sobytie', 'users')]
        for login, fio_rop, gorod in ROPS:
            kom = sorted(kom_po_gorodu.get(gorod, []))
            chuzhie = [u for u in PRODAVCY if u not in kom]
            print('-- %s (%s, %s): команда %s' % (login, fio_rop, gorod, ', '.join('%s %s' % (u, fio[u]) for u in kom)))
            par = '%s-%s' % (login[-4:], int(time.time()))
            sales.upsert_user(login, 'Tst-' + par + 'xY7', 'rop', path=sales_db)    # пароль копии – только для теста входа
            with TestClient(vnutr) as kl2:
                o = kl2.post(PUT + '/centro/login', data={'username': login, 'password': 'Tst-' + par + 'xY7'}, follow_redirects=False)
                g1 = kl2.get(PUT + '/centro', follow_redirects=False).status_code
                g2 = kl2.get(PUT + '/centro/stats', follow_redirects=False).status_code
            ok(g1 == 200 and g2 == 200, '%s: вход формой -> главная %s, статистика %s' % (login, g1, g2))
            for zp, nazv, Ad in (({}, 'период', A), ({'stat_vse': '1'}, 'всё время', A_vse)):
                o, z = zapros(login, '/centro/stats', **zp)
                R = z.get('centro_stats.html') or {}
                ok(o.status_code == 200, '%s: статистика (%s) %s' % (login, nazv, o.status_code))
                if not R:
                    continue
                pr_ = R.get('prodavcy') or []
                pa = {p['username']: p for p in Ad.get('prodavcy') or []}
                ok(sorted(p['username'] for p in pr_) == kom, '%s: «По менеджерам» – ровно команда' % nazv)
                ok(all(chisto(p) == chisto(pa.get(p['username'])) for p in pr_), '%s: строки менеджеров = строкам админа' % nazv)
                ob = R.get('obshchee') or {}
                for k in ('naznacheno', 'obrabotano', 'prosrocheno'):
                    ok(ob.get(k) == sum(p[k] for p in pr_), '%s: плитка %s = сумме команды (%s)' % (nazv, k, ob.get(k)))
                ok(sum((ob.get('po_rezultatu') or {}).values()) == sum(1 for i, u in vl.items() if u in kom and i in v_kat),
                   '%s: «по результатам звонка» – компании команды (%s)' % (nazv, sum((ob.get('po_rezultatu') or {}).values())))
                n_kom = c.execute('SELECT COUNT(*) FROM company_comment WHERE username IN (%s)' % ','.join('?' * len(kom)), kom).fetchone()[0]
                n_ned = c.execute("SELECT COUNT(*) FROM zvonok_sobytie WHERE vid='ne_dozvonilsya' AND state_user IN (%s)" % ','.join('?' * len(kom)), kom).fetchone()[0]
                inn_k = {i for i, u in vl.items() if u in kom}
                n_skr = sum(1 for r in c.execute("SELECT inn FROM hidden_item WHERE kind='company'") if str(r[0]) in inn_k)
                n_d = 0
                for r in c.execute('SELECT username, payload_json FROM activity_log'):
                    try:
                        pl = json.loads(r[1] or '{}')
                    except ValueError:
                        pl = {}
                    n_d += 1 if (r[0] in kom or str(pl.get('state_user') or '') in kom) else 0
                ok(ob.get('kommentariev') == n_kom and ob.get('nedozvon_vsego') == n_ned and ob.get('skryto') == n_skr
                   and ob.get('vsego_deystviy') == n_d,
                   '%s: плитки комментариев %s, недозвонов %s, скрыто %s, действий %s – по команде'
                   % (nazv, ob.get('kommentariev'), ob.get('nedozvon_vsego'), ob.get('skryto'), ob.get('vsego_deystviy')))
                sverit_prichiny(R, Ad, kom, nazv)
                h = o.text
                ok('Руководитель отдела продаж · %s' % gorod in h and fio_rop in h, '%s: шапка «%s · Руководитель отдела продаж · %s»' % (nazv, fio_rop, gorod))
                # передача компании В команду в ленте называет прежнего владельца – это история её компании
                h = re.sub(r'передал компанию:[^<]*', '', h)
                ok(not [fio[u] for u in chuzhie if fio[u] in h] and all(fio[u] in h for u in kom),
                   '%s: чужих менеджеров в странице нет (%s)' % (nazv, [fio[u] for u in chuzhie if fio[u] in h]))
                ok('компаний в каталоге' not in h and 'компаний без менеджера' not in h, '%s: плиток «в каталоге/без менеджера» нет' % nazv)
            # ---- главная
            o, z = zapros(login, '/centro')
            C = z.get('centro.html') or {}
            ok(o.status_code == 200 and C.get('total') == sum(adm_tot[u] for u in kom),
               'главная %s: компаний %s = сумме у админа по команде %s' % (o.status_code, C.get('total'), sum(adm_tot[u] for u in kom)))
            ok(all(r['assigned_user'] in kom for r in C.get('rows') or []) and sorted(C.get('sales_users') or []) == kom
               and (C.get('choices') or {}).get('bez_prodavca_n', 0) == 0,
               'главная: строки и выбор менеджера – только команда, «без менеджера» 0')
            h = o.text
            vybor = re.findall(r'<select name="assigned_user".*?</select>', h, re.S)
            ok(vybor and all(not [u for u in chuzhie if 'value="%s"' % u in v] for v in vybor) and '__net__' not in h
               and 'id="fixV-rop"' in h and 'Руководитель:' in h,
               'главная: в выборе «Сотрудник» только команда, без «Без менеджера», формы скрыты, «Руководитель:»')
            seg = list((C.get('choices') or {}).get('segment') or [])
            ok([s for s, _ in seg] == sorted([s for s, _ in seg], key=nomer), 'главная: сегменты по номеру (%d)' % len(seg))
            for s, n in seg[:2]:
                o2, z2 = zapros(login, '/centro', segment=s)
                ok(o2.status_code == 200 and (z2.get('centro.html') or {}).get('total') == n, 'главная: сегмент «%s» = %s строк' % (s, n))
            o, z = zapros(login, '/centro', call_status='v_rabote')
            ok((z.get('centro.html') or {}).get('total') == sum(adm_vr[u] for u in kom),
               '«Взял в работу»: %s = сумме у админа %s' % ((z.get('centro.html') or {}).get('total'), sum(adm_vr[u] for u in kom)))
            if kom:
                o, z = zapros(login, '/centro', assigned_user=kom[0])
                ok(o.status_code == 200 and (z.get('centro.html') or {}).get('total') == adm_tot[kom[0]],
                   'фильтр по своему менеджеру %s: %s' % (kom[0], (z.get('centro.html') or {}).get('total')))
                o, z = zapros(login, '/centro/stats', user=kom[0])
                o2, z2 = zapros('meyer_admin', '/centro/stats', user=kom[0])
                ok(o.status_code == 200 and len((z.get('centro_stats.html') or {}).get('ochered') or []) ==
                   len((z2.get('centro_stats.html') or {}).get('ochered') or []),
                   'очередь своего менеджера в статистике: %s строк, у админа %s' % (
                       len((z.get('centro_stats.html') or {}).get('ochered') or []), len((z2.get('centro_stats.html') or {}).get('ochered') or [])))
            svoi = [r['inn'] for r in C.get('rows') or []]
            chuzh_inn = next((i for i, u in sorted(vl.items()) if u in chuzhie and i in v_kat), '')
            if svoi:
                o, _ = zapros(login, '/centro', inn=svoi[0])
                ok(o.status_code == 200 and 'id="fixV-rop"' in o.text, 'карточка своей компании %s: %s' % (svoi[0], o.status_code))
            o, _ = zapros(login, '/centro', inn=chuzh_inn)
            ok(o.status_code in (403, 404), 'карточка чужой компании %s: %s' % (chuzh_inn, o.status_code))
            for put_, pp in (('/centro', {'assigned_user': chuzhie[0]}), ('/centro', {'assigned_user': '__net__'}),
                             ('/centro/stats', {'user': chuzhie[0]}), ('/centro/stats', {'stat_user': chuzhie[0]}),
                             ('/centro', {'kto_p': chuzhie[0]}), ('/centro/vygruzka.csv', {'assigned_user': chuzhie[0]})):
                o, _ = zapros(login, put_, **pp)
                ok(o.status_code in (403, 404), 'чужой менеджер %s %s: %s' % (put_, pp, o.status_code))
            o, _ = zapros(login, '/centro/admin')
            ok(o.status_code == 403, '«Распределение»: %s' % o.status_code)
            # ---- действия: всё запрещено, базы не изменились
            do_ = kolvo(c)
            inn0 = svoi[0] if svoi else chuzh_inn
            for put_, d in (('/centro/save', {'inn': inn0, 'call_result': 'v_rabote', 'comment': 'x'}),
                            ('/centro/save', {'inn': inn0, 'call_result': 'ne_dozvonilsya', 'comment': 'x'}),
                            ('/centro/reassign', {'inn': inn0, 'username': kom[0] if kom else 'meyer1'}),
                            ('/centro/hide', {'inn': inn0, 'kind': 'company', 'value': inn0}),
                            ('/centro/comments/1', {'body': 'x'}),
                            ('/centro/park/%s/musor' % inn0, {}),
                            ('/centro/park/%s/v-obzvon' % inn0, {'username': kom[0] if kom else ''})):
                o, _ = zapros(login, put_, metod='post', data=d)
                ok(o.status_code == 403, 'POST %s: %s' % (put_, o.status_code))
            ok(kolvo(c) == do_, 'после попыток действий базы продаж не изменились %s' % do_)
            # ---- выгрузка
            o, _ = zapros(login, '/centro/vygruzka.csv')
            st = list(csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))[1:] if o.status_code == 200 else []
            fio_kom = {fio[u] for u in kom}
            inn_adm = {r[2] for r in stroki_adm if r[18] in fio_kom}
            ok(o.status_code == 200 and len(st) == C.get('total') and all(r[18] in fio_kom for r in st)
               and {r[2] for r in st} == inn_adm,
               'выгрузка CSV: %s, строк %d = главной, менеджеры только команды, ИНН = строкам админа по команде (%d)'
               % (o.status_code, len(st), len(inn_adm)))
            o, _ = zapros(login, '/centro/spisok')
            ok(o.status_code == 200 and not [fio[u] for u in chuzhie if fio[u] in o.text],
               '«Список компаний»: %s, чужих менеджеров нет' % o.status_code)
        c.close()
        # ---------------- после руководителей: админ и продавец – как были (контекст не протёк)
        o, z = zapros('meyer_admin', '/centro/stats')
        ok(stats_sn(z) == sn['admin']['stats'], 'админ после руководителей: статистика та же')
        o, z = zapros('meyer_admin', '/centro')
        ok(glavn_sn(z) == sn['admin']['glavnaya'], 'админ после руководителей: главная та же (%s)' % (z.get('centro.html') or {}).get('total'))
        o, z = zapros('meyer5', '/centro')
        ok(glavn_sn(z) == sn['sales']['meyer5']['glavnaya'], 'meyer5 после руководителей: очередь та же')
        o, z = zapros('meyer_admin', '/centro', assigned_user='__net__')
        ok(o.status_code == 200, 'админ: «без менеджера» на месте (%s)' % (z.get('centro.html') or {}).get('total'))
    print('   время %.0f с' % (time.time() - t0))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--prep' in sys.argv:
    i = sys.argv.index('--prep')
    raise SystemExit(prep(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3]))
if '--snimok' in sys.argv:
    i = sys.argv.index('--snimok')
    raise SystemExit(1 if snimok(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3], sys.argv[i + 4], '--rop' in sys.argv) else 0)


def venv(*argi):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + list(argi), capture_output=True, timeout=1500, cwd=KOREN, env=SREDA)
    v = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        v += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:]
    return r.returncode == 0, v


def sravnit(papka, m_do, m_po):
    do = json.load(io.open(os.path.join(papka, 'fixV-snimok-%s.json' % m_do), encoding='utf-8'))
    po = json.load(io.open(os.path.join(papka, 'fixV-snimok-%s.json' % m_po), encoding='utf-8'))
    raz = []
    for k in sorted(set(do['admin']) | set(po['admin'])):
        a, b = do['admin'].get(k), po['admin'].get(k)
        if a != b:
            kl = sorted(x for x in set((a or {}) if isinstance(a, dict) else []) | set((b or {}) if isinstance(b, dict) else [])
                        if not isinstance(a, dict) or not isinstance(b, dict) or a.get(x) != b.get(x))
            raz.append('админ %s: %s' % (k, kl[:12]))
    for p in PRODAVCY:
        if do['sales'].get(p) != po['sales'].get(p):
            raz.append('%s: очередь/статистика' % p)
    return raz


def podnovit_zamok():
    try:
        os.utime(ZAMOK, None)
    except OSError:
        pass


def proverit(koren_app, papka, metka, vyvod, s_do=True):
    """Копии баз -> CHECK на копии -> руководители и синтетика (живой код) -> снимок «до» живым кодом ->
    снимок «после» и проверки руководителей кодом koren_app -> сравнение админа и продавцов."""
    ts, tk = os.path.join(papka, 't_sales_%s.db' % metka), os.path.join(papka, 't_kat_%s.db' % metka)
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    vyvod.append('копии баз: %s; CHECK на копии: %s' % (papka, migraciya_check(ts)))
    g, v = venv('--prep', KOREN, tk, ts)
    vyvod.append('----- синтетика на копии (живой код)\n' + v[-2500:])
    podnovit_zamok()
    good = g
    if g and s_do:
        g0, v0 = venv('--snimok', KOREN, tk, ts, 'do-' + metka)
        vyvod.append('----- снимок «до» (живой код)\n' + v0[-3000:])
        good = good and g0
        podnovit_zamok()
    if good:
        g1, v1 = venv('--snimok', koren_app, tk, ts, 'posle-' + metka, '--rop')
        vyvod.append('----- снимок «после» и проверки руководителей (%s)\n' % koren_app + v1)
        good = good and g1
        podnovit_zamok()
        if good and s_do:
            raz = sravnit(papka, 'do-' + metka, 'posle-' + metka)
            vyvod.append('----- админ и 9 продавцов «до/после»: РАСХОЖДЕНИЙ %d %s' % (len(raz), raz))
            good = good and not raz
    for f in (ts, tk, ts + '-wal', ts + '-shm'):
        try:
            os.remove(f)
        except OSError:
            pass
    return good


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
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


def ostanovit():
    p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in p.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
    time.sleep(2)


def zapustit(prichina):
    lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    lg.write('\n===== перезапуск: %s %s =====\n' % (prichina, time.strftime('%Y-%m-%d %H:%M:%S')))
    lg.flush()
    subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                     stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                     close_fds=True, env=SREDA)
    import urllib.request
    kod = ''
    for _ in range(12):
        time.sleep(5)
        try:
            kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            if kod == 200:
                break
        except Exception as e:  # noqa: BLE001
            kod = str(e)[:80]
    return kod


def sdelat_stage(novye, izm):
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    shutil.copytree(APP, os.path.join(STAGE, 'app'),
                    ignore=shutil.ignore_patterns('__pycache__', 'dokaz', '*.pyc', '*.db', '*.log'))
    zapisat(os.path.join(STAGE, 'app'), novye, izm)


PAPKA = os.path.join(KOREN, '_bekap', 'fixV-kod-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--suho' in sys.argv:
    teksty = prochitat(APP)
    novye, zh, vse_ok = nalozhit(teksty)
    print('\n'.join('   ' + x for x in zh))
    if not vse_ok:
        print('ЯКОРЯ НЕ НАЙДЕНЫ – ничего не делаю')
        raise SystemExit(4)
    izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
    sdelat_stage(novye, izm)
    vyvod = []
    good = proverit(STAGE, PAPKA, 'suho-' + VREMYA, vyvod)
    t = '\n'.join(vyvod)
    io.open(os.path.join(DROP, 'fixV-kod-suho-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5200:])
    print('СУХОЙ ПРОГОН: %s (живые файлы и базы не тронуты; меняются: %s)' % (
        'ОК' if good else 'ЕСТЬ ПЛОХОЕ', ', '.join(FAJLY[k_] for k_ in izm)))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixV (роль руководителя отдела продаж; сегменты по номеру)')
    vyvod = []
    try:
        teksty = prochitat(APP)
        novye, zh, vse_ok = nalozhit(teksty)
        vyvod.append('\n'.join('   ' + x for x in zh))
        if not vse_ok:
            print(vyvod[0])
            print('ЯКОРЯ НЕ НАЙДЕНЫ – живые файлы не тронуты')
            raise SystemExit(4)
        izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
        for k_ in izm:                                  # копия прежних файлов – только свои
            dst = os.path.join(PAPKA, 'app', *FAJLY[k_].split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(APP, *FAJLY[k_].split('/')), dst)
        if izm:
            sdelat_stage(novye, izm)
            good = proverit(STAGE, PAPKA, 'stage-' + VREMYA, vyvod, s_do=True)
            if not good:
                t = '\n'.join(vyvod)
                io.open(os.path.join(DROP, 'fixV-kod-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
                print(t[-4500:])
                print('ПРОВЕРКА НА STAGE НЕ ПРОШЛА – живые файлы и базы не тронуты')
                raise SystemExit(5)
            for k_ in izm:
                if io.open(os.path.join(APP, *FAJLY[k_].split('/')), encoding='utf-8', newline='').read() != teksty[k_]:
                    print('ФАЙЛ %s ИЗМЕНИЛСЯ ЗА ВРЕМЯ ПРОГОНА – не пишу' % FAJLY[k_])
                    raise SystemExit(6)
        # база продаж: копия и CHECK роли (данные не переписываются)
        kopiya(SALES, os.path.join(PAPKA, 'centro_sales_meyer1-do-fixV.db'))
        vyvod.append('база продаж: копия %s; CHECK: %s' % (os.path.join(PAPKA, 'centro_sales_meyer1-do-fixV.db'),
                                                           migraciya_check(SALES)))
        if izm:
            ostanovit()
            zapisat(APP, novye, izm)
            kod = zapustit('исправитель V: руководитель отдела продаж, сегменты по номеру')
            vyvod.append('записано: %s; перезапуск, вход: %s' % (', '.join(FAJLY[k_] for k_ in izm), kod))
            podnovit_zamok()
            g2 = proverit(KOREN, PAPKA, 'zhivoy-' + VREMYA, vyvod, s_do=False)
            if kod != 200 or not g2:
                for k_ in izm:
                    shutil.copy2(os.path.join(PAPKA, 'app', *FAJLY[k_].split('/')), os.path.join(APP, *FAJLY[k_].split('/')))
                ostanovit()
                kod2 = zapustit('исправитель V: ОТКАТ своих файлов')
                vyvod.append('ПОСЛЕ ЗАПИСИ ПЛОХО – свои файлы возвращены из %s, перезапуск, вход: %s' % (PAPKA, kod2))
            else:
                vyvod.append('ПРИМЕНЕНО: %s; копия прежних файлов: %s' % (', '.join(FAJLY[k_] for k_ in izm), PAPKA))
        else:
            vyvod.append('правки кода уже стоят – файлы не меняю')
        t = '\n'.join(vyvod)
        io.open(os.path.join(DROP, 'fixV-kod-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
        print(t[-5500:])
    finally:
        otdat_zamok()
