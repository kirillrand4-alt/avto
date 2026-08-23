# -*- coding: utf-8 -*-
r"""Возраст водяной метки доработки и появился ли круг."""
import json
import os
import time

д = {'сейчас': time.strftime('%H:%M:%S')}
м = r'C:\seostat\drop\zenno\dorabotka.metka'
if os.path.exists(м):
    try:
        з = float(open(м, encoding='utf-8').read().strip() or 0)
        д['метка_отстаёт_мин'] = int((time.time() - з) / 60)
    except Exception as e:  # noqa: BLE001
        д['метка'] = str(e)[:60]
else:
    д['метка'] = 'нет файла — доработка осмотрит ВЕСЬ кэш'
п = r'C:\seostat\drop\zenno\demon.out'
строки = [s.strip() for s in open(п, encoding='utf-8', errors='replace') if s.strip()]
д['последняя_строка'] = строки[-1][:150]
д['обновлён_сек_назад'] = int(time.time() - os.path.getmtime(п))
print(json.dumps(д, ensure_ascii=False, indent=1))
