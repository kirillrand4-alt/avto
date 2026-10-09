# -*- coding: utf-8 -*-
"""fixB2: убрать из панели Meyer результат «Получен личный номер ЛПР» (решение владельца 09.10:
«получен номер ЛПР они в Битриксе отметят, не нужен такой статус»).

Убирается: пункт в форме результата звонка (карточка продавца и форма «за продавца» у
директора), поля ФИО/должность/номер и их скрипт, строка «Личный номер ЛПР» в карточке и
метка «номер ЛПР получен» в списке, пункт в фильтре «Результат звонка», плитки, колонки и
блок статистики (блок становится «Недозвоны»), события в ленте и часах, колонка CSV.
Серверный приём: POST с call_result=lpr_nomer -> 400 «результат отключён». Остаются
«Не дозвонился» и новые причины отказа. Таблицы и колонки в базе не удаляются (строк с
этим результатом нет – проверяется и печатается). Функции _lpr_v_katalog и
_fixE2_pereschet_lpr остаются в коде неиспользуемыми.

Порядок (как fixB_panel.py): замок -> копия кода -> правки по якорям -> проверка на копиях
баз -> правки в боевых файлах -> быстрая проверка -> перезапуск -> отдать замок.
  python3 zapusk_na_servere.py fixB2_otkl.py --tolko-proverka   – только проверка на копиях
  python3 zapusk_na_servere.py fixB2_otkl.py                    – боевой прогон
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
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
ZAMOK = os.path.join(KOREN, '_zamok.txt')
METKA = time.strftime('%Y%m%d-%H%M%S')
BEKAP = os.path.join(KOREN, '_bekap', 'fixB2-' + METKA)
TEST_DB = os.path.join(KOREN, '_bekap', 'fixB2-test-sales.db')
TEST_KAT = os.path.join(KOREN, '_bekap', 'fixB2-test-katalog.db')
FAJLY = {
    'rcs': os.path.join('api', 'routes_centro_sales.py'),
    'cs': os.path.join('services', 'centro_sales.py'),
    'C': os.path.join('templates', 'centro.html'),
    'L': os.path.join('templates', '_ochered_spisok.html'),
    'SB': os.path.join('templates', '_statblok.html'),
    'ST': os.path.join('templates', 'centro_stats.html'),
}
OTKL = '«Получен личный номер ЛПР» отключён владельцем 09.10'

ST_NOVYY = r'''  {# ======== fixB (08.10) / fixB2 (09.10): «не дозвонился» – попытка без исхода, компания остаётся в очереди.
     Результат «Получен личный номер ЛПР» владелец отключил 09.10: номер ЛПР отмечают в Битриксе #}
  {% set sd = sobytiya_dir %}
  {% if sd %}
  <h2 id="nedozvony">Недозвоны <span class="period-metka">{{ d.period_ru }}</span></h2>
  <div class="stat-setka">
    <div class="plitka"><b>{{ sd.itog.nedozvon }}</b><span>попыток «не дозвонился»</span></div>
    <div class="plitka"><b>{{ ch(sd.itog.nedozvon_komp) }}</b><span>компаний с недозвоном</span></div>
  </div>
  <p class="pometka">«Не дозвонился» – попытка без исхода, компания осталась в очереди. Засчитывается продавцу, за которым компания (как и отметки). Число компаний открывает их списком.</p>
  <div style="overflow-x:auto"><table class="stat">
    <thead><tr><th>Продавец</th><th>Не дозвонился, попыток</th><th>в компаниях</th><th>Дней с недозвонами</th><th>Последний</th></tr></thead>
    <tbody>
    {% for s in sd.stroki %}
      <tr{% if s.itog %} class="itog"{% endif %}><td>{% if s.itog %}Все продавцы{% else %}{{ s.kto|fio }}{% endif %}</td><td><b>{{ s.nedozvon }}</b></td><td>{{ ch(s.nedozvon_komp) }}</td><td>{{ s.dney }}</td><td>{{ s.posled or '–' }}</td></tr>
    {% else %}<tr><td colspan="5">Продавцов нет.</td></tr>{% endfor %}
    </tbody>
  </table></div>
  {% if sd.po_dnyam %}
  <h3>По дням <span class="period-metka">попыток «не дозвонился»</span></h3>
  <div style="overflow-x:auto"><table class="stat">
    <thead><tr><th>День</th>{% for u in sd.kolonki %}<th>{{ u|fio }}</th>{% endfor %}<th>Всего</th></tr></thead>
    <tbody>
    {% for dn in sd.po_dnyam %}
      <tr><td style="white-space:nowrap">{{ dn.den_ru }}</td>{% for y in dn.yach %}<td>{{ y.nedozvon or '–' }}</td>{% endfor %}<td><b>{{ dn.nedozvon }}</b></td></tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% endif %}
  {% endif %}

'''

JS_NOVYY = r'''      /* fixB / fixB2: подсказка под результатом – что будет с компанией («Не дозвонился» –
         остаётся в очереди). Отдельного результата для номера ЛПР нет (владелец, 09.10). */
      (function () {
        var forma = document.querySelector('form.work-form');
        if (!forma) return;
        var pole = forma.querySelector('input[name=call_result]');
        var podsk = forma.querySelector('.rez-podskazka');
        if (!pole || !podsk) return;
        function obnovit() {
          podsk.textContent = pole.value === 'ne_dozvonilsya' ? 'Компания останется в очереди, попытка запишется.' : '';
        }
        forma.querySelectorAll('.rez-punkt[data-value]').forEach(function (p) { p.addEventListener('click', obnovit); });
        obnovit();
      })();
      </script>'''

# ('z', файл, было, стало, имя, признак, обязательная[, все])  – замена (one / all)
# ('m', файл, начало, конец, стало, имя, признак, обязательная) – от «начала» до первого «конца»
PRAVKI = [
    # ---------------- centro_sales.py
    ('z', 'cs', '''SOBYTIYA_ZVONKA = {
    "ne_dozvonilsya": "Не дозвонился",
    "lpr_nomer": "Получен личный номер ЛПР",
}''', '''SOBYTIYA_ZVONKA = {
    "ne_dozvonilsya": "Не дозвонился",
    # fixB2: «Получен личный номер ЛПР» отключён владельцем 09.10 – «они в Битриксе отметят»
}''', 'centro_sales: событие «номер ЛПР» убрано', 'fixB2: «Получен личный номер ЛПР» отключён владельцем 09.10 – «они', True),
    ('z', 'cs', '''    "ne_dozvonilsya": "Не дозвонился",
    "lpr_nomer": "Получен личный номер ЛПР",
}

# ЧТО ПРЕДЛАГАЕТСЯ В ФОРМЕ.''', '''    "ne_dozvonilsya": "Не дозвонился",
}

# ЧТО ПРЕДЛАГАЕТСЯ В ФОРМЕ.''', 'centro_sales: подпись «номер ЛПР» убрана', '''    "ne_dozvonilsya": "Не дозвонился",
}

# ЧТО ПРЕДЛАГАЕТСЯ В ФОРМЕ.''', True),
    # ---------------- routes_centro_sales.py
    ('z', 'rcs', '''    # fixB (владелец 08.10): «Не дозвонился» и «Получен личный номер ЛПР» – не статус, а
    # событие: компания остаётся там, где была, попытка или номер пишутся отдельно
    if call_result in sales.SOBYTIYA_ZVONKA:''', '''    # fixB2 (владелец 09.10): «Получен личный номер ЛПР» отключён – «они в Битриксе отметят»
    if call_result == "lpr_nomer":
        raise HTTPException(400, "Этот результат отключён: номер ЛПР отмечается в Битриксе")
    # fixB (владелец 08.10): «Не дозвонился» – не статус, а событие: компания остаётся там,
    # где была, попытка пишется отдельно
    if call_result in sales.SOBYTIYA_ZVONKA:''', 'save(): «номер ЛПР» -> 400', 'if call_result == "lpr_nomer":\n        raise HTTPException(400,', True),
    ('z', 'rcs', '''_SOB_DEYSTVIYA = ("ne_dozvonilsya", "lpr_nomer")
_SOB_NAZV = {"ne_dozvonilsya": "Не дозвонился", "lpr_nomer": "Получен личный номер ЛПР"}
_SOB_FILTR = {"ne_dozvonilsya": "popytok", "lpr_nomer": "lpr_poluchen"}''', '''# fixB2: «Получен личный номер ЛПР» отключён владельцем 09.10 – в ленте, часах, фильтрах его нет
_SOB_DEYSTVIYA = ("ne_dozvonilsya",)
_SOB_NAZV = {"ne_dozvonilsya": "Не дозвонился"}
_SOB_FILTR = {"ne_dozvonilsya": "popytok"}''', 'события: только «не дозвонился»', '_SOB_DEYSTVIYA = ("ne_dozvonilsya",)', True),
    ('z', 'rcs', '''    filtr += [("ne_dozvonilsya", "Не дозвонился (были попытки)"), ("lpr_nomer", "Получен личный номер ЛПР")]''',
     '''    filtr += [("ne_dozvonilsya", "Не дозвонился (были попытки)")]      # fixB2: без «номера ЛПР»''',
     'фильтр «Результат звонка» без «номера ЛПР»', '("ne_dozvonilsya", "Не дозвонился (были попытки)")]      # fixB2', True),
    ('z', 'rcs', '''                "Последний контакт", "Перезвонить", "Не дозвонился, попыток",
                "Личных номеров ЛПР получено", "Последний комментарий",''', '''                "Последний контакт", "Перезвонить", "Не дозвонился, попыток",
                "Последний комментарий",''', 'CSV: заголовок без «номеров ЛПР»', '"Не дозвонился, попыток",\n                "Последний комментарий",', True),
    ('z', 'rcs', '''            c.get("popytok") or 0, c.get("lpr_poluchen") or 0,''', '''            c.get("popytok") or 0,''',
     'CSV: строка без «номеров ЛПР»', '            c.get("popytok") or 0,\n', True),
    # ---------------- centro.html
    ('z', 'C', '''    {# fixB: попытки «не дозвонился» и личные номера ЛПР от продавцов по этой компании #}
    {% if dop_kartochka and (dop_kartochka.popytok or dop_kartochka.lpr) %}''', '''    {# fixB: попытки «не дозвонился» по этой компании #}
    {% if dop_kartochka and dop_kartochka.popytok %}''', 'карточка: блок попыток без номеров ЛПР', '{% if dop_kartochka and dop_kartochka.popytok %}', True),
    ('m', 'C', '''      {% for l in dop_kartochka.lpr %}''', '''{% endfor %}
''', '', 'карточка: строки «Личный номер ЛПР» убраны', None, True),
    ('m', 'C', '''      {# fixB: «Получен личный номер ЛПР» – ФИО, должность, номер (номер уйдёт в контакты компании) #}''',
     '''      <p class="rez-podskazka"></p>
''', '''      <p class="rez-podskazka"></p>
''', 'форма: поля ФИО/должность/номер ЛПР убраны', None, True),
    ('m', 'C', '''      /* fixB: поля ЛПР – только для «Получен личный номер ЛПР»;''', '''      })();
      </script>''', JS_NOVYY, 'форма: скрипт без полей ЛПР', 'fixB / fixB2: подсказка под результатом', True),
    # ---------------- _ochered_spisok.html
    ('m', 'L', '''          {% if c.lpr_poluchen %}''', '''{% endif %}</span>{% endif %}
''', '', 'список: метка «номер ЛПР получен» убрана', None, False),
    # ---------------- _statblok.html
    ('z', 'SB', '''<td class="cel" title="личных номеров ЛПР получено">{{ d.lpr or 0 }}</td>''', '',
     'календарь: ячейка «номер ЛПР» убрана', None, True),
    ('z', 'SB', '''<th title="личных номеров ЛПР получено">номер ЛПР</th>''', '',
     'календарь: заголовки «номер ЛПР» убраны', None, True, True),
    ('z', 'SB', '''<th class="gr razd" colspan="6">{% if statblok.vse %}за всё время (с''',
     '''<th class="gr razd" colspan="5">{% if statblok.vse %}за всё время (с''', 'календарь: colspan периода', 'colspan="5">{% if statblok.vse %}за всё время (с', True),
    ('z', 'SB', '''<th class="gr razd" colspan="6">{% if statblok.vse %}нынешний статус''',
     '''<th class="gr razd" colspan="5">{% if statblok.vse %}нынешний статус''', 'календарь: colspan «всё время»', 'colspan="5">{% if statblok.vse %}нынешний статус', True),
    ('z', 'SB', '''colspan="13" class="tiho">продавцов нет''', '''colspan="11" class="tiho">продавцов нет''',
     'календарь: colspan пустой таблицы', 'colspan="11" class="tiho">продавцов нет', True),
    ('z', 'SB', '''«Номер ЛПР» – личные номера ЛПР, которые продавец получил и вписал; «не дозвонился» – попытки без исхода, компания остаётся в очереди.''',
     '''«Не дозвонился» – попытки без исхода, компания остаётся в очереди.''', 'календарь: пояснение без «номера ЛПР»', None, True),
    # ---------------- centro_stats.html
    ('m', 'ST', '''  {# ======== fixB (08.10): цель владельца – личные номера ЛПР;''', '''  {% endif %}
  {% endif %}

''', ST_NOVYY, 'статистика: блок «Недозвоны» вместо «Личные номера ЛПР и недозвоны»', 'id="nedozvony"', True),
    ('z', 'ST', '''    <div class="plitka plitka-cel"><b>{{ obshchee.lpr_vsego or 0 }}</b><span>личных номеров ЛПР получено за всё время{% if obshchee.lpr_kompaniy %} ({{ obshchee.lpr_kompaniy }} комп.){% endif %}</span></div>
''', '', 'статистика: плитка «номеров ЛПР» убрана', None, True),
    ('z', 'ST', '''Сколько отметок и звонков без исхода («не дозвонился», «номер ЛПР») сохранено в каждый час.''',
     '''Сколько отметок и попыток «не дозвонился» сохранено в каждый час.''', 'статистика: подпись часов', None, True),
]


def primenit(koren_app, log) -> list:
    provaleno = []
    for pr in PRAVKI:
        vid, kl = pr[0], pr[1]
        p = os.path.join(koren_app, FAJLY[kl])
        t = io.open(p, encoding='utf-8').read()
        if vid == 'z':
            staro, novo, imya, priznak, nado = pr[2:7]
            vse = len(pr) > 7 and pr[7]
            if (priznak and priznak in t) or (not priznak and staro not in t and not novo):
                log.append('[уже] ' + imya)
                continue
            if not priznak and novo and novo in t and staro not in t:
                log.append('[уже] ' + imya)
                continue
            n = t.count(staro)
            if n == 0 or (n > 1 and not vse):
                log.append('[%s ЯКОРЬ: %d] %s' % ('НЕТ' if nado else 'пропуск', n, imya))
                if nado:
                    provaleno.append(imya)
                continue
            t = t.replace(staro, novo) if vse else t.replace(staro, novo, 1)
        else:
            nachalo, konec, novo, imya, priznak, nado = pr[2:8]
            if (priznak and priznak in t) or (not priznak and nachalo not in t):
                log.append('[уже] ' + imya)
                continue
            if t.count(nachalo) != 1:
                log.append('[%s ЯКОРЬ: %d] %s' % ('НЕТ' if nado else 'пропуск', t.count(nachalo), imya))
                if nado:
                    provaleno.append(imya)
                continue
            i = t.index(nachalo)
            j = t.find(konec, i + len(nachalo))
            if j < 0 or j - i > 12000:
                log.append('[НЕТ КОНЦА] ' + imya)
                if nado:
                    provaleno.append(imya)
                continue
            t = t[:i] + novo + t[j + len(konec):]
        io.open(p, 'w', encoding='utf-8').write(t)
        log.append('[ок] ' + imya)
    return provaleno


def kopiya_bazy(otkuda, kuda):
    if os.path.exists(kuda):
        os.remove(kuda)
    src = sqlite3.connect('file:%s?mode=ro' % otkuda, uri=True, timeout=30)
    dst = sqlite3.connect(kuda)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


if '--lokalno' in sys.argv:
    log = []
    prov = primenit(sys.argv[sys.argv.index('--lokalno') + 1], log)
    print('\n'.join(log))
    print('ПРОВАЛЕНО обязательных: %s' % prov)
    raise SystemExit(1 if prov else 0)


# =========================================================================== проверка (venv)
ZAPRET = ('data-value="lpr_nomer"', 'value="lpr_nomer"', 'name="lpr_nomer"', 'name="lpr_dolzhnost"', 'class="lpr-polya"',
          'получен личный номер лпр', 'личных номеров лпр', 'номер лпр</th>', 'номер лпр получен',
          'личный номер лпр</b>')


def proverka(koren_koda, bystro):
    import datetime as dt
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    sys.path.insert(0, koren_koda)
    ZH_S = os.environ['CENTRO_SALES_DB']
    ZH_K = os.environ['CENTRIFUGAL_DB']
    zs = sqlite3.connect('file:%s?mode=ro' % ZH_S, uri=True)
    try:
        n_sob = zs.execute("select count(*) from zvonok_sobytie where vid='lpr_nomer'").fetchone()[0]
    except sqlite3.OperationalError:
        n_sob = 0
    n_log = zs.execute("select count(*) from activity_log where action='lpr_nomer'").fetchone()[0]
    zs.close()
    zk = sqlite3.connect('file:%s?mode=ro' % ZH_K, uri=True)
    n_kat = zk.execute("select count(*) from contact where source like 'от продавца%'").fetchone()[0]
    zk.close()
    print('   рабочие базы: событий «номер ЛПР» %d, записей журнала %d, контактов «от продавца» %d' % (n_sob, n_log, n_kat))
    kopiya_bazy(ZH_S, TEST_DB)
    kopiya_bazy(ZH_K, TEST_KAT)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = TEST_DB
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[k] = TEST_KAT
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

    ok(os.path.abspath(app.__file__).lower().startswith(os.path.abspath(koren_koda).lower()), 'код из %s' % koren_koda)
    ok(str(catalog.db_path()) == TEST_KAT and str(sales.sales_db_path()) == TEST_DB, 'базы – временные копии')
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 5, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 7, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    vnutr.dependency_overrides[rcs._same_origin] = lambda: None

    def chislo(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1

    b = sqlite3.connect(TEST_DB)
    zanyatye = {str(r[0]) for r in b.execute('select inn from company_state')}
    kat = sqlite3.connect(TEST_KAT)
    v_kat = {str(r[0]) for r in kat.execute('select inn from company')}
    skryt = {str(r[0]) for r in b.execute("select inn from hidden_item where kind='company'")}
    A = [str(r[0]) for r in b.execute("select inn from company_assignment where username='meyer2' order by assignment_score desc")
         if str(r[0]) not in zanyatye and str(r[0]) in v_kat and str(r[0]) not in skryt]
    with TestClient(vnutr) as k:
        def poluchit(u, kak=ADMIN, **kw):
            kto['u'] = kak
            return k.get(PUT + u, **kw)

        def otpravit(d, kak=PROD):
            kto['u'] = kak
            return k.post(PUT + '/centro/save', data=d, follow_redirects=False)
        stranicy = {}
        for nazv, u, kak, kod in (('главная, админ', '/centro', ADMIN, 200),
                                  ('карточка, админ', '/centro?inn=' + A[0], ADMIN, 200),
                                  ('статистика, админ', '/centro/stats', ADMIN, 200),
                                  ('статистика «всё время», админ', '/centro/stats?stat_vse=1', ADMIN, 200),
                                  ('список компаний, админ', '/centro/spisok', ADMIN, 200),
                                  ('главная, продавец', '/centro', PROD, 200),
                                  ('карточка, продавец', '/centro?inn=' + A[0], PROD, 200),
                                  ('список компаний, продавец', '/centro/spisok', PROD, 200),
                                  ('статистика, продавец', '/centro/stats', PROD, 403)):
            o = poluchit(u, kak)
            stranicy[nazv] = o.text
            ok(o.status_code == kod, '%s: %s' % (nazv, o.status_code))
        o = poluchit('/centro/vygruzka.csv')
        ok(o.status_code == 200, 'CSV: %s' % o.status_code)
        stranicy['CSV'] = o.content.decode('utf-8-sig')
        for nazv, t in stranicy.items():
            nizh = t.lower()
            est = [z for z in ZAPRET if z in nizh]
            ok(not est, '%s: «номер ЛПР» как результата нет %s' % (nazv, est or ''))
        t_pr = stranicy['карточка, продавец']
        ok('data-value="ne_dozvonilsya"' in t_pr and 'data-value="v_rabote"' in t_pr and 'data-value="dubl"' in t_pr,
           'в меню: «Не дозвонился» и прежние результаты')
        for p in ('нет потребности', 'не наш профиль', 'компания закрыта', 'не та компания / не ЛПР', 'уже купили у конкурентов'):
            ok('data-prichina="%s"' % p in t_pr, 'причина в меню: %s' % p)
        ok('<details class="dir-forma">' in stranicy['карточка, админ'] and 'data-value="ne_dozvonilsya"' in stranicy['карточка, админ'],
           'у директора форма «за продавца» есть, свёрнута, с «Не дозвонился»')
        m = re.search(r'<select name="call_status">(.*?)</select>', stranicy['главная, админ'], re.S)
        zn = set(re.findall(r'<option value="([^"]*)"', m.group(1))) if m else set()
        ok('lpr_nomer' not in zn and 'ne_dozvonilsya' in zn, 'фильтр «Результат звонка»: %s' % sorted(zn))
        if bystro:
            print()
            print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
            raise SystemExit(0 if not plohih[0] else 1)
        # приём «номера ЛПР» отключён
        n0 = b.execute('select count(*) from activity_log').fetchone()[0]
        k0 = kat.execute('select count(*) from contact').fetchone()[0]
        o = otpravit({'inn': A[1], 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов Тест Тестович',
                      'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '+7 900 000-00-00'})
        ok(o.status_code == 400 and 'отключён' in o.text, '«номер ЛПР» на сервере: %s %s' % (o.status_code, o.text[:90]))
        o = otpravit({'inn': A[1], 'call_result': 'lpr_nomer', 'lpr_nomer': '+7 900 000-00-00'}, kak=ADMIN)
        ok(o.status_code == 400, '«номер ЛПР» от директора: %s' % o.status_code)
        ok(b.execute('select count(*) from activity_log').fetchone()[0] == n0
           and kat.execute('select count(*) from contact').fetchone()[0] == k0, 'ничего не записано (журнал и каталог)')
        # «Не дозвонился» работает
        o = otpravit({'inn': A[0], 'call_result': 'ne_dozvonilsya', 'comment': 'fixB2-тест занято'})
        ok(o.status_code == 303, '«Не дозвонился»: %s' % o.status_code)
        ok(b.execute("select count(*) from zvonok_sobytie where inn=? and vid='ne_dozvonilsya'", (A[0],)).fetchone()[0] == 1,
           'попытка записана')
        ok(('inn=' + A[0]) in poluchit('/centro?size=100', PROD).text, 'компания осталась во «Всей очереди»')
        ok('попыток: 1, последняя' in poluchit('/centro?inn=' + A[0], PROD).text, 'в карточке «попыток: 1, последняя …»')
        ok(chislo(poluchit('/centro?call_status=ne_dozvonilsya', PROD).text) == 1, 'фильтр «Не дозвонился (были попытки)»: 1')
        st = poluchit('/centro/stats').text
        io.open(os.path.join(DROP, 'fixB2-stats.html'), 'w', encoding='utf-8').write(st)
        ok('id="nedozvony"' in st and not [z for z in ZAPRET if z in st.lower()], 'статистика: блок «Недозвоны», без «номера ЛПР»')
        segodnya = (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()
        with sales.connect() as conn:
            sv = rcs._svodka_sobytiy(conn, segodnya, segodnya, '')
        m2 = next((s for s in sv['stroki'] if s['kto'] == 'meyer2'), None)
        ok(m2 and m2['nedozvon'] == 1 and m2['nedozvon_komp']['n'] == 1, 'сводка: meyer2 недозвонов 1 (1 комп.)')
        from html import unescape
        ssylki = list(dict.fromkeys((unescape(u), int(n)) for u, n in re.findall(
            r'<a href="(%s/centro\?[^"]*|%s/centro)">(\d+)</a>' % (PUT, PUT), st)))
        nerav = [(u, n, c) for u, n in ssylki for c in [chislo(poluchit(u.replace(PUT, '', 1)).text)] if c != n]
        ok(not nerav, 'цифры-ссылки статистики: %d, расхождений %d %s' % (len(ssylki), len(nerav), nerav[:3]))
        ok('Не дозвонился' in st, 'лента: «Не дозвонился» есть')
        o = otpravit({'inn': A[2], 'call_result': 'ne_ponravilas', 'prichina': 'нет потребности', 'comment': 'fixB2-тест'})
        ok(o.status_code == 303 and b.execute('select prichina from company_state where inn=?', (A[2],)).fetchone()[0] == 'нет потребности',
           'новая причина отказа сохраняется отдельным полем')
        o = otpravit({'inn': A[3], 'call_result': 'v_rabote', 'comment': 'fixB2-тест'})
        ok(o.status_code == 303 and ('inn=' + A[3]) in poluchit('/centro?call_status=v_rabote', PROD).text, '«Взял в работу» как раньше')
    b.close()
    kat.close()
    zs = sqlite3.connect('file:%s?mode=ro' % ZH_S, uri=True)
    sledy = zs.execute("select count(*) from company_comment where body like '%fixB2-тест%'").fetchone()[0]
    try:
        sledy += zs.execute("select count(*) from zvonok_sobytie where kommentariy like '%fixB2-тест%'").fetchone()[0]
    except sqlite3.OperationalError:
        pass
    zs.close()
    ok(sledy == 0, 'рабочая база продаж: следов проверки %d' % sledy)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    raise SystemExit(0 if not plohih[0] else 1)


if '--proverka' in sys.argv or '--bystro' in sys.argv:
    fl = '--proverka' if '--proverka' in sys.argv else '--bystro'
    proverka(sys.argv[sys.argv.index(fl) + 1], fl == '--bystro')


# =========================================================================== боевой прогон
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


def zapustit_proverku(koren_koda, rezhim, imya_otcheta):
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), rezhim, koren_koda], capture_output=True,
                       timeout=1300, cwd=KOREN, env=sreda)
    vyvod = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        vyvod += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-5000:]
    for p in (TEST_DB, TEST_KAT):
        for hv in ('', '-wal', '-shm'):
            try:
                os.remove(p + hv)
            except OSError:
                pass
    io.open(os.path.join(DROP, imya_otcheta), 'w', encoding='utf-8').write(vyvod)
    return r.returncode == 0 and 'ПЛОХИХ ПРОВЕРОК: 0' in vyvod, vyvod


def kopiya_koda(kuda):
    app = os.path.join(KOREN, 'app')
    for d, dirs, fs in os.walk(app):
        dirs[:] = [x for x in dirs if x not in ('dokaz', '__pycache__')]
        cel = os.path.join(kuda, 'app', os.path.relpath(d, app))
        os.makedirs(cel, exist_ok=True)
        for f in fs:
            shutil.copy2(os.path.join(d, f), os.path.join(cel, f))


def perezapusk():
    p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in p.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
    time.sleep(2)
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    lg.write('\n===== перезапуск: fixB2 – «Получен личный номер ЛПР» убран %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
    lg.flush()
    subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
                     creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
    import urllib.request
    kod = '?'
    for _ in range(6):
        time.sleep(5)
        try:
            kod = urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status
            if kod == 200:
                break
        except Exception as e:  # noqa: BLE001
            kod = str(e)[:80]
    return kod


def faza_kopii():
    vremya = os.path.join(KOREN, '_bekap', 'fixB2-kod-' + METKA)
    kopiya_koda(vremya)
    log = []
    prov = primenit(os.path.join(vremya, 'app'), log)
    print('--- правки в копии кода:')
    print('\n'.join('   ' + x for x in log))
    if prov:
        print('НЕ ВСЕ ОБЯЗАТЕЛЬНЫЕ ЯКОРЯ НАЙДЕНЫ: %s' % prov)
        return False, vremya
    uspeh, vyvod = zapustit_proverku(vremya, '--proverka', 'fixB2-proverka.txt')
    print('--- полная проверка (копия кода, копии баз):')
    print(vyvod[-3500:])
    return uspeh, vremya


def boevoy():
    vzyat_zamok('fixB2')
    try:
        uspeh, vremya = faza_kopii()
        shutil.rmtree(vremya, ignore_errors=True)
        if not uspeh:
            print('ПРОВЕРКА НЕ ПРОШЛА – боевые файлы не тронуты')
            return 1
        os.makedirs(BEKAP, exist_ok=True)
        app = os.path.join(KOREN, 'app')
        for kl, otn in FAJLY.items():
            shutil.copy2(os.path.join(app, otn), os.path.join(BEKAP, kl + '-' + os.path.basename(otn)))

        def vernut():
            for kl, otn in FAJLY.items():
                shutil.copy2(os.path.join(BEKAP, kl + '-' + os.path.basename(otn)), os.path.join(app, otn))
        log = []
        prov = primenit(app, log)
        print('--- правки в боевых файлах:')
        print('\n'.join('   ' + x for x in log if not x.startswith('[ок]')) or '   все [ок]')
        if prov:
            vernut()
            print('ЯКОРЯ В БОЕВЫХ ФАЙЛАХ НЕ СОШЛИСЬ: %s – файлы возвращены из %s' % (prov, BEKAP))
            return 1
        os.utime(ZAMOK, None)
        uspeh, vyvod = zapustit_proverku(KOREN, '--bystro', 'fixB2-proverka-boevaya.txt')
        print('--- быстрая проверка боевого кода:')
        print(vyvod[-2500:])
        if not uspeh:
            vernut()
            print('БЫСТРАЯ ПРОВЕРКА НЕ ПРОШЛА – файлы возвращены из %s, перезапуска нет' % BEKAP)
            return 1
        kod = perezapusk()
        print('перезапущено, вход: %s; бэкап файлов: %s' % (kod, BEKAP))
        return 0 if kod == 200 else 2
    finally:
        otdat_zamok()


if __name__ == '__main__':
    if '--tolko-proverka' in sys.argv:
        u, v = faza_kopii()
        shutil.rmtree(v, ignore_errors=True)
        raise SystemExit(0 if u else 1)
    raise SystemExit(boevoy())
