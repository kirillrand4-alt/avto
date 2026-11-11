# -*- coding: utf-8 -*-
r"""Добавки сборщика контактов (11.11; сверка с панелью по 944 общим компаниям — у панели 607 адресов, которых нет у нас;
владелец: «1,2,3,5,6 применяю, но в вакансии не лезь»). Подключаются в kc_kontakty только в глубоком режиме (набор «ca»
или KC_GLUB=1) — остальные наборы идут как раньше.

  * раскрыть_cf(html) — почты под защитой Cloudflare («[email protected]»: data-cfemail, /cdn-cgi/l/email-protection#…)
    -> обычный адрес в тексте и mailto (дальше их берут kc_pochty.почты и проверка видимости как любые другие);
  * карта_сайта(старт, скачать) — страницы контактов, руководства, филиалов, отделов из sitemap.xml (и Sitemap: из
    robots.txt), до 12 адресов, сначала контакты;
  * Браузер — повторное открытие сайта, который не открылся простым запросом: Chromium (Playwright), варианты адреса
    https/http и с www/без, таймаут 45 с; одновременно не больше KC_BRAUZEROV (2) браузеров на процесс;
  * ВАКАНСИИ — страницы вакансий, карьеры и резюме не открываем и не берём (владелец: «в вакансии не лезь»).
"""
import os
import re
import threading
import urllib.parse

# «карьер» — ещё и горная выработка (карьерная техника, карьероуправление): берём только «карьера/карьеры» и латиницу
ВАКАНСИИ = re.compile(r'vakans|vakanc|vacanc|ваканс|career|kariera|karera|karyera|карьера|карьеры|(?<![a-z])jobs?(?![a-z])|'
                      r'rabota-u-nas|работа-у-нас|rabota_v_kompanii|работа-в-компании|rezyume|rezume|resume|резюме|'
                      r'trudoustr|трудоустр|hh\.ru|superjob|zarplata\.ru|rabota\.ru|trudvsem|headhunter', re.I)
# страницы из карты сайта: контакты/реквизиты, руководство и сотрудники, филиалы и представительства, отделы, снабжение
КАРТА_ТЕМА = re.compile(r'kontakt|contact|контакт|rekvizit|реквизит|rukovod|руковод|management|leadership|direkc|дирекц|'
                        r'administr|администрац|team|komand|команд|sotrudnik|сотрудник|struktur|структур|otdel|отдел|'
                        r'podrazdel|подразд|filial|филиал|predstavitel|представител|ofis|офис|branch|region|регион|'
                        r'zakup|закуп|snab|снабж|tender|тендер|postavshik|поставщик|supplier|partner|партн|'
                        r'spravochn|справочн|telefon|телефон|o-kompanii|о-компании|about|o-nas|о-нас|company', re.I)
КАРТА_ПЕРВЫЕ = re.compile(r'kontakt|contact|контакт|rekvizit|реквизит|rukovod|руковод|management|filial|филиал|'
                          r'predstavitel|представител|otdel|отдел|snab|снабж|zakup|закуп', re.I)
# 11.11, смоук на сервере (vtf.ru): из карты шли новости «…представит новый логотип» и товары «stress-management» —
# разделы новостей, статей, каталога и товаров не берём
КАРТА_НЕ = re.compile(r'/(news|novost|новост|blog|press|smi|article|stat[iy]|статьи|goods|tovar|товар|catalog|katalog|'
                      r'каталог|product|produkc|продукц|shop|magazin|магазин|uslug|услуг|service|events?|sobyti|событи|'
                      r'tag|tags|search|poisk|page/\d)', re.I)
_ФАЙЛ = re.compile(r'\.(pdf|jpe?g|png|gif|webp|svg|docx?|xlsx?|zip|rar|mp4|xml|gz)(?:$|[?#])', re.I)


# ---------- 2. Cloudflare: защищённые почты ----------

def _cf(hexs):
    try:
        к = int(hexs[:2], 16)
        адр = ''.join(chr(int(hexs[i:i + 2], 16) ^ к) for i in range(2, len(hexs) - 1, 2))
    except ValueError:
        return ''
    return адр if re.fullmatch(r'[\w.+%-]+@[\w-]+(?:\.[\w-]+)+', адр) else ''


def раскрыть_cf(html):
    """Элемент с data-cfemail -> адрес текстом; ссылка /cdn-cgi/l/email-protection#HEX -> mailto:адрес."""
    if not html or ('cfemail' not in html and 'email-protection' not in html):
        return html

    def элемент(м):
        адр = _cf(м.group(2))
        return '<a href="mailto:%s">%s</a>' % (адр, адр) if адр else м.group(0)
    html = re.sub(r'<(a|span)\b[^>]*\bdata-cfemail=["\']([0-9a-fA-F]{6,})["\'][^>]*>.*?</\1>', элемент, html,
                  flags=re.I | re.S)

    def ссылка(м):
        адр = _cf(м.group(1))
        return 'href="mailto:%s"' % адр if адр else м.group(0)
    return re.sub(r'href=["\'][^"\']*/cdn-cgi/l/email-protection#([0-9a-fA-F]{6,})["\']', ссылка, html, flags=re.I)


# ---------- 3. карта сайта ----------

def _хост(u):
    h = (urllib.parse.urlsplit(u).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def карта_сайта(старт, скачать, предел=12, файлов=5):
    """Адреса страниц из sitemap.xml (индекс — до `файлов` файлов карты). скачать(u) -> (статус, текст, заголовок)."""
    ч = urllib.parse.urlsplit(старт)
    база = '%s://%s' % (ч.scheme or 'https', ч.netloc)
    свой = _хост(старт)
    очередь = []
    try:
        ст, т, _ = скачать(база + '/robots.txt')
        if ст == 'ok':
            очередь += [м.strip() for м in re.findall(r'(?im)^\s*sitemap:\s*(\S+)', т or '')][:3]
    except Exception:  # noqa: BLE001
        pass
    очередь += [база + '/sitemap.xml', база + '/sitemap_index.xml']
    видел, адреса, прочитано = set(), [], 0
    while очередь and прочитано < файлов:
        к = очередь.pop(0)
        if к in видел or _хост(к) != свой or к.endswith('.gz'):
            continue
        видел.add(к)
        try:
            ст, т, _ = скачать(к)
        except Exception:  # noqa: BLE001
            continue
        if ст != 'ok' or '<loc' not in (т or ''):
            continue
        прочитано += 1
        локи = [re.sub(r'<!\[CDATA\[|\]\]>', '', x).strip() for x in re.findall(r'<loc>\s*(.*?)\s*</loc>', т, re.S | re.I)]
        if re.search(r'<sitemapindex', т, re.I):
            # индекс: сначала карты страниц/разделов, карты товаров и каталога — в конец (там контактов нет)
            локи.sort(key=lambda x: bool(re.search(r'product|catalog|katalog|tovar|товар|goods|item|news|blog', x, re.I)))
            очередь += локи[:8]
            continue
        for u in локи:
            if _хост(u) != свой or _ФАЙЛ.search(u):
                continue
            п = urllib.parse.unquote(urllib.parse.urlsplit(u).path)
            if КАРТА_ТЕМА.search(п) and not ВАКАНСИИ.search(п) and not КАРТА_НЕ.search(п) and u not in адреса:
                адреса.append(u)
    адреса.sort(key=lambda u: (not КАРТА_ПЕРВЫЕ.search(urllib.parse.unquote(u)), u.count('/'), len(u)))
    return адреса[:предел]


# ---------- 1. браузер для неоткрывшихся сайтов ----------

CHROME = [r'C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe',
          r'C:\Program Files\Google\Chrome\Application\chrome.exe']
ПАРКОВКА = re.compile(r'Домен не прилинкован|домен припаркован|Домен .{0,40}продаётся|домен продается|domain is for sale|'
                      r'This domain (?:is|may be) for sale|Сайт не опубликован|Сайт заблокирован|Hosting is not configured|'
                      r'Index of /|Default Web Site Page|Welcome to nginx|Apache2 .{0,20}Default Page', re.I)
КАПЧА = re.compile(r'captcha|smartcaptcha|cf-challenge|challenge-platform|Подтвердите, что вы не робот|Проверка браузера|'
                   r'Just a moment|Access denied|Доступ ограничен', re.I)
_места = threading.BoundedSemaphore(int(os.environ.get('KC_BRAUZEROV', '2')))


def варианты(старт):
    ч = urllib.parse.urlsplit(старт if '://' in старт else 'https://' + старт)
    h = (ч.hostname or '').lower()
    голый = h[4:] if h.startswith('www.') else h
    путь = ч.path or '/'
    порт = ':%d' % ч.port if ч.port else ''
    хосты = (h, голый) if re.fullmatch(r'[\d.]+', голый) else (h, голый, 'www.' + голый)
    out = []
    for схема in ('https', 'http'):
        for хост in хосты:
            u = '%s://%s%s%s' % (схема, хост, порт, путь)
            if u not in out:
                out.append(u)
    return out


class Браузер:
    """Один Chromium на сайт, в потоке обхода (Playwright sync — свой экземпляр на поток). Закрыть — закрыть()."""

    def __init__(self):
        self.pw = self.б = self.к = self.стр = None
        self.взял = False
        self.сбой = ''

    def _старт(self):
        from playwright.sync_api import sync_playwright
        _места.acquire()
        self.взял = True
        self.pw = sync_playwright().start()
        exe = next((p for p in CHROME if os.path.exists(p)), None)
        self.б = self.pw.chromium.launch(headless=True, executable_path=exe)
        self.к = self.б.new_context(locale='ru-RU', viewport={'width': 1366, 'height': 900}, ignore_https_errors=True)
        self.к.route('**/*', lambda r: r.abort() if r.request.resource_type in ('image', 'media', 'font') else r.continue_())
        self.стр = self.к.new_page()

    def скачать(self, u, таймаут=30000):
        """-> (статус, html, заголовок), как meyer_nalichie.скачать."""
        try:
            if self.стр is None:
                self._старт()
            отв = self.стр.goto(u, timeout=таймаут, wait_until='domcontentloaded')
            self.стр.wait_for_timeout(2500)
            код = отв.status if отв else 0
            html = self.стр.content()
            if код >= 400:
                return 'ошибка: HTTP %d (браузер)' % код, '', ''
            if КАПЧА.search(html[:30000]) and len(re.sub(r'<[^>]+>', '', html)) < 3000:
                return 'ошибка: капча (браузер)', '', ''
            return 'ok', html, (self.стр.title() or '')[:150]
        except Exception as e:  # noqa: BLE001
            self.сбой = type(e).__name__
            # вкладка после неудачного перехода уходит на страницу ошибки и прерывает следующий переход — новая вкладка
            if self.стр is not None:
                try:
                    self.стр.close()
                    self.стр = self.к.new_page()
                except Exception:  # noqa: BLE001
                    pass
            return 'ошибка: браузер %s' % type(e).__name__, '', ''

    def открыть_сайт(self, старт):
        """Перебор вариантов адреса с таймаутом 45 с. -> (адрес, (статус, html, заголовок)) или ('', ошибка)."""
        посл = ('ошибка: браузер', '', '')
        for u in варианты(старт):
            посл = self.скачать(u, 45000)
            if посл[0] == 'ok' and len(re.sub(r'<[^>]+>', ' ', посл[1])) > 300:
                if ПАРКОВКА.search(посл[2] + ' ' + посл[1][:20000]):
                    return '', ('ошибка: заглушка хостинга (браузер)', '', '')
                return u, посл
            if self.стр is None:  # Chromium не запустился — дальше не пробуем
                break
        return '', посл

    def закрыть(self):
        for f in (lambda: self.б and self.б.close(), lambda: self.pw and self.pw.stop()):
            try:
                f()
            except Exception:  # noqa: BLE001
                pass
        if self.взял:
            self.взял = False
            _места.release()
