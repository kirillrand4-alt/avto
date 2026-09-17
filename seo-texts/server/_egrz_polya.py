# -*- coding: utf-8 -*-
"""Все поля публичной записи ЕГРЗ — что реально отдаётся."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C  # noqa: E402

код, d = C._page("ExpertiseConclusionDate gt 2026-09-01T00:00:00Z", 0, top=1)
зап = (d.get('value') or [{}])[0]
print('===ИТОГ===')
print(json.dumps({'код': код, 'полей': len(зап), 'поля': sorted(зап.keys()),
                  'образец': {k: str(v)[:60] for k, v in list(зап.items())[:8]}},
                 ensure_ascii=False, indent=1))
