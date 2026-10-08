# -*- coding: utf-8 -*-
"""«Компания не понравилась» -> подсписок из пяти причин при наведении.

Владелец: «добавь, чтобы при наведении в “компания не понравилась” выпадал подсписок
причин (5 причин)» — и список из Битрикса, где лишние зачёркнуты. Остались:
  неверно указан номер; нету ФТС и не надо (для хол); клиент не выходит на связь
  (3 звонка/2 письма); дубль; уже купили у конкурентов.

ПОЧЕМУ НЕ <select>. Родной выпадающий список браузера подменю при наведении не умеет —
только плоский список или optgroup без наведения. Поэтому «Результат» — своя менюшка:
те же пункты, у «Компания не понравилась» стрелка ▸ и подменю (наведение мышью, а на
телефоне — тап). Значение уходит в те же поля формы, маршрут сохранения тот же.

КУДА ПИШЕТСЯ ПРИЧИНА. В комментарий, первой строкой «Причина: …». Так она без новой
схемы попадает туда же, где комментарии уже показываются: под статусом в списке очереди
и в истории карточки. Маршрут проверяет: «не понравилась» без причины из списка не
сохраняется (раньше обязательность давал required у select; у своей менюшки её даёт
и скрипт, и сервер).
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
T = os.path.join(APP, 'templates')
PORT = 8016
PUT = '/obzvon-meyer'
PRICHINY = ['неверно указан номер', 'нету ФТС и не надо (для хол)',
            'клиент не выходит на связь (3 звонка/2 письма)', 'дубль', 'уже купили у конкурентов']
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('prichiny-%Y%m%d-%H%M%S'))

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import tempfile
    # Проверка сохранения пишет в базу — пишем во ВРЕМЕННУЮ копию, а не в рабочую базу
    # продавцов: на ней с сегодняшнего дня работает команда Мейера.
    rab = os.environ['CENTRO_SALES_DB']

    def otpechatok(put):
        x = sqlite3.connect(put)
        o = tuple(x.execute('select count(*) from %s' % t).fetchone()[0]
                  for t in ('company_state', 'company_comment', 'activity_log'))
        x.close()
        return o

    do = otpechatok(rab)
    vrem = os.path.join(tempfile.gettempdir(), 'proverka_prichin.db')
    shutil.copy2(rab, vrem)
    os.environ['CENTRO_SALES_DB'] = vrem
    os.environ['PARK_OCHERED_SALES_DB'] = vrem
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    put_s = getattr(sales, 'sales_db_path', '')
    put_s = put_s() if callable(put_s) else put_s
    proverit(os.path.normcase(str(put_s)) == os.path.normcase(vrem),
             'проверка пишет во временную копию базы продаж (%s), рабочая не трогается' % put_s)
    if os.path.normcase(str(put_s)) != os.path.normcase(vrem):
        print('ОСТАНОВ: база продаж не подменилась — сохранять в рабочую не буду')
        raise SystemExit(1)
    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    if hasattr(rcs, '_same_origin'):
        vnutr.dependency_overrides[rcs._same_origin] = lambda: None
    c = sqlite3.connect(vrem)
    inn = c.execute("select inn from company_assignment order by assignment_score desc limit 1").fetchone()[0]
    with TestClient(vnutr) as k:
        o = k.get(PUT + '/centro?inn=' + inn)
        t = o.text
        forma = t.split('class="work-form"')[1].split('</form>')[0] if 'class="work-form"' in t else ''
        proverit(o.status_code == 200 and 'class="rez-vybor"' in forma, 'карточка: своя менюшка «Результат»')
        proverit('<select name="call_result"' not in forma, 'родного select в форме больше нет')
        pod = re.findall(r'data-value="ne_ponravilas" data-prichina="([^"]*)"', forma)
        proverit(pod == PRICHINY, 'подсписок причин: %s' % pod)
        drugie = re.findall(r'<li class="rez-punkt" data-value="(\w+)"', forma)
        print('      пункты верхнего уровня: %s' % drugie)
        o = k.post(PUT + '/centro/save', data={'inn': inn, 'call_result': 'ne_ponravilas',
                                               'comment': '', 'return_query': ''},
                   follow_redirects=False)
        proverit(o.status_code == 422, '«не понравилась» без причины не сохраняется: %s' % o.status_code)
        o = k.post(PUT + '/centro/save', data={'inn': inn, 'call_result': 'ne_ponravilas',
                                               'prichina': 'выдуманная причина', 'return_query': ''},
                   follow_redirects=False)
        proverit(o.status_code == 422, 'причина не из списка не сохраняется: %s' % o.status_code)
        o = k.post(PUT + '/centro/save', data={'inn': inn, 'call_result': 'ne_ponravilas',
                                               'prichina': PRICHINY[4], 'comment': 'звонил гл. инженеру',
                                               'return_query': ''}, follow_redirects=False)
        proverit(o.status_code == 303, 'с причиной сохраняется: %s' % o.status_code)
        sost = c.execute('select call_result from company_state where inn=?', (inn,)).fetchone()
        kom = c.execute('select body from company_comment where inn=? order by id desc limit 1', (inn,)).fetchone()
        proverit(sost and sost[0] == 'ne_ponravilas', 'статус записан: %s' % (sost[0] if sost else None))
        proverit(kom and kom[0] == 'Причина: уже купили у конкурентов. звонил гл. инженеру',
                 'комментарий: %r' % (kom[0] if kom else None))
        t = k.get(PUT + '/centro?call_status=ne_ponravilas').text
        proverit('Причина: уже купили у конкурентов' in t, 'в списке «Компания не понравилась» причина видна под статусом')
        o = k.post(PUT + '/centro/save', data={'inn': inn, 'call_result': 'v_rabote', 'return_query': ''},
                   follow_redirects=False)
        proverit(o.status_code == 303, 'другие результаты сохраняются как раньше: %s' % o.status_code)
        open(r'C:\seostat\drop\drop-storage\centro2-karta-prichiny.html', 'w', encoding='utf-8').write(
            k.get(PUT + '/centro?inn=' + inn).text)
    c.close()
    os.remove(vrem)
    posle = otpechatok(rab)
    proverit(posle == do, 'рабочая база продавцов не тронута: статусы/комментарии/журнал %s до и %s после'
             % (do, posle))
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

os.makedirs(BEKAP, exist_ok=True)
log = []
nado = sdelano = 0


def pisat(put, t):
    cel = os.path.join(BEKAP, os.path.relpath(put, KOREN))
    if not os.path.exists(cel):
        os.makedirs(os.path.dirname(cel), exist_ok=True)
        shutil.copy2(put, cel)
    io.open(put, 'w', encoding='utf-8').write(t)


def pravka(put, staro, novo, imya, priznak=None, regex=False, funkciya=None):
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
    if regex:
        m = list(re.finditer(staro, kusok, re.S))
        if len(m) != 1:
            log.append('[ЯКОРЬ: %d] %s — не правлю' % (len(m), imya))
            return
        kusok = kusok[:m[0].start()] + m[0].expand(novo) + kusok[m[0].end():]
    else:
        if kusok.count(staro) != 1:
            log.append('[ЯКОРЬ: %d] %s — не правлю' % (kusok.count(staro), imya))
            return
        kusok = kusok.replace(staro, novo, 1)
    pisat(put, t[:i] + kusok + t[j:])
    sdelano += 1
    log.append('[ок] ' + imya)


RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
# ---- список причин (модульная константа: шаблон и маршрут сохранения берут одну и ту же)
nado += 1
t = io.open(RCS, encoding='utf-8').read()
if 'PRICHINY_NE_PONRAVILAS' in t:
    sdelano += 1
    log.append('[уже] список причин')
else:
    pisat(RCS, t.rstrip('\n') + '''


# Причины «Компания не понравилась». Владелец прислал список из Битрикса и зачеркнул
# лишние; остались эти пять. Одна константа на шаблон и на проверку при сохранении —
# чтобы в меню не появилась причина, которую сервер не примет, и наоборот.
PRICHINY_NE_PONRAVILAS = [
    "неверно указан номер",
    "нету ФТС и не надо (для хол)",
    "клиент не выходит на связь (3 звонка/2 письма)",
    "дубль",
    "уже купили у конкурентов",
]
''')
    sdelano += 1
    log.append('[ок] список причин')

pravka(RCS, '''    return_query: str = Form(""),
    user=Depends(current_user),
):
    try:
        sales.save_call(user, inn, call_result, next_contact_at, comment)''',
       '''    return_query: str = Form(""),
    prichina: str = Form(""),
    user=Depends(current_user),
):
    # «Компания не понравилась» — только с причиной из списка. Причина пишется первой
    # строкой комментария: так она видна там же, где комментарии уже показываются, —
    # под статусом в списке и в истории карточки.
    if call_result == "ne_ponravilas":
        prichina = (prichina or "").strip()
        if prichina not in PRICHINY_NE_PONRAVILAS:
            raise HTTPException(422, "Выберите причину, почему компания не понравилась")
        comment = "Причина: %s" % prichina + (". %s" % comment.strip() if comment.strip() else "")
    try:
        sales.save_call(user, inn, call_result, next_contact_at, comment)''',
       'сохранение: причина обязательна для «не понравилась»', priznak='prichina: str = Form("")',
       funkciya='def save(')
pravka(RCS, '''            "kommentarii": kommentarii,
''', '''            "kommentarii": kommentarii,
            "prichiny": PRICHINY_NE_PONRAVILAS,
''', 'карточка: причины в контекст', priznak='"prichiny": PRICHINY_NE_PONRAVILAS', funkciya='def centro(')

# ---- карточка: своя менюшка вместо select
C = os.path.join(T, 'centro.html')
MENU = r'''<div class="rez-pole"><span class="rez-podpis">Результат</span>
        {# Своя менюшка вместо <select>: родной список не умеет подменю при наведении, а
           у «Компания не понравилась» владельцу нужен подсписок причин. Значение уходит в
           те же поля формы. #}
        <input type="hidden" name="call_result" value="{{ company.call_result if company.call_result in call_choices else '' }}">
        <input type="hidden" name="prichina" value="">
        <div class="rez-vybor">
          <button type="button" class="rez-knopka" aria-haspopup="true">{{ call_choices.get(company.call_result) if company.call_result in call_choices else '— выберите —' }}</button>
          <ul class="rez-menu" role="menu">
            {% for value,label in call_choices.items() %}
            {% if value == 'ne_ponravilas' and prichiny %}
            <li class="rez-punkt est-pod" role="menuitem" aria-haspopup="true"><span>{{ label }}</span><span class="rez-strelka">▸</span>
              <ul class="rez-pod" role="menu">{% for p in prichiny %}<li class="rez-punkt" data-value="{{ value }}" data-prichina="{{ p }}" data-label="{{ label }}" role="menuitem">{{ p }}</li>{% endfor %}</ul>
            </li>
            {% else %}
            <li class="rez-punkt" data-value="{{ value }}" data-label="{{ label }}" role="menuitem">{{ label }}</li>
            {% endif %}
            {% endfor %}
          </ul>
        </div>
      </div>
      <style>
      .rez-pole{display:grid;gap:4px;font-size:13px;color:var(--muted)}
      .rez-vybor{position:relative}
      .rez-knopka{min-width:240px;text-align:left;padding:8px 30px 8px 10px;border:1px solid var(--line);
        border-radius:8px;background:var(--card);color:var(--navy);font:inherit;cursor:pointer;position:relative}
      .rez-knopka::after{content:'▾';position:absolute;right:10px;top:50%;transform:translateY(-50%);color:var(--muted)}
      .rez-vybor.oshibka .rez-knopka{border-color:#b3261e;box-shadow:0 0 0 2px #b3261e22}
      .rez-menu,.rez-pod{display:none;position:absolute;z-index:45;list-style:none;margin:0;padding:4px 0;
        background:#fff;border:1px solid #c9d2dd;border-radius:8px;box-shadow:0 8px 24px rgba(20,30,50,.18);
        min-width:240px;color:var(--navy)}
      .rez-menu{top:calc(100% + 4px);left:0}
      .rez-vybor.otkryt .rez-menu{display:block}
      .rez-punkt{padding:8px 12px;cursor:pointer;position:relative;white-space:nowrap;display:flex;
        justify-content:space-between;gap:16px}
      .rez-punkt:hover,.rez-punkt.est-pod.otkryt{background:#eef0fb}
      .rez-pod{top:-5px;left:100%}
      .rez-pod.vlevo{left:auto;right:100%}
      .est-pod:hover > .rez-pod,.est-pod.otkryt > .rez-pod{display:block}
      .rez-strelka{color:var(--muted)}
      </style>
      <script>
      (function () {
        var forma = document.querySelector('form.work-form');
        if (!forma) return;
        var vybor = forma.querySelector('.rez-vybor');
        var knopka = vybor.querySelector('.rez-knopka');
        var pole = forma.querySelector('input[name=call_result]');
        var prich = forma.querySelector('input[name=prichina]');
        function zakryt() {
          vybor.classList.remove('otkryt');
          vybor.querySelectorAll('.est-pod.otkryt').forEach(function (x) { x.classList.remove('otkryt'); });
        }
        knopka.addEventListener('click', function () { vybor.classList.toggle('otkryt'); });
        vybor.querySelectorAll('.est-pod').forEach(function (r) {
          /* подменю не должно уезжать за правый край экрана — тогда раскрываем влево */
          r.addEventListener('mouseenter', function () {
            var pod = r.querySelector('.rez-pod');
            pod.classList.remove('vlevo');
            pod.style.display = 'block';
            if (pod.getBoundingClientRect().right > window.innerWidth - 8) pod.classList.add('vlevo');
            pod.style.display = '';
          });
          /* на телефоне наведения нет — тап по пункту раскрывает подменю */
          r.addEventListener('click', function (e) {
            if (e.target.closest('.rez-pod')) return;
            r.classList.toggle('otkryt');
            e.stopPropagation();
          });
        });
        vybor.querySelectorAll('.rez-punkt[data-value]').forEach(function (p) {
          p.addEventListener('click', function (e) {
            e.stopPropagation();
            pole.value = p.dataset.value;
            prich.value = p.dataset.prichina || '';
            knopka.textContent = p.dataset.prichina ? (p.dataset.label + ': ' + p.dataset.prichina) : p.dataset.label;
            vybor.classList.remove('oshibka');
            zakryt();
          });
        });
        document.addEventListener('click', function (e) { if (!vybor.contains(e.target)) zakryt(); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') zakryt(); });
        /* обязательность: раньше её давал required у select */
        forma.addEventListener('submit', function (e) {
          if (!pole.value || (pole.value === 'ne_ponravilas' && !prich.value)) {
            e.preventDefault();
            vybor.classList.add('oshibka', 'otkryt');
          }
        });
      })();
      </script>'''
pravka(C, r'<label>Результат<select name="call_result" required>.*?</select></label>', MENU.replace('\\', '\\\\'),
       'карточка: «Результат» — меню с подсписком причин', priznak='class="rez-vybor"', regex=True)

print('правок внесено: %d из %d' % (sdelano, nado))
for x in log:
    print('   ' + x)
print('бэкап: %s' % BEKAP)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: причины «не понравилась» %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=1500, cwd=KOREN, env=sreda)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
