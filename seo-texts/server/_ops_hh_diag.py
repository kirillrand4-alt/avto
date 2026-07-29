# -*- coding: utf-8 -*-
"""Почему hh отдаёт ноль вакансий: показываем КАЖДЫЙ шаг поиска работодателя.

Прогон по 95 компаниям дал 0 вакансий, хотя до правок 32 компании давали 8.
Причин может быть три, и лечатся они по-разному: не стартует дельфин (тогда
пустой html), промахивается поиск по бренду (тогда html есть, а вакансий нет),
или новый рубеж принадлежности рубит всё подряд (тогда есть и html, и id, а
контактов ноль). Печатаем всё три состояния.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

e = EDB.EnrichDB().cx


def main():
    инны = [a for a in sys.argv[1:] if a.isdigit()]
    имена = {}
    try:
        БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
        порядок = []
        for строки in БАЗА.values():
            for x in строки:
                i = str(x.get('inn') or '').strip()
                n = str(x.get('name') or '').strip()
                if i and n and i not in имена:
                    имена[i] = n
                    порядок.append(i)
    except Exception:  # noqa: BLE001
        порядок = []
    # без аргументов берём НАСТОЯЩИЕ цели прогона, а не случайные ИНН: две
    # предыдущие пробы ушли в компании, которых в базе нет, и мерили пустоту
    if not инны:
        инны = порядок[:3]
    out = []
    for inn in инны:
        c = e.execute('SELECT name, site FROM companies WHERE inn=?',
                      (inn,)).fetchone()
        имя, сайт = (c or ['', ''])[0] or '', (c or ['', ''])[1] or ''
        # companies.name у части ИНН ПУСТО, а боевой прогон берёт имя из базы
        # продажников — значит и диагностика обязана брать оттуда же, иначе
        # меряет не то: на первой пробе бренд вышел пустым и функция вышла
        # сразу, хотя дельфин отдал страницу с шестью вакансиями.
        if not имя:
            имя = имена.get(inn, '')
        бренд = EC.бренд_компании(имя, сайт)
        зап = {'инн': inn, 'имя': имя[:60], 'сайт': сайт, 'бренд': бренд}
        # 1. что отдаёт дельфин на страницу поиска
        try:
            import browser_probe as BP
            tokd = EC._read_secret('DOLPHIN_TOKEN')
            профили = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
            зап['токен_дельфина'] = bool(tokd)
            зап['профилей'] = len(профили)
            u = ('https://hh.ru/search/vacancy?text='
                 + __import__('urllib.parse', fromlist=['x']).quote(бренд)
                 + '&search_field=company_name&items_on_page=50')
            r = BP.probe({'url': u, 'return_html': True, 'html_cap': 900000,
                          'wait_ms': 6000, 'screenshot': False, 'solve': True,
                          'dolphin_profile': профили[0], 'dolphin_token': tokd})
            h = (r or {}).get('html') or ''
            зап['поиск_байт'] = len(h)
            зап['поиск_ошибка'] = (r or {}).get('error') or ''
            зап['капча'] = (r or {}).get('captcha_type') or ''
            зап['вакансий_в_разметке'] = len(set(re.findall(r'/vacancy/(\d+)', h)))
            зап['есть_ничего_не_найдено'] = 'не найдено' in h.lower()
        except Exception as ex:  # noqa: BLE001
            зап['дельфин'] = f'{type(ex).__name__}: {str(ex)[:110]}'
        # 2. что отдаёт боевая функция целиком
        try:
            res = EC.hh_lpr_contacts({'name': имя, 'inn': inn, 'site': сайт})
            зап['боевая'] = {'вакансий': len((res or {}).get('vacancies') or []),
                             'контактов': len((res or {}).get('contacts') or []),
                             'отказ': (res or {}).get('отказ'),
                             'пропущено': ((res or {}).get('пропущено') or [])[:3]}
        except Exception as ex:  # noqa: BLE001
            зап['боевая'] = f'{type(ex).__name__}: {str(ex)[:110]}'
        out.append(зап)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4500])


if __name__ == '__main__':
    main()
