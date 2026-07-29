# -*- coding: utf-8 -*-
"""hh-ИНВЕРСИЯ, шаг 2а-бис: добор ИНН с сайтов, где первый заход не дал ничего.

Первый заход угадывал адрес страницы контактов из списка (/contacts/, /about/…)
и на 308 сайтах из 505 получил 404 — то есть главная открылась, а угаданного
пути на этом движке просто нет. Правильный способ — не угадывать, а ПРОЧИТАТЬ
ССЫЛКИ С ГЛАВНОЙ и пойти по тем, что называются «контакты» / «о компании» /
«реквизиты». Здесь же добавлен футер: на большинстве корпоративных сайтов ИНН
стоит именно в нём, и главной хватает.
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hh_site_inn import _ИНН, _ОГРН, _fetch, _norm_host  # noqa: E402

_ССЫЛКА = re.compile(r'<a[^>]+href=["\']([^"\'>]{1,300})["\'][^>]*>(.{0,120}?)</a>',
                     re.I | re.S)
_ХОЧУ = re.compile(r'контакт|contact|о\s*компани|о\s*нас|about|реквизит|'
                   r'requisite|company|предприяти', re.I)


def _текст(s):
    return re.sub(r'<[^>]+>', ' ', s or '').strip()


def добор(host):
    инны, огрны, где, ходов, ошибки = {}, {}, {}, 0, []
    главная, база = '', ''
    for схема in ('https://', 'http://'):
        try:
            главная, база = _fetch(схема + host, timeout=22)
            ходов += 1
            break
        except Exception as e:  # noqa: BLE001
            ошибки.append(f'{type(e).__name__}: {str(e)[:50]}')
    if not главная:
        return {'ошибка': '; '.join(ошибки)[:120] or 'главная не открылась',
                'ходов': ходов}

    def собрать(txt, url):
        for m in _ИНН.findall(txt):
            инны[m] = инны.get(m, 0) + 1
            где.setdefault(m, url)
        for m in _ОГРН.findall(txt):
            огрны[m] = огрны.get(m, 0) + 1

    собрать(главная, база)
    if not инны:
        кандидаты, видели = [], set()
        for href, подпись in _ССЫЛКА.findall(главная):
            if not (_ХОЧУ.search(подпись) or _ХОЧУ.search(href)):
                continue
            u = urllib.parse.urljoin(база, href.strip())
            if _norm_host(u) != host or u in видели:
                continue
            видели.add(u)
            кандидаты.append(u)
            if len(кандидаты) >= 5:
                break
        for u in кандидаты:
            try:
                txt, real = _fetch(u, timeout=20)
                ходов += 1
                собрать(txt, real)
            except Exception as e:  # noqa: BLE001
                ошибки.append(f'{type(e).__name__}: {str(e)[:40]}')
            if инны:
                break
    if not инны:
        return {'ошибка': 'ИНН на сайте не написан', 'ходов': ходов}
    парами = sorted(инны.items(), key=lambda kv: -kv[1])
    if len(парами) > 1 and парами[0][1] <= парами[1][1]:
        return {'ошибка': f'на сайте {len(парами)} разных ИНН, не различить',
                'кандидаты': [p[0] for p in парами[:4]], 'ходов': ходов}
    inn = парами[0][0]
    return {'inn': inn,
            'ogrn': (sorted(огрны.items(), key=lambda kv: -kv[1])[0][0] if огрны else ''),
            'url': где.get(inn, ''), 'ходов': ходов, 'всего_инн_на_сайте': len(парами)}


def main():
    было = sys.argv[1]          # hh_site_inn.jsonl (первый заход)
    out = sys.argv[2]           # hh_site_inn2.jsonl
    исх = [json.loads(l) for l in open(было, encoding='utf-8')]
    надо = {r['host']: r for r in исх if not r.get('inn')}
    готово = set()
    if os.path.exists(out):
        for l in open(out, encoding='utf-8'):
            try:
                готово.add(json.loads(l)['host'])
            except Exception:  # noqa: BLE001
                pass
    цель = [h for h in надо if h not in готово]
    print(f'=== ДОБОР: без ИНН было {len(надо)}, к обходу {len(цель)} ===', flush=True)
    fh = open(out, 'a', encoding='utf-8')
    сч = {'инн': 0, 'нет': 0}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        fut = {ex.submit(добор, h): h for h in цель}
        for i, f in enumerate(cf.as_completed(fut), 1):
            h = fut[f]
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                res = {'ошибка': f'{type(e).__name__}: {str(e)[:60]}'}
            res['host'] = h
            res['employers'] = надо[h].get('employers') or []
            fh.write(json.dumps(res, ensure_ascii=False) + '\n')
            fh.flush()
            os.fsync(fh.fileno())
            сч['инн' if res.get('inn') else 'нет'] += 1
            if i % 60 == 0:
                print(f'  {i}/{len(цель)} инн={сч["инн"]} нет={сч["нет"]}', flush=True)
    fh.close()
    print(f'=== ИТОГ добора: ИНН найден ещё у {сч["инн"]} из {len(цель)} ===')


if __name__ == '__main__':
    main()
