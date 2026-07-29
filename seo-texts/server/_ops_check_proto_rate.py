# -*- coding: utf-8 -*-
"""Насколько массовы приложенные протоколы и читаемы ли они.

Три протокола оказались сканами без текстового слоя. Три — не статистика,
а на решении «чинить обход или ставить OCR» это влияет напрямую. Считаем по
широкой выборке закупок: у скольких есть вкладка «Протоколы» с приложенным
файлом, какие это форматы и у скольких есть текстовый слой.

Запуск: python _ops_check_proto_rate.py [ИНН ...]
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател|член\w*\s+комисси|секретар|состав\w*\s+комисси'
                  r'|присутствовал', re.I)
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def инны_базы():
    п = r'C:\sender\_ops\sales_base.json'
    из = []
    if os.path.exists(п):
        d = json.load(open(п, encoding='utf-8', errors='replace'))
        куски = d.values() if isinstance(d, dict) else [d]
        for к in куски:
            if not isinstance(к, list):
                continue
            for x in к:
                s = str((x or {}).get('inn') or '') if isinstance(x, dict) else ''
                if s.isdigit() and s not in из:
                    из.append(s)
    return из


def main():
    буф = []
    старт = time.time()

    def P(s):
        буф.append(str(s))

    инны = [a for a in sys.argv[1:] if a.isdigit()]
    из_базы = инны_базы()
    P(f'ИНН в sales_base.json: {len(из_базы)} (первые {из_базы[:5]})')
    if not инны:
        инны = ['7424024375', '3801098402'] + из_базы[:2]
    итог = {'закупок': 0, 'с_протоколом': 0, 'с_файлом': 0, 'форматы': {},
            'pdf_с_текстом': 0, 'pdf_скан': 0, 'не_pdf_прочитано': 0,
            'с_комиссией': 0}
    import io as _io
    try:
        import pypdf
    except Exception:  # noqa: BLE001
        pypdf = None
    for inn in инны[:4]:
        if time.time() - старт > 600:
            P('  (стоп по времени)')
            break
        try:
            rss = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/extendedsearch/rss.html'
                '?searchString=' + inn + '&fz44=on&fz223=on&af=on&ca=on&pc=on'
                '&pa=on&recordsPerPage=_50&sortBy=UPDATE_DATE')
        except Exception as ex:  # noqa: BLE001
            P(f'ИНН {inn}: rss {type(ex).__name__}')
            continue
        рег = []
        for m in re.finditer(r'regNumber=(\d+)', rss):
            if m.group(1) not in рег:
                рег.append(m.group(1))
        P(f'=== ИНН {inn}: закупок в RSS={len(рег)}')
        for rn in рег[:5]:
            if time.time() - старт > 620:
                break
            итог['закупок'] += 1
            try:
                h = EC._eis_get(
                    'https://zakupki.gov.ru/epz/order/notice/notice223/'
                    'protocols.html?purchaseNoticeNumber=' + rn)
            except Exception:  # noqa: BLE001
                continue
            g = re.search(r'protocolGuid=([0-9a-fA-F\-]+)', h)
            if not g:
                P(f'  {rn}: протокола нет')
                continue
            итог['с_протоколом'] += 1
            try:
                hd = EC._eis_get(
                    'https://zakupki.gov.ru/epz/order/notice/protocol223/'
                    'document-info.html?protocolGuid=' + g.group(1)
                    + '&purchaseNoticeNumber=' + rn)
            except Exception:  # noqa: BLE001
                continue
            пары = []
            for m2 in re.finditer(
                    r'<a\b[^>]*href="([^"]*filestore[^"]*)"[^>]*>(.*?)</a>',
                    hd, re.S):
                имя = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                                                 m2.group(2))).strip()
                u = m2.group(1).replace('&amp;', '&')
                if u.startswith('/'):
                    u = 'https://zakupki.gov.ru' + u
                if u not in [x[1] for x in пары]:
                    пары.append((имя.split("'")[0].strip()[:55], u))
            if not пары:
                P(f'  {rn}: протокол есть, файла НЕТ')
                continue
            итог['с_файлом'] += 1
            имя, u = пары[0]
            расш = (re.search(r'\.(\w{2,5})$', имя) or [None, '?'])[1].lower() \
                if re.search(r'\.(\w{2,5})$', имя) else '?'
            итог['форматы'][расш] = итог['форматы'].get(расш, 0) + 1
            try:
                blob = EC._eis_get(u, raw=True)
            except Exception:  # noqa: BLE001
                P(f'  {rn}: «{имя}» не скачался')
                continue
            метка = ''
            if blob[:4] == b'%PDF' and pypdf:
                try:
                    r = pypdf.PdfReader(_io.BytesIO(blob))
                    t = '\n'.join((p.extract_text() or '') for p in r.pages[:25])
                except Exception as ex:  # noqa: BLE001
                    t = ''
                    метка = f'pypdf:{type(ex).__name__}'
                if len(t) > 200:
                    итог['pdf_с_текстом'] += 1
                    метка = 'ТЕКСТОВЫЙ СЛОЙ ЕСТЬ'
                    if _КОМ.search(t):
                        итог['с_комиссией'] += 1
                        m3 = _КОМ.search(t)
                        P('     КОМИССИЯ> ' + re.sub(
                            r'\s+', ' ', t[max(0, m3.start() - 300):
                                           m3.start() + 600]))
                        P('     фио> ' + json.dumps(
                            sorted(set(_ФИО.findall(t)))[:10],
                            ensure_ascii=False))
                else:
                    итог['pdf_скан'] += 1
                    метка = метка or 'скан (текста нет)'
            else:
                t = EC.doc_text(u)
                if t:
                    итог['не_pdf_прочитано'] += 1
                    метка = f'не-PDF, символов={len(t)}'
                    if _КОМ.search(t):
                        итог['с_комиссией'] += 1
                        m3 = _КОМ.search(t)
                        P('     КОМИССИЯ> ' + re.sub(
                            r'\s+', ' ', t[max(0, m3.start() - 300):
                                           m3.start() + 600]))
                else:
                    метка = 'не-PDF, doc_text пусто'
            P(f'  {rn}: «{имя}» {len(blob)}б -> {метка}')
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
