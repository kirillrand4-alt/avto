# -*- coding: utf-8 -*-
r"""База КЦ: полнота отбора. В нашей базе мало крупных (кормов всего 18 компаний). Берём всех
юрлиц с доходом 2025 >= 3 млрд из открытых данных ФНС (revexp) и смотрим, у кого из них ОКВЭД
нам известен (enrich/обзвон/парк), а кого в наших базах нет вовсе — тем нужен ОКВЭД (DaData).
Выход (fsync): C:\sender\server\kc-pishch-probel.json -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET
import zipfile

DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХОД = os.path.join(DIR, 'kc-pishch-probel.json')
ПОРОГ = 3e9


def main():
    доход = {}
    z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
    for zi in z.infolist():
        with z.open(zi) as fh:
            for ev, el in ET.iterparse(fh, events=('end',)):
                if not el.tag.endswith('Документ'):
                    continue
                inn = д = None
                for ch in el:
                    if 'СведНП' in ch.tag:
                        inn = ch.get('ИННЮЛ')
                    elif 'ДохРасх' in ch.tag:
                        д = ch.get('СумДоход')
                if inn and д:
                    try:
                        if float(д) >= ПОРОГ:
                            доход[inn] = float(д)
                    except ValueError:
                        pass
                el.clear()
    окв = {}
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    c.execute('create temp table t(inn text primary key)')
    c.executemany('insert into t values (?)', [(i,) for i in доход])
    for i, а, б in c.execute("select t.inn, coalesce(c.okved,''), coalesce(o.okved_main,'') from t "
                             'left join companies c on c.inn=t.inn left join obz.obzvon o on o.inn=t.inn'):
        к = (re.findall(r'\d{2}(?:\.\d{1,2}){0,3}', а + ' ' + б) or [''])[0]
        if к:
            окв[i] = к
    c.close()
    c = sqlite3.connect('file:%s?mode=ro' % os.path.join(ДРОП, 'park_panel.db'), uri=True)
    for i, о in c.execute('select inn, okved from predpriyatie'):
        i = str(i)
        if i in доход and i not in окв:
            к = (re.findall(r'\d{2}(?:\.\d{1,2}){0,3}', о or '') or [''])[0]
            if к:
                окв[i] = к
    c.close()
    нет = sorted(i for i in доход if i not in окв)
    o = {'доход_>=3млрд_юрлиц': len(доход), 'оквэд_известен': len(окв), 'нет_в_наших_базах': len(нет),
         'целевые_по_известному_оквэд': sum(1 for к in окв.values() if re.match(r'(10\.(51|11|13|71|91|92)|11\.)', к))}
    with io.open(ВЫХОД, 'w', encoding='utf-8') as f:
        json.dump({'итог': o, 'нет': {i: доход[i] for i in нет},
                   'известен': {i: [окв[i], доход[i]] for i in окв}}, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'kc-pishch-probel.json'))
    print('===ИТОГ===')
    print(json.dumps(o, ensure_ascii=False))


if __name__ == '__main__':
    main()
