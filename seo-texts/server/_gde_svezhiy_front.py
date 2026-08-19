# -*- coding: utf-8 -*-
"""Кто новее: исходники или сборка. Ищем «убрать из ленты» по всем копиям."""
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
ИСКАТЬ = 'убрать из ленты'
итог = {'нашли': [], 'исходники': []}
корни = [r'C:\sender\sender\web', r'C:\sender\web']
for д in os.listdir(r'C:\sender'):
    if д.startswith('_bak-'):
        корни.append(os.path.join(r'C:\sender', д, 'sender', 'web'))
for к in корни:
    if not os.path.exists(к):
        continue
    for d, ds, fs in os.walk(к):
        ds[:] = [x for x in ds if x != 'node_modules']
        for f in fs:
            if not f.endswith(('.tsx', '.ts', '.js')) or f.endswith('.map'):
                continue
            п = os.path.join(d, f)
            try:
                if os.path.getsize(п) > 6 * 2**20:
                    continue
                t = io.open(п, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if ИСКАТЬ in t:
                итог['нашли'].append({
                    'файл': п, 'изменён': time.strftime(
                        '%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(п)))})
# даты исходников ленты
for к in корни:
    п = os.path.join(к, 'src', 'screens', 'Leads.tsx')
    if os.path.exists(п):
        итог['исходники'].append({'файл': п, 'изменён': time.strftime(
            '%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(п))),
            'строк': len(io.open(п, encoding='utf-8', errors='replace').read().splitlines())})
итог['dist_index'] = [{'файл': f, 'изменён': time.strftime(
    '%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(os.path.join(r'C:\sender\web\dist\assets', f))))}
    for f in sorted(os.listdir(r'C:\sender\web\dist\assets'))
    if f.endswith('.js') and not f.endswith('.map')][-4:]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
