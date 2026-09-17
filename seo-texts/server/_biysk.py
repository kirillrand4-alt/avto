# -*- coding: utf-8 -*-
"""Полная запись ЕГРЗ по найденному кандидату (Бийск) + сверка с маской карточки."""
import json, sys
sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C

флт = ("ExpertiseConclusionDate gt 2024-01-01T00:00:00Z and "
       "contains(tolower(ExpertiseObjectName),'торгово-бытовой комплекс')")
код, d = C._page(флт, 0, top=10)
вывод = []
for з in (d.get('value') or []):
    если = {k: (str(з.get(k))[:200] if з.get(k) else '')
            for k in ('ExpertiseObjectName', 'ExpertiseObjectAddress', 'SubjectRf',
                      'DeveloperOrganizationInfo', 'PlannerOrganizationInfo',
                      'ExpertiseConclusionDate', 'ExpertiseNumber', 'WorkType',
                      'FunctionalPurpose', 'ExpertiseResultType')}
    вывод.append(если)
print('===ИТОГ===')
print(json.dumps({'код': код, 'всего': d.get('@odata.count'), 'записи': вывод[:3]},
                 ensure_ascii=False, indent=1)[:4500])
