# -*- coding: utf-8 -*-
r"""База для КЦ (07.10, запрос КЦ-шников через владельца): напитки, переработка молока, сыры,
хлебокомбинаты, корма, мясокомбинаты; выручка от 3 млрд. Шаг 1 — отбор компаний.

Как для файлов Meyer: сегмент по ОСНОВНОМУ ОКВЭД (meyer_baza.попадает_осн), источники компаний —
enrich.db + obzvon-index.db (161k) и park_panel.db; без конкурентов и ликвидированных.
Выручка: ФНС revexp (СумДоход), иначе выручка из базы. Запреты панели (sender.db, scope=inn).
Выход (fsync): C:\sender\server\kc-pishch-otbor.json -> копия на дроп. Печатает счёт по сегментам.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
from meyer_baza import коды, попадает_осн, имя_чисто  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХОД = os.path.join(DIR, 'kc-pishch-otbor.json')
ПОРОГ = 3e9
СЕГМЕНТЫ = [  # порядок = приоритет при пересечении
    ('сыры', ('10.51.4',)),
    ('переработка молока', ('10.51',)),
    ('мясокомбинаты', ('10.11', '10.13')),
    ('хлебокомбинаты', ('10.71',)),
    ('корма', ('10.91', '10.92')),
    ('напитки', ('11.',)),
]


def выручка(v):
    try:
        f = float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return 0
    return f if f > 0 else 0


def main():
    комп = {}

    def взять(inn, имя, рег, сайт, ок, окв, выр, год, конк, стат, откуда):
        inn = str(inn or '').strip()
        if not inn or конк or 'ликвид' in (стат or '').lower() or re.search(r'LIQUIDAT|BANKRUPT', стат or '', re.I):
            return
        осн = (коды(ок)[:1] or [''])[0]
        все = коды(ок, окв)
        сегм = [с for с, п in СЕГМЕНТЫ if попадает_осн(осн, все, п)]
        if 'сыры' in сегм and 'переработка молока' in сегм:
            сегм.remove('переработка молока')
        if not сегм:
            return
        к = комп.setdefault(inn, {'inn': inn, 'имя': имя_чисто(имя), 'регион': рег or '', 'сайт': сайт or '',
                                  'осн': осн, 'все': все, 'сегм': сегм[0], 'выр_база': 0, 'год_база': '',
                                  'статус': стат or '', 'откуда': []})
        if откуда not in к['откуда']:
            к['откуда'].append(откуда)
        if выручка(выр) > к['выр_база']:
            к['выр_база'], к['год_база'] = выручка(выр), str(год or '')
        if not к['сайт'] and сайт:
            к['сайт'] = сайт

    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    for р in c.execute(
            "select c.inn, coalesce(nullif(c.name,''), o.name_short, ''), coalesce(nullif(c.region,''), o.region, ''), "
            "coalesce(nullif(c.site,''), o.sites, ''), coalesce(nullif(c.okved,''), o.okved_main, ''), "
            "coalesce(c.okved_all,'')||' '||coalesce(o.okved_all_codes,''), "
            "case when coalesce(c.revenue_rub,0)>0 then c.revenue_rub else o.revenue_rub end, "
            "case when coalesce(c.revenue_rub,0)>0 then c.revenue_year else o.god_otch end, "
            "coalesce(c.is_competitor,0), coalesce(nullif(c.status_egrul,''), o.status, '') "
            'from companies c left join obz.obzvon o on o.inn=c.inn '
            'union all '
            "select o.inn, coalesce(o.name_short,''), coalesce(o.region,''), coalesce(o.sites,''), "
            "coalesce(o.okved_main,''), coalesce(o.okved_all_codes,''), o.revenue_rub, o.god_otch, 0, coalesce(o.status,'') "
            'from obz.obzvon o where not exists (select 1 from companies c where c.inn=o.inn)'):
        взять(*р, откуда='база обзвона/enrich')
    c.close()
    c = sqlite3.connect('file:%s?mode=ro' % os.path.join(ДРОП, 'park_panel.db'), uri=True)
    for р in c.execute("select inn, nazvanie, region, '', okved, coalesce(okved_vse,'')||' '||coalesce(okved_kody,''), "
                       "vyruchka, '', 0, coalesce(status_egrul,'') from predpriyatie"):
        взять(*р, откуда='парк компрессорного оборудования')
    c.close()
    # доход ФНС
    z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
    for zi in z.infolist():
        with z.open(zi) as fh:
            for ev, el in ET.iterparse(fh, events=('end',)):
                if not el.tag.endswith('Документ'):
                    continue
                inn = д = None
                for ch in el:
                    if 'СведНП' in ch.tag:
                        inn = ch.get('ИННЮЛ') or ch.get('ИННФЛ')
                    elif 'ДохРасх' in ch.tag:
                        д = ch.get('СумДоход')
                if inn in комп and д:
                    комп[inn]['доход_фнс'] = выручка(д)
                el.clear()
    # запреты панели
    c = sqlite3.connect(r'file:C:\sender\sender.db?mode=ro', uri=True, timeout=60)
    т = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name like '%suppress%'")][0]
    кол = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
    зап = {}
    for r in c.execute("select * from %s where scope='inn'" % т):
        x = dict(zip(кол, r))
        rs, src = x.get('reason') or '', x.get('source') or ''
        зап[str(x['value'])] = ('идёт сделка' if rs == 'deal_in_progress' or 'сделка' in src.lower() else
                                'конкурент' if 'competitor' in rs or 'конкурент' in rs else rs)
    c.close()
    for к in комп.values():
        к['выручка'] = к.get('доход_фнс') or к['выр_база']
        к['выручка_откуда'] = 'ФНС (доход 2025)' if к.get('доход_фнс') else ('база, %s' % к['год_база'] if к['выр_база'] else '')
        к['запрет'] = зап.get(к['inn'], '')
    with io.open(ВЫХОД, 'w', encoding='utf-8') as f:
        json.dump(комп, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'kc-pishch-otbor.json'))
    сч = {}
    for к in комп.values():
        с = сч.setdefault(к['сегм'], {'всего': 0, 'с_выручкой': 0, '>=3млрд': 0, '>=3млрд_без_запретов': 0,
                                      '1-3млрд_без_запретов': 0, 'запреты_среди_>=3млрд': {}})
        с['всего'] += 1
        с['с_выручкой'] += bool(к['выручка'])
        if к['выручка'] >= ПОРОГ:
            с['>=3млрд'] += 1
            if к['запрет']:
                с['запреты_среди_>=3млрд'][к['запрет']] = с['запреты_среди_>=3млрд'].get(к['запрет'], 0) + 1
            else:
                с['>=3млрд_без_запретов'] += 1
        elif к['выручка'] >= 1e9 and not к['запрет']:
            с['1-3млрд_без_запретов'] += 1
    print('===ИТОГ===')
    print(json.dumps({'компаний': len(комп), 'по_сегментам': сч,
                      'итого_>=3млрд_без_запретов': sum(с['>=3млрд_без_запретов'] for с in сч.values())},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
