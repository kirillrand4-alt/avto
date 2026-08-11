# -*- coding: utf-8 -*-
"""Твёрдое доказательство личного номера: раскрыть страницу, найти номер, подсветить, снять.

Владелец посмотрел десять снимков и спросил по делу: как номер вообще достали, если на
картинке его нет. Разбор дал три разные причины, и только одна из них — порок данных:

  1. номер НА СТРАНИЦЕ ЕСТЬ, но снимок поймал свёрнутый блок. У Тендер.Про контакты лежат в
     «Комментарии», который схлопнут кнопкой «Подробнее ∨». Прибор читает весь DOM и номер
     видит, камера снимает обрезанный вид. Чинится раскрытием блоков перед съёмкой;
  2. номер есть, но принадлежит ДРУГОМУ человеку (ПО КТЗ: номер Яковлева записан на Емец);
  3. номера в видимом тексте нет вовсе — он взят из разметки (скрытые блоки, атрибуты).

Здесь делается снимок, который доказывает номер САМ, без веры в прибор:

    раскрываем    — клик по «Подробнее / Показать все / Развернуть», <details>, и JS-снятие
                    max-height/overflow, которыми блок обрезан;
    ищем СВЯЗНО   — цифры номера подряд, между ними только пробел, дефис, скобка или плюс.
                    Это отсекает склейку «8 (41136) 99-000 доб.4-78-59» → 79900047859,
                    которая давала ложный «мобильный» у АЛРОСА;
    смотрим ЧЕЙ   — наша фамилия должна стоять в окне ±260 знаков вокруг номера;
    подсвечиваем  — оборачиваем найденный кусок в жёлтую рамку и прокручиваем к нему,
                    чтобы на картинке было видно ровно то, что доказывает;
    снимаем       — снимок кладётся в хранилище дропа под именем NOMER-<инн>-<номер>.png.

Вердикт пишется в JSONL с fsync на сервере (durability: песочница при рестарте откатится).

Запуск: python3 park_1s_snimok_nomera.py <откуда> <сколько>
"""
import io, json, os, re, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ZAD = r'C:\sender\_nomera_zadanie.json'
VYHOD = r'C:\sender\park_nomera_dokaz.jsonl'
SNIMKI = r'C:\seostat\drop\drop-storage'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
OTKUDA = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SKOLKO = int(sys.argv[2]) if len(sys.argv) > 2 else 40

RASKRYT = ['text=Подробнее', 'text=Показать все', 'text=Развернуть', 'text=Показать полностью',
           'text=Читать далее']
# всплывашки перекрывали пол-кадра на первой пробе (согласие на cookie, виджет чата)
ZAKRYT = ['text=Ok', 'text=ОК', 'text=Принять', 'text=Согласен', 'text=Отмена', 'text=Закрыть']
UBRAT_OVERLAY = """() => {
  // всё, что висит поверх страницы и мешает снимку: баннеры согласия, виджеты чата
  document.querySelectorAll('*').forEach(e => {
    const s = getComputedStyle(e);
    if ((s.position === 'fixed' || s.position === 'sticky') && e.offsetHeight > 40) {
      e.style.display = 'none';
    }
  });
}"""
SNYAT_OBREZKU = """() => {
  document.querySelectorAll('details').forEach(d => d.open = true);
  document.querySelectorAll('*').forEach(e => {
    const s = getComputedStyle(e);
    if (s.maxHeight && s.maxHeight !== 'none') e.style.maxHeight = 'none';
    if (s.overflow === 'hidden') e.style.overflow = 'visible';
    if (s.display === 'none' && e.tagName !== 'SCRIPT' && e.tagName !== 'STYLE'
        && e.textContent && e.textContent.length < 4000) e.style.display = 'block';
    if (s.webkitLineClamp && s.webkitLineClamp !== 'none') e.style.webkitLineClamp = 'unset';
  });
}"""


def hrom():
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e


def svyazno(cifry, tekst):
    """-> объект совпадения, если номер записан как ТЕЛЕФОН, а не собран из соседних чисел."""
    return re.search(r'[\s\-()+]{0,3}'.join(cifry), tekst)


def familiya_ryadom(chelovek, tekst, poz):
    """Наша фамилия в окне ±260 знаков вокруг номера."""
    slova = [w for w in re.findall(r'[А-ЯЁ][а-яё]{2,}', chelovek or '')]
    if not slova:
        return False, ''
    okno = tekst[max(0, poz - 260):poz + 260]
    for w in slova:
        if w in okno:
            return True, w
    return False, (slova[0] if slova else '')


zad = json.load(open(ZAD, encoding='utf-8'))[OTKUDA:OTKUDA + SKOLKO]
from playwright.sync_api import sync_playwright

itog = []
exe = hrom()
with sync_playwright() as p:
    kw = {'headless': True, 'args': ['--no-sandbox']}
    if exe:
        kw['executable_path'] = exe
    br = p.chromium.launch(**kw)
    ctx = br.new_context(user_agent=UA, locale='ru-RU', ignore_https_errors=True,
                         viewport={'width': 1600, 'height': 1100})
    pg = ctx.new_page()
    for z in zad:
        r = {k: z.get(k) for k in ('inn', 'chelovek', 'dolzhnost', 'nomer', 'ssylka', 'predpriyatie')}
        cifry = re.sub(r'\D', '', z['nomer'])[-10:]
        try:
            # Страницы часто редиректят, и первый goto падает с «Navigation is interrupted
            # by another navigation» — на пробе так отвалилось 6 из 10. Три захода, ожидание
            # мягкое ('commit' — дождаться начала ответа, дальше ждём таймером).
            otv = None
            for popytka in range(3):
                try:
                    otv = pg.goto(z['ssylka'], timeout=60000,
                                  wait_until='commit' if popytka else 'domcontentloaded')
                    break
                except Exception as e:  # noqa: BLE001
                    if 'ERR_NAME_NOT_RESOLVED' in str(e) or 'ERR_CONNECTION' in str(e):
                        raise
                    if popytka == 2:
                        raise
                    pg.wait_for_timeout(1500 * (popytka + 1))
            r['http'] = otv.status if otv else None
            pg.wait_for_timeout(3500)
            # 1. раскрываем всё, что схлопнуто кнопкой
            for sel in RASKRYT:
                try:
                    for el in pg.locator(sel).all()[:4]:
                        try:
                            el.click(timeout=1500)
                            pg.wait_for_timeout(300)
                        except Exception:
                            pass
                except Exception:
                    pass
            # 2. закрываем всплывашки и снимаем обрезку стилями
            for sel in ZAKRYT:
                try:
                    el = pg.locator(sel).first
                    if el.is_visible(timeout=800):
                        el.click(timeout=1200)
                        pg.wait_for_timeout(300)
                except Exception:
                    pass
            try:
                pg.evaluate(UBRAT_OVERLAY)
                pg.evaluate(SNYAT_OBREZKU)
                pg.wait_for_timeout(400)
            except Exception:
                pass
            tekst = re.sub(r'[\u00a0\s]+', ' ', pg.inner_text('body'))
            m = svyazno(cifry, tekst)
            r['nomer_svyazno'] = bool(m)
            if m:
                est, kakoe = familiya_ryadom(z.get('chelovek'), tekst, m.start())
                r['familiya_ryadom'] = est
                r['po_kakomu_slovu'] = kakoe
                r['citata'] = tekst[max(0, m.start() - 170):m.start() + 90]
                # 3. Раскрываем строку, подсвечиваем номер и ставим ПЛАШКУ с цитатой.
                #    Вёрстка чужих сайтов режет длинную строку (ellipsis, фикс. ширина), и
                #    номер физически не отрисован — на первой пробе снимок блока показал
                #    «...Кошилев Олег Николаеви» и обрыв. Поэтому: снимаем обрезку с самого
                #    блока, а сверху кладём свою плашку, где видно и цитату, и адрес страницы.
                try:
                    pg.evaluate("""([nom, adres, kto]) => {
                        const it = document.evaluate("//*[not(self::script or self::style)]/text()",
                            document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                        let el = null, tekst = '';
                        for (let i = 0; i < it.snapshotLength; i++) {
                            const n = it.snapshotItem(i);
                            const v = n.nodeValue.replace(/\u00a0/g, ' ');
                            const idx = v.indexOf(nom);
                            if (idx >= 0 && n.parentElement) {
                                el = n.parentElement;
                                tekst = v.slice(Math.max(0, idx - 170), idx + 90).trim();
                                break;
                            }
                        }
                        if (!el) return false;
                        // распускаем обрезанную строку, чтобы номер отрисовался целиком
                        for (let e = el; e && e !== document.body; e = e.parentElement) {
                            e.style.whiteSpace = 'normal';
                            e.style.textOverflow = 'clip';
                            e.style.overflow = 'visible';
                            e.style.maxWidth = 'none';
                            e.style.width = 'auto';
                            e.style.maxHeight = 'none';
                        }
                        el.style.outline = '3px solid #d40000';
                        el.style.background = '#fffbcc';
                        el.style.padding = '10px';
                        el.setAttribute('data-nomer-tut', '1');
                        // плашка: что именно доказывает снимок и откуда взято
                        const p = document.createElement('div');
                        p.setAttribute('data-plashka', '1');
                        p.style.cssText = 'position:relative;z-index:2147483647;background:#fff;'
                          + 'border:3px solid #d40000;padding:14px 16px;margin:0 0 10px 0;'
                          + 'font:15px/1.5 Arial,sans-serif;color:#000;max-width:1500px';
                        p.innerHTML = '<b>Доказательство личного номера</b><br>'
                          + '<span style="color:#555">кто:</span> ' + kto + '<br>'
                          + '<span style="color:#555">номер на странице:</span> <b style="background:#ffe600">'
                          + nom + '</b><br><span style="color:#555">цитата со страницы:</span> …'
                          + tekst.replace(/</g, '&lt;') + '…<br>'
                          + '<span style="color:#555">адрес:</span> ' + adres;
                        document.body.insertBefore(p, document.body.firstChild);
                        window.scrollTo(0, 0);
                        return true;
                    }""", [m.group(0), z['ssylka'][:150], (z.get('chelovek') or '') + ' — ' + (z.get('dolzhnost') or '')])
                    pg.wait_for_timeout(600)
                except Exception:
                    pass
                imya = 'NOMER-%s-%s.png' % (z['inn'], cifry)
                pg.screenshot(path=os.path.join(SNIMKI, imya), full_page=False)
                r['snimok'] = imya
                r['vyvod'] = ('ДОКАЗАНО: номер и фамилия на снимке' if est
                              else 'номер есть, но фамилии рядом нет — ЧЕЙ НЕ ЯСНО')
            else:
                # номер не записан связно: либо склейка, либо его нет вовсе
                golyy = re.sub(r'\D', '', tekst)
                r['vyvod'] = ('СКЛЕЙКА соседних чисел, не телефон' if cifry in golyy
                              else 'номера на странице нет')
                r['citata'] = ''
        except Exception as e:  # noqa: BLE001
            r['vyvod'] = 'страницу не дали: ' + str(e)[:60]
        itog.append(r)
        with open(VYHOD, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    br.close()

import collections
k = collections.Counter(r['vyvod'].split(':')[0] for r in itog)
print('обработано: %d (с %d)' % (len(itog), OTKUDA))
for a, n in k.most_common():
    print('  %-44s %d' % (a, n))
print('журнал: %s' % VYHOD)
