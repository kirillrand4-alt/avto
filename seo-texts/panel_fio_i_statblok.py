# -*- coding: utf-8 -*-
"""ФИО продавцов везде + блок статистики с календарём на «Списке компаний» + починка очереди.

ЧТО ДЕЛАЕТСЯ
  1. users.fio — отдельное поле ФИО. Логины meyer1..meyer4 НЕ трогаются: пароли уже
     выданы, а на логин ссылаются назначения, состояния, комментарии и журнал.
  2. Фильтр шаблонов |fio: логин -> ФИО (или сам логин, если ФИО пусто). Одним фильтром
     во всех местах вывода, иначе продавец увидит себя «Пятковой» в шапке и «meyer1»
     в статистике — это хуже, чем везде логин.
  3. На «Списке компаний», в пустом месте полосы счётчиков: календарь, выбор продавца,
     таблица «взял в работу / не понравилась / дубль / в очереди» за дату и за всё время,
     итогом и по каждому продавцу.
  4. Починка страницы статистики: очередь продавца теперь без скрытых и без ИНН вне
     каталога — так её видит сам продавец. Было 704 у user2 при видимых 212.

ПОЧЕМУ ТАК СЧИТАЕТСЯ «НА ДАТУ»
  Не по company_state.last_contact_at: это время ПОСЛЕДНЕГО действия, и если компанию
  тронули сегодня, вчерашняя отметка по ней пропадёт задним числом. Считается по журналу
  activity_log (action='call_saved', результат в payload_json): за день берётся последняя
  отметка по каждой компании, чтобы «сперва не понравилась, потом взял в работу» не
  посчиталось дважды. День — по Москве: продавцы звонят по Москве, а база пишет UTC.

Каждый файл перед правкой копируется в C:\\centro2\\_bekap\\<время>\\.
"""
import io
import os
import re
import shutil
import sqlite3
import time

KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
BAZA = os.path.join(KOREN, 'data', 'centro_sales.db')
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('fio-stat-%Y%m%d-%H%M%S'))

FIO = {'meyer1': 'Пяткова Ксения', 'meyer2': 'Ерохин Александр',
       'meyer3': 'Беляев Максим', 'meyer4': 'Волков Роман'}

itog = []
nado = 0
sdelano = 0
zabekaplen = set()


def skazat(s=''):
    itog.append(str(s))
    print(s)


def bekap(put):
    if put in zabekaplen:
        return
    cel = os.path.join(BEKAP, os.path.relpath(put, KOREN))
    os.makedirs(os.path.dirname(cel), exist_ok=True)
    shutil.copy2(put, cel)
    zabekaplen.add(put)


def chitat(put):
    return io.open(put, encoding='utf-8').read()


def pisat(put, t):
    bekap(put)
    io.open(put, 'w', encoding='utf-8').write(t)


def pravka(put, staro, novo, imya, vse=False, priznak=None):
    """Одна правка с учётом. vse=True — заменить все вхождения (и сказать сколько)."""
    global nado, sdelano
    nado += 1
    t = chitat(put)
    if priznak and priznak in t:
        sdelano += 1
        skazat('   [уже] %s' % imya)
        return
    n = t.count(staro)
    if n == 0:
        skazat('   [НЕТ ЯКОРЯ] %s' % imya)
        return
    if n > 1 and not vse:
        skazat('   [ЯКОРЬ НЕ ЕДИНСТВЕННЫЙ: %d] %s — не правлю' % (n, imya))
        return
    pisat(put, t.replace(staro, novo) if vse else t.replace(staro, novo, 1))
    sdelano += 1
    skazat('   [ок] %s%s' % (imya, (' (вхождений %d)' % n) if vse else ''))


def pravka_v_funkcii(put, nachalo, staro, novo, imya, priznak=None):
    """Правка только внутри одной функции: в routes_park.py те же строки есть и у
    других маршрутов, и правка «первого вхождения» уехала бы не туда."""
    global nado, sdelano
    nado += 1
    t = chitat(put)
    i = t.find(nachalo)
    if i < 0:
        skazat('   [НЕТ ФУНКЦИИ] %s' % imya)
        return
    j = t.find('\n@router.', i + len(nachalo))
    j = len(t) if j < 0 else j
    kusok = t[i:j]
    if priznak and priznak in kusok:
        sdelano += 1
        skazat('   [уже] %s' % imya)
        return
    n = kusok.count(staro)
    if n != 1:
        skazat('   [ЯКОРЬ В ФУНКЦИИ: %d вхождений] %s — не правлю' % (n, imya))
        return
    pisat(put, t[:i] + kusok.replace(staro, novo, 1) + t[j:])
    sdelano += 1
    skazat('   [ок] %s' % imya)


def dopisat(put, priznak, kod, imya):
    global nado, sdelano
    nado += 1
    t = chitat(put)
    if priznak in t:
        sdelano += 1
        skazat('   [уже] %s' % imya)
        return
    pisat(put, t.rstrip('\n') + '\n' + kod)
    sdelano += 1
    skazat('   [ок] %s' % imya)


CS = os.path.join(APP, 'services', 'centro_sales.py')
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
RP = os.path.join(APP, 'api', 'routes_park.py')
T = os.path.join(APP, 'templates')

# ================================================================ 1. колонка fio
skazat('########## 1. ПОЛЕ ФИО')
c = sqlite3.connect(BAZA)
kol = {r[1] for r in c.execute('PRAGMA table_info(users)')}
if 'fio' not in kol:
    c.execute("ALTER TABLE users ADD COLUMN fio TEXT NOT NULL DEFAULT ''")
    skazat('   колонка users.fio добавлена')
else:
    skazat('   колонка users.fio уже была')
for login, imya in FIO.items():
    n = c.execute('UPDATE users SET fio=? WHERE username=?', (imya, login)).rowcount
    skazat('   %-8s -> %s%s' % (login, imya, '' if n else '   (ЛОГИНА НЕТ!)'))
c.commit()
c.close()

# чтобы новая база (её пришлют) получила колонку сама, тем же приёмом, что у панели
dopisat(CS, '_ensure_users_columns', '''

# ---------------------------------------------------------------- ФИО пользователя
# Добавлено в копии панели: продавцы показываются по имени и фамилии, логин остаётся
# внутренним ключом (на него ссылаются назначения, состояния, комментарии и журнал).
_USERS_COLUMNS = {
    "fio": "TEXT NOT NULL DEFAULT ''",
}


def _ensure_users_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    for name, definition in _USERS_COLUMNS.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
''', 'centro_sales.py: _ensure_users_columns')

nado += 1
t = chitat(CS)
if '_ensure_users_columns(conn)\n' in t.replace('def _ensure_users_columns(conn', ''):
    sdelano += 1
    skazat('   [уже] вызовы _ensure_users_columns')
else:
    novyy, n = re.subn(r'^([ \t]+)_ensure_assignment_columns\(conn\)[ \t]*$',
                       r'\1_ensure_assignment_columns(conn)\n\1_ensure_users_columns(conn)',
                       t, flags=re.M)
    if n:
        pisat(CS, novyy)
        sdelano += 1
        skazat('   [ок] вызов _ensure_users_columns рядом с _ensure_assignment_columns (%d)' % n)
    else:
        skazat('   [НЕТ ЯКОРЯ] вызовы _ensure_assignment_columns')

# ================================================================ 2. фильтр |fio
skazat()
skazat('########## 2. ФИЛЬТР |fio И ПОЧИНКА СТРАНИЦЫ СТАТИСТИКИ')
dopisat(RCS, '_fio_dlya_shablona', '''

# ---------------------------------------------------------------- ФИО в шаблонах
# Фильтр |fio: логин -> «Фамилия Имя». Один на все шаблоны (объект Jinja общий,
# app/web.py), чтобы имя не расходилось между шапкой, списком и статистикой.
# Кэш на 30 секунд: в списке 600 строк, и запрос в базу на каждую строку не нужен.
import time as _time_fio

_FIO_KESH: dict = {"t": 0.0, "karta": {}}


def _fio_dlya_shablona(username) -> str:
    u = str(username or "")
    if not u:
        return u
    seychas = _time_fio.time()
    if seychas - _FIO_KESH["t"] > 30:
        try:
            with sales.connect() as conn:
                _FIO_KESH["karta"] = {
                    str(r[0]): str(r[1]) for r in conn.execute(
                        "SELECT username, fio FROM users WHERE COALESCE(fio,'')<>''")}
        except Exception:  # noqa: BLE001 — нет колонки в чужой базе: показываем логин
            _FIO_KESH["karta"] = {}
        _FIO_KESH["t"] = seychas
    return _FIO_KESH["karta"].get(u) or u


templates.env.filters["fio"] = _fio_dlya_shablona
''', 'routes_centro_sales.py: фильтр |fio')

pravka(RCS,
       '''    stroki = []
    for row in conn.execute(
        "SELECT a.inn, a.assignment_score, a.has_phone''',
       '''    # Продавец не видит скрытые компании и ИНН вне каталога: так фильтрует сама
    # очередь в карточке. Без этого очередь user2 показывалась как 704 строки,
    # а продавец видел 212 — админ и продавец смотрели бы на разные списки.
    skrytye = {str(r[0]) for r in conn.execute(
        "SELECT inn FROM hidden_item WHERE kind='company'")}
    stroki = []
    for row in conn.execute(
        "SELECT a.inn, a.assignment_score, a.has_phone''',
       'статистика: скрытые в очереди продавца, запрос', priznak='skrytye = {str(r[0])')
pravka(RCS,
       '''        d = dict(row)
        d["nazvanie"] = imena.get(str(d["inn"]), "")
        stroki.append(d)''',
       '''        d = dict(row)
        inn = str(d["inn"])
        if inn not in imena or inn in skrytye:
            continue
        d["nazvanie"] = imena.get(inn, "")
        stroki.append(d)''',
       'статистика: скрытые в очереди продавца, фильтр',
       priznak='if inn not in imena or inn in skrytye')
pravka(RCS,
       '''        prodavcy = _stats_po_prodavcam(conn)
''',
       '''        prodavcy = _stats_po_prodavcam(conn)
        # Сколько продавец реально видит и сколько из этого ещё не тронуто — по тем же
        # правилам, что очередь в карточке (без скрытых и без ИНН вне каталога).
        skrytye_st = {str(r[0]) for r in conn.execute(
            "SELECT inn FROM hidden_item WHERE kind='company'")}
        po_loginu = {z["username"]: z for z in prodavcy}
        for z in prodavcy:
            z["vidno"] = 0
            z["vidno_ochered"] = 0
        for r in conn.execute(
            "SELECT a.username, a.inn, s.call_result FROM company_assignment a "
            "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username"
        ):
            z = po_loginu.get(r[0])
            inn = str(r[1])
            if z is None or inn not in imena or inn in skrytye_st:
                continue
            z["vidno"] += 1
            if not r[2] or r[2] == "new":
                z["vidno_ochered"] += 1
''',
       'статистика: «видно продавцу» и «в очереди» по продавцам', priznak='skrytye_st')

# ================================================================ 3. блок на списке
skazat()
skazat('########## 3. БЛОК СТАТИСТИКИ НА «СПИСКЕ КОМПАНИЙ»')
FN = 'def centro_spisok('
pravka_v_funkcii(RP, FN,
                 '''    tolko_teh = p.get("teh") == "1"
''',
                 '''    tolko_teh = p.get("teh") == "1"
    # блок статистики: дата (календарь) и продавец; пустая дата = сегодня по Москве
    stat_data_param = (p.get("stat_data") or "").strip()
    try:
        stat_den = (_dt_stat.date.fromisoformat(stat_data_param)
                    if stat_data_param else None)
    except ValueError:
        stat_den, stat_data_param = None, ""
    stat_user = (p.get("stat_user") or "").strip()
''', 'список: чтение даты и продавца', priznak='stat_data_param')
pravka_v_funkcii(RP, FN,
                 '''    prodavcy = [r[0] for r in conn.execute(
        "select distinct username from company_assignment order by 1")]
    conn.close()''',
                 '''    prodavcy = [r[0] for r in conn.execute(
        "select distinct username from company_assignment order by 1")]
    statblok = _statblok(conn, user, stat_den, stat_user)
    statblok["param_data"] = stat_data_param
    statblok["param_user"] = stat_user if user.get("role") == "admin" else ""
    conn.close()
    # фильтры списка, которые форма блока статистики должна сохранить при смене даты
    sohranit = {k: v for k, v in {
        "sort": sort, "okved": okved, "region": region, "kto": kto, "sost": sost,
        "q": poisk, "est_vyruchka": "1" if tolko_vyr else "",
        "teh": "1" if tolko_teh else ""}.items() if v}''',
                 'список: расчёт блока', priznak='statblok = _statblok(')
pravka_v_funkcii(RP, FN,
                 '''            "teh": "1" if tolko_teh else "", **kw}.items() if v}''',
                 '''            "teh": "1" if tolko_teh else "", "stat_data": stat_data_param,
            "stat_user": stat_user, **kw}.items() if v}''',
                 'список: ссылки страниц и сортировки помнят дату и продавца',
                 priznak='"stat_data": stat_data_param,')
pravka_v_funkcii(RP, FN,
                 '''"ssylka": ssylka}''',
                 '''"ssylka": ssylka, "statblok": statblok, "sohranit": sohranit}''',
                 'список: блок в контекст шаблона', priznak='"statblok": statblok')

dopisat(RP, 'def _statblok(', '''

# ---------------------------------------------------------------- блок статистики
# Добавлено в копии панели по просьбе владельца: на «Списке компаний» календарь, выбор
# продавца и «взял в работу / не понравилась / дубль / в очереди» за дату и за всё время.
import datetime as _dt_stat
import json as _json_stat

_MSK = _dt_stat.timedelta(hours=3)
_STAT_KLYUCHI = ("v_rabote", "ne_ponravilas", "dubl")


def _msk_den(znach):
    """Время из базы (UTC, ISO) -> календарный день по Москве."""
    if not znach:
        return None
    try:
        dt = _dt_stat.datetime.fromisoformat(str(znach).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(_dt_stat.timezone.utc).replace(tzinfo=None)
    return (dt + _MSK).date()


def _statblok(conn, user: dict, den, kto: str) -> dict:
    """Статистика по продавцам за день и за всё время.

    ЗА ДЕНЬ считается по журналу (action='call_saved'), а не по company_state:
    last_contact_at — время ПОСЛЕДНЕГО действия, и если компанию тронули сегодня,
    вчерашняя отметка по ней пропала бы задним числом. Берётся последняя отметка по
    компании за день, поэтому «сперва не понравилась, потом взял в работу» не
    считается дважды. Отметка засчитывается владельцу компании (state_user): если
    админ сохранил звонок за продавца, это работа по очереди продавца.

    В ОЧЕРЕДИ НА КОНЕЦ ДНЯ — назначено к концу дня (assigned_at), видно продавцу (есть
    в каталоге и не скрыто) и ещё не отмечено к концу дня.

    ЗА ВСЁ ВРЕМЯ — нынешний статус. Результаты — по всем компаниям продавца, в том числе
    скрытым позже: сделанная работа остаётся сделанной. Очередь — только видимое, то
    есть ровно то, что продавцу ещё предстоит обзвонить.
    """
    segodnya = (_dt_stat.datetime.utcnow() + _MSK).date()
    den = den or segodnya
    try:
        lyudi = {r["username"]: dict(r) for r in conn.execute(
            "select username, role, is_active, coalesce(fio,'') fio from users")}
    except sqlite3.OperationalError:          # чужая база без колонки fio
        lyudi = {r["username"]: dict(r, fio="") for r in conn.execute(
            "select username, role, is_active from users")}
    skrytye = {str(r[0]) for r in conn.execute(
        "select inn from hidden_item where kind='company'")}
    v_kataloge = {str(r[0]) for r in conn.execute("select inn from centro.company")}

    naznach = {}
    for r in conn.execute("select username, inn, assigned_at from company_assignment"):
        inn = str(r["inn"])
        naznach[(r["username"], inn)] = {
            "kogda": _msk_den(r["assigned_at"]),
            "vidno": inn in v_kataloge and inn not in skrytye,
        }
    sost = {}
    for r in conn.execute(
            "select inn, username, call_result, last_contact_at from company_state"):
        sost[(r["username"], str(r["inn"]))] = (
            str(r["call_result"] or ""), _msk_den(r["last_contact_at"]))

    za_den: dict = {}      # (владелец, ИНН) -> результат последней отметки за день
    pervaya: dict = {}     # (владелец, ИНН) -> день первой отметки
    posledniy_den = None
    for r in conn.execute(
            "select inn, username, payload_json, created_at from activity_log "
            "where action='call_saved' order by created_at, id"):
        try:
            pl = _json_stat.loads(r["payload_json"] or "{}")
        except ValueError:
            pl = {}
        d = _msk_den(r["created_at"])
        if d is None:
            continue
        kl = (pl.get("state_user") or r["username"], str(r["inn"]))
        pervaya.setdefault(kl, d)
        if d == den:
            za_den[kl] = str(pl.get("result") or "")
        if posledniy_den is None or d > posledniy_den:
            posledniy_den = d

    def pusto():
        return {"v_rabote": 0, "ne_ponravilas": 0, "dubl": 0, "ochered": 0, "prochee": 0}

    po: dict = {}

    def stroka(u):
        if u not in po:
            ch = lyudi.get(u, {})
            po[u] = {"username": u, "fio": ch.get("fio") or "",
                     "aktiven": bool(ch.get("is_active", 0)),
                     "rol": ch.get("role") or "", "den": pusto(), "vse": pusto()}
        return po[u]

    for (u, inn), nz in naznach.items():
        z = stroka(u)
        rez = sost.get((u, inn), ("", None))[0]
        if rez in _STAT_KLYUCHI:
            z["vse"][rez] += 1
        elif rez and rez != "new":
            z["vse"]["prochee"] += 1
        elif nz["vidno"]:
            z["vse"]["ochered"] += 1
        if nz["vidno"] and (nz["kogda"] is None or nz["kogda"] <= den):
            kl = (u, inn)
            if kl in pervaya:
                otmecheno = pervaya[kl] <= den
            else:
                rez_s, d_s = sost.get(kl, ("", None))
                otmecheno = bool(rez_s) and rez_s != "new" and d_s is not None and d_s <= den
            if not otmecheno:
                z["den"]["ochered"] += 1
    for (u, inn), rez in za_den.items():
        z = stroka(u)
        if rez in _STAT_KLYUCHI:
            z["den"][rez] += 1
        elif rez:
            z["den"]["prochee"] += 1
    for u, ch in lyudi.items():
        if ch.get("role") == "sales" and ch.get("is_active"):
            stroka(u)                      # активный продавец виден и с нулями

    vse_stroki = [z for z in po.values()
                  if z["aktiven"] or any(z["den"].values()) or any(z["vse"].values())]
    vse_stroki.sort(key=lambda z: (not z["aktiven"], (z["fio"] or z["username"]).lower()))
    admin = user.get("role") == "admin"
    if not admin:
        kto = user["username"]             # продавец видит только свою строку
    stroki = [z for z in vse_stroki if z["username"] == kto] if kto else vse_stroki
    itogo = {"den": pusto(), "vse": pusto()}
    for z in stroki:
        for chast in ("den", "vse"):
            for k, v in z[chast].items():
                itogo[chast][k] += v
    return {
        "admin": admin, "kto": kto if admin else "",
        "den_iso": den.isoformat(), "den_ru": den.strftime("%d.%m.%Y"),
        "segodnya_iso": segodnya.isoformat(), "eto_segodnya": den == segodnya,
        "posledniy_iso": posledniy_den.isoformat() if posledniy_den else "",
        "posledniy_ru": posledniy_den.strftime("%d.%m.%Y") if posledniy_den else "",
        "stroki": stroki, "itog": itogo, "vybor": vse_stroki,
    }
''', 'routes_park.py: расчёт блока _statblok')

# ---- шаблон списка
SP = os.path.join(T, 'spisok.html')
pravka(SP, '''  </style>''', '''    .sp-shapka{display:flex;gap:26px;align-items:flex-start;flex-wrap:wrap}
    .sp-stat{flex:1 1 560px;min-width:0;display:grid;gap:8px}
    .sp-stat-forma{display:flex;gap:12px;align-items:end;flex-wrap:wrap;font-size:12px;color:var(--muted)}
    .sp-stat-forma label{display:grid;gap:3px}
    .sp-stat-forma input,.sp-stat-forma select{padding:5px 8px;border:1px solid var(--line);
      border-radius:8px;background:var(--card);color:var(--navy)}
    .sp-stat-forma a{color:var(--blue)}
    table.sp-stat-tab{border-collapse:collapse;width:100%;font-size:12px}
    table.sp-stat-tab th,table.sp-stat-tab td{padding:4px 8px;border-bottom:1px solid var(--line);
      text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
    table.sp-stat-tab th{color:var(--muted);font-weight:600}
    table.sp-stat-tab th:first-child,table.sp-stat-tab td:first-child{text-align:left}
    table.sp-stat-tab th.gr{text-align:center}
    table.sp-stat-tab .razd{border-left:1px solid var(--line)}
    table.sp-stat-tab tr.itog td{font-weight:700}
  </style>''', 'список: стили блока', priznak='.sp-shapka')

pravka(SP, '''  <section class="card">
    <div class="sp-svod">''', '''  <section class="card sp-shapka">
    <div class="sp-svod">''', 'список: карточка счётчиков становится строкой',
       priznak='card sp-shapka')

BLOK = '''      {% if svod.summa_vyr %}
      <div><b>{{ money_ru(svod.summa_vyr) }}</b><span>суммарная выручка</span></div>
      {% endif %}
    </div>
    {# Блок статистики. Владелец: «календарь, выбор юзера и общая статистика по всем
       юзерам — сколько взял в работу, не понравилось, в очереди, дублей — на дату и за
       всё время, общую и отдельно по всем юзерам». #}
    {% macro chetyre(d) %}<td class="razd">{{ d.v_rabote }}</td><td>{{ d.ne_ponravilas }}</td><td>{{ d.dubl }}</td><td>{{ d.ochered }}</td>{% endmacro %}
    <div class="sp-stat">
      <form class="sp-stat-forma" method="get" action="{{ bp }}/centro/spisok">
        {% for k, v in sohranit.items() %}<input type="hidden" name="{{ k }}" value="{{ v }}">{% endfor %}
        <label>Дата
          <input type="date" name="stat_data" value="{{ statblok.den_iso }}" max="{{ statblok.segodnya_iso }}" onchange="this.form.submit()">
        </label>
        {% if statblok.admin %}
        <label>Продавец
          <select name="stat_user" onchange="this.form.submit()">
            <option value="">все продавцы</option>
            {% for u in statblok.vybor %}<option value="{{ u.username }}" {% if u.username == statblok.kto %}selected{% endif %}>{{ u.fio or u.username }}{% if not u.aktiven %} (отключён){% endif %}</option>{% endfor %}
          </select>
        </label>
        {% endif %}
        <button class="action-button" type="submit">Показать</button>
        <span>
          {% if not statblok.eto_segodnya %}<a href="{{ ssylka(stat_data='') }}">сегодня</a>{% endif %}
          {% if statblok.posledniy_iso and statblok.posledniy_iso != statblok.den_iso %}{% if not statblok.eto_segodnya %} · {% endif %}последний день с отметками: <a href="{{ ssylka(stat_data=statblok.posledniy_iso) }}">{{ statblok.posledniy_ru }}</a>{% endif %}
        </span>
      </form>
      <div style="overflow-x:auto">
      <table class="sp-stat-tab">
        <thead>
          <tr><th rowspan="2">Продавец</th>
            <th class="gr razd" colspan="4">за {{ statblok.den_ru }}{% if statblok.eto_segodnya %} (сегодня){% endif %}</th>
            <th class="gr razd" colspan="4">за всё время</th></tr>
          <tr><th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди</th>
            <th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th>в очереди</th></tr>
        </thead>
        <tbody>
          {% if statblok.stroki|length > 1 %}
          <tr class="itog"><td>Все продавцы</td>{{ chetyre(statblok.itog.den) }}{{ chetyre(statblok.itog.vse) }}</tr>
          {% endif %}
          {% for z in statblok.stroki %}
          <tr><td>{{ z.fio or z.username }}{% if not z.aktiven %} <span class="tiho">(отключён)</span>{% endif %}</td>{{ chetyre(z.den) }}{{ chetyre(z.vse) }}</tr>
          {% else %}
          <tr><td colspan="9" class="tiho">продавцов нет</td></tr>
          {% endfor %}
        </tbody>
      </table>
      </div>
      <span class="tiho">«Взял в работу» — только этот статус; «в работе» слева — все обработанные.
        За день — последняя отметка по компании за этот день по Москве; очередь — на конец дня.
        За всё время — нынешний статус; в очереди только то, что продавец видит (без скрытых).{% if statblok.itog.vse.prochee %}
        Ещё {{ statblok.itog.vse.prochee }} — со старым статусом вне этих трёх.{% endif %}</span>
    </div>
  </section>'''
pravka(SP, '''      {% if svod.summa_vyr %}
      <div><b>{{ money_ru(svod.summa_vyr) }}</b><span>суммарная выручка</span></div>
      {% endif %}
    </div>
  </section>''', BLOK, 'список: блок статистики в пустом месте полосы счётчиков',
       priznak='class="sp-stat"')

pravka(SP, '''    <input type="hidden" name="sort" value="{{ sort }}">''',
       '''    <input type="hidden" name="sort" value="{{ sort }}">
    {% if statblok.param_data %}<input type="hidden" name="stat_data" value="{{ statblok.param_data }}">{% endif %}
    {% if statblok.param_user %}<input type="hidden" name="stat_user" value="{{ statblok.param_user }}">{% endif %}''',
       'список: фильтры не сбрасывают дату блока', priznak='name="stat_data" value="{{ statblok.param_data')

# ================================================================ 4. ФИО во всех шаблонах
skazat()
skazat('########## 4. ФИО ВО ВСЕХ МЕСТАХ ВЫВОДА')
for f in ('centro.html', 'centro_admin.html', 'centro_stats.html', 'park.html',
          'park_card.html', 'park_net.html', 'spisok.html'):
    pravka(os.path.join(T, f), '{{ user.username }}', '{{ user.username|fio }}',
           '%s: шапка' % f, vse=True, priznak='{{ user.username|fio }}')
pravka(os.path.join(T, 'centro.html'), '<b>{{ item.username }}</b>',
       '<b>{{ item.username|fio }}</b>', 'centro.html: автор комментария')
pravka(os.path.join(T, 'centro_admin.html'), '<td>{{ row.username }}</td>',
       '<td>{{ row.username|fio }}</td>', 'centro_admin.html: таблица распределения')
pravka(os.path.join(T, 'centro_admin.html'),
       '<option value="{{ value }}">{{ value }}</option>',
       '<option value="{{ value }}">{{ value|fio }}</option>',
       'centro_admin.html: выбор при переназначении')
ST = os.path.join(T, 'centro_stats.html')
pravka(ST, '">{{ p.username }}</a>', '">{{ p.username|fio }}</a>', 'статистика: продавец')
pravka(ST, '<tr><td>{{ v.username }}</td><td>{{ v.inn }}</td></tr>',
       '<tr><td>{{ v.username|fio }}</td><td>{{ v.inn }}</td></tr>',
       'статистика: список вне каталога')
pravka(ST, 'Очередь продавца {{ vybrannyy }} —', 'Очередь продавца {{ vybrannyy|fio }} —',
       'статистика: заголовок очереди')
pravka(ST, '<th>Осталось</th>', '<th>Видно продавцу</th><th>В очереди</th>',
       'статистика: колонки видимости, шапка')
pravka(ST, '<td>{{ p.ostalos }}</td>', '<td>{{ p.vidno }}</td><td>{{ p.vidno_ochered }}</td>',
       'статистика: колонки видимости, значения')
pravka(ST, '<tr><td colspan="9" style="font-size:12px;color:#5a6472">',
       '<tr><td colspan="10" style="font-size:12px;color:#5a6472">',
       'статистика: ширина строки раскладки')
pravka(ST, '<tr><td colspan="9">Пользователей нет.</td></tr>',
       '<tr><td colspan="10">Пользователей нет.</td></tr>', 'статистика: ширина пустой строки')
pravka(ST, 'сроку, внутри — по убыванию балла. Красным отмечен просроченный следующий контакт.</p>',
       'сроку, внутри — по убыванию балла. Красным отмечен просроченный следующий контакт.\n'
       '    Скрытые компании и ИНН вне каталога не показываются: продавец их тоже не видит.</p>',
       'статистика: пометка про скрытые', priznak='продавец их тоже не видит')
SPS = os.path.join(T, 'spisok.html')
pravka(SPS, '{% if u == kto %}selected{% endif %}>{{ u }}</option>',
       '{% if u == kto %}selected{% endif %}>{{ u|fio }}</option>', 'список: фильтр «Продавец»')
pravka(SPS, 'в обзвоне у {{ s.username }}', 'в обзвоне у {{ s.username|fio }}',
       'список: «в обзвоне у»')
pravka(SPS, "<td>{{ s.username or '' }}</td>",
       "<td>{{ s.username|fio if s.username else '' }}</td>", 'список: колонка продавца')

print()
print('===== ИТОГ =====')
print('правок внесено: %d из %d' % (sdelano, nado))
print('бэкап: %s (%d файлов)' % (BEKAP, len(zabekaplen)))
for s in itog:
    if '[ок]' not in s and '[уже]' not in s:
        print(s)
