# -*- coding: utf-8 -*-
"""Доказательство: ноль на агрегаторах — дефект ДЕКОДИРОВКИ, а не пустота.

Зум показал на листе tenderguru кракозябры «��� �����������» и в них живые
ASCII-хвосты: zakupki@lorp.ru и +7 (4112) 408009. Кракозябры значит одно:
страница в cp1251, а _fetch_site декодирует ЛЮБОЙ ответ как utf-8 с
'replace'. Кириллица гибнет ДО разбора, и подпись «Контактное лицо» боевая
регулярка увидеть не может физически.

Проверяем в лоб: те же байты, декодированные по объявленной кодировке.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
VC = EC.VC

ЛИСТЫ = ['https://www.tenderguru.ru/tender/64392184',
         'https://rostender.info/region/irkutskaya-oblast/irkutsk/'
         '93950490-tender-okazanie-uslug-po-perevozke-gruzov-po-marshrutu-']


def сырые(u):
    req = urllib.request.Request(u, headers={
        'User-Agent': VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml'})
    with EC._DIRECT.open(req, timeout=30) as r:
        return r.read(), dict(r.headers)


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    итог = {}
    for u in ЛИСТЫ:
        P(f'=== {u[:95]} ===')
        try:
            blob, hh = сырые(u)
        except Exception as ex:  # noqa: BLE001
            P(f'  не скачалось: {type(ex).__name__}: {str(ex)[:80]}')
            continue
        ct = hh.get('Content-Type') or hh.get('content-type') or ''
        мета = re.search(rb'charset=["\']?([\w\-]+)', blob[:3000], re.I)
        P(f'  байт={len(blob)} Content-Type={ct!r} meta_charset='
          f'{(мета.group(1).decode() if мета else "нет")!r}')
        как_боевой = blob.decode('utf-8', 'replace')
        порча = как_боевой.count('\ufffd')
        P(f'  БОЕВАЯ декодировка utf-8: символов-замен U+FFFD = {порча}')
        t_бой = текст(как_боевой)
        t_1251 = текст(blob.decode('cp1251', 'replace'))
        итог[EC._domain(u)] = {'ufffd': порча}
        for имя, t in (('БОЕВОЙ(utf-8)', t_бой), ('cp1251', t_1251)):
            окна = [m.group(1) for m in re.finditer(
                r'Контактн\w+\s+лиц\w+\s*[:\-]?\s*(.{0,260})', t, re.I)]
            почты = sorted(set(x.lower() for x in EC.EMAIL_RE.findall(t)))
            свои = [e for e in почты if not EC._is_junk_email(e)
                    and not any(a.split('.')[0] in e
                                for a in EC._АГРЕГАТОРЫ_ТЕНДЕР)]
            P(f'  [{имя}] боевых_окон={len(окна)} почт_чистых={len(свои)} {свои[:4]}')
            for о in окна[:2]:
                P('     ОКНО> ' + о[:250])
                P('     _фио(окно)=' + repr(EC._фио(о)))
            итог.setdefault(EC._domain(u), {})[имя] = len(окна)
        # где именно лежит контакт в правильной кодировке
        for сл in ('Контактное лицо', 'Контактный телефон', 'Электронная почта',
                   'Ответственн', 'Контактная информация'):
            i = t_1251.find(сл)
            if i >= 0:
                P(f'  [cp1251] «{сл}»> ' + t_1251[i:i + 260])
        # и что боевая функция делала бы, если декодировать верно
        if 'tenderguru' in u:
            люди = []
            for m in re.finditer(r'Контактн\w+\s+лиц\w+\s*[:\-]?\s*(.{0,260})',
                                 t_1251, re.I):
                о = m.group(1)
                люди.append({'фио': EC._фио(о),
                             'почты': [x.lower() for x in EC.EMAIL_RE.findall(о)]})
            P('  ЧТО БЫЛО БЫ: ' + json.dumps(люди[:4], ensure_ascii=False)[:400])
            итог['tenderguru_контактов_при_верной_кодировке'] = len(
                [x for x in люди if x['фио'] or x['почты']])

    # заодно: где база продажников и какой у неё формат
    for п in (r'C:\sender\_ops\sales_base.json', r'C:\sender\sales_base.json',
              r'C:\seostat\drop\sales_base.json'):
        if os.path.exists(п):
            d = json.load(open(п, encoding='utf-8', errors='replace'))
            if isinstance(d, list):
                P(f'  база {п}: список из {len(d)}, ключи[0]='
                  f'{list((d[0] or {}).keys())[:12] if d else []}')
            else:
                P(f'  база {п}: dict ключи={list(d.keys())[:12]}')
            break
    else:
        P('  sales_base.json НЕ НАЙДЕН ни по одному пути')
    print('\n'.join(буф)[-11000:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
