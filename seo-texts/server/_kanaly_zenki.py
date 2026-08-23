# -*- coding: utf-8 -*-
r"""Каким выходом Зенка берёт сайты и сколько страниц привозит.

Если большинство компаний идёт через смену прокси и капчу, узкое место не в
числе потоков, а в сопротивлении сайтов: добавление потоков только упрёт
машину в процессор.
"""
import gzip
import json
import os
import time

КЕШ = r'C:\seostat\drop\pagecache'
свежие = []
порог = time.time() - 6 * 3600
with os.scandir(КЕШ) as it:
    for e in it:
        if not e.name.endswith('.json.gz'):
            continue
        try:
            if e.stat().st_mtime >= порог:
                свежие.append((e.stat().st_mtime, e.path))
        except OSError:
            pass
свежие.sort(reverse=True)
каналы, страниц, отказов, n = {}, 0, 0, 0
for _t, п in свежие[:400]:
    try:
        with gzip.open(п, 'rb') as f:
            д = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        continue
    n += 1
    к = str(д.get('kanal') or '(пусто)')[:24]
    каналы[к] = каналы.get(к, 0) + 1
    страниц += len(д.get('pages') or [])
    отказов += len(д.get('otkazy') or [])
print(json.dumps({
    'свежих_файлов_за_6ч': len(свежие),
    'проверено': n,
    'страниц_в_среднем': round(страниц / max(1, n), 1),
    'отказов_в_среднем': round(отказов / max(1, n), 1),
    'каналы': dict(sorted(каналы.items(), key=lambda x: -x[1])[:10]),
}, ensure_ascii=False, indent=1))
