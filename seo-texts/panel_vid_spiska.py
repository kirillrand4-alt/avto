# -*- coding: utf-8 -*-
"""Вид списка: метка базы незаметная, описание обычным цветом и шире, «ЛПР» уже.

Владелец: «сделай менее выделяющуюся надпись “База 1” и вопросик, чтобы внимание вообще
не привлекала; описание с сайта таким же цветом, как и выручка (не более серым); поле ещё
расширь за счёт столбца ЛПР».
Только стили и класс на ячейке «ЛПР» — шаблоны перечитываются сами, перезапуск не нужен.
"""
import io
import os
import re
import shutil
import time

T = r'C:\centro2\app\templates'
BEKAP = os.path.join(r'C:\centro2\_bekap', time.strftime('vid-spiska-%Y%m%d-%H%M%S'))
os.makedirs(BEKAP, exist_ok=True)
nado = sdelano = 0


def pravka(f, staro, novo, imya, priznak, regex=False):
    global nado, sdelano
    nado += 1
    p = os.path.join(T, f)
    t = io.open(p, encoding='utf-8').read()
    if priznak in t:
        sdelano += 1
        print('   [уже] ' + imya)
        return
    n = len(re.findall(staro, t, re.S)) if regex else t.count(staro)
    if n != 1:
        print('   [ЯКОРЬ: %d] %s — не правлю' % (n, imya))
        return
    if not os.path.exists(os.path.join(BEKAP, f)):
        shutil.copy2(p, os.path.join(BEKAP, f))
    t = re.sub(staro, novo, t, count=1, flags=re.S) if regex else t.replace(staro, novo, 1)
    io.open(p, 'w', encoding='utf-8').write(t)
    sdelano += 1
    print('   [ок] ' + imya)


# метка базы: без плашки, мелким серым; «?» — тонкий кружок того же цвета
pravka('_shapka.html', r'\.baza-metka\{[^}]*\}\.baza-vopros\{[^}]*\}',
       '.baza-metka{display:inline-flex;align-items:center;gap:3px;margin-left:6px;'
       'color:#9aa1ad;font-size:11px;font-weight:400;vertical-align:middle;white-space:nowrap;'
       'background:none;border:0;padding:0}'
       '.baza-vopros{display:inline-flex;width:11px;height:11px;border-radius:50%;align-items:center;'
       'justify-content:center;border:1px solid #c4c9d2;color:#9aa1ad;font-size:8px;font-weight:400;'
       'cursor:help;background:none}',
       'метка «База 1 ?» — незаметная', priznak='color:#9aa1ad;font-size:11px;font-weight:400', regex=True)
# описание — цветом выручки (обычный цвет ячейки) и шире
pravka('_ochered_spisok.html',
       '.komp-opis{flex:1 1 auto;max-width:520px;color:var(--muted);font-size:12px;line-height:1.4}',
       '.komp-opis{flex:1 1 auto;min-width:360px;max-width:760px;color:inherit;font-size:12px;line-height:1.4}\n'
       '.lpr-yach{width:150px;max-width:150px;white-space:normal}',
       'описание цветом выручки и шире; «ЛПР» уже', priznak='.lpr-yach{')
pravka('_ochered_spisok.html', '<td>{% if c.bitrix_kc %}', '<td class="lpr-yach">{% if c.bitrix_kc %}',
       'класс на ячейке «ЛПР»', priznak='<td class="lpr-yach">')
print('правок внесено: %d из %d' % (sdelano, nado))
print('бэкап: %s' % BEKAP)
