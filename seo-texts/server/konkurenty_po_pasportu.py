# -*- coding: utf-8 -*-
r"""Конкуренты, видимые в СОБСТВЕННОМ паспорте, но не помеченные флагом.

ПОВОД (26.08). ООО «Энергоремкомплект» (ИНН 6679054575, erk-ekb.ru) получило
письмо кампании 10 и ответило: «мы тоже занимаемся поршневыми компрессорами и
производим запасные части к ним». Разбор цепочки:

  * ступень 1 (ОКВЭД 28.12/28.13 основным) промахнулась честно — у них 25.62
    «обработка металлических изделий», компрессорного кода нет вовсе;
  * ступень 2 (провайдер-судья по сайту, is_compressor_maker) по компании НЕ
    проходила: обогащения не было, сайт нашёл xmlriver и подтвердил по ИНН;
  * а ПАСПОРТ, собранный за три дня до письма, перечислял в «продукции»
    винтовые и поршневые компрессоры и ЗИП к ним.

То есть улика лежала в нашей же базе, а загрузка в кампанию смотрела только на
companies.is_competitor. Это ступень 3: читать собственный паспорт.

Правило живёт в enrich_db.konkurent_po_pasportu — там же и оговорки: смотреть
можно только «продукцию» (соседнее «оборудование_линии» — то, чем компания
пользуется, а «разбор_КЦ» — наш вывод о потреблении сжатого воздуха, признак
КЛИЕНТА), и подрядчик, который СТРОИТ компрессорные станции, не конкурент.

    python konkurenty_po_pasportu.py           только замер, ничего не пишет
    python konkurenty_po_pasportu.py --gasit   + стоп-лист и флаг is_competitor
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import enrich_db as EDB  # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SND = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
ПРИЧИНА = 'конкурент по паспорту'
ОТЧЁТ = os.path.join(os.environ.get('TEMP_DIR', r'C:\sender\_tmp'),
                     'konk-po-pasportu.json')


def _iz_rassylki():
    s = sqlite3.connect('file:%s?mode=ro' % SND.replace('\\', '/'), uri=True)
    в_базе, в_935 = set(), set()
    for r in s.execute("select coalesce(inn,''), coalesce(extra_json,'') "
                       'from recipients'):
        инн = ''.join(x for x in str(r[0]) if x.isdigit())
        if not инн:
            continue
        в_базе.add(инн)
        if 'Партия 935' in (r[1] or ''):
            в_935.add(инн)
    писали = {''.join(x for x in str(r[0]) if x.isdigit())
              for r in s.execute("select inn from send_log where outcome='sent'")}
    стоп = {''.join(x for x in str(r[0]) if x.isdigit())
            for r in s.execute("select value from suppression where scope='inn'")}
    s.close()
    return в_базе, в_935, писали, стоп


def найти():
    в_базе, в_935, писали, стоп = _iz_rassylki()
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    итог = {'проверено_паспортов': 0, 'найдено': 0, 'по_признакам': {},
            'уже_помечены': 0, 'уже_в_стоп-листе': 0, 'НОВЫХ': 0,
            'новых_в_рассылке': 0, 'новых_в_935': 0, 'новым_уже_писали': 0}
    новые = []
    for r in c.execute(
            "select f.inn, coalesce(f.facts_json,'') fj, coalesce(k.name,'') name, "
            "coalesce(k.is_competitor,0) konk, coalesce(k.okved,'') okved, "
            "coalesce(k.site,'') site, coalesce(k.division,'') div "
            'from site_facts f left join companies k on k.inn=f.inn '
            "where coalesce(f.facts_json,'')<>''"):
        итог['проверено_паспортов'] += 1
        да, признаки = EDB.konkurent_po_pasportu(r['fj'])
        if not да:
            continue
        итог['найдено'] += 1
        for п in признаки:
            итог['по_признакам'][п] = итог['по_признакам'].get(п, 0) + 1
        инн = str(r['inn'])
        if str(r['konk'] or '').strip().lower() in ('1', 'true', 'да', 'yes'):
            итог['уже_помечены'] += 1
            continue
        if инн in стоп:
            итог['уже_в_стоп-листе'] += 1
            continue
        итог['НОВЫХ'] += 1
        итог['новых_в_рассылке'] += инн in в_базе
        итог['новых_в_935'] += инн in в_935
        итог['новым_уже_писали'] += инн in писали
        try:
            прод = json.loads(r['fj']).get('продукция')
        except Exception:  # noqa: BLE001
            прод = ''
        новые.append({'инн': инн, 'имя': r['name'][:60], 'сайт': r['site'][:40],
                      'оквэд': r['okved'][:34], 'напр': r['div'],
                      'признаки': признаки, 'в_935': инн in в_935,
                      'писали': инн in писали, 'улика': str(прод)[:200]})
    c.close()
    новые.sort(key=lambda x: (not x['писали'], not x['в_935']))
    return итог, новые


def гасить(новые):
    """Стоп-лист + флаг. Обратимо: строка стоп-листа помечена своей причиной.

    Пишем МЕЛКИМИ транзакциями по пять ИНН: enrich.db почти непрерывно держит
    `zenno_most --demon`, и одна длинная транзакция на семьдесят строк дважды
    упиралась в «database is locked», а пятёрки проскакивают между его кругами.
    """
    теперь = time.strftime('%Y-%m-%dT%H:%M:%S')
    d = {}
    s = sqlite3.connect(SND, timeout=90)
    s.execute('PRAGMA busy_timeout=90000')
    было = {''.join(x for x in str(r[0]) if x.isdigit())
            for r in s.execute("select value from suppression where scope='inn'")}
    ко = [r[1] for r in s.execute('PRAGMA table_info(suppression)')]
    поля = [k for k in ('scope', 'value', 'reason', 'source', 'created_at')
            if k in ко]
    добавлено = 0
    for x in новые:
        if x['инн'] in было:
            continue
        зн = {'scope': 'inn', 'value': x['инн'],
              'reason': '%s (%s)' % (ПРИЧИНА, ', '.join(x['признаки'])),
              'source': 'konkurenty_po_pasportu', 'created_at': теперь}
        s.execute('INSERT INTO suppression(%s) VALUES(%s)'
                  % (','.join(поля), ','.join('?' * len(поля))),
                  tuple(зн[k] for k in поля))
        добавлено += 1
    s.commit()
    s.close()
    d['добавлено_в_стоп-лист'] = добавлено

    e = sqlite3.connect(BD, timeout=90)
    e.execute('PRAGMA busy_timeout=90000')
    куски = [новые[i:i + 5] for i in range(0, len(новые), 5)]
    ок, мимо = 0, 0
    for кусок in куски:
        for _ in range(40):
            try:
                e.execute('BEGIN IMMEDIATE')
                for x in кусок:
                    e.execute('UPDATE companies SET is_competitor=1 WHERE inn=?',
                              (x['инн'],))
                    e.execute('INSERT INTO stage_log(inn, stage, detail, ts) '
                              'VALUES(?,?,?,?) ON CONFLICT(inn, stage) DO UPDATE '
                              'SET detail=excluded.detail, ts=excluded.ts',
                              (x['инн'], 'konk_pasport',
                               ','.join(x['признаки'])[:80], теперь))
                e.commit()
                ок += 1
                break
            except sqlite3.OperationalError:
                try:
                    e.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(3)
        else:
            мимо += 1
    d['кусков_записано'] = ок
    d['кусков_не_вышло'] = мимо
    d['всего_is_competitor'] = e.execute(
        'select count(*) from companies where is_competitor=1').fetchone()[0]
    e.close()
    return d


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    итог, новые = найти()
    os.makedirs(os.path.dirname(ОТЧЁТ), exist_ok=True)
    with open(ОТЧЁТ, 'w', encoding='utf-8') as fh:
        json.dump({'итог': итог, 'новые': новые}, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    if '--gasit' in sys.argv and новые:
        итог['погашено'] = гасить(новые)
    итог['примеры'] = новые[:10]
    итог['отчёт'] = ОТЧЁТ
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
