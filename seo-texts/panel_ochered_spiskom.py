# -*- coding: utf-8 -*-
"""Вкладки очереди открываются СПИСКОМ, карточка — по клику на компанию.

Владелец: «вся очередь списком с основными данными в списке, когда проваливаешься в
компанию — тогда открывается карточка».

БЫЛО. /centro без inn подставлял первую компанию страницы и сразу рисовал её полную
карточку; список из 20 компаний жил в самом низу карточки, под всеми блоками.

СТАЛО.
  /centro (и вкладки ?call_status=…) без inn — список: те же фильтры, тот же порядок
     (_queue_rank), 20/50/100 на странице, строка кликается целиком.
  /centro?inn=… — карточка, как была, плюс «← к списку» (на ту страницу списка, где
     эта компания) и «К списку» внизу.
  «Сохранить и перейти дальше» — ведёт на СЛЕДУЮЩУЮ компанию очереди. Раньше «дальше»
     значило «первая компания страницы», и после сохранения карточка открывалась сама;
     в режиме списка без этой правки продавец после каждого звонка падал бы в список.
     Последняя в очереди — возврат в список.
  «← Назад» / «Пропустить →» — соседние компании очереди, а не страницы по 20.

Обёртка списка — НЕ main.page-wrap: на ней висит скрипт «⚙ Вид» для блоков карточки,
он сам выходит, если такой обёртки нет. В списке настраивать нечего.

Каждый файл перед правкой копируется в C:\\centro2\\_bekap\\<время>\\.
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
PUT = '/obzvon-meyer'
PORT = 8016

if '--proverka' in sys.argv:
    # ================================================================ ПРОВЕРКА
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401 — окружение копии, как у сервера
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

    def stroki(html):
        m = re.search(r'<table class="och-tab">.*?<tbody>(.*?)</tbody>', html, re.S)
        return re.findall(r'<tr data-href="[^"]*inn=(\d+)', m.group(1)) if m else None

    def kak(login, rol):
        vnutr.dependency_overrides[rcs.current_user] = (
            lambda: {'id': 0, 'username': login, 'role': rol, 'is_active': 1})

    kak('meyer_admin', 'admin')
    with TestClient(vnutr) as k:
        print('########## СПИСОК')
        o = k.get(PUT + '/centro')
        s = stroki(o.text)
        proverit(o.status_code == 200 and s is not None, '/centro -> %s, режим списка' % o.status_code)
        proverit('company-hero' not in o.text, 'в списке нет карточки компании')
        proverit('class="page-wrap"' not in o.text, 'обёртки карточки нет — «⚙ Вид» не появится')
        m = re.search(r'Компании (\d+)–(\d+) из (\d+)', o.text)
        print('      %s, строк на странице %d' % (m.group(0) if m else '?', len(s or [])))
        proverit(len(s or []) == 20, '20 строк по умолчанию')
        perv = s[0] if s else ''
        vtor = s[1] if s and len(s) > 1 else ''
        dvadc1 = None
        for kod, ozh in (('v_rabote', 53), ('ne_ponravilas', 12), ('dubl', 21)):
            t = k.get(PUT + '/centro?call_status=' + kod).text
            m = re.search(r'из (\d+)', t)
            proverit(stroki(t) is not None and m and int(m.group(1)) == ozh,
                     'вкладка %-14s списком, всего %s (ждём %s)' % (kod, m.group(1) if m else '?', ozh))
        t = k.get(PUT + '/centro?size=50').text
        proverit(len(stroki(t) or []) == 50, 'по 50 на странице: %d строк' % len(stroki(t) or []))
        t2 = k.get(PUT + '/centro?page=2').text
        s2 = stroki(t2) or []
        dvadc1 = s2[0] if s2 else ''
        proverit(s2 and s2[0] not in s, 'вторая страница — другие компании')

        print()
        print('########## КАРТОЧКА ИЗ СПИСКА')
        o = k.get(PUT + '/centro?inn=' + perv)
        proverit(o.status_code == 200 and 'company-hero' in o.text, 'клик по первой -> карточка')
        m = re.search(r'<a href="([^"]*)">← к списку</a>', o.text)
        proverit(m is not None, '«← к списку» есть: %s' % (m.group(1) if m else None))
        proverit('Компания 1 из' in o.text, 'показано место в очереди: «Компания 1 из …»')
        m = re.search(r'class="work-form">\s*<input[^>]*>\s*<input type="hidden" name="return_query" value="([^"]*)"', o.text)
        rq = (m.group(1) if m else '').replace('&amp;', '&')
        proverit(('inn=' + vtor) in rq, '«Сохранить и перейти дальше» ведёт на следующую (%s): %r' % (vtor, rq))
        m = re.search(r'href="[^"]*inn=(\d+)[^"]*">Пропустить →', o.text)
        proverit(m and m.group(1) == vtor, '«Пропустить →» -> следующая компания %s' % vtor)
        proverit('← Предыдущая' not in o.text, 'у первой нет «← Предыдущая»')
        o = k.get(PUT + '/centro?inn=' + dvadc1)
        m = re.search(r'<a href="([^"]*)">← к списку</a>', o.text)
        ss = (m.group(1) if m else '').replace('&amp;', '&')
        proverit('page=2' in ss, 'из 21-й «к списку» ведёт на 2-ю страницу: %s' % ss)
        proverit('Компания 21 из' in o.text, 'место в очереди 21')
        proverit('← Предыдущая' in o.text, 'у 21-й есть «← Предыдущая»')
        o = k.get(PUT + '/centro?inn=' + perv + '&call_status=v_rabote')
        print('      карточка не из этой вкладки -> %s (ждём 404, как и раньше)' % o.status_code)
        # вкладка «взял в работу»: карточка и «дальше» в пределах вкладки
        tv = k.get(PUT + '/centro?call_status=v_rabote').text
        sv = stroki(tv) or []
        o = k.get(PUT + '/centro?inn=%s&call_status=v_rabote' % sv[0])
        m = re.search(r'class="work-form">\s*<input[^>]*>\s*<input type="hidden" name="return_query" value="([^"]*)"', o.text)
        rq = (m.group(1) if m else '').replace('&amp;', '&')
        proverit('call_status=v_rabote' in rq and ('inn=' + sv[1]) in rq,
                 'во вкладке «Взял в работу» «дальше» остаётся во вкладке: %r' % rq)

    print()
    print('########## ПРОДАВЕЦ БЕЗ НАЗНАЧЕНИЙ')
    kak('meyer1', 'sales')
    with TestClient(vnutr) as k:
        o = k.get(PUT + '/centro')
        proverit(o.status_code == 200 and 'Компании не найдены' in o.text,
                 'список пуст, страница не падает: %s' % o.status_code)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ======================================================================= ПРАВКИ
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('ochered-spiskom-%Y%m%d-%H%M%S'))
nado = sdelano = 0
log = []


def pisat(put, t):
    if os.path.exists(put):
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
            log.append('[НЕТ ФУНКЦИИ] ' + imya)
            return
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


SPISOK = r'''{# Режим СПИСКА очереди. Владелец: «вся очередь списком с основными данными в списке,
   когда проваливаешься в компанию — тогда открывается карточка». Те же фильтры и
   вкладки, что у карточки, тот же порядок (_queue_rank), только строками.
   Обёртка НЕ main.page-wrap намеренно: на ней висит скрипт «⚙ Вид» для блоков
   карточки, и он сам выходит, если такой обёртки нет. #}
{% macro dengi(v) -%}
  {%- if v -%}{%- set v = v|float -%}
    {%- if v >= 1000000000 -%}{{ ('%.1f'|format(v / 1000000000)).replace('.', ',') }} млрд ₽
    {%- elif v >= 1000000 -%}{{ ('%.1f'|format(v / 1000000)).replace('.', ',') }} млн ₽
    {%- elif v >= 1000 -%}{{ '%.0f'|format(v / 1000) }} тыс ₽
    {%- else -%}{{ '%.0f'|format(v) }} ₽{%- endif -%}
  {%- else -%}—{%- endif -%}
{%- endmacro %}
<style>
.ochered-wrap{padding:16px 22px;display:grid;gap:12px}
.och-shapka{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;font-size:13px;color:var(--muted)}
.och-shapka b{color:var(--navy);font-size:15px}
.och-shapka a{color:var(--blue)}
.och-razmer a,.och-razmer strong{margin:0 3px}
table.och-tab{border-collapse:collapse;width:100%}
table.och-tab th,table.och-tab td{padding:8px 10px;border-bottom:1px solid var(--line);
  text-align:left;vertical-align:top;font-size:13px}
table.och-tab th{position:sticky;top:0;background:var(--soft);color:var(--muted);
  font-weight:600;white-space:nowrap;z-index:5}
table.och-tab tbody tr{cursor:pointer}
table.och-tab tbody tr:hover td{background:#f4f6fb}
table.och-tab td.chislo{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
table.och-tab .nazv{font-weight:600;color:var(--blue);text-decoration:none}
table.och-tab .nazv:hover{text-decoration:underline}
table.och-tab .tiho{color:var(--muted);font-size:12px}
.och-tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;
  border:1px solid var(--line);white-space:nowrap}
.och-tag.da{background:#e8f6ee;border-color:#b7e1c7;color:#17663a}
.och-tag.net{background:#fdecec;border-color:#f3c2c2;color:#9b1c1c}
.och-tag.zam{background:#fff4e0;border-color:#f3d39b;color:#8a5300}
.och-stranicy{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.och-stranicy a{padding:5px 11px;border:1px solid var(--line);border-radius:8px;
  text-decoration:none;color:var(--navy);background:var(--card)}
</style>
<main class="ochered-wrap">
  {% set ot = (page - 1) * size + 1 %}{% set do = [page * size, total]|min %}
  <section class="card och-shapka">
    <b>{% if total %}Компании {{ ot }}–{{ do }} из {{ total }}{% else %}Компании не найдены{% endif %}</b>
    {% if hidden_companies_n %}<a href="{{ base_path }}/centro?skrytye={{ 0 if pokaz_skrytye else 1 }}">{% if pokaz_skrytye %}вернуться к обычному списку{% else %}скрытых предприятий: {{ hidden_companies_n }}{% endif %}</a>{% endif %}
    <span class="och-razmer">по{% for n in (20, 50, 100) %}{% if n == size %}<strong>{{ n }}</strong>{% else %}<a href="{{ base_path }}/centro?size={{ n }}{% if query_bez_size %}&{{ query_bez_size }}{% endif %}">{{ n }}</a>{% endif %}{% endfor %}на странице</span>
    <span>порядок — как у очереди: сначала новые, внутри по баллу</span>
  </section>
  {% if not total %}
  <div class="state-card"><h2>Компании не найдены</h2><p>Ослабьте фильтры или проверьте распределение.</p></div>
  {% else %}
  <section class="card" style="overflow-x:auto;padding:0">
    <table class="och-tab">
      <thead><tr>
        <th>№</th><th>Компания</th><th>ОКВЭД</th><th>Выручка</th><th>Машины</th><th>Приговор</th>
        <th>Контакты</th><th>Статус</th><th>Балл</th>{% if user.role == 'admin' %}<th>Продавец</th>{% endif %}
      </tr></thead>
      <tbody>
      {% for c in rows %}
      {% set ssylka = base_path ~ '/centro?inn=' ~ c.inn ~ (('&' ~ query_string) if query_string else '') %}
      <tr data-href="{{ ssylka }}">
        <td class="chislo tiho">{{ ot + loop.index0 }}</td>
        <td><a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>
          <br><span class="tiho">{{ c.inn }}{% if c.region %} · {{ c.region }}{% endif %}{% if c.status_egrul and (c.status_egrul|upper) != 'ACTIVE' %} · {{ c.status_egrul }}{% endif %}</span></td>
        <td title="{{ c.okved or '' }}">{{ (c.okved or '—')|truncate(60, True, '…') }}</td>
        <td class="chislo">{{ dengi(c.vyruchka_rub) }}</td>
        <td>{{ c.tipy_mashin or '—' }}{% if c.pod_zamenu %} <span class="och-tag zam">под замену</span>{% endif %}
          {% if c.sostoyaniya_mashin %}<br><span class="tiho">{{ c.sostoyaniya_mashin|join(', ') }}</span>{% endif %}</td>
        <td>{% if c.verdikt %}<span class="och-tag {{ 'da' if c.verdikt in ['есть','покупает','планирует'] else ('net' if c.verdikt == 'нет' else '') }}">{{ c.verdikt }}</span>{% else %}—{% endif %}</td>
        <td class="tiho">{{ c.n_phones or 0 }} тел · {{ c.n_tech or 0 }} тех · {{ c.n_purchaser or 0 }} закуп{% if c.has_role_phone %}<br><span class="och-tag da">телефон с ролью</span>{% endif %}</td>
        <td>{{ call_results.get(c.call_result or 'new', c.call_result or 'Новый') }}
          {% if c.last_contact_at %}<br><span class="tiho">{{ c.last_contact_at[:10] }}</span>{% endif %}
          {% if c.next_contact_at %}<br><span class="tiho">перезвонить {{ c.next_contact_at[:16]|replace('T', ' ') }}</span>{% endif %}</td>
        <td class="chislo tiho">{{ '%.1f'|format(c.assignment_score or 0) }}</td>
        {% if user.role == 'admin' %}<td>{{ (c.assigned_user|fio) if c.assigned_user else '—' }}</td>{% endif %}
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>
  {% if pages > 1 %}
  <nav class="och-stranicy">
    {% if page > 1 %}<a href="{{ base_path }}/centro?page={{ page - 1 }}{% if query_string %}&{{ query_string }}{% endif %}">← Назад</a>{% endif %}
    <span>{{ page }} / {{ pages }}</span>
    {% if page < pages %}<a href="{{ base_path }}/centro?page={{ page + 1 }}{% if query_string %}&{{ query_string }}{% endif %}">Далее →</a>{% endif %}
  </nav>
  {% endif %}
  {% endif %}
</main>
<script>
/* строка кликается целиком; если выделяли текст (скопировать ИНН) — не прыгаем */
document.querySelectorAll('table.och-tab tr[data-href]').forEach(function (tr) {
  tr.addEventListener('click', function (e) {
    if (e.target.closest('a')) return;
    if (window.getSelection && String(window.getSelection())) return;
    location.href = tr.dataset.href;
  });
});
</script>
'''
pisat(os.path.join(T, '_ochered_spisok.html'), SPISOK)
log.append('[ок] _ochered_spisok.html записан')

# ---------------------------------------------------------------- маршрут /centro
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
FN = 'def centro('
pravka(RCS, '''    if not chosen and visible:
        chosen = visible[(page - 1) * size]
''', '''    # Без выбранной компании — СПИСОК очереди, карточка открывается по клику.
    # Владелец: «вся очередь списком с основными данными, когда проваливаешься в
    # компанию — тогда открывается карточка». Раньше здесь подставлялась первая
    # компания страницы, и вместо списка сразу открывалась её карточка.
    rezhim = "kartochka" if chosen else "spisok"
    pred_inn = sled_inn = ""
    pozitsiya = 0
    if chosen:
        poz = visible.index(chosen)
        pozitsiya = poz + 1
        page = poz // size + 1          # «к списку» — на ту страницу, где эта компания
        pred_inn = visible[poz - 1]["inn"] if poz > 0 else ""
        sled_inn = visible[poz + 1]["inn"] if poz + 1 < len(visible) else ""
''', 'маршрут: список без inn, соседи и место в очереди', funkciya=FN, priznak='rezhim = "kartochka"')
pravka(RCS, '''    filter_query = urlencode(query)
''', '''    filter_query = urlencode(query)
    query_bez_size = urlencode({k: v for k, v in query.items() if k != "size"})
    q_spisok = dict(query)
    if rezhim == "kartochka" and page > 1:
        q_spisok["page"] = page
    spisok_ssylka = "%s/centro%s" % (BP, ("?" + urlencode(q_spisok)) if q_spisok else "")
''', 'маршрут: ссылки списка', funkciya=FN, priznak='spisok_ssylka =')
pravka(RCS, '''            "query_string": filter_query,
''', '''            "query_string": filter_query,
            "query_bez_size": query_bez_size,
            "rezhim": rezhim,
            "pred_inn": pred_inn,
            "sled_inn": sled_inn,
            "pozitsiya": pozitsiya,
            "spisok_ssylka": spisok_ssylka,
''', 'маршрут: контекст', funkciya=FN, priznak='"rezhim": rezhim')

# ---------------------------------------------------------------- centro.html
C = os.path.join(T, 'centro.html')
pravka(C, '''{% elif not company %}''', '''{% elif rezhim == 'spisok' %}
  {% include "_ochered_spisok.html" %}
{% elif not company %}''', 'карточка: режим списка', priznak='_ochered_spisok.html')
pravka(C, '''<span class="eyebrow">Компания {{ (page-1)*size+1 }}–{{ [page*size,total]|min }} из {{ total }}''',
       '''<span class="eyebrow"><a href="{{ spisok_ssylka }}">← к списку</a> · Компания {{ pozitsiya }} из {{ total }}''',
       'карточка: «← к списку» и место в очереди', priznak='← к списку</a>')
pravka(C, '''    <form method="post" action="{{ base_path }}/centro/save" class="work-form">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      <input type="hidden" name="return_query" value="{{ query_string }}">''',
       '''    <form method="post" action="{{ base_path }}/centro/save" class="work-form">
      <input type="hidden" name="inn" value="{{ company.inn }}">
      {# «дальше» = следующая компания очереди; последняя — возврат в список #}
      <input type="hidden" name="return_query" value="{{ query_string }}{% if sled_inn %}{{ '&' if query_string else '' }}inn={{ sled_inn }}{% endif %}">''',
       'карточка: «Сохранить и перейти дальше» -> следующая', priznak='inn={{ sled_inn }}{% endif %}">')
pravka(C, '''      {% if page > 1 %}<a class="action-button" href="?page={{ page-1 }}{% if query_string %}&{{ query_string }}{% endif %}">← Назад</a>{% endif %}
      {% if page < pages %}<a class="action-button primary" href="?page={{ page+1 }}{% if query_string %}&{{ query_string }}{% endif %}">Пропустить →</a>{% endif %}''',
       '''      {% if pred_inn %}<a class="action-button" href="{{ base_path }}/centro?inn={{ pred_inn }}{% if query_string %}&{{ query_string }}{% endif %}">← Предыдущая</a>{% endif %}
      {% if sled_inn %}<a class="action-button primary" href="{{ base_path }}/centro?inn={{ sled_inn }}{% if query_string %}&{{ query_string }}{% endif %}">Пропустить →</a>{% endif %}
      <a class="action-button" href="{{ spisok_ssylka }}">К списку</a>''',
       'карточка: «Назад/Пропустить» по соседям', priznak='← Предыдущая')

print('правок внесено: %d из %d' % (sdelano, nado))
for s in log:
    print('   ' + s)
print('бэкап: %s' % BEKAP)

# ---------------------------------------------------------------- перезапуск и проверка
r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in r.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: очередь списком %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
