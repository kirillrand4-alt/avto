# -*- coding: utf-8 -*-
"""Один кандидат под лупой: качается ли главная, находятся ли ссылки.

Доразбор кандидатов дал 0 из 25 за 13 секунд — на 25 сайтов с загрузкой
главной и подстраниц столько времени физически не уходит. Значит либо
главная не качается, либо ссылки не находятся, либо ИНН ищется не так.
Смотрим по шагам на живых пяти кандидатах.
"""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB       # noqa: E402
import enrich_contacts as EC  # noqa: E402
import kandidaty_sajtov as K  # noqa: E402

cx = EDB.EnrichDB().cx
ряды = cx.execute(
    "SELECT inn,cand_site FROM companies WHERE COALESCE(cand_site,'')<>'' "
    "AND COALESCE(site,'')='' LIMIT 5").fetchall()

итог = []
for инн, сайт in ряды:
    осн = сайт.rstrip('/')
    if not осн.startswith('http'):
        осн = 'http://' + осн
    try:
        h, m, mt = EC._fetch_site(осн)
    except Exception as e:  # noqa: BLE001
        итог.append({'инн': инн, 'сайт': сайт, 'исключение': str(e)[:90]})
        continue
    h = h or ''
    ссылки = K._ССЫЛКА.findall(h)
    подходящие = []
    дом = EC.site_domain(осн)
    for адрес, текст in ссылки:
        подпись = K._ТЕГИ.sub(' ', текст)
        if K._ПОХОЖЕ.search(подпись) or K._ПОХОЖЕ.search(адрес):
            полный = urllib.parse.urljoin(осн + '/', адрес.strip())
            if EC.site_domain(полный) == дом:
                подходящие.append(полный)
    цифры = re.sub(r'\D', '', инн)
    итог.append({
        'инн': инн, 'сайт': сайт, 'домен': дом,
        'байт_главной': len(h), 'мета': str(m)[:60], 'тип': str(mt)[:40],
        'всего_ссылок': len(ссылки),
        'подходящих_ссылок': len(dict.fromkeys(подходящие)),
        'примеры': list(dict.fromkeys(подходящие))[:6],
        'ИНН_на_главной': K._есть_инн(h, цифры),
    })

print(json.dumps(итог, ensure_ascii=False, indent=1)[:4000])
