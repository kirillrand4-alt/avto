# -*- coding: utf-8 -*-
"""Дословно: как ai_quota сопоставляет получателей кампании (группа/сегмент)."""
import io
import sys

sys.stdout.reconfigure(encoding='utf-8')
t = io.open(r'C:\sender\sender\ai_quota.py', encoding='utf-8',
            errors='replace').read().splitlines()
print('\n'.join('%4d| %s' % (i + 1, t[i][:120]) for i in range(505, 615)))
