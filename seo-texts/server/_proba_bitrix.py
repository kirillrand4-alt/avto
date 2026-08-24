# -*- coding: utf-8 -*-
r"""Проба: прячет ли лента лидов статус «в Bitrix» и виден ли он по фильтру."""
import json
import sys

sys.path.insert(0, r'C:\sender')
from sender import store as store  # модули панели живут пакетом

s = store.Store(r'C:\sender\sender.db') if hasattr(store, 'Store') else None
d = {}
if s is None:
    d['ошибка'] = 'нет класса Store'
else:
    лента = s.list_leads(limit=1000)
    d['в_ленте_всего'] = len(лента)
    d['в_ленте_с_bitrix'] = sum(1 for l in лента
                                if getattr(l, 'status', '') == 'in_bitrix')
    по_фильтру = s.list_leads(status='in_bitrix', limit=1000)
    d['по_фильтру_in_bitrix'] = len(по_фильтру)
    d['пример'] = [{'id': getattr(l, 'id', None),
                    'компания': str(getattr(l, 'company_name', ''))[:40]}
                   for l in по_фильтру[:3]]
print(json.dumps(d, ensure_ascii=False, indent=1))
