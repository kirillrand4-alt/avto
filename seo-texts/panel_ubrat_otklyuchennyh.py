# -*- coding: utf-8 -*-
"""Убрать отключённых пользователей из всех сводок и выборов панели Мейера.

Владелец: «юзер отключен убери теперь». Речь о строках «user1 (отключён)» и т.п.

ИЗ БАЗЫ НЕ УДАЛЯЮ. На user1..user3 висят 1 638 назначений, 94 состояния, комментарии и
журнал; удаление необратимо, а скрытие — нет. Убираю из показа:
  1. блок статистики на «Списке» — строки, итог, выбор продавца, «последний день»;
  2. таблица продавцов на /centro/stats;
  3. таблица на «Распределении» — заодно строится от действующих продавцов, а не от
     назначений: иначе новые четыре продавца там не видны вовсе (у них нет назначений);
  4. фильтр «Продавец» на «Списке» — действующие продавцы, а не владельцы назначений.

НЕ ТРОГАЮ то, что относится к компании, а не к продавцу: «в обзвоне у …» и колонку
продавца в строках списка. Это факт назначения — все компании снимка назначены старой
команде, и подменять его в показе значило бы врать о данных.
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
PUT = '/obzvon-meyer'
PORT = 8016

if '--proverka' in sys.argv:
    # =========================================================== проверка под venv
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    for n in ('httpx', 'httpcore', 'app'):
        logging.getLogger(n).setLevel(logging.CRITICAL)
    os.chdir(KOREN)
    sys.path.insert(0, KOREN)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(KOREN, '.env'), override=True)
    except Exception:  # noqa: BLE001
        pass
    os.environ['OBZVON_ROOT_PATH'] = PUT
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    IMENA = ['Беляев Максим', 'Волков Роман', 'Ерохин Александр', 'Пяткова Ксения']
    STARYE = ['user1', 'user2', 'user3']
    plohih = 0

    def proverit(uslovie, tekst):
        global plohih
        if not uslovie:
            plohih += 1
        print('   %s %s' % ('ОК ' if uslovie else 'ПЛОХО', tekst))

    with TestClient(vnutr) as k:
        st = {s: k.get(PUT + s) for s in (
            '/centro/spisok', '/centro/spisok?stat_data=2026-08-11',
            '/centro/stats', '/centro/admin')}
    for s, o in st.items():
        proverit(o.status_code == 200, '%-38s -> %s' % (s, o.status_code))

    def blok(html):
        m = re.search(r'<table class="sp-stat-tab">.*?<tbody>(.*?)</tbody>', html, re.S)
        if not m:
            return []
        rez = []
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', m.group(1), re.S):
            yach = [re.sub(r'<[^>]+>', '', x).strip()
                    for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
            if len(yach) == 9:
                rez.append(yach)
        return rez

    sp = st['/centro/spisok'].text
    b = blok(sp)
    imena_bloka = [r[0] for r in b if r[0] != 'Все продавцы']
    proverit(imena_bloka == IMENA, 'блок на списке: строки %s' % imena_bloka)
    proverit('отключён' not in sp, 'на списке нет слова «отключён»')
    m = re.search(r'<select name="stat_user".*?</select>', sp, re.S)
    vybor = re.findall(r'<option value="([^"]*)"', m.group(0)) if m else []
    proverit(vybor == ['', 'meyer3', 'meyer4', 'meyer2', 'meyer1'],
             'выбор продавца в блоке: %s' % vybor)
    m = re.search(r'<select name="kto".*?</select>', sp, re.S)
    kto = re.findall(r'>([^<]+)</option>', m.group(0)) if m else []
    proverit(not any(x in kto for x in STARYE) and all(i in kto for i in IMENA),
             'фильтр «Продавец» на списке: %s' % kto)
    proverit('последний день с отметками' not in sp,
             'нет ссылки «последний день» на день, где у видимых продавцов нули')
    itog = [r for r in b if r[0] == 'Все продавцы']
    print('   итог блока: %s' % (itog[0][1:] if itog else '—'))
    n_spisok = len(re.findall(r'в обзвоне у user\d', sp))
    print('   строк списка «в обзвоне у userN» (факт назначения, оставлены): %d' % n_spisok)

    sts = st['/centro/stats'].text
    m = re.search(r'<h2>По продавцам</h2>.*?</table>', sts, re.S)
    tab = m.group(0) if m else ''
    proverit(all(i in tab for i in IMENA) and not any('>%s<' % x in tab for x in STARYE)
             and 'отключён' not in tab, 'статистика: в таблице продавцов только четверо')
    adm = st['/centro/admin'].text
    m = re.search(r'<tbody>(.*?)</tbody>', adm, re.S)
    tab = m.group(1) if m else ''
    proverit(all(i in tab for i in IMENA) and not any(x in tab for x in STARYE),
             'распределение: таблица — четверо действующих, старых нет')

    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# =============================================================== правки (системный питон)
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('ubrat-otkl-%Y%m%d-%H%M%S'))
nado = sdelano = 0
log_pravok = []


def pisat(put, t):
    cel = os.path.join(BEKAP, os.path.relpath(put, KOREN))
    if not os.path.exists(cel):
        os.makedirs(os.path.dirname(cel), exist_ok=True)
        shutil.copy2(put, cel)
    io.open(put, 'w', encoding='utf-8').write(t)


def pravka(put, staro, novo, imya, funkciya=None, priznak=None):
    global nado, sdelano
    nado += 1
    t = io.open(put, encoding='utf-8').read()
    i, j = 0, len(t)
    if funkciya:
        i = t.find(funkciya)
        if i < 0:
            log_pravok.append('[НЕТ ФУНКЦИИ] ' + imya)
            return
        j = t.find('\n@router.', i + len(funkciya))
        j = len(t) if j < 0 else j
    kusok = t[i:j]
    if priznak and priznak in kusok:
        sdelano += 1
        log_pravok.append('[уже] ' + imya)
        return
    n = kusok.count(staro)
    if n != 1:
        log_pravok.append('[ЯКОРЬ: %d вхождений] %s — не правлю' % (n, imya))
        return
    pisat(put, t[:i] + kusok.replace(staro, novo, 1) + t[j:])
    sdelano += 1
    log_pravok.append('[ок] ' + imya)


RP = os.path.join(APP, 'api', 'routes_park.py')
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')

# ---- 1. блок на списке
pravka(RP, '''    vse_stroki = [z for z in po.values()
                  if z["aktiven"] or any(z["den"].values()) or any(z["vse"].values())]''',
       '''    # Отключённые не показываются вовсе (владелец: «юзер отключен убери»). Их данные
    # в базе целы, но в строках, в итоге и в выборе их нет — итог равен сумме строк.
    vse_stroki = [z for z in po.values() if z["aktiven"]]''',
       'список: блок без отключённых', priznak='if z["aktiven"]]')
pravka(RP, '''        if posledniy_den is None or d > posledniy_den:
            posledniy_den = d''',
       '''        # «последний день» — только по действующим: иначе ссылка вела бы на день,
        # где в таблице одни нули
        if lyudi.get(kl[0], {}).get("is_active") and (
                posledniy_den is None or d > posledniy_den):
            posledniy_den = d''',
       'список: «последний день» по действующим', priznak='lyudi.get(kl[0], {}).get("is_active")')

# ---- 4. фильтр «Продавец» на списке
pravka(RP, '''    prodavcy = [r[0] for r in conn.execute(
        "select distinct username from company_assignment order by 1")]''',
       '''    # действующие продавцы, а не владельцы назначений: иначе в выборе одни отключённые
    prodavcy = [r[0] for r in conn.execute(
        "select username from users where is_active=1 and role='sales' order by 1")]''',
       'список: фильтр «Продавец» — действующие', funkciya='def centro_spisok(',
       priznak="where is_active=1 and role='sales'")

# ---- 2. таблица продавцов на статистике
pravka(RCS, '"SELECT username, role, is_active FROM users ORDER BY username"',
       '"SELECT username, role, is_active FROM users WHERE is_active=1 ORDER BY username"',
       'статистика: продавцы только действующие', priznak='FROM users WHERE is_active=1 ORDER BY username')
pravka(RCS, '''        z = stroki.setdefault(row["username"], {
            "username": row["username"], "role": "?", "aktiven": False,
            "naznacheno": 0, "obrabotano": 0, "ball_summa": 0.0, "ball_sredniy": 0.0,
            "prosrocheno": 0, "po_rezultatu": {}, "poslednyaya_aktivnost": ""})''',
       '''        z = stroki.get(row["username"])
        if z is None:
            continue    # владелец назначения отключён или его нет в users — не показываем''',
       'статистика: назначения отключённых не добавляют строк', priznak='не показываем')

# ---- 3. «Распределение»: от действующих продавцов
pravka(RCS, '''                "SELECT a.username, COUNT(*) companies, "
                "SUM(a.assignment_score) score, AVG(a.assignment_score) average, "
                "SUM(CASE WHEN COALESCE(s.call_result,'new') <> 'new' THEN 1 ELSE 0 END) processed "
                "FROM company_assignment a "
                "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username "
                "GROUP BY a.username ORDER BY a.username"''',
       '''                # от действующих продавцов, а не от назначений: отключённые не
                # показываются, а новый продавец без назначений виден с нулями
                "SELECT u.username, COUNT(a.inn) companies, "
                "COALESCE(SUM(a.assignment_score),0) score, "
                "COALESCE(AVG(a.assignment_score),0) average, "
                "SUM(CASE WHEN a.inn IS NOT NULL AND COALESCE(s.call_result,'new') <> 'new' "
                "THEN 1 ELSE 0 END) processed "
                "FROM users u "
                "LEFT JOIN company_assignment a ON a.username=u.username "
                "LEFT JOIN company_state s ON s.inn=a.inn AND s.username=a.username "
                "WHERE u.is_active=1 AND u.role='sales' "
                "GROUP BY u.username ORDER BY u.username"''',
       'распределение: таблица от действующих продавцов', funkciya='def admin_page(',
       priznak='FROM users u ')

print('правок внесено: %d из %d' % (sdelano, nado))
for s in log_pravok:
    print('   ' + s)
print('бэкап: %s' % BEKAP)

# ---- перезапуск
r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in r.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
log = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
log.write('\n===== перезапуск: отключённые убраны из сводок %s =====\n'
          % time.strftime('%Y-%m-%d %H:%M:%S'))
log.flush()
subprocess.Popen(
    [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1', '--port', str(PORT)],
    cwd=KOREN, stdout=log, stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200, close_fds=True,
    env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=PUT,
             ENV_FILE=os.path.join(KOREN, '.env')))
time.sleep(8)
r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
slushaet = any((':%d ' % PORT) in l and 'LISTENING' in l.upper()
               for l in r.stdout.decode('cp866', 'replace').splitlines())
print('порт %d после перезапуска: %s' % (PORT, 'слушает' if slushaet else 'НЕ СЛУШАЕТ'))

# ---- проверка под venv
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=1500, env=dict(os.environ, PYTHONIOENCODING='utf-8',
                                          OBZVON_ROOT_PATH=PUT))
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
