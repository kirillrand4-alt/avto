# -*- coding: utf-8 -*-
"""hh-ИНВЕРСИЯ, шаг 2а: ИНН С САЙТА РАБОТОДАТЕЛЯ (доказательство принадлежности).

Зачем именно так. Резолв «название -> ИНН» через dadata угадывает, и на этом
уже обожглись: по слову «криоген» открылся чужой завод в другом городе. hh же
сам публикует у работодателя АДРЕС САЙТА (companySiteUrl) — то есть говорит,
чей это сайт. Если на этом сайте написан ИНН, связка получается не по
совпадению слова, а по цепочке «hh называет сайт компании -> сайт называет
свой ИНН». Это лучшее доказательство, доступное без ручной проверки.

Ходим ЛОКАЛЬНО из песочницы: у сервера IP помечен, а тут обычный HTTPS.
Пишем построчно с fsync — прогон резюмируемый.
"""
import concurrent.futures as cf
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# Якорь ОБЯЗАТЕЛЕН: голые десять цифр на странице — это что угодно (телефон,
# артикул, номер счёта). Ровно на этом в проекте уже подрывались: «ОГРН
# 1083801006860» читался регуляркой как телефон 83801006860.
_ИНН = re.compile(r'ИНН[\s:/\\-]*(?:КПП[\s:/\\-]*)?(\d{10}|\d{12})(?!\d)', re.I)
_ОГРН = re.compile(r'ОГРН(?:ИП)?[\s:/\\-]*(\d{13}|\d{15})(?!\d)', re.I)

_ПУТИ = ('', '/contacts/', '/kontakty/', '/about/', '/contact/', '/o-kompanii/',
         '/company/', '/rekvizity/')


def _norm_host(u):
    u = (u or '').strip()
    if not u:
        return ''
    if not re.match(r'^https?://', u, re.I):
        u = 'http://' + u
    try:
        h = urllib.parse.urlparse(u).netloc.lower().split(':')[0]
    except Exception:  # noqa: BLE001
        return ''
    return h[4:] if h.startswith('www.') else h


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': 'text/html,*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(1200000)
        if (r.headers.get('Content-Encoding') or '').lower() == 'gzip':
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except Exception:  # noqa: BLE001
                pass
        enc = 'utf-8'
        ct = (r.headers.get('Content-Type') or '').lower()
        if 'windows-1251' in ct or 'cp1251' in ct:
            enc = 'cp1251'
        txt = raw.decode(enc, 'replace')
        if enc == 'utf-8' and 'windows-1251' in txt[:2000].lower():
            txt = raw.decode('cp1251', 'replace')
        return txt, r.geturl()


def проверить_сайт(host):
    """Возвращает {'inn':…, 'ogrn':…, 'url':…, 'ходов':N} или причину отказа."""
    инны, огрны, где, ходов, ошибка = {}, {}, {}, 0, ''
    for схема in ('https://', 'http://'):
        for путь in _ПУТИ:
            url = схема + host + путь
            try:
                txt, real = _fetch(url)
                ходов += 1
            except Exception as e:  # noqa: BLE001
                ошибка = ошибка or f'{type(e).__name__}: {str(e)[:60]}'
                if путь == '' and схема == 'http://':
                    return {'ошибка': ошибка, 'ходов': ходов}
                continue
            for m in _ИНН.findall(txt):
                инны[m] = инны.get(m, 0) + 1
                где.setdefault(m, real)
            for m in _ОГРН.findall(txt):
                огрны[m] = огрны.get(m, 0) + 1
            if инны:
                break
        if инны or ходов:
            break
    if not инны:
        return {'ошибка': ошибка or 'ИНН на сайте не написан', 'ходов': ходов}
    # Если на сайте несколько РАЗНЫХ ИНН (холдинг, партнёры, реквизиты в
    # оферте) — это НЕ доказательство, а неоднозначность. Берём только когда
    # кандидат один либо один явно доминирует.
    парами = sorted(инны.items(), key=lambda kv: -kv[1])
    if len(парами) > 1 and парами[0][1] <= парами[1][1]:
        return {'ошибка': f'на сайте {len(парами)} разных ИНН, не различить',
                'кандидаты': [p[0] for p in парами[:4]], 'ходов': ходов}
    inn = парами[0][0]
    return {'inn': inn, 'ogrn': (sorted(огрны.items(), key=lambda kv: -kv[1])[0][0]
                                 if огрны else ''),
            'url': где.get(inn, ''), 'ходов': ходов,
            'всего_инн_на_сайте': len(парами)}


def main():
    src = sys.argv[1]
    out = sys.argv[2]
    recs = [json.loads(l) for l in open(src, encoding='utf-8')]
    хосты = {}
    for r in recs:
        h = _norm_host(r.get('employer_site'))
        if not h:
            continue
        хосты.setdefault(h, set()).add((r['employer_id'], r['employer']))
    готово = set()
    if os.path.exists(out):
        for l in open(out, encoding='utf-8'):
            try:
                готово.add(json.loads(l)['host'])
            except Exception:  # noqa: BLE001
                pass
    надо = [h for h in хосты if h not in готово]
    print(f'=== СТАРТ: хостов всего {len(хосты)}, уже сделано {len(готово)}, '
          f'к обходу {len(надо)} ===', flush=True)
    fh = open(out, 'a', encoding='utf-8')
    сч = {'инн': 0, 'нет': 0, 'ошибка': 0}
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        fut = {ex.submit(проверить_сайт, h): h for h in надо}
        for i, f in enumerate(cf.as_completed(fut), 1):
            h = fut[f]
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                res = {'ошибка': f'{type(e).__name__}: {str(e)[:60]}'}
            res['host'] = h
            res['employers'] = [{'id': a, 'name': b} for a, b in sorted(хосты[h])]
            fh.write(json.dumps(res, ensure_ascii=False) + '\n')
            fh.flush()
            os.fsync(fh.fileno())
            if res.get('inn'):
                сч['инн'] += 1
            elif 'не написан' in (res.get('ошибка') or ''):
                сч['нет'] += 1
            else:
                сч['ошибка'] += 1
            if i % 50 == 0:
                print(f'  {i}/{len(надо)} инн={сч["инн"]} нет={сч["нет"]} '
                      f'ошибка={сч["ошибка"]}', flush=True)
    fh.close()
    print(f'=== ИТОГ: обойдено {len(надо)}, ИНН найден у {сч["инн"]}, '
          f'ИНН не написан у {сч["нет"]}, сайт не открылся у {сч["ошибка"]} ===')


if __name__ == '__main__':
    main()
