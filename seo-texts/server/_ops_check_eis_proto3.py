# -*- coding: utf-8 -*-
"""Что ВНУТРИ протокола ЕИС: есть ли состав комиссии поимённо.

Установлено: вкладка «Протоколы» есть у каждой карточки и она НЕ пуста —
в каждой лежит «Иной протокол №...-01, Действующая». Боевой код её не
открывает вовсе, а filestore-ссылок на ней нет: протокол в ЕИС — это не
приложенный файл, а собственная карточка (protocol-common-info.html) и
печатная форма (printForm/viewXml.html). Читаем обе и ищем комиссию.

Запуск: python _ops_check_eis_proto3.py [регномер ...]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател|член\w*\s+комисси|секретар|состав\w*\s+комисси'
                  r'|заседани|присутствовал|комисси', re.I)
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    рег = [a for a in sys.argv[1:] if a.isdigit()] or [
        '32616212054', '32616105797', '32515460126']
    итог = {'протоколов': 0, 'страниц_прочитано': 0, 'с_словом_комиссия': 0,
            'с_председателем': 0, 'фио_всего': 0, 'файлов_у_протокола': 0}
    for rn in рег[:3]:
        u = ('https://zakupki.gov.ru/epz/order/notice/notice223/protocols.html'
             '?purchaseNoticeNumber=' + rn)
        try:
            h = EC._eis_get(u)
        except Exception as ex:  # noqa: BLE001
            P(f'{rn}: вкладка не открылась {type(ex).__name__}')
            continue
        гайды = sorted(set(re.findall(r'protocolGuid=([0-9a-f\-]{20,})', h, re.I)))
        P(f'=== закупка {rn}: протоколов={len(гайды)}')
        итог['протоколов'] += len(гайды)
        for g in гайды[:2]:
            for вид, шаб in (
                    ('карточка',
                     'https://zakupki.gov.ru/epz/order/notice/protocol223/'
                     'protocol-common-info.html?protocolGuid='),
                    ('печатная_форма',
                     'https://zakupki.gov.ru/epz/order/notice/protocol223/'
                     'printForm/viewXml.html?protocolGuid=')):
                try:
                    hp = EC._eis_get(шаб + g)
                except Exception as ex:  # noqa: BLE001
                    P(f'  [{вид}] не открылась: {type(ex).__name__} '
                      f'{str(ex)[:50]}')
                    continue
                итог['страниц_прочитано'] += 1
                t = текст(hp)
                файлы = re.findall(r'href="([^"]*filestore[^"]*)"', hp)
                итог['файлов_у_протокола'] += len(файлы)
                есть_ком = bool(re.search(r'комисси', t, re.I))
                есть_пред = bool(re.search(r'председател', t, re.I))
                фио = sorted(set(_ФИО.findall(t)))
                итог['с_словом_комиссия'] += 1 if есть_ком else 0
                итог['с_председателем'] += 1 if есть_пред else 0
                итог['фио_всего'] += len(фио)
                P(f'  [{вид}] html={len(hp)} текст={len(t)} комиссия={есть_ком} '
                  f'председатель={есть_пред} фио={len(фио)} файлов={len(файлы)}')
                if фио:
                    P('     ФИО> ' + json.dumps(фио[:12], ensure_ascii=False))
                m = re.search(r'комисси', t, re.I)
                if m:
                    P('     сырьё_комиссия> ' + t[max(0, m.start() - 350):
                                                  m.start() + 650])
                elif вид == 'печатная_форма':
                    P('     начало> ' + t[:400])
                if файлы:
                    P('     файлы: ' + json.dumps([x[:90] for x in файлы[:4]],
                                                  ensure_ascii=False))
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
