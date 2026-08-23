#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка готовых статей в пакет по сайтам.

    python3 sobrat_paket.py [--out paket]

ЧТО ДЕЛАЕТ. Статьи лежат фрагментами разметки - <h1>, <h2>, <p>, таблицы.
Для передачи владельцу этого мало: нужен файл, который открывается
в браузере и выглядит как страница. Скрипт заворачивает каждый фрагмент
в полноценный документ, раскладывает по папкам доменов и делает
на каждый сайт оглавление.

ЧЕСТНО ПРО ВЁРСТКУ. Это НЕ шаблон боевого сайта - его CSS у меня нет.
Это предпросмотр: нейтральная типографика, читаемые таблицы, шапка
с брендом и каноническим адресом. Вставлять на сайт надо содержимое
<article>, а не файл целиком.

ПРАВИЛА ПРОЕКТА, УЧТЁННЫЕ В CSS:
- никаких <ul> в текстах (их и нет) - перечисления идут абзацами;
- таблицы прокручиваются по горизонтали на узком экране, а не ломают
  страницу;
- тёмная тема поддержана, потому что владелец смотрит файлы ночью.
"""
import argparse
import html as H
import json
import os
import re
import shutil

DIR = os.path.dirname(os.path.abspath(__file__))

STIL = """
:root{
  --fon:#fbfaf8; --tekst:#23201d; --tusklyy:#6a635b; --liniya:#e3ded6;
  --akcent:#8c5a2b; --plashka:#f3efe8;
}
:root:not([data-theme="light"]){@media (prefers-color-scheme:dark){
  --fon:#171614; --tekst:#e8e4de; --tusklyy:#9a938a; --liniya:#332f2a;
  --akcent:#d0975c; --plashka:#201e1b;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--fon);color:var(--tekst);
  font:17px/1.65 Georgia,"Times New Roman",serif;}
.shapka{background:var(--plashka);border-bottom:1px solid var(--liniya);
  padding:14px 20px;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:14px;display:flex;gap:14px;flex-wrap:wrap;align-items:baseline}
.shapka b{font-size:15px}
.shapka a{color:var(--akcent);text-decoration:none}
.obertka{max-width:760px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:31px;line-height:1.25;margin:.6em 0 .5em;text-wrap:balance}
h2{font-size:22px;line-height:1.3;margin:1.9em 0 .5em;text-wrap:balance;
  padding-top:.5em;border-top:1px solid var(--liniya)}
h3{font-size:18px;margin:1.4em 0 .4em}
p{margin:0 0 1em}
a{color:var(--akcent)}
table{border-collapse:collapse;width:100%;margin:1.2em 0;font-size:15px;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  font-variant-numeric:tabular-nums}
.tablica{overflow-x:auto;margin:1.2em 0}
.tablica table{margin:0}
th,td{border:1px solid var(--liniya);padding:7px 10px;text-align:left;
  vertical-align:top}
th{background:var(--plashka);font-weight:600}
.cta{background:var(--plashka);border-left:3px solid var(--akcent);
  padding:12px 16px;margin:1.4em 0}
em{color:var(--tusklyy)}
.snoska{margin-top:48px;padding-top:14px;border-top:1px solid var(--liniya);
  color:var(--tusklyy);font-size:13px;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.spisok{max-width:900px;margin:0 auto;padding:28px 20px 80px}
.spisok a{display:block;padding:11px 0;border-bottom:1px solid var(--liniya);
  text-decoration:none;color:var(--tekst)}
.spisok a:hover{color:var(--akcent)}
.spisok .adres{display:block;color:var(--tusklyy);font-size:13px;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
"""


def _mety(slug):
    put = os.path.join(DIR, 'statyi', f'{slug}.meta.json')
    if os.path.exists(put):
        try:
            return json.load(open(put, encoding='utf-8'))
        except Exception:
            pass
    return {}


def _obernut_tablicy(kus):
    """Таблица в прокручиваемой обёртке: на телефоне не ломает страницу."""
    return re.sub(r'(<table.*?</table>)', r'<div class="tablica">\1</div>',
                  kus, flags=re.S | re.I)


def stranica(slug, telo, job, meta):
    m = _mety(slug)
    zag = m.get('title') or re.sub(r'<[^>]+>', '', (re.findall(
        r'<h1[^>]*>(.*?)</h1>', telo, re.S) or [slug])[0])
    opis = m.get('description') or ''
    url = (job or {}).get('url') or ''
    brend = (job or {}).get('brand') or ''
    sayt = (job or {}).get('site') or ''
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(zag)}</title>
<meta name="description" content="{H.escape(opis)}">
{f'<link rel="canonical" href="{H.escape(url)}">' if url else ''}
<style>{STIL}</style>
</head>
<body>
<div class="shapka">
  <b>{H.escape(brend)}</b>
  <span>{H.escape(sayt)}</span>
  {f'<a href="{H.escape(url)}">{H.escape(url)}</a>' if url else ''}
</div>
<div class="obertka">
<article>
{_obernut_tablicy(telo)}
</article>
<div class="snoska">
  Предпросмотр для вычитки. На сайт вставляется содержимое &lt;article&gt;,
  а не файл целиком: заголовок, описание и канонический адрес уже
  проставлены выше и на боевой странице придут из шаблона.
</div>
</div>
</body>
</html>
"""


def oglavlenie(sayt, brend, strany):
    stroki = '\n'.join(
        f'<a href="{H.escape(imya)}">{H.escape(zag)}'
        f'<span class="adres">{H.escape(url or imya)}</span></a>'
        for imya, zag, url in sorted(strany, key=lambda x: x[1]))
    return f"""<!doctype html>
<html lang="ru">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(brend)} - страницы</title>
<style>{STIL}</style></head>
<body>
<div class="shapka"><b>{H.escape(brend)}</b><span>{H.escape(sayt)}</span>
<span>{len(strany)} страниц</span></div>
<div class="spisok">
{stroki}
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(DIR, 'paket'))
    a = ap.parse_args()

    jobs = {j['slug']: j for j in
            json.load(open(os.path.join(DIR, 'tz-jobs.json'), encoding='utf-8'))
            + json.load(open(os.path.join(DIR, 'station-jobs.json'), encoding='utf-8'))}
    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    po_saytam = {}
    vsego = 0
    import glob
    # ОДИН ФАЙЛ НА СТРАНИЦУ. У ekomak--kompressornaya-stanciya лежали
    # и .final, и .RUCHNOY - от перегона доводки, сменившего вердикт.
    # В пакет идёт .final: это версия, к которой у линз претензий нет.
    luchshie = {}
    for f in sorted(glob.glob(os.path.join(DIR, 'statyi-final', '*.html'))):
        slug = os.path.basename(f).split('.')[0]
        vid = os.path.basename(f).split('.')[1]
        if slug not in luchshie or vid == 'final':
            luchshie[slug] = f
    for slug, f in sorted(luchshie.items()):
        job = jobs.get(slug) or {}
        sayt = job.get('site') or slug.split('--')[0]
        papka = os.path.join(a.out, sayt)
        os.makedirs(papka, exist_ok=True)
        telo = open(f, encoding='utf-8').read()
        tema = slug.split('--', 1)[1] if '--' in slug else slug
        imya = f'{tema}.html'
        with open(os.path.join(papka, imya), 'w', encoding='utf-8') as g:
            g.write(stranica(slug, telo, job, None))
        zag = re.sub(r'<[^>]+>', '', (re.findall(r'<h1[^>]*>(.*?)</h1>',
                                                 telo, re.S) or [tema])[0])
        # КЛЮЧ - ТОЛЬКО САЙТ. Ключ (сайт, бренд) развалил dali-kompressor.ru
        # надвое: в заданиях бренд записан и «DALI», и «Dali», получилось
        # два ключа, оглавление перезаписалось вторым, и пять страниц
        # из десяти стали недоступны из списка. Регистр бренда - не повод
        # заводить второй сайт.
        po_saytam.setdefault(sayt, {'brend': {}, 'strany': []})
        po_saytam[sayt]['strany'].append((imya, zag, job.get('url') or ''))
        b = job.get('brand') or sayt
        po_saytam[sayt]['brend'][b] = po_saytam[sayt]['brend'].get(b, 0) + 1
        vsego += 1
    for sayt, d in po_saytam.items():
        brend = max(d['brend'], key=d['brend'].get)
        with open(os.path.join(a.out, sayt, 'index.html'), 'w', encoding='utf-8') as g:
            g.write(oglavlenie(sayt, brend, d['strany']))
    # общий указатель
    obshchiy = '\n'.join(
        f'<a href="{s}/index.html">'
        f'{H.escape(max(d["brend"], key=d["brend"].get))}'
        f'<span class="adres">{s} - {len(d["strany"])} страниц</span></a>'
        for s, d in sorted(po_saytam.items()))
    with open(os.path.join(a.out, 'index.html'), 'w', encoding='utf-8') as g:
        g.write(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Статьи брендовых сайтов</title><style>{STIL}</style></head>
<body><div class="shapka"><b>Брендовые сайты</b>
<span>{vsego} страниц на {len(po_saytam)} доменах</span></div>
<div class="spisok">{obshchiy}</div></body></html>
""")
    print(f'собрано {vsego} страниц на {len(po_saytam)} сайтах -> {a.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
