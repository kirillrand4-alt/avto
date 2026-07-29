# -*- coding: utf-8 -*-
"""Чей это работодатель: проверка привязки вакансий hh к компании.

Запасной путь через выдачу берёт ПЕРВУЮ ссылку вида hh.ru/employer/<id>, а
выдача по бренду легко приводит к однофамильцу. Прежде чем оставить в базе
шесть телефонов, надо увидеть НАЗВАНИЕ работодателя на самой странице
вакансии. Ничего не пишем — только смотрим.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def main():
    адреса = [a for a in sys.argv[1:] if a.startswith('http')]
    if not адреса:
        адреса = ['https://hh.ru/vacancy/134482395',
                  'https://hh.ru/vacancy/135068450']
    r = EC.hh_lpr_contacts.__globals__  # доступ к _пачка нельзя — зовём probe сам
    import browser_probe as BP
    tokd = EC._read_secret('DOLPHIN_TOKEN')
    профили = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
    res = BP.probe({'url': адреса[0], 'urls': адреса, 'return_html': True,
                    'html_cap': 1200000, 'urls_cap': len(адреса),
                    'wait_ms': 6000, 'urls_wait_ms': 2500, 'screenshot': False,
                    'solve': True, 'dolphin_profile': профили[0],
                    'dolphin_token': tokd})
    страницы = [{'url': (res or {}).get('url'), 'html': (res or {}).get('html')}]
    страницы += list((res or {}).get('pages') or [])
    out = []
    for стр in страницы:
        h = стр.get('html') or ''
        if not h:
            continue
        имена = re.findall(r'"employer"\s*:\s*\{[^{}]{0,200}?"name"\s*:\s*"([^"]{2,90})"', h)
        имена += re.findall(r'data-qa="vacancy-company-name"[^>]*>\s*<[^>]*>\s*([^<]{2,80})', h)
        имена += re.findall(r'<title>([^<]{5,140})</title>', h)
        out.append({'url': (стр.get('url') or '')[:70],
                    'байт': len(h),
                    'работодатель': sorted(set(x.strip() for x in имена))[:4],
                    'есть_криогенмаш': 'риогенмаш' in h,
                    'есть_эльмаш': 'льмаш' in h})
    print(json.dumps(out, ensure_ascii=False, indent=1)[:3000])


if __name__ == '__main__':
    main()
