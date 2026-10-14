# -*- coding: utf-8 -*-
import io, os, re
APP = r'C:\centro2\app'
for f in ('_ochered_spisok.html', 'spisok.html', '_shapka.html'):
    p = os.path.join(APP, 'templates', f)
    if not os.path.exists(p):
        continue
    for i, s in enumerate(io.open(p, encoding='utf-8').read().splitlines(), 1):
        if re.search(r'opisanie|produkciya|otrasl|segment', s):
            print('%s:%d: %s' % (f, i, s.strip()[:900]))
