# -*- coding: utf-8 -*-
r"""Куски Leads.tsx: список статусов и что отсекается из ленты по умолчанию."""
import os

п = r'C:\sender\_tmp\web-pravki\screens\Leads.tsx'
строки = open(п, encoding='utf-8', errors='replace').read().splitlines()
for a, b in ((20, 50), (76, 106), (140, 175)):
    print('--- %d-%d ---' % (a, b))
    for i in range(a - 1, min(len(строки), b)):
        print('%3d %s' % (i + 1, строки[i][:120]))
