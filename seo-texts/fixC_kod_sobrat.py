# -*- coding: utf-8 -*-
"""fixC: собрать серверный fixC_kod.py из шаблона, вложив модуль правок и классификатор.
    python3 fixC_kod_sobrat.py <локальная копия centro_catalog.py (для md5 ожидаемых функций)>"""
import base64
import json
import os
import sys

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import fixC_kod_pravki as PR  # noqa: E402

t = open(sys.argv[1], encoding='utf-8').read()
zhdem = {}
for imya in PR.NOVYE:
    a, b = PR._najti_funkciyu(t, imya)
    zhdem[imya] = PR.md5(t[a:b].rstrip())
vlozh = {imya: base64.b64encode(open(os.path.join(D, imya), encoding='utf-8').read().encode('utf-8')).decode()
         for imya in ('fixC_kod_pravki.py', 'fixC_klass_kod.py')}
s = open(os.path.join(D, 'fixC_kod_shablon.py'), encoding='utf-8').read()
s = s.replace('__VLOZH__', json.dumps(vlozh)).replace('__ZHDEM__', json.dumps(zhdem))
open(os.path.join(D, 'fixC_kod.py'), 'w', encoding='utf-8').write(s)
print('собран fixC_kod.py; ожидаемые md5:', zhdem)
