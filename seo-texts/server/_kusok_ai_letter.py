# -*- coding: utf-8 -*-
"""Точный кусок ai_letter.py вокруг вычисления надёжности имени."""
import io, sys
sys.stdout.reconfigure(encoding='utf-8')
t = io.open(r'C:\sender\sender\ai_letter.py', encoding='utf-8', errors='replace').read().splitlines()
print('\n'.join('%4d| %s' % (i + 1, t[i][:130]) for i in range(1335, 1400)))
