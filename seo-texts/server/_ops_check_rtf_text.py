# -*- coding: utf-8 -*-
"""Правда ли, что в читаемых протоколах нет комиссии — или мы читаем мусор.

Три RTF-протокола отдали по 32 тысячи «символов», и ни в одном нет ни
«председател», ни «член комиссии», ни «секретар». Для протокола это странно.
Подозрение к _rtf_text: он раскрывает только \\uNNNN, а русский RTF обычно
пишет кириллицу шестнадцатеричными вставками \\'ef\\'f0. Такие вставки
регулярка управляющих слов не трогает, и они остаются в тексте как есть —
длина большая, а слов нет. Печатаем сырой результат разбора и долю кириллицы.

Запуск: python _ops_check_rtf_text.py [регномер]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател|член\w*\s+комисси|секретар|состав\w*\s+комисси'
                  r'|присутствовал|комисси', re.I)
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def кир(s):
    if not s:
        return 0.0
    b = sum(1 for c in s if 'а' <= c.lower() <= 'я' or c in 'ёЁ')
    return round(b / len(s), 3)


def правильный_rtf(blob):
    """Разбор RTF с раскрытием \\'XX по кодовой странице документа."""
    s = blob.decode('latin-1')
    m = re.search(r'\\ansicpg(\d+)', s)
    cp = 'cp' + (m.group(1) if m else '1251')
    s = re.sub(r'\\u(-?\d+)\s?\??', lambda x: chr(int(x.group(1)) % 65536), s)
    s = re.sub(r"\\'([0-9a-fA-F]{2})",
               lambda x: bytes([int(x.group(1), 16)]).decode(cp, 'replace'), s)
    s = re.sub(r'\\par[d]?\b', '\n', s)
    s = re.sub(r'\\[a-zA-Z]+-?\d*\s?', ' ', s)
    s = re.sub(r'[{}]', ' ', s)
    return re.sub(r'[ \t]+', ' ', s), cp


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    рег = [a for a in sys.argv[1:] if a.isdigit()] or [
        '32616212519', '32616207815']
    итог = {'файлов': 0, 'боевой_кириллица': [], 'правильный_кириллица': [],
            'боевой_комиссия': 0, 'правильный_комиссия': 0, 'фио': 0}
    for rn in рег[:2]:
        try:
            h = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/notice/notice223/protocols.html'
                '?purchaseNoticeNumber=' + rn)
            g = re.search(r'protocolGuid=([0-9a-fA-F\-]+)', h)
            hd = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/notice/protocol223/'
                'document-info.html?protocolGuid=' + g.group(1)
                + '&purchaseNoticeNumber=' + rn)
        except Exception as ex:  # noqa: BLE001
            P(f'{rn}: {type(ex).__name__}')
            continue
        u = None
        for m2 in re.finditer(r'href="([^"]*filestore[^"]*)"', hd):
            u = m2.group(1).replace('&amp;', '&')
            if u.startswith('/'):
                u = 'https://zakupki.gov.ru' + u
            break
        if not u:
            P(f'{rn}: файла нет')
            continue
        blob = EC._eis_get(u, raw=True)
        P(f'=== {rn}: {len(blob)}б сигнатура={blob[:6]!r}')
        итог['файлов'] += 1
        бой = EC.doc_text(u)
        P(f'  БОЕВОЙ doc_text: символов={len(бой or "")} кириллица={кир(бой)}')
        P('  БОЕВОЙ сырьё> ' + re.sub(r'\s+', ' ', (бой or ''))[:330])
        итог['боевой_кириллица'].append(кир(бой))
        if бой and _КОМ.search(бой):
            итог['боевой_комиссия'] += 1
        прав, cp = правильный_rtf(blob)
        P(f'  ПРАВИЛЬНЫЙ разбор ({cp}): символов={len(прав)} '
          f'кириллица={кир(прав)}')
        P('  ПРАВИЛЬНЫЙ сырьё> ' + re.sub(r'\s+', ' ', прав)[:330])
        итог['правильный_кириллица'].append(кир(прав))
        m3 = _КОМ.search(прав)
        if m3:
            итог['правильный_комиссия'] += 1
            P('  КОМИССИЯ> ' + re.sub(r'\s+', ' ',
                                      прав[max(0, m3.start() - 400):
                                           m3.start() + 900]))
        фио = sorted(set(_ФИО.findall(прав)))
        итог['фио'] += len(фио)
        P(f'  фио={len(фио)} ' + json.dumps(фио[:14], ensure_ascii=False))
        # где стоят должности
        for сл in ('Председатель', 'Секретарь', 'Члены комиссии',
                   'Главный инженер', 'Главный энергетик', 'Начальник'):
            i = прав.find(сл)
            if i >= 0:
                P(f'  «{сл}»> ' + re.sub(r'\s+', ' ', прав[i:i + 220]))
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
