# -*- coding: utf-8 -*-
"""«Назначено: meyer1» в карточке -> ФИО. Поле assigned_user, а не username, поэтому при
замене логинов на имена его пропустили. Плюс поиск остальных мест с assigned_user."""
import io, os, re, shutil, time
T = r'C:\centro2\app\templates'
BEKAP = os.path.join(r'C:\centro2\_bekap', time.strftime('naznacheno-%Y%m%d-%H%M%S'))
os.makedirs(BEKAP, exist_ok=True)
for f in sorted(os.listdir(T)):
    if not f.endswith('.html'):
        continue
    p = os.path.join(T, f)
    t = io.open(p, encoding='utf-8').read()
    for m in re.finditer(r'\{\{[^}]*assigned_user[^}]*\}\}', t):
        print('%-24s %s' % (f, m.group(0)))
P = os.path.join(T, 'centro.html')
t = io.open(P, encoding='utf-8').read()
staro = "{{ company.assigned_user or 'не назначено' }}"
novo = "{{ (company.assigned_user|fio) if company.assigned_user else 'не назначено' }}"
if novo in t:
    print('уже правлено')
elif t.count(staro) == 1:
    shutil.copy2(P, os.path.join(BEKAP, 'centro.html'))
    io.open(P, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    print('правка внесена: «Назначено» показывает ФИО')
else:
    print('ЯКОРЬ: %d вхождений' % t.count(staro))
