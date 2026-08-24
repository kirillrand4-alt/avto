# -*- coding: utf-8 -*-
r"""Проба: что осталось в ленте и что ушло в свои очереди."""
import json
import sys

sys.path.insert(0, r'C:\sender')
from sender import store as store  # noqa: E402

s = store.Store(r'C:\sender\sender.db')
лента = s.list_leads(limit=2000)
из_ленты = {}
for l in лента:
    к = getattr(l, 'status', '')
    из_ленты[к] = из_ленты.get(к, 0) + 1
свои = {}
for к in store.СКРЫТЫЕ_ИЗ_ЛЕНТЫ:
    свои[к] = len(s.list_leads(status=к, limit=2000))
print(json.dumps({'в_ленте_всего': len(лента), 'в_ленте_по_статусам': из_ленты,
                  'свои_очереди': свои,
                  'скрытые_из_ленты': list(store.СКРЫТЫЕ_ИЗ_ЛЕНТЫ)},
                 ensure_ascii=False, indent=1))
