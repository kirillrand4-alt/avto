# -*- coding: utf-8 -*-
"""Журнал судьи: доля сбоев по видам и два полных примера."""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
п = r'C:\sender\server\prigovor-domenov.jsonl'
итог = {'файла_нет': not os.path.exists(п)}
if os.path.exists(п):
    строки = [json.loads(l) for l in
              io.open(п, encoding='utf-8', errors='replace') if l.strip()]
    итог = {'записей': len(строки), 'по_вердиктам': {}}
    примеры_сбоев = []
    for r in строки:
        в = r.get('verdikt', '?')
        итог['по_вердиктам'][в] = итог['по_вердиктам'].get(в, 0) + 1
        if в == 'сбой' and len(примеры_сбоев) < 3:
            примеры_сбоев.append({'домен': r.get('домен'),
                                  'почему': r.get('pochemu', '')[:220]})
    итог['примеры_сбоев'] = примеры_сбоев
    настоящие = [r for r in строки if r.get('verdikt') in
                 ('свой', 'группа', 'чужой', 'не_понять')]
    итог['примеры_вердиктов'] = [
        {'домен': r.get('домен'), 'имя': (r.get('name') or '')[:35],
         'вердикт': r['verdikt'], 'почему': r.get('pochemu', '')[:120]}
        for r in настоящие[:6]]
print(json.dumps(итог, ensure_ascii=False, indent=1))
