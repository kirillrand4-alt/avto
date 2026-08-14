# -*- coding: utf-8 -*-
r"""Отчёт по спорам судьи ролей: снимок места, где стоит адрес.

Что это. Судья ролей не арбитр, а сигнальщик: на 1486 адресах он согласился с
нами в 83,5%, а из 245 споров в 39 его собственная цитата подтверждает НАШУ роль.
Значит спор надо смотреть глазами — и смотреть быстро, а не открывая по ссылке
каждый сайт.

Почему не скриншот живого сайта. Из песочницы браузер наружу не ходит: агентский
прокси рвёт CONNECT от Chromium (ERR_CONNECTION_RESET на трёх адресах подряд,
при том что curl через тот же прокси отвечает 200). И даже если бы ходил — живой
сайт сегодня уже не тот, по которому судья выносил вердикт. Поэтому снимок
делается с НАШЕЙ копии страницы из pagecache: это ровно то, что видел разбор.

Что на выходе:
  * spory.html — страница с карточками: наша роль против роли судьи, его довод,
    ссылка и кусок ВЁРСТКИ вокруг адреса с подсветкой;
  * snimki/*.png — те же карточки картинками (Chromium рендерит локально, сеть
    не нужна), если запустить с --skrinshoty.

    python spory_otchet.py SPORY-SUDI-KUSKI.json [--skrinshoty N]
"""
import html as _html
import json
import os
import re
import sys

_UBRAT = re.compile(r'<(script|style|noscript|svg|iframe|link|meta|form|button)\b[^>]*>'
                    r'(?:.*?</\1>)?', re.S | re.I)
_ATRIB = re.compile(r'\s(?:on\w+|style|class|id|srcset|data-[\w-]+)\s*=\s*"[^"]*"', re.I)
_KARTINKI = re.compile(r'<img\b[^>]*>', re.I)


def _chisto(kusok, adres):
    """Разметку оставляем (в ней привязка), но обезвреживаем: без скриптов,
    стилей, форм и картинок — они всё равно не загрузятся и только мешают."""
    k = _UBRAT.sub(' ', kusok or '')
    k = _KARTINKI.sub('<span class="img">[фото]</span>', k)
    k = _ATRIB.sub('', k)
    return k


ГОЛОВА = """<title>Разбор споров о ролях</title>
<style>
/* Палитра под задачу: две стороны спора — наша разметка и судья — разведены по
   цвету (холодная зелень против глины), нейтральный фон уведён в холод, потому
   что страница про разбор данных, а не про уют. Жёлтая подсветка адреса — та
   единственная громкая точка, всё остальное держим тихим. */
:root{
  --fon:#f6f7f8; --karta:#ffffff; --tekst:#14171a; --tusklo:#5b636b;
  --ramka:#dfe3e6; --pole:#eef1f3;
  --nash:#0f6b5c; --nash-fon:rgba(15,107,92,.10);
  --sud:#a4590f;  --sud-fon:rgba(164,89,15,.10);
  --svet:#ffe08a; --ssylka:#1f5fa8;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --fon:#0f1215; --karta:#161a1e; --tekst:#e6e9ec; --tusklo:#9aa3ab;
    --ramka:#272d33; --pole:#1b2026;
    --nash:#4fc2a8; --nash-fon:rgba(79,194,168,.14);
    --sud:#e0a35c;  --sud-fon:rgba(224,163,92,.14);
    --svet:#7a6320; --ssylka:#7fb0ee;
  }
}
:root[data-theme="dark"]{
  --fon:#0f1215; --karta:#161a1e; --tekst:#e6e9ec; --tusklo:#9aa3ab;
  --ramka:#272d33; --pole:#1b2026;
  --nash:#4fc2a8; --nash-fon:rgba(79,194,168,.14);
  --sud:#e0a35c;  --sud-fon:rgba(224,163,92,.14);
  --svet:#7a6320; --ssylka:#7fb0ee;
}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 64px;background:var(--fon);color:var(--tekst);
  font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-variant-numeric:tabular-nums}
.obolochka{max-width:1180px;margin:0 auto}
h1{font-size:26px;letter-spacing:-.015em;margin:0 0 6px;text-wrap:balance}
.pod{color:var(--tusklo);margin:0;max-width:62ch}
.schet{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0 10px}
.schet button{font:inherit;cursor:pointer;background:var(--karta);color:var(--tekst);
  border:1px solid var(--ramka);border-radius:999px;padding:7px 14px;display:flex;gap:8px;align-items:center}
.schet button:hover{border-color:var(--tusklo)}
.schet button:focus-visible{outline:2px solid var(--ssylka);outline-offset:2px}
.schet button[aria-pressed="true"]{background:var(--pole);border-color:var(--tusklo)}
.schet b{font-size:15px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.09em;color:var(--tusklo);
  margin:34px 0 12px;position:sticky;top:0;background:var(--fon);padding:10px 0 6px;z-index:2}
.karta{background:var(--karta);border:1px solid var(--ramka);border-radius:12px;
  margin:0 0 14px;overflow:hidden;display:grid;grid-template-columns:340px 1fr}
@media (max-width:860px){.karta{grid-template-columns:1fr}}
.verdikt{padding:14px 16px;border-right:1px solid var(--ramka);display:flex;flex-direction:column;gap:10px}
@media (max-width:860px){.verdikt{border-right:0;border-bottom:1px solid var(--ramka)}}
.imya{font-weight:600;line-height:1.3}
.pochta{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;
  color:var(--tusklo);word-break:break-all}
.roli{display:flex;gap:8px;flex-wrap:wrap}
.rol{font-size:13px;padding:3px 9px;border-radius:6px;white-space:nowrap}
.rol.nash{background:var(--nash-fon);color:var(--nash)}
.rol.sud{background:var(--sud-fon);color:var(--sud)}
.dovod{font-size:13px;color:var(--tusklo);border-left:2px solid var(--ramka);padding-left:10px}
.dovod span{color:var(--tekst)}
.niz a{color:var(--ssylka);font-size:12px;word-break:break-all}
.mesto{padding:12px 16px;max-height:360px;overflow:auto;font-size:13px;line-height:1.45}
.mesto table{border-collapse:collapse;max-width:100%}
.mesto td,.mesto th{border:1px solid var(--ramka);padding:4px 8px;text-align:left;vertical-align:top}
.mesto mark{background:var(--svet);color:inherit;padding:1px 3px;border-radius:3px}
.mesto .img{color:var(--tusklo);font-size:12px}
.mesto a{color:var(--ssylka)}
.mesto h1,.mesto h2,.mesto h3{font-size:15px;margin:8px 0;position:static;background:none;
  text-transform:none;letter-spacing:normal;color:var(--tekst);padding:0}
.pusto{color:var(--tusklo);font-style:italic}
</style>
"""


def sobrat_html(spory, tolko=None):
    klassy = {}
    for s in spory:
        klassy.setdefault(s.get('klass', 'не решить'), []).append(s)
    ПОРЯДОК = ('судья против себя', 'мы против довода', 'не решить')
    ПОЯСНЕНИЕ = {
        'судья против себя': 'его же цитата подтверждает нашу роль',
        'мы против довода': 'цитата подтверждает роль судьи',
        'не решить': 'по цитате не видно, чья роль верна',
    }
    ch = [ГОЛОВА, '<div class="obolochka">',
          '<h1>Разбор споров о ролях</h1>',
          '<p class="pod">Судья размечал адрес по куску страницы и нашей роли не видел. '
          'Здесь только расхождения. Слева вердикт обеих сторон, справа — место, '
          'откуда адрес снят: наша копия страницы из кэша, та самая, по которой шёл '
          'разбор.</p>',
          '<div class="schet">',
          '<button type="button" data-klass="все" aria-pressed="true">'
          '<b>%d</b> всего</button>' % len(spory)]
    for k in ПОРЯДОК:
        if klassy.get(k):
            ch.append('<button type="button" data-klass="%s" aria-pressed="false">'
                      '<b>%d</b> %s</button>' % (_html.escape(k), len(klassy[k]),
                                                 _html.escape(k)))
    ch.append('</div>')
    for k in ПОРЯДОК:
        spisok = klassy.get(k) or []
        if tolko:
            spisok = spisok[:tolko]
        if not spisok:
            continue
        ch.append('<section data-klass="%s"><h2>%s — %d, %s</h2>' % (
            _html.escape(k), _html.escape(k), len(klassy[k]),
            _html.escape(ПОЯСНЕНИЕ.get(k, ''))))
        for s in spisok:
            ch.append(
                '<article class="karta">'
                '<div class="verdikt">'
                '<div class="imya">%s</div>'
                '<div class="pochta">%s</div>'
                '<div class="roli"><span class="rol nash">наша: %s</span>'
                '<span class="rol sud">судья: %s</span></div>'
                '<div class="dovod">довод судьи<br><span>%s</span></div>'
                '<div class="niz"><a href="%s">%s</a></div>'
                '</div>'
                '<div class="mesto" data-pochta="%s">%s</div>'
                '</article>' % (
                    _html.escape((s.get('name') or 'без названия')[:70]),
                    _html.escape(s.get('email') or ''),
                    _html.escape(s.get('nasha') or '—'),
                    _html.escape(s.get('sudya') or 'не видно'),
                    _html.escape((s.get('dovod') or '—')[:400]),
                    _html.escape(s.get('stranica') or s.get('url') or ''),
                    _html.escape((s.get('stranica') or s.get('url') or 'ссылки нет')[:80]),
                    _html.escape(s.get('email') or ''),
                    _chisto(s.get('kusok'), s.get('email')) or
                    '<span class="pusto">страницы в кэше нет</span>'))
        ch.append('</section>')
    ch.append('''</div>
<script>
// Подсветка адреса идёт ПО ТЕКСТОВЫМ УЗЛАМ: вставка <mark> в строку разметки
// ломала атрибуты (href="mailto:...") и рвала вёрстку куска.
document.querySelectorAll('.mesto').forEach(function (m) {
  var pochta = (m.dataset.pochta || '').toLowerCase();
  if (!pochta) { return; }
  var hod = document.createTreeWalker(m, NodeFilter.SHOW_TEXT), uzly = [], u;
  while ((u = hod.nextNode())) { uzly.push(u); }
  uzly.forEach(function (t) {
    var i = t.nodeValue.toLowerCase().indexOf(pochta);
    if (i < 0) { return; }
    var sredina = t.splitText(i);
    sredina.splitText(pochta.length);
    var mk = document.createElement('mark');
    sredina.parentNode.replaceChild(mk, sredina);
    mk.appendChild(sredina);
  });
});
// Фильтр по классу спора
var knopki = document.querySelectorAll('.schet button');
knopki.forEach(function (b) {
  b.addEventListener('click', function () {
    var k = b.dataset.klass;
    knopki.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
    document.querySelectorAll('section[data-klass]').forEach(function (s) {
      s.hidden = !(k === 'все' || s.dataset.klass === k);
    });
  });
});
</script>''')
    return '\n'.join(ch)


async def _snimki(put_html, kuda, skolko):
    """Карточки картинками. Сеть не нужна: страница локальная."""
    from playwright.async_api import async_playwright
    os.makedirs(kuda, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(
            executable_path=os.environ.get(
                'CHROME_BIN', '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'),
            args=['--no-sandbox'])
        pg = await (await b.new_context(viewport={'width': 1200, 'height': 900})).new_page()
        await pg.goto('file://' + os.path.abspath(put_html), wait_until='load')
        karty = await pg.query_selector_all('.karta')
        n = 0
        for i, k in enumerate(karty[:skolko]):
            try:
                await k.screenshot(path=os.path.join(kuda, 'spor-%03d.png' % i))
                n += 1
            except Exception:  # noqa: BLE001
                pass
        await b.close()
        return n


def main():
    vhod = sys.argv[1] if len(sys.argv) > 1 else 'SPORY-SUDI-KUSKI.json'
    spory = json.load(open(vhod, encoding='utf-8'))
    put = os.path.join(os.path.dirname(os.path.abspath(vhod)), 'spory.html')
    with open(put, 'w', encoding='utf-8') as f:
        f.write(sobrat_html(spory))
    itog = {'споров': len(spory), 'страница': put, 'байт': os.path.getsize(put)}
    if '--skrinshoty' in sys.argv:
        i = sys.argv.index('--skrinshoty')
        skolko = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 20
        import asyncio
        kuda = os.path.join(os.path.dirname(put), 'snimki')
        itog['снимков'] = asyncio.run(_snimki(put, kuda, skolko))
        itog['папка_снимков'] = kuda
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
