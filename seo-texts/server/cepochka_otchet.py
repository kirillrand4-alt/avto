# -*- coding: utf-8 -*-
r"""Отчёт «от источника до результата»: как из адреса получается заход в письме.

Владелец 16.08: «сделай ещё выборку 50 глазами от источника до результата». Смысл
не в том, чтобы показать паспорта — их видно и так, — а в том, чтобы по каждой
компании была видна ВСЯ цепочка и место, где она может порваться:

    откуда взялся адрес  →  чем привязка доказана  →  какие страницы скачаны
    →  что вытащил разбор  →  что из этого подтверждается текстом дословно
    →  что реально пойдёт в письмо

Каждый факт помечен: подтверждён ли он дословным поиском по скачанному тексту.
Непроверяемое (новости, цитаты) помечено отдельно — их проверяет свой гейт.

Отчёт — самостоятельный HTML без внешних файлов: его открывают на телефоне.

    python cepochka_otchet.py [сколько] > otchet.html
"""
import gzip
import html
import json
import os
import random
import re
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import pasport_sverka as PS       # noqa: E402
import sverka_privyazki as SP     # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ПОЛЯ = ('продукция', 'оборудование_линии', 'мощности', 'сырьё', 'контроль_качества',
        'клиенты', 'география_поставок', 'экспорт', 'масштаб', 'энергохозяйство',
        'газы', 'расширение', 'год_основания')
# что из паспорта реально идёт в заход письма — по разбору КЦ и рентгена
ДЛЯ_ПИСЬМА = ('продукция', 'энергохозяйство', 'газы', 'расширение', 'мощности')


def страницы(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return []
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return []
    из = []
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        из.append({'url': pg.get('url') or '', 'знаков': len(h)})
    return из


def выборка(сколько=50):
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    строки = list(c.execute(
        "select f.inn, f.facts_json, f.ts, coalesce(f.site,'') site, "
        "coalesce(f.privyazka,'') privyazka, coalesce(k.name,'') name, "
        "coalesce(k.okved,'') okved, coalesce(k.region,'') region, "
        "coalesce(k.verified,'') verified, coalesce(k.site_source,'') site_source, "
        "coalesce(k.ogrn,'') ogrn, coalesce(k.best_email,'') best_email "
        "from site_facts f join companies k on k.inn=f.inn "
        "where coalesce(f.facts_json,'')<>'' and coalesce(f.format,0)>=2 "
        "order by f.ts desc limit 600"))
    c.close()
    random.seed(50)
    return random.sample(строки, min(сколько, len(строки)))


def _э(s):
    return html.escape(str(s or ''))


def карточка(r, n):
    d = json.loads(r['facts_json'])
    t = PS._tekst(str(r['inn']))
    улики, _ = SP.улики(str(r['inn']), r['name'], r['site'], r['ogrn'])
    стр = страницы(str(r['inn']))
    ч = ['<article><h2>%d. %s</h2>' % (n, _э(r['name'][:80]))]

    # 1. источник
    ч.append('<table class="src"><tbody>')
    ч.append('<tr><th>ИНН</th><td>%s</td></tr>' % _э(r['inn']))
    ч.append('<tr><th>ОКВЭД</th><td>%s</td></tr>' % _э(r['okved'][:90] or '—'))
    ч.append('<tr><th>регион</th><td>%s</td></tr>' % _э(r['region'] or '—'))
    ч.append('<tr><th>сайт</th><td><b>%s</b></td></tr>' % _э(r['site'] or '—'))
    ч.append('<tr><th>откуда адрес</th><td>%s</td></tr>'
             % _э(r['site_source'] or 'из базы/выгрузки (источник не помечен)'))
    ч.append('<tr><th>чем привязка доказана</th><td>%s</td></tr>'
             % (('улики на страницах: <b>%s</b>' % _э('+'.join(улики))) if улики
                else '<span class="bad">улик на страницах нет</span>'))
    ч.append('<tr><th>вердикт обогащения</th><td>%s</td></tr>' % _э(r['verified'] or '—'))
    ч.append('<tr><th>почта для письма</th><td>%s</td></tr>'
             % (_э(r['best_email']) if r['best_email'] else '<span class="bad">нет</span>'))
    ч.append('</tbody></table>')

    # 2. страницы
    ч.append('<h3>Скачано страниц: %d</h3><ul class="pages">' % len(стр))
    for s in стр[:6]:
        ч.append('<li><span class="u">%s</span> <span class="dim">%d знаков</span></li>'
                 % (_э(s['url'][:110]), s['знаков']))
    if len(стр) > 6:
        ч.append('<li class="dim">… и ещё %d</li>' % (len(стр) - 6))
    ч.append('</ul>')

    # 3. что вытащил разбор, с пометкой подтверждения
    ч.append('<h3>Что вытащил разбор</h3><table class="f"><tbody>')
    пусто = True
    for k in ПОЛЯ:
        v = d.get(k)
        сп = v if isinstance(v, list) else ([v] if v else [])
        сп = [str(x) for x in сп if x]
        if not сп:
            continue
        пусто = False
        куски = []
        for ф in сп[:8]:
            ок = PS._podtverzhdena(ф.lower().replace('ё', 'е'), t) if t else None
            куски.append('<span class="%s">%s</span>'
                         % ('ok' if ок else 'bad', _э(ф[:80])))
        ч.append('<tr><th>%s</th><td>%s</td></tr>' % (_э(k), ' · '.join(куски)))
    if пусто:
        ч.append('<tr><td colspan="2" class="dim">разбор не нашёл ни одного факта</td></tr>')
    ч.append('</tbody></table>')

    нов = d.get('новости') or []
    if нов:
        p = нов[0]
        ч.append('<p class="news"><b>свежая новость:</b> %s — %s %s</p>'
                 % (_э(p.get('дата', '')), _э((p.get('заголовок') or '')[:110]),
                    ('<a href="%s">ссылка</a>' % _э(p.get('url'))) if p.get('url') else ''))

    # 4. что пойдёт в письмо
    в_письмо = []
    for k in ДЛЯ_ПИСЬМА:
        v = d.get(k)
        сп = v if isinstance(v, list) else ([v] if v else [])
        for ф in [str(x) for x in сп if x][:3]:
            если_ок = PS._podtverzhdena(ф.lower().replace('ё', 'е'), t) if t else False
            if если_ок:
                в_письмо.append(ф[:70])
    ч.append('<h3>Материал для захода</h3>')
    if в_письмо:
        ч.append('<p class="use">%s</p>' % ' · '.join(_э(x) for x in в_письмо[:8]))
    else:
        ч.append('<p class="bad">подтверждённого материала нет — письму не на что опереться</p>')
    ч.append('</article>')
    return '\n'.join(ч)


def отчёт(сколько=50):
    строки = выборка(сколько)
    куски = [СТИЛЬ, '<h1>От источника до результата: %d компаний</h1>' % len(строки),
             '<p class="dim">Зелёное — факт найден в тексте скачанных страниц дословно '
             '(с учётом падежей). Красное — в тексте не найдено.</p>']
    for i, r in enumerate(строки, 1):
        куски.append(карточка(r, i))
    return '\n'.join(куски)


СТИЛЬ = """<title>От источника до результата</title>
<style>
:root{--fg:#1a1a1a;--dim:#6b6b6b;--line:#e2e2e2;--ok:#0a6b3d;--bad:#a11;--bg:#fff;--card:#fafafa}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--fg:#e8e8e8;--dim:#9a9a9a;
--line:#333;--ok:#5fd39b;--bad:#ff8080;--bg:#141414;--card:#1c1c1c}}
:root[data-theme="dark"]{--fg:#e8e8e8;--dim:#9a9a9a;--line:#333;--ok:#5fd39b;--bad:#ff8080;
--bg:#141414;--card:#1c1c1c}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
max-width:900px;margin:0 auto;padding:16px}
h1{font-size:22px} h2{font-size:17px;margin:0 0 8px} h3{font-size:14px;margin:14px 0 6px;color:var(--dim)}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:14px}
th{text-align:left;color:var(--dim);font-weight:400;padding:3px 10px 3px 0;vertical-align:top;width:190px}
td{padding:3px 0;vertical-align:top}
.ok{color:var(--ok)} .bad{color:var(--bad)} .dim{color:var(--dim)}
.u{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;word-break:break-all}
ul.pages{margin:4px 0;padding-left:18px} li{margin:2px 0}
.use{background:rgba(10,107,61,.08);border-left:3px solid var(--ok);padding:8px 10px;border-radius:4px}
.news{color:var(--dim)}
</style>"""


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 50
    sys.stdout.reconfigure(encoding='utf-8')
    print(отчёт(n))
