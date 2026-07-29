# -*- coding: utf-8 -*-
"""Живая проверка: что отдают ЕИС и hh с сервера прямо сейчас."""
import json
import re
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def main():
    out = {}
    инн = sys.argv[1] if len(sys.argv) > 1 else '6832008411'
    try:
        z = EC.find_zakupki_contacts(инн, max_cards=2)
        out['еис'] = {'rss': (z or {}).get('rss_items'), 'ошибка': (z or {}).get('error'),
                      'карточки': [{'url': (c.get('url') or '')[-46:],
                                    'люди': c.get('people')}
                                   for c in ((z or {}).get('cards') or [])]}
        # сырой контактный блок — чтобы видеть, что вообще на странице
        if (z or {}).get('cards'):
            h = EC._eis_get(z['cards'][0]['url'])
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                         re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                flags=re.S | re.I)))
            out['сырой_блок'] = EC._eis_contact_block(txt)[:900]
    except Exception as ex:  # noqa: BLE001
        out['еис'] = f'{type(ex).__name__}: {str(ex)[:140]}'

    ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for имя, u in (('выдача', 'https://hh.ru/search/vacancy?text=%D0%B3%D0%BB%D0%B0%D0%B2'
                              '%D0%BD%D1%8B%D0%B9+%D1%8D%D0%BD%D0%B5%D1%80%D0%B3%D0%B5'
                              '%D1%82%D0%B8%D0%BA&items_on_page=20'),
                   ('вакансия', 'https://hh.ru/vacancy/1')):
        try:
            req = urllib.request.Request(u, headers={
                'User-Agent': ua, 'Accept-Language': 'ru-RU,ru;q=0.9',
                'Accept': 'text/html,application/xhtml+xml'})
            b = op.open(req, timeout=25).read().decode('utf-8', 'replace')
            out[f'hh_{имя}'] = {'байт': len(b),
                                'есть_стейт': 'HH-Lux-InitialState' in b,
                                'вакансий_в_разметке': len(set(
                                    re.findall(r'/vacancy/(\d+)', b))),
                                'капча': 'captcha' in b.lower()}
        except Exception as ex:  # noqa: BLE001
            out[f'hh_{имя}'] = f'{type(ex).__name__}: {str(ex)[:120]}'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
