# -*- coding: utf-8 -*-
r"""Откуда 186 и откуда 390: два счётчика отправки за сегодня."""
import json, re, os
d = {}
for п, что in ((r'C:\sender\sender\analytics.py', 'def rate_series'),
               (r'C:\sender\sender\sender.py', 'def mailbox_readiness')):
    if not os.path.exists(п):
        d[os.path.basename(п)] = 'нет файла'; continue
    t = open(п, encoding='utf-8', errors='replace').read()
    i = t.find(что)
    d[что] = t[i:i+1700] if i > 0 else 'не найдено в ' + os.path.basename(п)
# где считается sent_today
t = open(r'C:\sender\sender\sender.py', encoding='utf-8', errors='replace').read()
d['sent_today_места'] = [m.group(0)[:200] for m in
                         re.finditer(r'.{80}sent_today.{110}', t, re.S)][:3]
print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
