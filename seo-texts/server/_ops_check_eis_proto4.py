# -*- coding: utf-8 -*-
"""Вкладка «Документы» САМОГО протокола: есть ли подписанный файл с комиссией.

Карточка протокола — машинная: «Решение комиссии» там таблица допусков, ни
одного ФИО. Но у карточки протокола свои вкладки, и среди них «Документы».
Если заказчик приложил подписанный протокол файлом, состав комиссии будет
именно там. Открываем все вкладки протокола и читаем всё, что приложено.

Запуск: python _ops_check_eis_proto4.py [регномер ...]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател|член\w*\s+комисси|секретар|состав\w*\s+комисси'
                  r'|присутствовал|подпис', re.I)
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')
_МУСОР = re.compile(r'Федерац|Правительств|Президент|Каталог|Новости|Опросы'
                    r'|Министерств|Поставщикам|Заказчикам|Статистика', re.I)


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    рег = [a for a in sys.argv[1:] if a.isdigit()] or [
        '32616105797', '32616212054', '32616100827']
    итог = {'протоколов': 0, 'вкладок_протокола': 0, 'файлов': 0,
            'прочитано': 0, 'пустых': 0, 'с_комиссией': 0, 'фио': 0}
    for rn in рег[:3]:
        try:
            h = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/notice/notice223/protocols.html'
                '?purchaseNoticeNumber=' + rn)
        except Exception as ex:  # noqa: BLE001
            P(f'{rn}: {type(ex).__name__}')
            continue
        карт = sorted(set(x.replace('&amp;', '&') for x in re.findall(
            r'href="([^"]*protocol223[^"]*common-info[^"]*)"', h, re.I)))
        P(f'=== закупка {rn}: карточек протокола={len(карт)}')
        for c in карт[:1]:
            итог['протоколов'] += 1
            full = 'https://zakupki.gov.ru' + c if c.startswith('/') else c
            try:
                hp = EC._eis_get(full)
            except Exception as ex:  # noqa: BLE001
                P(f'  карточка не открылась {type(ex).__name__}')
                continue
            # ВСЕ вкладки карточки протокола
            вкл = []
            for m in re.finditer(r'<a\b[^>]*href="([^"]*protocol223[^"]*)"[^>]*>'
                                 r'(.*?)</a>', hp, re.S | re.I):
                п = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(2))).strip()
                href = m.group(1).replace('&amp;', '&')
                if п and (href, п) not in вкл:
                    вкл.append((href, п))
            итог['вкладок_протокола'] += len(вкл)
            P('  вкладки протокола: ' + json.dumps(
                sorted(set(п for _h, п in вкл))[:14], ensure_ascii=False))
            цели = [x for x in вкл if re.search(r'document|документ', x[0] + x[1],
                                                re.I)]
            P('  документные вкладки: ' + json.dumps(
                [f'{п} -> {hr[:95]}' for hr, п in цели[:3]], ensure_ascii=False))
            for hr, _п in цели[:2]:
                full2 = 'https://zakupki.gov.ru' + hr if hr.startswith('/') else hr
                try:
                    hd = EC._eis_get(full2)
                except Exception as ex:  # noqa: BLE001
                    P(f'    вкладка документов не открылась {type(ex).__name__}')
                    continue
                файлы = []
                for m2 in re.finditer(
                        r'<a\b[^>]*href="([^"]*filestore[^"]*)"[^>]*>(.*?)</a>',
                        hd, re.S):
                    имя = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                                                     m2.group(2))).strip()
                    сс = m2.group(1).replace('&amp;', '&')
                    if сс.startswith('/'):
                        сс = 'https://zakupki.gov.ru' + сс
                    if (имя, сс) not in файлы:
                        файлы.append((имя[:70], сс))
                итог['файлов'] += len(файлы)
                t = текст(hd)
                P(f'    вкладка документов html={len(hd)} файлов={len(файлы)}')
                P('    имена: ' + json.dumps([n for n, _ in файлы][:8],
                                             ensure_ascii=False))
                if not файлы:
                    i = t.find('Документ')
                    P('    текст> ' + t[max(0, i - 60):i + 300])
                for имя, сс in файлы[:3]:
                    txt = EC.doc_text(сс)
                    итог['прочитано'] += 1
                    P(f'    ФАЙЛ «{имя}» символов={len(txt or "")}')
                    if not txt:
                        итог['пустых'] += 1
                        # почему пусто: смотрим сигнатуру
                        try:
                            b = EC._eis_get(сс, raw=True)[:8]
                        except Exception:  # noqa: BLE001
                            b = b''
                        P(f'      ПУСТО, первые байты={b!r}')
                        continue
                    m3 = _КОМ.search(txt)
                    фио = [x for x in sorted(set(_ФИО.findall(txt)))
                           if not _МУСОР.search(x)]
                    итог['фио'] += len(фио)
                    if m3:
                        итог['с_комиссией'] += 1
                        P('      КОМИССИЯ> ' + re.sub(
                            r'\s+', ' ', txt[max(0, m3.start() - 350):
                                             m3.start() + 750]))
                    P(f'      фио={len(фио)} ' + json.dumps(фио[:10],
                                                            ensure_ascii=False))
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
