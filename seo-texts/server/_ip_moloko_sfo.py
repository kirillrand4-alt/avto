# -*- coding: utf-8 -*-
"""Молочноконсервный комбинат в СФО: ищем прицельно."""
import json, sys
sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C

СФО = ('04','17','19','22','24','38','42','54','55','70')
o = {}
def поиск(имя, слова, с_даты, регионы=None, лимит=8):
    усл = ' or '.join("contains(tolower(ExpertiseObjectName),'%s')" % s for s in слова)
    флт = "ExpertiseConclusionDate gt %s and (%s)" % (с_даты, усл)
    if регионы:
        флт += ' and (%s)' % ' or '.join("SubjectRfCode eq '%s'" % r for r in регионы)
    код, d = C._page(флт, 0, top=лимит)
    o[имя] = {'всего': d.get('@odata.count') if isinstance(d, dict) else None,
              'записи': [{'объект': (з.get('ExpertiseObjectName') or '')[:95],
                          'регион': (з.get('SubjectRf') or '')[:28],
                          'застройщик': (з.get('DeveloperOrganizationInfo') or '')[:85],
                          'дата': (з.get('ExpertiseConclusionDate') or '')[:10],
                          'вид': (з.get('WorkType') or '')[:20]}
                         for з in (d.get('value') or [])][:6]}

поиск('молоко_СФО', ['молочн', 'молоко', 'сгущ', 'сухое молоко'], '2025-06-01T00:00:00Z', СФО)
поиск('любинский', ['любин'], '2023-01-01T00:00:00Z')
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
