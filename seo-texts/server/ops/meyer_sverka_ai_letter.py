# -*- coding: utf-8 -*-
"""READ-ONLY: сверка боевого ai_letter.py с копией в репо по ключевым строкам."""
import hashlib
import sys
b = open(r"C:\sender\sender\ai_letter.py", 'rb').read()
print(hashlib.md5(b.replace(b'\r\n', b'\n')).hexdigest(), b.count(b'\n'))
ключи = sys.argv[1:] or ['_NAPITKI_СЛОВА = ', "компонент\\w*(?![а-яё])", '_ПРИЗНАК_ЗЕРНА = ',
                         '_ЗОНТИК_RE = {', "(r'(?i)компрессор'", '_отказ = re.search(',
                         'r\'(?i)чуж(ая', 'def vne_profilya_meyer', 'пивовар']
for н, с in enumerate(b.decode('utf-8').splitlines(), 1):
    for к in ключи:
        if к in с:
            print(н, с.strip()[:110])
