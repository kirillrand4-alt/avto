# -*- coding: utf-8 -*-
"""Третий проход: молочноконсервный в СФО и производство роботов."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C  # noqa: E402

СФО = ('04', '17', '19', '22', '24', '38', '42', '54', '55', '70')
o = {}


def поиск(имя, слова, с_даты, регионы=None, лимит=10):
    усл = ' or '.join("contains(tolower(ExpertiseObjectName),'%s')" % s for s in слова)
    флт = "ExpertiseConclusionDate gt %s and (%s)" % (с_даты, усл)
    if регионы:
        флт += ' and (%s)' % ' or '.join("SubjectRfCode eq '%s'" % r for r in регионы)
    код, d = C._page(флт, 0, top=лимит)
    зап = []
    for з in (d.get('value') or []) if isinstance(d, dict) else []:
        зап.append({'объект': (з.get('ExpertiseObjectName') or '')[:100],
                    'регион': (з.get('SubjectRf') or '')[:30],
                    'застройщик': (з.get('DeveloperOrganizationInfo') or '')[:95],
                    'дата': (з.get('ExpertiseConclusionDate') or '')[:10],
                    'вид': (з.get('WorkType') or '')[:24]})
    o[имя] = {'всего': d.get('@odata.count') if isinstance(d, dict) else None, 'записи': зап}


поиск('роботы_вся_страна', ['робот', 'манипулятор'], '2024-01-01T00:00:00Z')
поиск('молочноконсервный_везде', ['молочноконсерв', 'молочно-консерв', 'молочный комбинат',
                                  'молочно-консервн'], '2023-01-01T00:00:00Z')
поиск('консервный_СФО', ['консерв', 'сухое молоко', 'сгущ'], '2025-01-01T00:00:00Z', СФО)
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5600])
