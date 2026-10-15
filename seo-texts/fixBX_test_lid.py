# -*- coding: utf-8 -*-
r"""fixBX (15.10): ОДИН тестовый лид в Битрикс24 из данных панели Meyer – по команде владельца.

Владелец 15.10: «Баданина Ксения Андреевна (id 7981) – тестируем на ней, создавай тестовый с источником "Маркетинг
подогнали"» (SOURCE_ID 149). Ссылка вебхука – из настроек сервера (C:\centro2\data\bitrix-webhook.secret), не печатается.

    python3 zapusk_na_servere.py fixBX_test_lid.py --razvedka      # только чтение: схема контактов и кандидат
    python3 zapusk_na_servere.py fixBX_test_lid.py --sozdat <ИНН>  # создать один лид (crm.lead.add)
"""
import io
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request

KAT = r'C:\centro2\data\meyer_baza1.db'
B = io.open(r'C:\centro2\data\bitrix-webhook.secret', encoding='utf-8').read().strip()
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row

PANEL = 'https://parsercompressor.online/obzvon-meyer/centro?inn='
GRUPPA = {'рентген': 11797, 'оба': 11797}          # «Группа товара (MEYER)»: Рентгены
GRUPPA_SORT = [('пластм', 11793), ('полимер', 11793), ('вторсыр', 11793), ('стекл', 11794), ('руд', 11795), ('угол', 11795),
               ('уголь', 11795), ('нерудн', 11795), ('минерал', 11795), ('соль', 11795), ('орех', 11791), ('сухофрукт', 11791),
               ('снек', 11791), ('ягод', 11790), ('овощ', 11790), ('фрукт', 11790), ('кофе', 11863), ('чай', 11863),
               ('трав', 11863), ('специ', 11863)]


def kandidaty():
    q = """SELECT c.inn, c.predpriyatie, c.region, p.value AS tel, p.person AS fio, p.position AS dolzhnost
           FROM company c JOIN contact p ON p.inn=c.inn
           WHERE c.meyer_verdikt='покупатель' AND c.meyer_verdikt_uverennost='высокая' AND c.meyer_verdikt_napravlenie='рентген'
             AND COALESCE(c.bitrix_kc,0)=0 AND COALESCE(TRIM(c.bitrix_metki),'')=''
             AND p.kind='phone' AND p.vid_nomera='мобильный' AND COALESCE(TRIM(p.person),'')<>''
             AND COALESCE(TRIM(p.chuzhoy_istochnik),'')='' AND (p.position LIKE '%енеральн%' OR p.position LIKE '%лавный инженер%' OR p.position LIKE '%ехническ%директор%' OR p.position LIKE '%иректор по производств%') AND p.position NOT LIKE '%продаж%'
           ORDER BY CAST(COALESCE(c.vyruchka, 0) AS REAL) DESC"""
    try:
        return [dict(r) for r in k.execute(q)]
    except sqlite3.OperationalError:
        return [dict(r) for r in k.execute(q.replace("CAST(COALESCE(c.vyruchka, 0) AS REAL) DESC", "c.inn"))]


def vyzov(metod, dannye=None, **params):
    q = urllib.parse.urlencode(params, doseq=True)
    zapros = urllib.request.Request(B + metod + '.json' + ('?' + q if q else ''),
                                    data=json.dumps(dannye).encode('utf-8') if dannye is not None else None,
                                    headers={'Content-Type': 'application/json'} if dannye is not None else {})
    try:
        with urllib.request.urlopen(zapros, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8') or '{}')


if '--razvedka' in sys.argv:
    for t in ('contact', 'person'):
        print(t, [r[1] for r in k.execute('PRAGMA table_info(%s)' % t)])
    for r in kandidaty()[:5]:
        print('кандидат: %s | %s | %s | %s | %s' % (r['inn'], r['predpriyatie'], r['region'], r['fio'], r['dolzhnost']))
    raise SystemExit(0)

if '--sozdat' in sys.argv:
    inn = sys.argv[sys.argv.index('--sozdat') + 1]
    c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
    lpr = next(r for r in kandidaty() if r['inn'] == inn)
    pochta = k.execute("SELECT value FROM contact WHERE inn=? AND kind='email' AND COALESCE(TRIM(chuzhoy_istochnik),'')='' "
                       "ORDER BY id LIMIT 1", (inn,)).fetchone()
    pole = vyzov('crm.lead.fields')['result']

    def net_id(kod):
        return next((x['ID'] for x in (pole.get(kod) or {}).get('items') or [] if str(x.get('VALUE', '')).strip().lower().startswith('нет')), None)
    chasti = lpr['fio'].split()
    napr = c.get('meyer_verdikt_napravlenie') or ''
    gruppa = GRUPPA.get(napr) or next((g for s, g in GRUPPA_SORT if s in ((c.get('otrasl') or '') + ' ' + (c.get('segment') or '')).lower()), 11789)
    pasp = '; '.join('%s: %s' % (n, str(c.get(kl))[:200]) for n, kl in (('Продукция', 'produkciya'), ('Масштаб', 'pasport_masshtab'))
                     if (c.get(kl) or '').strip())
    kom = '<br>'.join(x for x in (
        '<b>ТЕСТ интеграции панели обзвона Meyer — лид можно удалить.</b>',
        'Компания: %s; ИНН %s; %s' % (c['predpriyatie'], inn, c.get('region') or ''),
        'ЛПР: %s, %s' % (lpr['fio'], lpr['dolzhnost']),
        'Покупатель Meyer: да — %s. %s' % (napr, c.get('meyer_verdikt_pochemu') or ''),
        ('Паспорт: ' + pasp) if pasp else '',
        'Подробнее в панели: <a href="%s%s">%s%s</a>' % (PANEL, inn, PANEL, inn)) if x)
    f = {'TITLE': 'ТЕСТ — %s (обзвон Meyer)' % c['predpriyatie'], 'COMPANY_TITLE': c['predpriyatie'],
         'LAST_NAME': chasti[0] if chasti else '', 'NAME': chasti[1] if len(chasti) > 1 else '',
         'SECOND_NAME': ' '.join(chasti[2:]), 'POST': lpr['dolzhnost'],
         'PHONE': [{'VALUE': lpr['tel'], 'VALUE_TYPE': 'MOBILE'}],
         'SOURCE_ID': '149', 'SOURCE_DESCRIPTION': 'Панель обзвона Meyer', 'STATUS_ID': 'NEW', 'ASSIGNED_BY_ID': 7981,
         'COMMENTS': kom, 'UF_CRM_1711628077': gruppa, 'UF_CRM_68B688D287BE4': c.get('region') or '',
         'ADDRESS': c.get('adres') or c.get('address') or ''}
    if pochta:
        f['EMAIL'] = [{'VALUE': pochta[0], 'VALUE_TYPE': 'WORK'}]
    if (c.get('sayt') or '').strip():
        f['WEB'] = [{'VALUE': c['sayt'].strip(), 'VALUE_TYPE': 'WORK'}]
    for kod in ('UF_CRM_61B6C14B0E2A1', 'UF_CRM_1639366376'):
        if net_id(kod):
            f[kod] = net_id(kod)
    o = vyzov('crm.lead.add', {'fields': f, 'params': {'REGISTER_SONET_EVENT': 'Y'}})
    if o.get('error'):
        print('ОШИБКА:', o.get('error'), o.get('error_description'))
        raise SystemExit(2)
    lid = o['result']
    print('СОЗДАН ЛИД %s: https://bitrix-po22.ru/crm/lead/details/%s/' % (lid, lid))
    g = vyzov('crm.lead.get', id=lid)
    r = g.get('result') or {}
    print('прочитан обратно:', g.get('error') or {x: r.get(x) for x in ('TITLE', 'STATUS_ID', 'SOURCE_ID', 'ASSIGNED_BY_ID',
                                                                        'COMPANY_TITLE', 'POST', 'UF_CRM_1711628077')})
    print('заполнено полей: %d (%s)' % (len(f), ', '.join(sorted(f))))

if '--udalit' in sys.argv:
    # только ТЕСТОВЫЙ лид, созданный этим скриптом (владелец 15.10: «попробуй удалить, но только этот»)
    lid = sys.argv[sys.argv.index('--udalit') + 1]
    if lid != '379865':
        raise SystemExit('удалять можно только тестовый лид 379865')
    o = vyzov('crm.lead.delete', id=lid)
    print('УДАЛЕНИЕ ЛИДА %s: %s' % (lid, 'ОШИБКА %s %s' % (o.get('error'), o.get('error_description')) if o.get('error') else ('ок' if o.get('result') else o)))
