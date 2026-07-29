# -*- coding: utf-8 -*-
"""Добивка разбора А7 и проверка hh-сигналов.

Первый разбор показал: выдача агрегаторы отдаёт, страницы качаются без капчи,
ИНН на странице есть — а подписи «Контактное лицо» нет ни одной. Остаётся два
объяснения, и они требуют разных выводов: либо формулировка на листе иная (наша
вина), либо контакты закрыты регистрацией (источник пуст). Смотрим ЖИВОЙ текст.

Заодно проверяем сигналы «наём в техслужбу»: прогон агрегаторов шёл с --src agg,
поэтому hh-ветка в нём не исполнялась вовсе, и ноль сигналов в том прогоне ничего
не доказывает. Спрашиваем таблицу signals напрямую.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

СТРАНИЦЫ = [
    'https://rostender.info/region/irkutskaya-oblast/irkutsk/'
    '93950490-tender-okazanie-uslug-po-perevozke-gruzov-po-',
    'https://synapsenet.ru/organizacii/1083801006860-ao-aehk/zakazchik',
    'https://www.tenderguru.ru/zakupki_organizaciy/143069/ao-aehk',
]


def текст(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                  re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                         flags=re.S | re.I)))


def main():
    out = {'страницы': []}
    for u in СТРАНИЦЫ:
        h, _m, mt = EC._fetch_site(u)
        с = {'url': u[:70], 'html_байт': len(h or '')}
        if h:
            t = текст(h)
            с['текст'] = t[:900]
            # прямые признаки закрытого доступа
            for сл in ('зарегистр', 'регистрац', 'авториз', 'подписк',
                       'доступ', 'войти', 'demo', 'бесплатн'):
                if сл in t.lower():
                    с.setdefault('замки', []).append(сл)
            # любые почты и телефоны на всей странице, не только у подписи
            с['почты'] = sorted(set(x.lower() for x in EC.EMAIL_RE.findall(t)))[:8]
            с['телефоны'] = sorted(set(x.strip() for x in
                                       EC._PHONE_SITE.findall(t)))[:8] \
                if hasattr(EC, '_PHONE_SITE') else []
            # окно вокруг слова «контакт» в ЛЮБОМ падеже
            окна = [t[max(0, m.start() - 40):m.start() + 220]
                    for m in re.finditer(r'[Кк]онтакт', t)][:3]
            с['окна_контакт'] = окна
        else:
            с['ошибка'] = mt.get('error') or mt.get('status') or 'пусто'
        out['страницы'].append(с)

    e = EDB.EnrichDB().cx
    try:
        out['сигналов_наём'] = e.execute(
            "select count(*) from signals where event_type like '%наём%'"
        ).fetchone()[0]
        out['сигналов_hh'] = e.execute(
            "select count(*) from signals where source='hh'").fetchone()[0]
        out['сигналов_всего'] = e.execute(
            'select count(*) from signals').fetchone()[0]
        out['примеры_сигналов'] = [
            dict(zip(('inn', 'source', 'event_type', 'what'), r))
            for r in e.execute("select inn, source, event_type, what from signals "
                               "where source='hh' limit 5")]
    except Exception as ex:  # noqa: BLE001
        out['сигналы_ошибка'] = f'{type(ex).__name__}: {str(ex)[:90]}'
    print(json.dumps(out, ensure_ascii=False)[:7000])


if __name__ == '__main__':
    main()
