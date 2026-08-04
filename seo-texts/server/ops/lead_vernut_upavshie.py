# -*- coding: utf-8 -*-
"""Вернуть в очередь тех, кого обход «прошёл» с ошибкой.

`отсечь_пройденные` считает пройденным любой ИНН, попавший в поток. Двадцать
целей пилота попали туда с `err: AttributeError` — то есть канал их не смотрел
вовсе, а очередь считает их закрытыми. Ошибка не есть пройденность.

Убираю из потока записи с `err`, прежний файл сохраняю рядом.
"""
import io, json, os, shutil, time
П = r'C:\seostat\drop\p25_leadership_stream.jsonl'
if not os.path.exists(П):
    print('потока нет:', П); raise SystemExit
строки = [s for s in io.open(П, encoding='utf-8', errors='replace') if s.strip()]
живые, битые = [], 0
for s in строки:
    try:
        з = json.loads(s)
    except Exception:
        живые.append(s); continue
    if з.get('err'):
        битые += 1
    else:
        живые.append(s)
бэкап = П + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
shutil.copy2(П, бэкап)
with io.open(П, 'w', encoding='utf-8') as ф:
    ф.writelines(живые); ф.flush(); os.fsync(ф.fileno())
print(f'записей было {len(строки)}, с ошибкой убрано {битые}, осталось {len(живые)}')
print('бэкап:', os.path.basename(бэкап))
