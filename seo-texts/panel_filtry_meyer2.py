# -*- coding: utf-8 -*-
"""Ещё шесть фильтров для холодного обзвона Meyer (выбор владельца из предложенных).

  1. «Есть номер в битриксе»              bitrix=1      (название — владельца)
  2. «Сейчас рабочее время у компании»    rabochee=1    9:00–18:00 по местному, пн–пт
  3. Роль ЛПР                             rol_lpr=…
  4. Перезвон: сегодня / просроченные     perezvon=…    по «Следующий контакт»
  5. «ЛПР с ФИО»                          lpr_fio=1
  6. Источник базы                        baza=…        «База 1», дальше 2, 3

ЧАСОВОЙ ПОЯС — по региону компании, таблица по ключевым словам на все субъекты РФ, а не
только на 38 регионов Базы 1: следующие базы придут из других мест. Не распознан (бывает
город вместо региона) — считается по Москве, и это записано у компании (chas_poyas_kak),
чтобы было видно, где пояс угадан, а где выведен.

ПЕРЕЗВОН показывает компании ИЗ ВСЕХ ВКЛАДОК: перезвоны обычно стоят у «Взял в работу»,
а «Вся очередь» обработанные не показывает — без этого фильтр во «Всей очереди» был бы
всегда пуст. Время «Следующего контакта» — московское (его вводят продавцы в браузере).

СЧЁТЧИКИ у фильтров — по компаниям, которые видит этот пользователь (у продавца — его
очередь), а не по всей базе: раньше продавец видел «техЛПР · 16» по всей базе, а в своём
списке находил меньше.
"""
import io
import json
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
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
JSON_PUT = r'C:\seostat\drop\drop-storage\meyer-baza1.json'
PORT = 8016
PUT = '/obzvon-meyer'
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('filtry2-%Y%m%d-%H%M%S'))

# Пояса (смещение от UTC). Порядок важен: сначала более узкие слова.
POYASA = [
    (2, ('калининград',)),
    (12, ('камчат', 'чукот')),
    (11, ('магадан', 'сахалин')),
    (10, ('хабаровск', 'приморск', 'владивосток', 'еврейск')),
    (9, ('забайкаль', 'чита', 'амурск', 'якут', 'саха (')),
    (8, ('иркут', 'бурят')),
    (7, ('новосиб', 'томск', 'кемеров', 'кузбас', 'алтай', 'краснояр', 'хакас', 'тыва')),
    (6, ('омск',)),
    (5, ('башкорт', 'уфа', 'оренбург', 'перм', 'свердлов', 'екатеринбург', 'челябин', 'курган',
         'тюмен', 'ханты', 'югра', 'ямал')),
    (4, ('самар', 'саратов', 'ульянов', 'астрахан', 'удмурт', 'ижевск')),
]


def poyas(region):
    r = (region or '').casefold()
    for smeshch, slova in POYASA:
        # «омск» — не путать с «томск»: томск проверен раньше (в +7)
        if any(s in r for s in slova):
            return smeshch, 'по региону'
    if not r:
        return 3, 'по Москве: регион не указан'
    return 3, 'по региону' if _evropeyskiy(r) else 'по Москве: регион не распознан'


def _evropeyskiy(r):
    return any(s in r for s in (
        'москв', 'петербург', 'ленинград', 'владимир', 'волгоград', 'вологод', 'воронеж', 'киров',
        'костром', 'краснодар', 'курск', 'нижегород', 'рязан', 'тамбов', 'туль', 'ярослав', 'калмык',
        'крым', 'севастопол', 'татарстан', 'ставропол', 'твер', 'пенз', 'мордов', 'чуваш', 'марий',
        'белгород', 'брянск', 'калуж', 'липец', 'орлов', 'смолен', 'иванов', 'мурман', 'карел', 'коми',
        'архангел', 'ненец', 'новгород', 'псков', 'ростов', 'адыге', 'дагестан', 'ингуш', 'кабардин',
        'карачаев', 'осетия', 'чечен'))


if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import datetime
    import tempfile
    rab = os.environ['CENTRO_SALES_DB']
    vrem = os.path.join(tempfile.gettempdir(), 'proverka_filtrov2.db')
    shutil.copy2(rab, vrem)
    os.environ['CENTRO_SALES_DB'] = vrem          # перезвоны ставлю во ВРЕМЕННУЮ копию
    os.environ['PARK_OCHERED_SALES_DB'] = vrem
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from urllib.parse import urlencode
    from app.api import routes_centro_sales as rcs
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    d = json.load(io.open(JSON_PUT, encoding='utf-8'))
    K = d['kompanii']
    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    # НЕЗАВИСИМАЯ таблица поясов для 38 регионов Базы 1 — набрана отдельно, не из POYASA
    NEZAV = {'Алтайский край': 7, 'Астраханская область': 4, 'Владимирская область': 3,
             'Волгоградская область': 3, 'Вологодская область': 3, 'Воронежская область': 3,
             'Забайкальский край': 9, 'Камчатский край': 12, 'Кировская область': 3,
             'Костромская область': 3, 'Краснодарский край': 3, 'Красноярский край': 7,
             'Курская область': 3, 'Ленинградская область': 3, 'Москва': 3, 'Московская область': 3,
             'Нижегородская область': 3, 'Новосибирская область': 7, 'Оренбургская область': 5,
             'Пермский край': 5, 'Республика Алтай': 7, 'Республика Башкортостан': 5,
             'Республика Калмыкия': 3, 'Республика Крым': 3, 'Республика Татарстан': 3,
             'Республика Хакасия': 7, 'Рязанская область': 3, 'Санкт-Петербург': 3,
             'Свердловская область': 5, 'Ставропольский край': 3, 'Старица': 3,
             'Тамбовская область': 3, 'Тульская область': 3, 'Удмуртская Республика': 4,
             'Ульяновская область': 4, 'Челябинская область': 5, 'Череповец': 3,
             'Ярославская область': 3}
    kat = sqlite3.connect(KAT)
    v_baze = dict(kat.execute('select inn, chas_poyas from company'))
    neverno = [(c['region'], v_baze[c['inn']], NEZAV.get(c['region'])) for c in K
               if v_baze[c['inn']] != NEZAV.get(c['region'])]
    proverit(not neverno, 'часовые пояса всех 65 компаний сходятся с независимой таблицей %s'
             % (neverno[:5] or ''))

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}

    def skolko(k, **para):
        para['size'] = '100'
        t = k.get(PUT + '/centro?' + urlencode(para)).text
        m = re.search(r'Компании \d+–\d+ из (\d+)', t)
        return int(m.group(1)) if m else (0 if 'Компании не найдены' in t else -1)

    kont = d['kontakty']
    with TestClient(vnutr) as k:
        t = k.get(PUT + '/centro').text
        dlg = re.search(r'<dialog id="allFilters">.*?</dialog>', t, re.S).group(0)
        for imya in ('bitrix', 'rabochee', 'rol_lpr', 'perezvon', 'lpr_fio', 'baza'):
            proverit('name="%s"' % imya in dlg, 'в диалоге фильтр %s' % imya)
        stroka = t.split('<dialog')[0]
        proverit('name="perezvon"' in stroka and 'name="rabochee"' in stroka,
                 'перезвон и рабочее время — и в основной строке')
        proverit('Есть номер в битриксе' in dlg, 'название: «Есть номер в битриксе»')
        print()
        n = skolko(k, bitrix='1')
        proverit(n == 6, 'есть номер в битриксе: %d (ждём 6)' % n)
        ozh = len({x['inn'] for x in kont if x['person']})
        n = skolko(k, lpr_fio='1')
        proverit(n == ozh, 'ЛПР с ФИО: %d (ждём %d)' % (n, ozh))
        for rol in sorted({x['role'] for x in kont}):
            ozh = len({x['inn'] for x in kont if x['role'] == rol})
            n = skolko(k, rol_lpr=rol)
            proverit(n == ozh, 'роль %-22s %2d (ждём %d)' % (rol, n, ozh))
        n = skolko(k, baza='База 1')
        proverit(n == 65, 'источник «База 1»: %d (ждём 65)' % n)
        seychas = datetime.datetime.utcnow()
        ozh = sum(1 for c in K if (lambda m: m.weekday() < 5 and 9 <= m.hour < 18)(
            seychas + datetime.timedelta(hours=NEZAV[c['region']])))
        n = skolko(k, rabochee='1')
        proverit(n == ozh, 'сейчас рабочее время (UTC %s): %d (ждём %d)' % (seychas.strftime('%H:%M %a'), n, ozh))
        # перезвоны: ставлю два во временную копию — на сегодня 23:59 и на вчера
        msk = seychas + datetime.timedelta(hours=3)
        admin = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
        sales.save_call(admin, K[0]['inn'], 'v_rabote', msk.strftime('%Y-%m-%dT23:59'), 'проверка перезвона')
        sales.save_call(admin, K[1]['inn'], 'v_rabote',
                        (msk - datetime.timedelta(days=1)).strftime('%Y-%m-%dT10:00'), 'проверка перезвона')
        n = skolko(k, perezvon='segodnya')
        proverit(n == 1, 'перезвонить сегодня: %d (ждём 1)' % n)
        n = skolko(k, perezvon='prosrocheno')
        proverit(n == 1, 'просроченные перезвоны: %d (ждём 1)' % n)
        n = skolko(k)
        proverit(n == 63, 'без фильтра «Вся очередь» не показывает обработанные: %d (ждём 63)' % n)
        t = k.get(PUT + '/centro?perezvon=segodnya').text
        m = re.search(r'<tr data-href="([^"]*)"', t)
        ss = (m.group(1) if m else '').replace('&amp;', '&')
        o = k.get(ss) if ss else None
        proverit(o is not None and o.status_code == 200,
                 'из списка перезвонов карточка открывается: %s -> %s' % (ss, o.status_code if o else None))
        n = skolko(k, segment='3 пищевые', has_tech='1', lpr_fio='1')
        ozh = sum(1 for c in K if '3 пищевые' in c['segment'] and c['n_tech'] > 0
                  and any(x['person'] for x in kont if x['inn'] == c['inn']))
        proverit(n == ozh, 'сочетание «пищевые + техЛПР + ФИО»: %d (ждём %d)' % (n, ozh))
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

os.makedirs(BEKAP, exist_ok=True)
log = []
nado = sdelano = 0

# ------------------------------------------------------------- 0. каталог: пояс и ФИО
shutil.copy2(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
k = sqlite3.connect(KAT)
kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
for imya, opr in (('chas_poyas', 'INTEGER'), ('chas_poyas_kak', 'TEXT'),
                  ('lpr_s_fio', 'INTEGER NOT NULL DEFAULT 0')):
    if imya not in kol:
        k.execute('ALTER TABLE company ADD COLUMN %s %s' % (imya, opr))
nerasp = []
for inn, region in k.execute('select inn, region from company').fetchall():
    sm, kak = poyas(region)
    if 'не распознан' in kak:
        nerasp.append(region)
    k.execute('UPDATE company SET chas_poyas=?, chas_poyas_kak=? WHERE inn=?', (sm, kak, inn))
k.execute("UPDATE company SET lpr_s_fio=(SELECT COUNT(*) FROM contact ct WHERE ct.inn=company.inn "
          "AND COALESCE(ct.person,'')<>'')")
k.commit()
log.append('[ок] каталог: пояс у всех, не распознано по региону %d %s; ЛПР с ФИО у %d компаний'
           % (len(nerasp), sorted(set(nerasp)), k.execute('select count(*) from company where lpr_s_fio>0').fetchone()[0]))
k.close()


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
        j = len(t)
        for kon in ('\n@router.', '\ndef '):
            jj = t.find(kon, i + len(funkciya))
            if jj >= 0:
                j = min(j, jj)
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
# ------------------------------------------------------------- 1. сервер
pravka(RCS, '''    okved_kod = params.get("okved_kod", "").strip()
''', '''    okved_kod = params.get("okved_kod", "").strip()
    rol_lpr = params.get("rol_lpr", "").strip()
    baza_f = params.get("baza", "").strip()
    perezvon = params.get("perezvon", "").strip()
''', 'фильтры: чтение роли, источника, перезвона', priznak='rol_lpr = params.get', funkciya='def _matches(')
pravka(RCS, '''        if not call_status and company.get("call_result") in sales.CALL_RESULT_CHOICES:''',
       '''        # перезвон ищется ПО ВСЕМ вкладкам: перезвоны стоят у «Взял в работу», и во
        # «Всей очереди» без этого фильтр был бы всегда пуст
        if not call_status and not perezvon and company.get("call_result") in sales.CALL_RESULT_CHOICES:''',
       'фильтры: перезвон смотрит во все вкладки', priznak='and not perezvon and', funkciya='def _matches(')
pravka(RCS, '''        if okved_kod and not _okved_sovpal(company, okved_kod):
            continue
''', '''        if okved_kod and not _okved_sovpal(company, okved_kod):
            continue
        if params.get("bitrix") == "1" and not company.get("bitrix_kc"):
            continue
        if params.get("lpr_fio") == "1" and not company.get("lpr_s_fio"):
            continue
        if rol_lpr and rol_lpr not in [r.strip() for r in str(company.get("lpr_roli") or "").split(",")]:
            continue
        if baza_f and baza_f not in [b.strip() for b in str(company.get("bazy") or "").split("|")]:
            continue
        if params.get("rabochee") == "1" and not _rabochee_vremya(company):
            continue
        if perezvon and not _perezvon_sovpal(company, perezvon):
            continue
''', 'фильтры: битрикс, ФИО, роль, источник, рабочее время, перезвон', priznak='_rabochee_vremya(company)',
       funkciya='def _matches(')
nado += 1
t = io.open(RCS, encoding='utf-8').read()
if 'def _rabochee_vremya' in t:
    sdelano += 1
    log.append('[уже] функции рабочего времени и перезвона')
else:
    pisat(RCS, t.rstrip('\n') + '''


def _rabochee_vremya(company: dict) -> bool:
    """Сейчас у компании рабочее время: 9:00–18:00 по её местному времени, пн–пт.
    Пояс — chas_poyas (смещение от UTC, проставлено по региону); нет — по Москве."""
    try:
        smeshchenie = int(company.get("chas_poyas"))
    except (TypeError, ValueError):
        smeshchenie = 3
    mestnoe = datetime.datetime.utcnow() + datetime.timedelta(hours=smeshchenie)
    return mestnoe.weekday() < 5 and 9 <= mestnoe.hour < 18


def _perezvon_sovpal(company: dict, rezhim: str) -> bool:
    """Перезвон по «Следующему контакту». Время в поле — московское (вводят продавцы)."""
    nk = str(company.get("next_contact_at") or "").strip()
    if not nk:
        return False
    try:
        kogda = datetime.datetime.fromisoformat(nk.replace("Z", "+00:00"))
    except ValueError:
        return False
    if kogda.tzinfo is not None:
        kogda = (kogda.astimezone(datetime.timezone.utc) + datetime.timedelta(hours=3)).replace(tzinfo=None)
    seychas = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    if rezhim == "segodnya":
        return kogda.date() == seychas.date()
    if rezhim == "prosrocheno":
        return kogda < seychas
    return True
''')
    sdelano += 1
    log.append('[ок] функции рабочего времени и перезвона')
pravka(RCS, '''    visible = _matches(visible, request)
''', '''    vidimye_vladeltsu = list(visible)   # для счётчиков у фильтров: «из ваших компаний»
    visible = _matches(visible, request)
''', 'счётчики фильтров — по компаниям пользователя', priznak='vidimye_vladeltsu = list(visible)',
       funkciya='def centro(')
pravka(RCS, r'    # для фильтров под базу Meyer:.*?    choices\["est_oborudovanie"\]',
       '''    # Счётчики у фильтров под базу Meyer — по компаниям, которые видит ЭТОТ пользователь
    # (у продавца — его очередь), а не по всей базе.
    счёт_сегм: dict[str, int] = {}
    счёт_ролей: dict[str, int] = {}
    счёт_баз: dict[str, int] = {}
    опис_баз: dict[str, str] = {}
    for company in vidimye_vladeltsu:
        for сегм in str(company.get("segment") or "").split("|"):
            if сегм.strip():
                счёт_сегм[сегм.strip()] = счёт_сегм.get(сегм.strip(), 0) + 1
        for роль in str(company.get("lpr_roli") or "").split(","):
            if роль.strip():
                счёт_ролей[роль.strip()] = счёт_ролей.get(роль.strip(), 0) + 1
        базы = [b.strip() for b in str(company.get("bazy") or "").split("|")]
        опис = [o.strip() for o in str(company.get("bazy_opisanie") or "").split("|")]
        for i_б, база in enumerate(базы):
            if база:
                счёт_баз[база] = счёт_баз.get(база, 0) + 1
                опис_баз.setdefault(база, опис[i_б] if i_б < len(опис) else "")
    choices["segment"] = sorted(счёт_сегм.items())
    choices["rol_lpr"] = sorted(счёт_ролей.items(), key=lambda x: -x[1])
    choices["baza"] = [(b, n, опис_баз.get(b, "")) for b, n in sorted(счёт_баз.items())]
    choices["has_tech_n"] = sum(1 for c in vidimye_vladeltsu if c.get("has_tech"))
    choices["lpr_mobilnyy_n"] = sum(1 for c in vidimye_vladeltsu if c.get("lpr_mobilnyy"))
    choices["lpr_fio_n"] = sum(1 for c in vidimye_vladeltsu if c.get("lpr_s_fio"))
    choices["bitrix_n"] = sum(1 for c in vidimye_vladeltsu if c.get("bitrix_kc"))
    choices["rabochee_n"] = sum(1 for c in vidimye_vladeltsu if _rabochee_vremya(c))
    choices["perezvon_segodnya_n"] = sum(1 for c in vidimye_vladeltsu if _perezvon_sovpal(c, "segodnya"))
    choices["perezvon_prosrocheno_n"] = sum(1 for c in vidimye_vladeltsu if _perezvon_sovpal(c, "prosrocheno"))
    choices["est_oborudovanie"]''', 'счётчики: роли, источники, битрикс, ФИО, рабочее время, перезвоны',
       priznak='choices["rol_lpr"]', regex=True, funkciya='def centro(')

# ------------------------------------------------------------- 2. шаблон
C = os.path.join(T, 'centro.html')
RABOCHEE_TITLE = ('9:00–18:00 по местному времени компании, пн–пт. Часовой пояс — по региону; '
                  'если регион не распознан — по Москве')
pravka(C, r'<section class="filter-section">\s*<h3>Сегмент и ЛПР</h3>.*?</section>',
       '''<section class="filter-section">
        <h3>Сегмент и ЛПР</h3>
        <div class="filter-grid">
          <label>Сегмент<select name="segment"><option value="">Любой</option>{% for value, n in choices.segment %}<option value="{{ value }}" {% if request.query_params.get('segment') == value %}selected{% endif %}>{{ value }} — {{ n }}</option>{% endfor %}</select></label>
          <label>Роль ЛПР<select name="rol_lpr"><option value="">Любая</option>{% for value, n in choices.rol_lpr %}<option value="{{ value }}" {% if request.query_params.get('rol_lpr') == value %}selected{% endif %}>{{ value }} — {{ n }}</option>{% endfor %}</select></label>
          <label>Источник базы<select name="baza"><option value="">Любой</option>{% for value, n, op in choices.baza %}<option value="{{ value }}" title="{{ op }}" {% if request.query_params.get('baza') == value %}selected{% endif %}>{{ value }}{% if op %} — {{ op }}{% endif %} · {{ n }}</option>{% endfor %}</select></label>
        </div>
        <div class="checks-grid" style="margin-top:10px">
          <label class="check"><input type="checkbox" name="has_tech" value="1" {% if request.query_params.get('has_tech') == '1' %}checked{% endif %}> Есть техЛПР · {{ choices.has_tech_n }}</label>
          <label class="check"><input type="checkbox" name="lpr_mobilnyy" value="1" {% if request.query_params.get('lpr_mobilnyy') == '1' %}checked{% endif %}> ЛПР с мобильным · {{ choices.lpr_mobilnyy_n }}</label>
          <label class="check"><input type="checkbox" name="lpr_fio" value="1" {% if request.query_params.get('lpr_fio') == '1' %}checked{% endif %}> ЛПР с ФИО · {{ choices.lpr_fio_n }}</label>
          <label class="check"><input type="checkbox" name="has_purchaser" value="1" {% if request.query_params.get('has_purchaser') == '1' %}checked{% endif %}> Закупщик / снабжение</label>
          <label class="check"><input type="checkbox" name="bitrix" value="1" {% if request.query_params.get('bitrix') == '1' %}checked{% endif %}> Есть номер в битриксе · {{ choices.bitrix_n }}</label>
        </div>
      </section>

      <section class="filter-section">
        <h3>Когда звонить</h3>
        <div class="filter-grid">
          <label>Перезвон<select name="perezvon"><option value="">Любой</option><option value="segodnya" {% if request.query_params.get('perezvon') == 'segodnya' %}selected{% endif %}>Перезвонить сегодня · {{ choices.perezvon_segodnya_n }}</option><option value="prosrocheno" {% if request.query_params.get('perezvon') == 'prosrocheno' %}selected{% endif %}>Просроченные · {{ choices.perezvon_prosrocheno_n }}</option></select></label>
        </div>
        <div class="checks-grid" style="margin-top:10px">
          <label class="check" title="''' + RABOCHEE_TITLE + '''"><input type="checkbox" name="rabochee" value="1" {% if request.query_params.get('rabochee') == '1' %}checked{% endif %}> Сейчас рабочее время у компании · {{ choices.rabochee_n }}</label>
        </div>
      </section>''', 'диалог: роль, источник, ФИО, битрикс; раздел «Когда звонить»', priznak='name="rol_lpr"', regex=True)
pravka(C, r'(<option value="">Все сегменты</option>.*?</select>\{% endif %\})',
       '\\1\n  <select name="perezvon" title="Перезвоны по полю «Следующий контакт» — из всех вкладок">'
       '<option value="">Перезвон: любой</option>'
       '<option value="segodnya" {% if request.query_params.get(\'perezvon\') == \'segodnya\' %}selected{% endif %}>'
       'Перезвонить сегодня · {{ choices.perezvon_segodnya_n }}</option>'
       '<option value="prosrocheno" {% if request.query_params.get(\'perezvon\') == \'prosrocheno\' %}selected{% endif %}>'
       'Просроченные · {{ choices.perezvon_prosrocheno_n }}</option></select>\n'
       '  <label class="check" title="' + RABOCHEE_TITLE + '"><input type="checkbox" name="rabochee" value="1" '
       '{% if request.query_params.get(\'rabochee\') == \'1\' %}checked{% endif %}> Сейчас рабочее время</label>',
       'основная строка: перезвон и рабочее время', priznak='<option value="">Перезвон: любой</option>', regex=True)

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
lg.write('\n===== перезапуск: фильтры Meyer 2 %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
import tempfile  # noqa: E402
_v = os.path.join(tempfile.gettempdir(), 'proverka_filtrov2.db')
if os.path.exists(_v):
    os.remove(_v)
print('временная копия базы продаж: %s' % ('убрана' if not os.path.exists(_v) else 'ОСТАЛАСЬ'))
