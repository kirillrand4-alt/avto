# -*- coding: utf-8 -*-
"""Полный текст ответа «Росткрана» и что классификатор о нём думает."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
r = s.execute("select id, coalesce(need,'') need, coalesce(reply_kind,'') kind "
              "from leads where lower(email)='chernyavin@rostkran.ru'").fetchone()
s.close()
из = {'lead_id': r[0], 'метка_сейчас': r[2], 'текст_целиком': r[1][:900]}
from sender.reply_classify import classify_reply, bez_citaty  # noqa: E402
з = classify_reply('', r[1])
из['классификатор'] = {'вердикт': з.kind, 'по_чему': list(з.matched)[:6],
                       'уверенность': з.confidence}
из['что_читает_классификатор'] = bez_citaty(r[1])[:400]
print(json.dumps(из, ensure_ascii=False, indent=1)[:2600])
