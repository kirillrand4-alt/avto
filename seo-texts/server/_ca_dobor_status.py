# -*- coding: utf-8 -*-
"""Статус ca_okved_dobor.py: прогресс, хвост последнего лога, замок. Только чтение."""
import glob, os
П = r'C:\sender\server\ca'
print('===ИТОГ===')
for имя in ('ca-okved-dobor-progress.json', 'ca_okved_dobor.lock'):
    п = os.path.join(П, имя)
    print(имя, open(п, encoding='utf-8', errors='replace').read()[:1500] if os.path.exists(п) else 'нет')
логи = sorted(glob.glob(os.path.join(П, 'ca_okved_dobor_*.log')), key=os.path.getmtime)
for л in логи[-2:]:
    print(os.path.basename(л), open(л, encoding='utf-8', errors='replace').read()[-1200:])
