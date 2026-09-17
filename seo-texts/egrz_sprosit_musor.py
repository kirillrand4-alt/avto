# -*- coding: utf-8 -*-
"""Чужой взгляд на МОЙ отсев: показываю провайдеру 140 записей, помеченных «производство»,
и прошу найти мусор, которого я не вижу. Владелец ткнул в «Магазин по реализации
оборудования пищевого производства» — значит мои глаза этот класс пропустили."""
import io, os, sys
sys.path.insert(0, '/home/user/avto/seo-texts')
import gen_provider as P
KAT = os.path.dirname(os.path.abspath(__file__))
p = io.open(os.path.join(KAT, 'proverka_musora_prompt.txt'), encoding='utf-8').read()
msg = P.call(P.make_client(), [{'role': 'user', 'content': p}],
             model='claude-fable-5', attempts=3)
t = ''.join(b.text for b in msg.content if b.type == 'text')
io.open(os.path.join(KAT, 'proverka_musora.md'), 'w', encoding='utf-8').write(t)
print('знаков %d, классов мусора %d, сомнений %d' % (len(t), t.count('МУСОР |'), t.count('СОМНЕНИЕ |')))
