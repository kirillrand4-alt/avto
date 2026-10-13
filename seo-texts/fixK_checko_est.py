# -*- coding: utf-8 -*-
"""fixK (сервер, только чтение): какие страницы checko уже скачаны в checko_meyer_fixK (список ИНН – на дроп)."""
import os
P = r'C:\sender\server\checko_meyer_fixK'
est = sorted(f[:-8] for f in os.listdir(P) if f.endswith('.html.gz') and '-kontakty' not in f)
open(r'C:\seostat\drop\drop-storage\fixK-checko-est.txt', 'w').write('\n'.join(est) + '\n')
print(len(est))
