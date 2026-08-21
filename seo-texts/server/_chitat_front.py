# -*- coding: utf-8 -*-
r"""Куски фронта: запрос очереди и локальный фильтр направления."""
import os

БАЗА = r'C:\sender\_tmp\web-src-iz-mapy'
ПРАВКИ = r'C:\sender\_tmp\web-pravki'


def взять(отн):
    п = os.path.join(ПРАВКИ, отн)
    откуда = 'ПРАВКИ'
    if not os.path.exists(п):
        п, откуда = os.path.join(БАЗА, отн), 'база'
    with open(п, encoding='utf-8', errors='replace') as f:
        return откуда, f.read().splitlines()


for отн, куски in (('screens/Confirm.tsx', ((750, 30), (835, 24))),
                   ('api/client.ts', ((248, 22),))):
    откуда, строки = взять(отн)
    print('=== %s (%s), всего %d ===' % (отн, откуда, len(строки)))
    for начало, сколько in куски:
        for i in range(начало - 1, min(len(строки), начало - 1 + сколько)):
            print('%4d %s' % (i + 1, строки[i][:150]))
        print('   ...')
