# -*- coding: utf-8 -*-
"""СНИМОК У КАЖДОГО ДОКАЗАТЕЛЬСТВА — прямая просьба владельца.

Ссылку можно открыть и убедиться, но открывать 5 258 ссылок руками никто не станет.
Снимок показывает, что на том конце, не выходя из карточки: видно название предприятия,
предмет закупки или объект экспертизы — то есть ровно то, чем факт доказан.

Имя файла: `DOKAZ-<ИНН>-<номер факта>.png` — по ИНН и факту, а НЕ по времени.
Урок 3-й сессии: её проба называла кадры по секундам, и четыре потока, закончив в одну
секунду, писали один файл — 118 снимков имели 72 разных имени, под именем одного человека
лежала карточка про дробилки. Имя из ключа записи столкнуться не может.

Кладём прямо в статику панели (`C:\\seostat\\app\\static\\dokaz\\`), чтобы карточка
показывала картинку без отдельного сервера. Ход пишем в C:\\sender\\park_dokaz.jsonl
с fsync — переживает рестарт, повторный запуск продолжает с места.

Запуск: panel_py, argv = [<сколько за вызов>]
"""
import json, os, re, sys, time

ZAD = r'C:\sender\_dokaz_zadanie.json'
OUT = r'C:\sender\park_dokaz.jsonl'
# Папка ОБЯЗАНА содержать слово `centro`: приложение обзвона закрыто HTTP Basic
# везде, кроме таких путей, и `/static/dokaz/...` отвечал 401 — картинка в
# карточке не показывалась, хотя файл лежал на месте.
KUDA = r'C:\seostat\app\static\centro\dokaz'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


def sdelano():
    v = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8', errors='replace'):
            try:
                v.add(json.loads(ln)['fakt_id'])
            except Exception:
                pass
    return v


os.makedirs(KUDA, exist_ok=True)
skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 60
zad = json.load(open(ZAD, encoding='utf-8'))
gotovo = sdelano()
ochered = [z for z in zad if z['fakt_id'] not in gotovo][:skolko]
itog = {'v_zadanii': len(zad), 'ranee': len(gotovo), 'v_vyzove': len(ochered),
        'snyato': 0, 'pustaya_stranica': 0, 'oshibok': 0}
if not ochered:
    print(json.dumps(itog, ensure_ascii=False))
    sys.exit()

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    e = hrom()
    if e:
        kw['executable_path'] = e
    br = p.chromium.launch(**kw)
    ctx = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True,
                         viewport={'width': 1400, 'height': 900})
    pg = ctx.new_page()
    for z in ochered:
        imya = 'DOKAZ-%s-%s.png' % (z['inn'], z['fakt_id'])
        put = os.path.join(KUDA, imya)
        r = {'fakt_id': z['fakt_id'], 'inn': z['inn'], 'url': z['url'], 'snimok': imya,
             'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
        try:
            otv = pg.goto(z['url'], timeout=60000, wait_until='domcontentloaded')
            pg.wait_for_timeout(1800)
            t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            r['http'] = otv.status if otv else None
            r['znakov'] = len(t)
            # ИНН и слово типа на странице — чтобы по снимку было ясно, ЧТО он доказывает
            # Признаки считаем ПО СМЫСЛУ, а не буквой. На снимке «Ростсельмашэнерго»
            # подпись говорила «ИНН нет, слова типа нет», хотя на странице стоит и
            # название предприятия, и «Ремонт ротора компрессора К 250-61-1»: ИНН там
            # правда не печатается, а тип назван словом «компрессор», не
            # «турбокомпрессор». Подпись, которая занижает верное доказательство, хуже
            # отсутствия подписи.
            nizh = t.lower()
            r['inn_na_stranice'] = z['inn'] in t
            koren = ''
            for chast in re.findall(r'[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z\-]{4,}', z.get('nazvanie') or ''):
                if chast.upper() not in ('ОБЩЕСТВО', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ',
                                         'АКЦИОНЕРНОЕ', 'ПУБЛИЧНОЕ', 'ФЕДЕРАЛЬНОЕ'):
                    koren = chast.lower()
                    break
            r['imya_na_stranice'] = bool(koren and koren[:9] in nizh)
            SIN = {'турбокомпрессор': ['турбокомпрессор', 'центробежн', 'компрессор'],
                   'компрессорная станция': ['компрессорн'], 'ПКС': ['компрессор'],
                   'МКС': ['компрессорн'], 'ГПА': ['газоперекачив', 'нагнетател'],
                   'воздуходувка': ['воздуходувк', 'газодувк', 'компрессор'],
                   'ресивер': ['ресивер', 'воздухосборник'],
                   'осушитель': ['осушител', 'влагоотделител'],
                   'ВРУ': ['воздухораздел', 'кислород', 'азот'],
                   'генератор азота': ['азот'], 'генератор кислорода': ['кислород']}
            tip = z.get('tip') or ''
            slova = SIN.get(tip, [tip.split()[0].lower()[:9]] if tip else [])
            r['tip_na_stranice'] = any(s and s in nizh for s in slova)
            if len(t) < 300:
                r['verdikt'] = 'страница пустая — снимок не делаю'
                itog['pustaya_stranica'] += 1
            else:
                pg.screenshot(path=put, full_page=False)
                r['bayt'] = os.path.getsize(put)
                r['verdikt'] = 'снимок сделан'
                itog['snyato'] += 1
        except Exception as ex:
            r['verdikt'] = 'ошибка'
            r['oshibka'] = str(ex)[:140]
            itog['oshibok'] += 1
        with open(OUT, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    br.close()
print(json.dumps(itog, ensure_ascii=False))
