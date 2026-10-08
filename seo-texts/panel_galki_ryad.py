# -*- coding: utf-8 -*-
"""Галочки раздела «Сегмент и ЛПР» — в ту же сетку, что «Наличие данных» (одинаковый вид)."""
import io, os, re, shutil, time
P = r'C:\centro2\app\templates\centro.html'
t = io.open(P, encoding='utf-8').read()
if 'class="checks-grid" style="margin-top:10px"' in t:
    print('уже правлено')
else:
    m = list(re.finditer(r'(<h3>Сегмент и ЛПР</h3>\s*<div class="filter-grid">\s*<label>Сегмент<select name="segment">.*?</select></label>)'
                         r'\s*(<label class="check">.*?Закупщик / снабжение</label>)\s*</div>', t, re.S))
    if len(m) != 1:
        print('ЯКОРЬ: %d' % len(m))
    else:
        b = os.path.join(r'C:\centro2\_bekap', time.strftime('galki-%Y%m%d-%H%M%S'))
        os.makedirs(b, exist_ok=True)
        shutil.copy2(P, os.path.join(b, 'centro.html'))
        novo = (m[0].group(1) + '\n        </div>\n        <div class="checks-grid" style="margin-top:10px">\n          '
                + m[0].group(2) + '\n        </div>')
        io.open(P, 'w', encoding='utf-8').write(t[:m[0].start()] + novo + t[m[0].end():])
        print('правка внесена')
