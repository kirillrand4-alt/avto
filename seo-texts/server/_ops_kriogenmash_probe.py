# -*- coding: utf-8 -*-
"""Разведка по конкретной компании: почему обход не нашёл ни одного человека.

Печатаем сырьё, а не выводы: сколько байт отдала главная, сколько на ней
внутренних ссылок и какие, что говорит поиск на прямые запросы про
руководство и главного инженера, и что отвечает hh на имя работодателя.
"""
import json
import re
import sys
import urllib.parse

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ДОМ = sys.argv[1] if len(sys.argv) > 1 else 'cryogenmash.ru'
ИМЯ = ' '.join(sys.argv[2:]) or 'Криогенмаш'


def серп(запрос, n=10):
    import os
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return ['нет ключей xmlriver']
    u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
         + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
         + '&query=' + urllib.parse.quote(запрос))
    try:
        xml = EC._DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace')
    except Exception as ex:  # noqa: BLE001
        return [f'{type(ex).__name__}: {str(ex)[:60]}']
    ош = re.search(r'<error[^>]*>(.{0,90})', xml, re.S)
    if ош:
        return ['ошибка выдачи: ' + ош.group(1).strip()]
    из = []
    for блок in re.findall(r'<doc>(.*?)</doc>', xml, re.S)[:n]:
        url = (re.search(r'<url>(.*?)</url>', блок, re.S) or [None, ''])[1] \
            if False else ''
        m = re.search(r'<url>(.*?)</url>', блок, re.S)
        t = re.search(r'<title>(.*?)</title>', блок, re.S)
        url = (m.group(1).strip() if m else '')
        загл = re.sub(r'<[^>]+>', '', t.group(1)) if t else ''
        из.append({'url': url[:110], 'заголовок': загл[:90]})
    return из


def main():
    out = {'домен': ДОМ}
    h, _m, mt = EC._fetch_site('http://' + ДОМ)
    out['главная_байт'] = len(h or '')
    out['главная_статус'] = mt.get('status') or mt.get('error') or ''
    out['капча'] = mt.get('captcha_type') or ''
    ссылки = []
    for u in re.findall(r'href="([^"#]+)"', h or ''):
        if u.startswith('/'):
            u = 'http://' + ДОМ + u
        if EC.site_domain(u) == ДОМ and u not in ссылки:
            ссылки.append(u)
    out['внутренних_ссылок'] = len(ссылки)
    out['ссылки'] = [u[:90] for u in ссылки[:40]]
    подсказки = [u for u in ссылки
                 if any(k in u.lower() for k in EC._STAFF_HINTS)]
    out['ссылки_на_людей'] = [u[:90] for u in подсказки[:12]]
    out['есть_слово_руководство'] = 'руководств' in (h or '').lower()
    out['есть_слово_инженер'] = 'инженер' in (h or '').lower()

    out['выдача'] = {}
    for з in (f'{ИМЯ} руководство', f'{ИМЯ} главный инженер',
              f'{ИМЯ} технический директор', f'сайт:{ДОМ} руководство',
              f'{ИМЯ} контакты отдел снабжения'):
        out['выдача'][з] = серп(з, 6)

    try:
        hh = EC.hh_lpr_contacts({'name': ИМЯ, 'inn': ''})
        out['hh'] = {'вакансий': len((hh or {}).get('vacancies') or []),
                     'контактов': len((hh or {}).get('contacts') or []),
                     'примеры': [(v.get('name') or '')[:60]
                                 for v in ((hh or {}).get('vacancies') or [])[:8]]}
    except Exception as ex:  # noqa: BLE001
        out['hh'] = f'{type(ex).__name__}: {str(ex)[:70]}'
    print(json.dumps(out, ensure_ascii=False, indent=1)[:8000])


if __name__ == '__main__':
    main()
