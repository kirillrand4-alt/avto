# -*- coding: utf-8 -*-
"""Карточка Meyer: убрать блок «Почему звонить сейчас» (владелец: «этот блок тоже выкинь»).
У Meyer там показывалась расшифровка балла; прячется тем же признаком, что компрессорные
блоки (choices.est_oborudovanie): у центробежной базы блок со своими поводами остался бы."""
import io, os, re, shutil, time
P = r'C:\centro2\app\templates\centro.html'
t = io.open(P, encoding='utf-8').read()
metka = '{# call-reason: только у баз с данными об оборудовании #}'
if metka in t:
    print('уже правлено')
else:
    m = list(re.finditer(r'(\n  <section class="card call-reason">.*?\n  </section>)', t, re.S))
    if len(m) != 1:
        print('ЯКОРЬ: %d — не правлю' % len(m))
    else:
        b = os.path.join(r'C:\centro2\_bekap', time.strftime('bez-pochemu-%Y%m%d-%H%M%S'))
        os.makedirs(b, exist_ok=True)
        shutil.copy2(P, os.path.join(b, 'centro.html'))
        t = t[:m[0].start()] + '\n  {% if choices.est_oborudovanie %}' + metka + m[0].group(1) + '\n  {% endif %}' + t[m[0].end():]
        io.open(P, 'w', encoding='utf-8').write(t)
        print('правка внесена: блок «Почему звонить сейчас» прячется у баз без оборудования')
