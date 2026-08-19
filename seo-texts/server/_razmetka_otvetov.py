# -*- coding: utf-8 -*-
"""Что классификатор ставит ответам и совпадает ли это с их текстом."""
import io
import json
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог['лиды_по_reply_kind'] = [list(r) for r in s.execute(
    "select coalesce(reply_kind,'(пусто)'), count(*) from leads group by 1 order by 2 desc")]
итог['лиды_по_readiness'] = [list(r) for r in s.execute(
    "select coalesce(readiness,'(пусто)'), count(*) from leads group by 1 order by 2 desc")]
строки = [dict(r) for r in s.execute(
    "select id, coalesce(company_name,'') nm, coalesce(email,'') em, "
    "coalesce(reply_kind,'') kind, coalesce(readiness,'') ready, "
    "coalesce(need,'') need from leads order by id desc limit 45")]
s.close()
НЕ_ИНТЕРЕСНО = re.compile(
    r'не интересн|неинтересн|не актуальн|неактуальн|не нужн|не требуетс|'
    r'не планируем|отказ|спасибо, нет|не рассматрива|исключите|отпишите|'
    r'не пишите|нет потребност', re.I)
АВТО = re.compile(r'автоответ|отпуск|в отпуске|получено ваше|автоматическ|'
                  r'не отвечайте на это письмо|out of office', re.I)
СМЕНА = re.compile(r'новый адрес|пишите на|перешлите|направьте на', re.I)
несоответствия = []
for r in строки:
    т = r['need'] or ''
    ожидание = ('не интересно' if НЕ_ИНТЕРЕСНО.search(т) else
                'смена адреса' if СМЕНА.search(т) else
                'автоответ' if АВТО.search(т) else '')
    if ожидание and r['kind'] and ожидание != r['kind']:
        несоответствия.append({'id': r['id'], 'компания': r['nm'][:28],
                               'поставлено': r['kind'], 'по_тексту': ожидание,
                               'готовность': r['ready'],
                               'текст': т[:110]})
итог['проверено_лидов'] = len(строки)
итог['несоответствий'] = len(несоответствия)
итог['примеры'] = несоответствия[:8]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4200])
