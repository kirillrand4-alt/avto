# -*- coding: utf-8 -*-
"""Текст C:\\sender\\server\\storozh.py целиком."""
import io
import sys

sys.stdout.reconfigure(encoding='utf-8')
print(io.open(r'C:\sender\server\storozh.py', encoding='utf-8',
              errors='replace').read()[:5200])
