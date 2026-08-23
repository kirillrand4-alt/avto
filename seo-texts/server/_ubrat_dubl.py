# -*- coding: utf-8 -*-
r"""Убрать дубль lid_ssylka в C:\sender\server: две копии одного модуля разойдутся.

Прогон подписей импортирует его первым делом из своего каталога, и копия там
незаметно перебила бы панельную. Источник один — C:\sender\sender.
"""
import json
import os

п = r'C:\sender\server\lid_ssylka.py'
d = {'было': os.path.exists(п)}
if d['было']:
    os.remove(п)
d['осталось_в_панели'] = os.path.exists(r'C:\sender\sender\lid_ssylka.py')
print(json.dumps(d, ensure_ascii=False))
