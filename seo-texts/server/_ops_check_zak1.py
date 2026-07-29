# -*- coding: utf-8 -*-
"""Разведка №6: ЕИС «компания как ПОСТАВЩИК» — правда ли контактов нет.

Автор смотрел ТОЛЬКО ту страницу, что даёт RSS (common-info). У карточки
контракта есть и другие вкладки; если контакт поставщика живёт там, вывод
«источник пуст» — дефект разбора, а не свойство ЕИС. Поэтому: сначала боевая
функция, потом РУЧНОЙ обход всех вкладок карточки со сплошным поиском.
"""
import json
import re
import sys
import time
import traceback

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def p(*a):
    print(*a)
    sys.stdout.flush()


ТЕЛ = re.compile(r'(?<!\d)(?:\+7|8)[\s\-(]*\d{3,5}[\s\-)]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}')
ПОЧТА = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}')


def текст(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


def отпечаток_браузера():
    """Поддерживает ли СЕРВЕРНЫЙ browser_probe пачку урлов одной сессией.

    Прошлый замер hh открыл ровно ОДНУ вакансию из восьми — если серверная
    копия старше локальной и ключа 'urls' не знает, то весь боевой прогон hh
    смотрел по одной вакансии на компанию, и «8 вакансий с 32 компаний» —
    это дефект транспорта, а не пустота источника.
    """
    import inspect
    try:
        import browser_probe as BP
        src = inspect.getsource(BP.probe)
        p('BROWSER_PROBE: файл=%s байт=%d поддержка_urls=%s urls_cap=%s'
          % (BP.__file__, len(inspect.getsource(BP)), "args.get('urls')" in src,
             'urls_cap' in src))
    except Exception as ex:  # noqa: BLE001
        p('BROWSER_PROBE: не прочитан', type(ex).__name__, str(ex)[:70])


def main():
    отпечаток_браузера()
    inn = sys.argv[1]
    # 1. что говорит боевая функция
    try:
        r = EC.find_zakupki_supplier(inn, max_cards=2) or {}
        p('БОЕВАЯ: rss_items=%s карточек=%s ошибка=%s' % (
            r.get('rss_items'), len(r.get('cards') or []), r.get('error')))
        for c in (r.get('cards') or []):
            p('  карточка:', json.dumps(
                {'url': c.get('url'), 'people': c.get('people'),
                 'customer': (c.get('customer') or '')[:60],
                 'error': c.get('error')}, ensure_ascii=False)[:400])
    except Exception:  # noqa: BLE001
        p('БОЕВАЯ упала:', traceback.format_exc()[-300:])
        r = {}
    # 2. берём первую карточку и лезем ВО ВСЕ вкладки
    url = ''
    for c in (r.get('cards') or []):
        if c.get('url'):
            url = c['url']
            break
    if not url:
        p('ИТОГ: карточек нет, дальше идти не с чем')
        return
    рег = (re.search(r'reestrNumber=(\d+)', url) or [None, ''])[1]
    p('карточка:', url, '| reestrNumber=', рег)
    try:
        h0 = EC._eis_get(url)
    except Exception as ex:  # noqa: BLE001
        p('ИТОГ: карточка не скачалась:', type(ex).__name__, str(ex)[:80])
        return
    # реальные вкладки берём ИЗ САМОЙ КАРТОЧКИ, а не угадываем
    вкладки = []
    for a in re.findall(r'href="([^"]*contract[^"]*\.html[^"]*)"', h0):
        a = a.replace('&amp;', '&')
        if рег and рег not in a:
            continue
        if not a.startswith('http'):
            a = 'https://zakupki.gov.ru' + a
        if a not in вкладки:
            вкладки.append(a)
    p('ВКЛАДОК найдено:', len(вкладки))
    for a in вкладки[:12]:
        p('   ', a[:150])
    итог = {'вкладок': 0, 'с_телефоном_у_инн': 0, 'с_почтой_у_инн': 0}
    for a in ([url] + [x for x in вкладки if x != url])[:8]:
        try:
            h = EC._eis_get(a)
        except Exception as ex:  # noqa: BLE001
            p('вкладка ОШИБКА', a[-45:], type(ex).__name__, str(ex)[:50])
            continue
        t = текст(h)
        итог['вкладок'] += 1
        окна = []
        for m in re.finditer(re.escape(inn), t):
            окна.append(t[max(0, m.start() - 700):m.start() + 900])
        тел_у = sum(len(ТЕЛ.findall(o)) for o in окна)
        поч_у = sum(len([x for x in ПОЧТА.findall(o)
                         if 'zakupki' not in x.lower()]) for o in окна)
        if тел_у:
            итог['с_телефоном_у_инн'] += 1
        if поч_у:
            итог['с_почтой_у_инн'] += 1
        p(json.dumps({'вкладка': a.split('/')[-1][:60], 'байт': len(h),
                      'текст': len(t), 'вхожд_инн': len(окна),
                      'телефонов_всего': len(ТЕЛ.findall(t)),
                      'почт_всего': len([x for x in ПОЧТА.findall(t)
                                         if 'zakupki' not in x.lower()]),
                      'тел_рядом_с_инн': тел_у, 'почт_рядом_с_инн': поч_у,
                      'слово_Контактн': len(re.findall(r'Контактн\w+', t)),
                      'слово_Поставщик': len(re.findall(r'[Пп]оставщик', t)),
                      }, ensure_ascii=False))
        if окна:
            p('   ОКНО У ИНН:', окна[0][550:1100].strip()[:420])
        time.sleep(1.2)
    p('ИТОГ инн=%s: %s' % (inn, json.dumps(итог, ensure_ascii=False)))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-600:])
