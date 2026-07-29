# -*- coding: utf-8 -*-
"""Разведка №8: чего боевой обход ЕИС по поставщику НЕ СМОТРЕЛ.

Первый заход показал: на вкладках карточки 44-ФЗ нет ни слова «Контактн», ни
одной почты — то есть контакта поставщика там действительно нет. Остаются два
непроверенных места, из-за которых цифра «70 компаний -> 1 контракт» могла
быть занижена нашим кодом, а не жизнью:
  1) поиск идёт ТОЛЬКО по 44-ФЗ (fz44=on), а промышленник поставляет
     госкорпорациям по 223-ФЗ — это отдельный реестр договоров;
  2) сколько вообще RSS отдаёт по ИНН.
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


def отпечаток():
    import inspect
    try:
        import browser_probe as BP
        src = inspect.getsource(BP.probe)
        p('BROWSER_PROBE: %s поддержка_urls=%s html_full_len=%s click=%s'
          % (BP.__file__, "args.get('urls')" in src,
             'html_full_len' in src, "args.get('click')" in src))
    except Exception as ex:  # noqa: BLE001
        p('BROWSER_PROBE: не прочитан', type(ex).__name__, str(ex)[:60])


def rss(url):
    try:
        t = EC._eis_get(url, timeout=40)
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:60]}'
    похоже = bool(re.search(r'<(?:rss|channel)\b', t or '', re.I))
    items = re.findall(r'<item>(.*?)</item>', t or '', re.S)
    return (items if похоже else None), ('ок' if похоже else 'не RSS (%d байт)' % len(t or ''))


def обрезанные_имена():
    """Сколько имён в базе ОБРЕЗАНО — по ним поиск hh по названию заведомо
    промахнётся («ГОРНО-МЕТАЛЛУРГИЧЕСКАЯ КОМПА» вместо «Норникель»)."""
    try:
        d = json.load(open(r'C:\\sender\\_ops\\sales_base.json', encoding='utf-8'))
    except Exception as ex:  # noqa: BLE001
        p('БАЗА не прочитана:', type(ex).__name__, str(ex)[:60])
        return
    строки = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                строки += v
    else:
        строки = d
    всего = обрез = без_кавычек = длинный_бренд = 0
    примеры = []
    for x in строки:
        n = str(x.get('name') or '')
        if not n:
            continue
        всего += 1
        # открывающая кавычка есть, закрывающей нет -> имя срезано
        if n.count('"') == 1 or n.count('«') > n.count('»'):
            обрез += 1
            if len(примеры) < 4:
                примеры.append(n[-42:])
        if '"' not in n and '«' not in n:
            без_кавычек += 1
        б = EC.бренд_компании(n, '')
        if len(б) > 26 or len(б.split()) > 3:
            длинный_бренд += 1
    p('БАЗА: имён=%d обрезано=%d без_кавычек=%d бренд_длинный=%d'
      % (всего, обрез, без_кавычек, длинный_бренд))
    p('  примеры обрезанных:', json.dumps(примеры, ensure_ascii=False))


def main():
    отпечаток()
    обрезанные_имена()
    for inn in sys.argv[1:]:
        p('===== ИНН', inn)
        адреса = [
            ('44_как_в_коде',
             'https://zakupki.gov.ru/epz/contract/search/rss.html?searchString='
             + inn + '&morphology=on&fz44=on&contractStageList_0=on'
             '&contractStageList_1=on&contractStageList_2=on'
             '&contractStageList_3=on&recordsPerPage=_50'),
            ('44_голый',
             'https://zakupki.gov.ru/epz/contract/search/rss.html?searchString=' + inn),
            ('223_реестр_договоров',
             'https://zakupki.gov.ru/epz/contractfz223/search/rss.html?searchString='
             + inn + '&recordsPerPage=_50'),
            ('223_вариант2',
             'https://zakupki.gov.ru/epz/contractfz223/search/rss.html?searchString='
             + inn + '&morphology=on&recordsPerPage=_50'),
        ]
        ссылки223 = []
        for метка, u in адреса:
            items, сост = rss(u)
            p('  %-22s items=%s %s' % (метка, (len(items) if items is not None else '-'), сост))
            if метка.startswith('223') and items:
                for it in items[:2]:
                    lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
                    if lm:
                        v = lm.group(1)
                        ссылки223.append('https://zakupki.gov.ru' + v
                                         if v.startswith('/') else v)
            time.sleep(1.0)
        # если 223 что-то дал — смотрим карточку договора ЦЕЛИКОМ
        for u in ссылки223[:1]:
            try:
                h = EC._eis_get(u, timeout=40)
            except Exception as ex:  # noqa: BLE001
                p('  карточка223 ОШИБКА', type(ex).__name__, str(ex)[:60])
                continue
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                       re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                              flags=re.S | re.I)))
            почты = [x for x in ПОЧТА.findall(t) if 'zakupki' not in x.lower()]
            p('  карточка223 %s байт=%d текст=%d Контактн=%d почт=%d тел=%d'
              % (u[-60:], len(h), len(t), len(re.findall(r'Контактн\w+', t)),
                 len(почты), len(ТЕЛ.findall(t))))
            m = re.search(r'(Контактн\w+.{0,400})', t)
            if m:
                p('  КУСОК:', m.group(1)[:380])
            if почты:
                p('  ПОЧТЫ:', почты[:5])
    p('ИТОГ: проверено ИНН=%d' % (len(sys.argv) - 1))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-500:])
