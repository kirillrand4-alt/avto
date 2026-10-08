# -*- coding: utf-8 -*-
"""Последний комментарий — в списке очереди, под статусом звонка.

Владелец, глядя на вкладку «Компания не понравилась»: «сюда выводится комментарий,
который был бы оставлен?» — нет: под статусом стояла только дата, комментарий был виден
лишь внутри карточки. Теперь под статусом — последний комментарий по компании.

Правило видимости то же, что в карточке: админ видит все комментарии, продавец — свои.
Комментарии берутся отдельным запросом по ИНН строк текущей страницы, а не из списка
«последних 1000», который маршрут грузит для карточки: на большой базе старый комментарий
к компании мог в эту тысячу не попасть, и в списке его бы молча не было.
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
PUT = '/obzvon-meyer'
PORT = 8016

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    plohih = 0

    def proverit(uslovie, tekst):
        global plohih
        if not uslovie:
            plohih += 1
        print('   %s %s' % ('ОК ' if uslovie else 'ПЛОХО', tekst))

    c = sqlite3.connect(os.path.join(KOREN, 'data', 'centro_sales.db'))
    c.execute("attach database ? as centro", (os.path.join(KOREN, 'data', 'centrifugal.db'),))
    VIDNO = ("s.inn in (select inn from centro.company) and "
             "s.inn not in (select inn from hidden_item where kind='company')")
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    with TestClient(vnutr) as k:
        for kod in ('ne_ponravilas', 'v_rabote', 'dubl'):
            vsego = c.execute("select count(*) from company_state s where call_result=? and "
                              + VIDNO, (kod,)).fetchone()[0]
            s_komm = c.execute(
                "select count(*) from company_state s where call_result=? and " + VIDNO +
                " and exists (select 1 from company_comment k where k.inn=s.inn)",
                (kod,)).fetchone()[0]
            t = k.get(PUT + '/centro?size=100&call_status=' + kod).text
            na_stranice = len(re.findall(r'<div class="och-komm"', t))
            proverit(na_stranice == s_komm,
                     'вкладка %-14s компаний %3d, с комментарием по базе %3d, показано в списке %3d'
                     % (kod, vsego, s_komm, na_stranice))
            if kod == 'ne_ponravilas':
                for m in list(re.finditer(
                        r'<a class="nazv"[^>]*>([^<]+)</a>.*?<div class="och-komm" title="([^"]*)"',
                        t, re.S))[:4]:
                    print('      %-44s «%s»' % (m.group(1)[:44], m.group(2)[:90]))
        # вся очередь: комментарии и у новых строк не ломают страницу
        o = k.get(PUT + '/centro')
        proverit(o.status_code == 200, 'вся очередь -> %s' % o.status_code)

    # продавец видит только свои комментарии: имитация продавца user1 (его комментарии)
    # и чужого продавца на тех же компаниях — у чужого комментариев быть не должно
    avtory = dict(c.execute("select username, count(*) from company_comment group by 1").fetchall())
    print('      авторы комментариев в базе: %s' % avtory)
    for login in ('user1', 'meyer1'):
        vnutr.dependency_overrides[rcs.current_user] = (
            lambda l=login: {'id': 0, 'username': l, 'role': 'sales', 'is_active': 1})
        with TestClient(vnutr) as k:
            t = k.get(PUT + '/centro?size=100&call_status=ne_ponravilas').text
        n = len(re.findall(r'<div class="och-komm"', t))
        chuzhie = len(re.findall(r'<div class="och-komm"[^>]*>[^<]*<span class="tiho"> — ', t))
        print('      продавец %-7s видит комментариев: %d (подписей автора: %d — продавцу не нужны)'
              % (login, n, chuzhie))
        if login == 'meyer1':
            proverit(n == 0, 'чужие комментарии продавцу не показываются')
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ======================================================================= ПРАВКИ
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('komment-spisok-%Y%m%d-%H%M%S'))
nado = sdelano = 0
log = []


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
        j = t.find('\n@router.', i + len(funkciya))
        j = len(t) if j < 0 else j
    kusok = t[i:j]
    if priznak and priznak in kusok:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    n = kusok.count(staro)
    if n != 1:
        log.append('[ЯКОРЬ: %d] %s — не правлю' % (n, imya))
        return
    pisat(put, t[:i] + kusok.replace(staro, novo, 1) + t[j:])
    sdelano += 1
    log.append('[ок] ' + imya)


RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
pravka(RCS, '''    hidden = sales.hidden_for(chosen["inn"]) if chosen else {"fact": {}, "phone": {}}
''', '''    # Последний комментарий по каждой компании страницы — в списке он стоит под
    # статусом. Владелец: «если компания не понравилась, сюда выводится комментарий?»
    # — раньше нет, он был виден только в карточке. Видимость как в карточке: админ —
    # все, продавец — свои. Отдельный запрос по ИНН страницы, а не «последние 1000»:
    # на большой базе старый комментарий в эту тысячу не попал бы и пропал молча.
    kommentarii: dict = {}
    if rezhim == "spisok":
        inn_str = [str(c["inn"]) for c in visible[(page - 1) * size : page * size]]
        if inn_str:
            with sales.connect() as conn:
                for r in conn.execute(
                    "SELECT inn, username, body, created_at FROM company_comment "
                    "WHERE inn IN (%s) ORDER BY created_at DESC, id DESC"
                    % ",".join("?" * len(inn_str)),
                    inn_str,
                ):
                    if user["role"] == "admin" or r["username"] == user["username"]:
                        kommentarii.setdefault(str(r["inn"]), dict(r))
    hidden = sales.hidden_for(chosen["inn"]) if chosen else {"fact": {}, "phone": {}}
''', 'маршрут: последний комментарий по строкам списка', funkciya='def centro(',
       priznak='kommentarii: dict = {}')
pravka(RCS, '''            "spisok_ssylka": spisok_ssylka,
''', '''            "spisok_ssylka": spisok_ssylka,
            "kommentarii": kommentarii,
''', 'маршрут: комментарии в контекст', funkciya='def centro(', priznak='"kommentarii": kommentarii')

SP = os.path.join(APP, 'templates', '_ochered_spisok.html')
pravka(SP, '''{% if c.next_contact_at %}<br><span class="tiho">перезвонить {{ c.next_contact_at[:16]|replace('T', ' ') }}</span>{% endif %}</td>''',
       '''{% if c.next_contact_at %}<br><span class="tiho">перезвонить {{ c.next_contact_at[:16]|replace('T', ' ') }}</span>{% endif %}
          {% set km = kommentarii.get(c.inn|string) if kommentarii else none %}
          {% if km %}<div class="och-komm" title="{{ km.body }}">{{ km.body|truncate(120, True, '…') }}{% if user.role == 'admin' %}<span class="tiho"> — {{ km.username|fio }}{% if (km.created_at or '')[:10] != (c.last_contact_at or '')[:10] %}, {{ (km.created_at or '')[:10] }}{% endif %}</span>{% endif %}</div>{% endif %}</td>''',
       'список: комментарий под статусом', priznak='och-komm')
pravka(SP, '''.och-stranicy{display:flex;''', '''.och-komm{margin-top:5px;max-width:300px;font-size:12px;line-height:1.35;color:var(--navy);
  white-space:normal;background:#f6f7fb;border-left:3px solid #c7cbe8;padding:4px 7px;border-radius:4px}
.och-stranicy{display:flex;''', 'список: стиль комментария', priznak='.och-komm{')

print('правок внесено: %d из %d' % (sdelano, nado))
for s in log:
    print('   ' + s)

r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in r.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: комментарий в списке %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
time.sleep(9)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=1500, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
