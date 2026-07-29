# -*- coding: utf-8 -*-
"""Почему doc_text вернул НОЛЬ символов на трёх подписанных протоколах-PDF.

Три варианта, и они требуют разных выводов:
 (1) pypdf на сервере нет -> _pdf_text молча возвращает '' (дефект среды);
 (2) doc_text режет блоб до 800 000 байт, а таблица xref у PDF лежит В КОНЦЕ
     файла -> обрезанный PDF не парсится вообще (дефект кода);
 (3) это скан без текстового слоя (источник правда нечитаем без OCR).
Проверяем все три на одних и тех же байтах.

Запуск: python _ops_check_pdf_zero.py [регномер ...]
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_КОМ = re.compile(r'председател|член\w*\s+комисси|секретар|состав\w*\s+комисси'
                  r'|присутствовал', re.I)
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def main():
    буф = []

    def P(s):
        буф.append(str(s))

    try:
        import pypdf
        P(f'pypdf ЕСТЬ, версия={getattr(pypdf, "__version__", "?")}')
        есть = True
    except Exception as ex:  # noqa: BLE001
        P(f'pypdf НЕТ: {type(ex).__name__}: {str(ex)[:80]}')
        есть = False

    рег = [a for a in sys.argv[1:] if a.isdigit()] or [
        '32616105797', '32616212054', '32616100827']
    итог = {'pypdf': есть, 'файлов': 0, 'обрезанных_капом': 0,
            'полный_текст_есть': 0, 'сканов': 0, 'с_комиссией': 0, 'фио': 0}
    for rn in рег[:3]:
        try:
            h = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/notice/notice223/protocols.html'
                '?purchaseNoticeNumber=' + rn)
            c = re.search(r'href="([^"]*protocol223[^"]*common-info[^"]*)"', h, re.I)
            if not c:
                P(f'{rn}: карточка протокола не найдена')
                continue
            g = re.search(r'protocolGuid=([0-9a-fA-F\-]+)', c.group(1))
            hd = EC._eis_get(
                'https://zakupki.gov.ru/epz/order/notice/protocol223/'
                'document-info.html?protocolGuid=' + g.group(1)
                + '&purchaseNoticeNumber=' + rn)
        except Exception as ex:  # noqa: BLE001
            P(f'{rn}: {type(ex).__name__}: {str(ex)[:60]}')
            continue
        сс = [x.replace('&amp;', '&') for x in
              re.findall(r'href="([^"]*filestore[^"]*)"', hd)]
        сс = [('https://zakupki.gov.ru' + x if x.startswith('/') else x)
              for x in сс]
        сс = sorted(set(сс))
        P(f'=== {rn}: файлов={len(сс)}')
        for u in сс[:1]:
            итог['файлов'] += 1
            # ПОЛНЫЕ байты, без капа doc_text
            try:
                blob = EC._eis_get(u, raw=True)
            except Exception as ex:  # noqa: BLE001
                P(f'  скачать не вышло {type(ex).__name__}')
                continue
            обрезан = len(blob) > 800000
            итог['обрезанных_капом'] += 1 if обрезан else 0
            P(f'  байт={len(blob)} превышает_кап_800000={обрезан} '
              f'сигнатура={blob[:8]!r}')
            P(f'  боевой doc_text: символов={len(EC.doc_text(u) or "")}')
            if not есть:
                continue
            import io as _io
            for ярлык, b in (('ПОЛНЫЙ', blob), ('ОБРЕЗАННЫЙ_как_в_коде',
                                                 blob[:800000])):
                try:
                    r = pypdf.PdfReader(_io.BytesIO(b))
                    страниц = len(r.pages)
                    куски = []
                    for стр in r.pages[:25]:
                        try:
                            куски.append(стр.extract_text() or '')
                        except Exception:  # noqa: BLE001
                            pass
                    t = '\n'.join(куски)
                    P(f'  [{ярлык}] страниц={страниц} символов={len(t)}')
                    if ярлык == 'ПОЛНЫЙ':
                        if len(t) > 200:
                            итог['полный_текст_есть'] += 1
                            m = _КОМ.search(t)
                            фио = sorted(set(_ФИО.findall(t)))
                            итог['фио'] += len(фио)
                            if m:
                                итог['с_комиссией'] += 1
                                P('    КОМИССИЯ> ' + re.sub(
                                    r'\s+', ' ', t[max(0, m.start() - 400):
                                                   m.start() + 800]))
                            else:
                                P('    начало> ' + re.sub(r'\s+', ' ', t)[:400])
                            P(f'    фио={len(фио)} ' + json.dumps(
                                фио[:12], ensure_ascii=False))
                        else:
                            итог['сканов'] += 1
                            P('    текстового слоя нет -> скан (нужен OCR)')
                except Exception as ex:  # noqa: BLE001
                    P(f'  [{ярлык}] pypdf упал: {type(ex).__name__}: '
                      f'{str(ex)[:100]}')
    print('\n'.join(буф)[-11500:])
    print('ИТОГ ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
