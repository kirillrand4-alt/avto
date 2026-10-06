# -*- coding: utf-8 -*-
import re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import analiz as A
print('===ИТОГ===')
for sid in ('82230','82500'):
    st, _, d = A.get('https://catalog.expocentr.ru/catalog.php?wyst_id=171&info_id=0&stand_id='+sid, timeout=30)
    for m in re.finditer(r'(Сайт|E-mail|Город|Телефон)', d):
        print(sid, m.group(1), re.sub(r'\s+',' ', d[m.start()-80:m.start()+250]).replace('\n',' '))
        print('--')
