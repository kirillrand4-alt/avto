# -*- coding: utf-8 -*-
"""Что лежит в полях ТЭП/эффективности/бюджета и в проектировщике."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C  # noqa: E402

код, d = C._page("ExpertiseConclusionDate gt 2026-09-10T00:00:00Z and "
                 "ExpertiseResultType eq 'Положительное заключение'", 0, top=8)
инт = ('ExpertiseObjectName', 'TechIssueInfo', 'TechIssues', 'EconomyEfficiencyInfo',
       'IsEconomyEfficiency', 'EBudgetCode', 'PlannerOrganizationInfo',
       'TechnicalCustomerOrganizationInfo', 'IsTpr', 'Tpr')
строки = []
for з in (d.get('value') or []):
    строки.append({k: (str(з.get(k))[:180] if з.get(k) not in (None, '') else '') for k in инт})
print('===ИТОГ===')
print(json.dumps({'код': код, 'записей': len(строки), 'строки': строки},
                 ensure_ascii=False, indent=1))
