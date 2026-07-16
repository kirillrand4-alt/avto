#!/bin/bash
cd /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad
CSV=bitrix/export_file_2ov3pw9ju90trsle.csv
# по названию товара (IE_NAME, 2-я колонка) выделяем некомпрессорные типы
python3 - <<'PYEOF'
import csv, sys, json, re
from collections import Counter
csv.field_size_limit(sys.maxsize)
kinds = Counter(); samples = {}
with open('bitrix/export_file_2ov3pw9ju90trsle.csv', encoding='utf-8', errors='ignore') as f:
    rd = csv.reader(f, delimiter=';')
    header = next(rd)
    for row in rd:
        if len(row) < 2: continue
        name = row[1].lower()
        k = None
        if 'осушител' in name: k='осушитель'
        elif 'генератор' in name and ('азот' in name or 'кислород' in name): k='генератор газов'
        elif 'ресивер' in name: k='ресивер'
        elif 'фильтр' in name: k='фильтр'
        elif 'сепаратор' in name: k='сепаратор'
        elif 'компрессор' in name: k='компрессор'
        else: k='прочее/запчасти'
        kinds[k]+=1
        if k!='компрессор' and k!='прочее/запчасти' and len(samples.get(k,[]))<3:
            samples.setdefault(k,[]).append(row[1][:60])
print('ТОВАРОВ ПО ТИПАМ:')
for k,v in kinds.most_common(): print(f'  {v:6}  {k}')
json.dump({'kinds':dict(kinds),'samples':samples}, open('katalogi/bitrix-types.json','w'), ensure_ascii=False, indent=1)
PYEOF
echo "BITRIX-СКАН ГОТОВ"
