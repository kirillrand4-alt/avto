# -*- coding: utf-8 -*-
r"""Точный кусок list_leads вокруг правила скрытия."""
import re

п = r'C:\sender\sender\store.py'
строки = open(п, encoding='utf-8', errors='replace').read().splitlines()
нач = next(i for i, s in enumerate(строки) if 'def list_leads' in s)
for i in range(нач, нач + 34):
    print('%4d %s' % (i + 1, строки[i][:130]))
