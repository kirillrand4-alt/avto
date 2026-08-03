# -*- coding: utf-8 -*-
"""Залить добытое в песочнице в панель владельца: людей и их контакты.

ЗАЧЕМ. Всё, что найдено поиском по должности и обратным ходом, лежит в песочнице. Панель
про это не знает, и два следствия сразу: владелец не видит добытого, а серверный обратный
ход (`lpr_serp back`) берёт цели из таблицы `person` панели — то есть при живом запасе в
две тысячи имён он через несколько заданий упрётся в пустоту.

КАК. Раннер исполняет питон рассыльщика, и импорт сервисов панели падает на `bcrypt` —
поэтому пишем сырым `sqlite3`, как это делалось и раньше. Ничего не удаляем и не
перезаписываем: только вставка, и только того, чего ещё нет по паре «ИНН + человек +
контакт». Источник назван явно и отдельно от чужих, чтобы откатить можно было одним
запросом.

ОСТОРОЖНО С ПРИЗНАКОМ `is_tech`. Он поднимает человека в панели наверх, и ставить его надо
только там, где должность действительно техническая, а не «неясно». Роль берём из той же
таблицы ролей, что и свод.
"""
import base64, csv, json, os, re, sys
sys.path.insert(0, '/home/user/avto/seo-texts/server')
sys.path.insert(0, '/home/user/avto/seo-texts')
import run_on_server as R
from svesti_vseh_lyudej import rol_ves, nomer, vid_nomera, fio_ok

TEH = {'главный инженер', 'главный механик или энергетик', 'компрессорное хозяйство',
       'производство', 'технолог'}
ISTOCHNIK = 'поиск-ЛПР-3с-песочница'

lyudi = {}
for ln in open('lpr-pesochnica.jsonl', encoding='utf-8'):
    if not ln.strip():
        continue
    z = json.loads(ln)
    for ch in z.get('lyudi') or []:
        if not fio_ok(ch['fio']) and ch.get('vid_imeni') != 'фамилия с инициалами':
            continue
        k = (z['inn'], ch['fio'].strip().lower())
        if k in lyudi:
            continue
        _v, rol = rol_ves(ch['dolzhnost'])
        lyudi[k] = {'inn': z['inn'], 'person': ch['fio'].strip(),
                    'position': (ch['dolzhnost'] or '')[:120], 'role': rol,
                    'phone': '', 'phone_type': '', 'email': '',
                    'source_url': (ch.get('ssylka') or '')[:300],
                    'source': ISTOCHNIK, 'is_tech': 1 if rol in TEH else 0}

# Контакты обратного хода кладём В ТЕХ ЖЕ строках человека — так панель показывает их вместе.
nk = 0
if os.path.exists('lpr-obratnyy.jsonl'):
    for ln in open('lpr-obratnyy.jsonl', encoding='utf-8'):
        if not ln.strip():
            continue
        z = json.loads(ln)
        k = (z['inn'], (z['fio'] or '').strip().lower())
        if k not in lyudi:
            continue
        for c in z.get('kontakty') or []:
            zn = (c.get('znachenie') or '').strip()
            if c.get('tip') == 'телефон':
                n = nomer(zn)
                if n and not lyudi[k]['phone']:
                    lyudi[k]['phone'] = n
                    lyudi[k]['phone_type'] = vid_nomera(n)
                    lyudi[k]['source_url'] = (c.get('ssylka') or '')[:300]
                    nk += 1
            elif '@' in zn and not lyudi[k]['email']:
                lyudi[k]['email'] = zn.lower()
                nk += 1

zapisi = list(lyudi.values())
print(f'людей к заливке {len(zapisi)}, из них с контактом {nk}, '
      f'технических {sum(1 for x in zapisi if x["is_tech"])}', file=sys.stderr)
if '--suho' in sys.argv:
    for x in zapisi[:5]:
        print('  ', x, file=sys.stderr)
    sys.exit()

SCRIPT = r'''
import sqlite3, json, sys, os
dannye = json.load(open(r'C:\sender\_ops\3s_lyudi.json', encoding='utf-8'))
cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
est = set()
for inn, p, ph, em in cx.execute(
        "select coalesce(inn,''), lower(coalesce(person,'')), coalesce(phone,''), "
        "coalesce(email,'') from person"):
    est.add((inn, p, ph, em))
novyh = obnovleno = 0
for r in dannye:
    k = (r['inn'], r['person'].lower(), r['phone'], r['email'])
    if k in est:
        continue
    cx.execute(
        "insert into person(inn,person,position,role,phone,phone_type,email,"
        "source_url,source,is_tech) values(?,?,?,?,?,?,?,?,?,?)",
        (r['inn'], r['person'], r['position'], r['role'], r['phone'],
         r['phone_type'], r['email'], r['source_url'], r['source'], r['is_tech']))
    novyh += 1
cx.commit()
o = {'zalito': novyh, 'bylo_uzhe': len(dannye) - novyh,
     'vsego_person_stalo': cx.execute('select count(*) from person').fetchone()[0],
     'nashih': cx.execute("select count(*) from person where source=?",
                          (dannye[0]['source'],)).fetchone()[0]}
print(json.dumps(o, ensure_ascii=False))
'''
R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
    {'dest': r'C:\sender\_ops\3s_lyudi.json',
     'b64': base64.b64encode(json.dumps(zapisi, ensure_ascii=False).encode()).decode()},
    {'dest': r'C:\sender\_ops\3s_zalivka.py',
     'b64': base64.b64encode(SCRIPT.encode()).decode()}]}, timeout=600)
r = R.submit('enrich_contacts', {'op': 'panel_py',
                                 'script': r'C:\sender\_ops\3s_zalivka.py',
                                 'timeout': 600}, timeout=900)
d = r.get('data') or {}
print((d.get('stdout_tail') or d.get('stderr_tail') or '')[-800:])
