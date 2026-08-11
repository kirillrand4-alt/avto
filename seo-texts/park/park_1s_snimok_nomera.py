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
    снимаем       — снимок кладётся в хранилище дропа под именем NOMER-<инн>-<номер>.png;
    СМОТРИМ КАДР  — и только потом пишем «доказано».

Последнее условие добавлено после того, как владелец открыл `NOMER-7718560636-9022000976.png`
и написал: «пустой скриншот». Белый лист 1600x1100, ноль не-белых точек — а в базе против
него стояло «доказано». Таких кадров нашлось 12 из 99, и семь из них считались доказанными.

Прибор спрашивал «файл записался?» и «есть ли номер в тексте страницы» — оба ответа «да».
Он не спрашивал «на картинке что-нибудь нарисовано?». Текст в DOM был, а кадр вышел пустым:
все 12 пустых весят байт в байт одинаково (7 676), то есть содержимое кадра одно и то же —
пустота; страница успевала увести себя редиректом уже после наших правок стилей.

Теперь после съёмки кадр взвешивается: белый лист при этом окне жмётся в 7,7 КБ, а самый
бедный кадр с содержимым весит 18 КБ — промежутка нет, порог 12 КБ стоит посередине разрыва.
Пустой кадр — не повод соврать: страница перезагружается и снимается заново (до трёх раз,
без снятия overlay, которое и могло стереть кадр). Не вышло и с третьего — пишем «снимок
пустой», доказанность НЕ ставится. Отдельным прибором `park_1s_snimok_chernila.py` весь
каталог потом пересчитывается по ТОЧКАМ, а не по весу — вес тут только чтобы не гонять
разбор PNG внутри цикла съёмки.

Вердикт пишется в JSONL с fsync на сервере (durability: песочница при рестарте откатится).

Запуск: python3 park_1s_snimok_nomera.py <откуда> <сколько>
"""
import io, json, os, re, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
# Пути берутся из окружения: тот же прибор работает и на сервере, и в песочнице.
# Это понадобилось, когда выяснилось, что Тендер.Про С СЕРВЕРА отдаёт пустую страницу, а из
# песочницы — полную: 11 из 12 пустых кадров были именно оттуда. Разделение по месту запуска
# уже встречалось с monitor-pb (наоборот: он читается из песочницы и не читается с сервера).
ZAD = os.environ.get('NOMERA_ZAD', r'C:\sender\_nomera_zadanie.json')
VYHOD = os.environ.get('NOMERA_VYHOD', r'C:\sender\park_nomera_dokaz.jsonl')
SNIMKI = os.environ.get('NOMERA_SNIMKI', r'C:\seostat\drop\drop-storage')
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
# Белый лист при окне 1600x1100 весит 7 676 байт, самый бедный кадр с содержимым — 18 074.
# Порог стоит посередине разрыва; точную долю чернил считает park_1s_snimok_chernila.py.
PUSTOY_KADR = 12000

PLASHKA_JS = """([nom, adres, kto]) => {
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
    }"""


def podsvetit(pg, nom, z):
    """Подсветить номер и положить плашку. Молча возвращает False, если не вышло."""
    try:
        return bool(pg.evaluate(PLASHKA_JS, [nom, z['ssylka'][:150],
                                             (z.get('chelovek') or '') + ' \u2014 '
                                             + (z.get('dolzhnost') or '')]))
    except Exception:  # noqa: BLE001
        return False


def snyat_kadr(pg, put, nom, z):
    """Снять кадр и УБЕДИТЬСЯ, что он не пустой: до трёх заходов со свежей страницы.

    Overlay при повторе не снимаем: пряча всё `position:fixed`, можно стереть саму разметку
    страницы — на части площадок содержимое лежит именно в закреплённом контейнере, и тогда
    кадр выходит белым при живом тексте в DOM.
    """
    pg.screenshot(path=put, full_page=False)
    for popytka in range(3):
        if os.path.getsize(put) >= PUSTOY_KADR:
            return os.path.getsize(put), popytka
        try:
            pg.goto(z['ssylka'], timeout=60000, wait_until='domcontentloaded')
            pg.wait_for_timeout(4000 + 2500 * popytka)
            pg.evaluate(SNYAT_OBREZKU)
            pg.wait_for_timeout(500)
            podsvetit(pg, nom, z)
            pg.wait_for_timeout(700)
            pg.screenshot(path=put, full_page=False)
        except Exception:  # noqa: BLE001
            pass
    return os.path.getsize(put), 3


def hrom():
    """Путь к браузеру. В песочнице свой каталог, и версия playwright там разошлась с
    установленным Chromium (ждёт chromium_headless_shell-1234, лежит 1194) — поэтому путь
    задаём явно, а не полагаемся на «playwright install», которого в этой среде делать нельзя.
    """
    k = r'C:\sender\pw-browsers'
    if os.path.isdir(k):
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    for e in ('/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
              '/opt/pw-browsers/chromium/chrome-linux/chrome'):
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
    # В песочнице наружу пускает только прокси (HTTPS_PROXY), иначе Chromium получает
    # ERR_CONNECTION_RESET, хотя curl с теми же адресами работает. На сервере переменной нет
    # и ничего не меняется.
    _proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if _proxy:
        kw['proxy'] = {'server': _proxy}
        kw['args'] = kw['args'] + ['--ignore-certificate-errors']
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
                podsvetit(pg, m.group(0), z)
                pg.wait_for_timeout(600)
                imya = 'NOMER-%s-%s.png' % (z['inn'], cifry)
                bayt, peresnyato = snyat_kadr(pg, os.path.join(SNIMKI, imya), m.group(0), z)
                r['snimok'] = imya
                r['bayt_snimka'] = bayt
                r['peresnyato_raz'] = peresnyato
                if bayt < PUSTOY_KADR:
                    # кадр пуст: номер в тексте есть, но ПОКАЗАТЬ его нечем — не доказано
                    r['snimok_pustoy'] = 1
                    r['vyvod'] = 'снимок пустой (%d б): показать номер нечем' % bayt
                else:
                    r['snimok_pustoy'] = 0
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
