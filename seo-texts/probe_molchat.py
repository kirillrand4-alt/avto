# -*- coding: utf-8 -*-
"""Проверить браузером домены, промолчавшие обходчику: защита это или пустота.

30 доменов не отдали простому обходчику НИ ОДНОЙ страницы. Гипотеза была «их держит
защита», но гипотезу надо проверять, а не записывать в вывод. `browser_probe` открывает
страницу настоящим Chromium — если и он видит капчу, гипотеза подтверждена; если страница
открывается, значит дело в обходчике, и вывод надо менять.

Скриншоты браузера складываются на дроп и остаются там мусором — владелец уже просил такие
удалять. Поэтому имена снимков собираются и стираются в конце.
"""
import json, re, subprocess, sys, time

RUN = '/home/user/avto/seo-texts/server/run_on_server.py'
DROP = '/home/user/avto/seo-texts/server/drop_client.sh'
KAPCHA = re.compile(r'капч|captcha|robot|не робот|проверка безопасн|cloudflare|'
                    r'доступ ограничен|подтвердите', re.I)

domeny = json.load(open('molchat-domeny.json', encoding='utf-8'))
itog, snimki = [], []
for i, d in enumerate(domeny, 1):
    arg = json.dumps({'url': f'https://{d}/', 'wait': 4}, ensure_ascii=False)
    try:
        p = subprocess.run([sys.executable, RUN, 'browser_probe', arg],
                           capture_output=True, text=True, timeout=300)
        o = json.loads(p.stdout[p.stdout.find('{'):])
    except Exception as e:  # noqa: BLE001
        itog.append({'domen': d, 'itog': 'сбой задания', 'podrobno': str(e)[:80]})
        print(f'[{i}/{len(domeny)}] {d}: СБОЙ ЗАДАНИЯ', file=sys.stderr, flush=True)
        continue
    dd = o.get('data') or {}
    # Поле называется `text_snippet`, а не `text`. С неверным именем ВСЕ домены выглядели
    # как «пусто и в браузере» — то есть проверка бодро подтверждала бы вывод, которого
    # на самом деле не проверяла. Заголовок берём тоже: у капчи он прямо «Captcha».
    t = ((dd.get('title') or '') + ' ' + (dd.get('text_snippet') or ''))[:4000].strip()
    st = dd.get('http_status')
    if dd.get('screenshot_drop'):
        snimki.append(dd['screenshot_drop'])
    if KAPCHA.search(t):
        vyvod = 'КАПЧА'
    elif not o.get('ok'):
        vyvod = 'браузер не открыл'
    elif len(t) < 400:
        vyvod = f'пусто и в браузере ({len(t)} знаков)'
    else:
        vyvod = f'ОТКРЫЛСЯ, {len(t)} знаков — дело не в защите'
    itog.append({'domen': d, 'itog': vyvod, 'http': st, 'znakov': len(t),
                 'nachalo': t[:160]})
    print(f'[{i}/{len(domeny)}] {d}: {vyvod}', file=sys.stderr, flush=True)

json.dump(itog, open('molchat-proverka.json', 'w', encoding='utf-8'), ensure_ascii=False,
          indent=1)
sv = {}
for x in itog:
    k = x['itog'].split(',')[0].split(' (')[0]
    sv[k] = sv.get(k, 0) + 1
print(f'\nитог по 30 доменам: {sv}', file=sys.stderr)

# За собой убираем: снимки браузера — мусор на дропе, владелец уже просил такие удалять.
for s in snimki:
    subprocess.run(['bash', DROP, 'del', s], capture_output=True, timeout=60)
print(f'снимков браузера удалено с дропа: {len(snimki)}', file=sys.stderr)
