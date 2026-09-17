# -*- coding: utf-8 -*-
"""Контроль моей оценки мощности чужими глазами: те же объекты, независимая оценка кВт."""
import io, os, sys
sys.path.insert(0, '/home/user/avto/seo-texts')
import gen_provider as P
KAT = os.path.dirname(os.path.abspath(__file__))
p = io.open(os.path.join(KAT, 'kvt_kontrol_prompt.txt'), encoding='utf-8').read()
msg = P.call(P.make_client(), [{'role': 'user', 'content': p}], model='claude-fable-5', attempts=3)
t = ''.join(b.text for b in msg.content if b.type == 'text')
io.open(os.path.join(KAT, 'kvt_kontrol.md'), 'w', encoding='utf-8').write(t)
print('знаков %d, оценок %d, замечаний %d' % (len(t), t.count('ОЦЕНКА |'), t.count('ЗАМЕЧАНИЕ |')))
