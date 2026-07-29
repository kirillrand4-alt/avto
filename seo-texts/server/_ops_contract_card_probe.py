# -*- coding: utf-8 -*-
"""Что лежит в карточке контракта ЕИС вокруг блока поставщика.

Прогон скачал девять карточек и не достал ни одного контакта. Прежде чем
править разбор вслепую, смотрим живой текст: как называется блок, есть ли в
нём вообще телефон и почта, и стоит ли рядом наш ИНН.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def main():
    inn = next((a for a in sys.argv[1:] if a.isdigit()), '7707049388')
    r = EC.find_zakupki_supplier(inn, max_cards=2) or {}
    out = {'инн': inn, 'rss_items': r.get('rss_items'),
           'карточек': len(r.get('cards') or []), 'разбор': []}
    for c in (r.get('cards') or [])[:2]:
        зап = {'url': (c.get('url') or '')[:100], 'людей_нашли': len(c.get('people') or [])}
        try:
            h = EC._eis_get(c['url'])
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                         re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                flags=re.S | re.I)))
            зап['текст_байт'] = len(txt)
            зап['инн_на_странице'] = inn in txt
            зап['почт_всего'] = len(set(EC.EMAIL_RE.findall(txt)))
            зап['телефонов_всего'] = len({m.group(0) for m in EC.phones_in(txt)})
            # как называются блоки: печатаем все подписи со словом «поставщик»
            подписи = re.findall(r'.{0,40}[Пп]оставщик\w*.{0,90}', txt)[:5]
            зап['подписи_поставщика'] = подписи
            # окно вокруг первого упоминания
            m = re.search(r'[Пп]оставщик', txt)
            if m:
                зап['окно'] = txt[m.start():m.start() + 700]
        except Exception as ex:  # noqa: BLE001
            зап['ошибка'] = f'{type(ex).__name__}: {str(ex)[:80]}'
        out['разбор'].append(зап)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])


if __name__ == '__main__':
    main()
