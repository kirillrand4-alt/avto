# -*- coding: utf-8 -*-
"""hh-ИНВЕРСИЯ, сбор вакансий — СЕРВЕРНАЯ версия (для регулярного прогона).

Важная поправка к тому, что считалось известным. В передаче сессии записано,
что обычная выдача hh с серверного IP отдаёт капчу, и из-за этого весь сбор
шёл из песочницы. Проверка 29.07 показала другое: капчи нет, отдаётся живой
HH-Lux-InitialState с totalResults 541 и сотней вакансий на страницу. Ноль,
который я получил перед этим, был дефектом МОЕЙ проверки — она искала
"vacancyId" в СЫРОМ html, где кавычки экранированы, вместо распакованного
стейта. Ровно тот случай, про который в передаче написано «пустой ответ ещё не
сломанный источник».

Единственное, что действительно важно, — заголовки: с 'Accept: text/html,
application/json' hh отвечает 406 Not Acceptable, с полным набором заголовков
Chrome — 200. Поэтому набор заголовков здесь трогать нельзя.

Пишет durable-поток на сервере (C:\\seostat\\drop\\drop-storage) с fsync,
резюмируется по vacancy_id, бюджет времени — аргументом.
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

STORE = r'C:\seostat\drop\drop-storage'
OUT = os.path.join(STORE, 'hh_inv_vacancies.jsonl')

ЗАГОЛОВКИ = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                   ' (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'),
    'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
               'image/avif,image/webp,*/*;q=0.8'),
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8',
    'Accept-Encoding': 'identity',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1',
    'sec-ch-ua': '"Chromium";v="126", "Google Chrome";v="126"',
    'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"',
}

# по НАЗВАНИЮ должности — сильный сигнал (человек нужен к машине)
ПО_НАЗВАНИЮ = ['компрессор', 'компрессорная станция', 'воздухоразделения',
               'воздухоразделительной установки', 'воздуходувных машин',
               'азотная станция', 'кислородная станция', 'технических газов',
               'криогенного производства', 'пневматического оборудования']
# по ТЕКСТУ вакансии — сигнал слабее, но работодателей втрое больше
ПО_ТЕКСТУ = ['"компрессорная станция"', '"компрессорного оборудования"',
             '"сжатого воздуха"', '"машинист компрессорных установок"',
             '"винтовой компрессор"', '"азотная станция"',
             '"воздухоразделительная установка"', '"генератор азота"',
             '"компрессорный цех"', '"осушитель воздуха"']

_ОП = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(url, tries=3):
    for a in range(tries):
        try:
            return _ОП.open(urllib.request.Request(url, headers=ЗАГОЛОВКИ),
                            timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if a == tries - 1:
                print(f'   ! {type(e).__name__}: {str(e)[:80]}', flush=True)
            time.sleep(3.0 * (a + 1))
    return ''


def _state(b):
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', b or '', re.S)
    if not m:
        return {}
    try:
        return json.loads(html.unescape(m.group(1)))
    except Exception:  # noqa: BLE001
        return {}


def страница(q, page, field):
    url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q)
           + f'&area=113&items_on_page=100&search_period=30&search_field={field}'
           + (f'&page={page}' if page else ''))
    vr = _state(_get(url)).get('vacancySearchResult') or {}
    return vr.get('totalResults'), (vr.get('vacancies') or [])


def main():
    бюджет = 380.0
    for i, a in enumerate(sys.argv):
        if a == '--budget' and i + 1 < len(sys.argv):
            бюджет = float(sys.argv[i + 1])
    только = None
    for i, a in enumerate(sys.argv):
        if a == '--queries' and i + 1 < len(sys.argv):
            только = sys.argv[i + 1]
    t0 = time.time()
    seen = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8'):
            try:
                seen.add(str(json.loads(ln).get('vacancy_id')))
            except Exception:  # noqa: BLE001
                pass
    print(f'=== СТАРТ сбор (сервер): в файле уже {len(seen)} вакансий, '
          f'бюджет {бюджет:.0f}с ===', flush=True)
    fh = open(OUT, 'a', encoding='utf-8')
    новых, свод = 0, []
    задания = ([(q, 'name') for q in ПО_НАЗВАНИЮ]
               + [(q, 'description') for q in ПО_ТЕКСТУ])
    if только:
        задания = [z for z in задания if только in z[0]]
    for q, field in задания:
        if time.time() - t0 > бюджет:
            свод.append((q, field, 'бюджет кончился', 0))
            continue
        стр, добавлено, total = 0, 0, None
        while стр < 12 and time.time() - t0 < бюджет:
            t, vs = страница(q, стр, field)
            if total is None:
                total = t
            if not vs:
                break
            for v in vs:
                vid = str(v.get('vacancyId') or '')
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                c = v.get('company') or {}
                fh.write(json.dumps({
                    'vacancy_id': vid, 'vacancy': v.get('name') or '',
                    'vacancy_url': f'https://hh.ru/vacancy/{vid}',
                    'employer_id': str(c.get('id') or ''),
                    'employer': c.get('visibleName') or c.get('name') or '',
                    'employer_url': (f'https://hh.ru/employer/{c.get("id")}'
                                     if c.get('id') else ''),
                    'employer_site': (c.get('companySiteUrl') or '').strip(),
                    'area': (v.get('area') or {}).get('name') or '',
                    'city': (v.get('address') or {}).get('city') or '',
                    'published': ((v.get('publicationTime') or {}).get('$') or '')[:10],
                    'query': q, 'field': field,
                }, ensure_ascii=False) + '\n')
                добавлено += 1
                новых += 1
            fh.flush()
            os.fsync(fh.fileno())
            стр += 1
            if len(vs) < 100:
                break
            time.sleep(2.0)
        свод.append((q, field, total, добавлено))
        print(f'  {field:11s} {q[:34]:34s} hh={total} новых={добавлено}', flush=True)
    fh.close()
    print('=== ИТОГ ===', flush=True)
    for q, f, t, d in свод:
        print(f'  {f:11s} {q[:34]:34s} hh={t} новых={d}')
    print(f'НОВЫХ за прогон {новых}; ВСЕГО в файле {len(seen)}; '
          f'{time.time()-t0:.0f}с', flush=True)


if __name__ == '__main__':
    main()
    os._exit(0)
