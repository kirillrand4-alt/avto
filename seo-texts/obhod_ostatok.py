# -*- coding: utf-8 -*-
"""Обход оставшихся предприятий с известным сайтом — пачками по 12.

ПОЧЕМУ ПО 12. Задание раннера умирает по таймауту на 1800 с. Замерено: пачка 82 сайта не
доходит никогда, 30 прошли один раз из одного, 25 упали один раз из четырёх, 12 проходят
устойчиво. Пачка больше — это не «быстрее», это потерянный час и ноль строк.

ПОЧЕМУ РЕЗУЛЬТАТ ПИШЕТСЯ СРАЗУ. Пачка кладётся в свой файл `obhod-n-<id>.json` и ИНН
вычёркиваются из остатка тем же шагом. Иначе падение на середине списка стирает всё, что
уже прошло, — так уже было.
"""
import json, os, re, subprocess, sys, time

OST = 'obhod-ostatok.json'
RUN = '/home/user/avto/seo-texts/server/run_on_server.py'
PACHKA = int(os.environ.get('PACHKA', '12'))
PACHEK = int(os.environ.get('PACHEK', '4'))

ost = json.load(open(OST, encoding='utf-8'))
sdelano_f = 'obhod-sdelano.json'
sdelano = set(json.load(open(sdelano_f)) if os.path.exists(sdelano_f) else [])
ochered = [x for x in ost if x['inn'] not in sdelano]
print(f'в остатке {len(ochered)} предприятий, пачек по {PACHKA} запускаю {PACHEK}', file=sys.stderr)

for k in range(PACHEK):
    pach = ochered[k * PACHKA:(k + 1) * PACHKA]
    if not pach:
        break
    # Задача ждёт СПИСОК СТРОК-доменов, а не карточек, и отвечает словарём по ДОМЕНУ,
    # не по ИНН. Первый заход отдал 0 страниц за 35 с — задача падала на `su.startswith`,
    # получив словарь. Соответствие домен→ИНН держу здесь.
    po_domenu = {}
    for x in pach:
        d = (x.get('domain') or '').strip().lower()
        d = re.sub(r'^https?://', '', d).split('/')[0]
        if d.startswith('www.'):
            d = d[4:]
        if d:
            po_domenu[d] = x
    arg = json.dumps({'site_crawl': sorted(po_domenu), 'pages_cap': 40}, ensure_ascii=False)
    t = time.time()
    p = subprocess.run([sys.executable, RUN, 'news_scan', arg],
                       capture_output=True, text=True, timeout=2100)
    out = p.stdout.strip()
    if not out or out.lstrip()[:1] not in '{[':
        print(f'пачка {k+1}: СБОЙ раннера — {(p.stderr or out)[:200]}', file=sys.stderr)
        continue
    d = json.loads(out)
    # Ответ кладём НА ДИСК ДО любых проверок. Пачка 3 вернула ok=false, а в её stderr стояло
    # «gkoksugol.ru: 36 страниц, metafrax.ru: 40, npoiskra.ru: 40» — то есть обход прошёл, а
    # упало что-то после него, и мой ранний `continue` выбросил час работы сервера.
    nom = f'obhod-ost-{int(t)}-{k+1}.json'
    json.dump(d, open(nom, 'w', encoding='utf-8'), ensure_ascii=False)
    stranicy = ((d.get('data') or {}).get('pages') or {})
    if not stranicy:
        print(f'пачка {k+1}: ни одной страницы, ok={d.get("ok")} — '
              f'{str(d.get("stderr_tail"))[-300:]}', file=sys.stderr)
        continue
    if not d.get('ok'):
        print(f'пачка {k+1}: задача пометилась упавшей, но страницы есть — беру их. '
              f'Хвост ошибки: {str(d.get("stderr_tail"))[-200:]}', file=sys.stderr)
    d['inn_po_domenu'] = {dm: po_domenu[dm]['inn'] for dm in po_domenu}
    nom = f'obhod-ost-{int(t)}-{k+1}.json'
    json.dump(d, open(nom, 'w', encoding='utf-8'), ensure_ascii=False)
    # Вычёркиваем только те ИНН, по которым РЕАЛЬНО пришёл ответ. Заявленные, но не
    # вернувшиеся, остаются в очереди: ноль это отказ прибора, пока не доказано иное.
    # Вычёркиваем только домены, вернувшие ХОТЯ БЫ ОДНУ страницу. Домен, ответивший пусто,
    # остаётся в очереди: это может быть блокировка или ГОСТ-TLS, а не «нечего брать».
    prishli = {po_domenu[dm]['inn'] for dm, ps in stranicy.items() if dm in po_domenu and ps}
    pusto = [dm for dm, ps in stranicy.items() if not ps]
    sdelano |= prishli
    json.dump(sorted(sdelano), open(sdelano_f, 'w'))
    stranic = sum(len(ps) for ps in stranicy.values())
    print(f'пачка {k+1}: заявлено {len(pach)}, с текстом {len(prishli)}, пусто {len(pusto)}, '
          f'страниц {stranic}, {int(time.time()-t)} с → {nom}', file=sys.stderr)
    if pusto:
        print(f'    пустые: {", ".join(pusto[:12])}', file=sys.stderr)
print(f'сделано всего: {len(sdelano)} из {len(ost)}', file=sys.stderr)
