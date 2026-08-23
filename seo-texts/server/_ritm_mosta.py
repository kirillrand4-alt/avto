# -*- coding: utf-8 -*-
r"""Ритм моста: времена последних кругов и сколько компаний в каждом."""
import json
import os

п = r'C:\seostat\drop\zenno\demon.out'
строки = [s.strip() for s in open(п, encoding='utf-8', errors='replace') if s.strip()]
вых = []
for s in строки[-14:]:
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    п_ = o.get('приём') or {}
    вых.append('%s  компаний %3s  страниц %5s  пустых %3s' %
               (o.get('время'), п_.get('компаний'), п_.get('страниц'),
                п_.get('пустых')))
print('\n'.join(вых))
