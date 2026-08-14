# -*- coding: utf-8 -*-
"""Обогащение контактами: ИНН/имя компании -> сайт -> страница «Контакты» ->
провайдер вытаскивает email С РОЛЯМИ (закупки/директор/гл.инженер + ФИО) ->
MX-проверка. Запускается раннером (task=enrich_contacts). Медленный темп (антибот).

stdin: {"companies":[{"inn","name","city","site"(опц.)}], "source_site":"list-org",
        "pace_min":6,"pace_max":14}
stdout: {"results":[{inn,name,site,emails:[{email,role,person,mx_ok}],
                     phones,best_for_outreach,method,error?}], "summary":{...}}"""
from itertools import zip_longest
import os, sys, json, re, time, random, threading
import urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor

# Параллелим МЕЖДУ компаниями (у каждой свой сайт), но ОБЩИЕ хосты держим по одному
# потоку КАЖДЫЙ — list-org и поисковик разные сайты, потому идут параллельно друг другу,
# но сами по себе не долбятся в много потоков (правило владельца «не грузить один сайт»).
_SEM_LISTORG = threading.Semaphore(1)
_SEM_SEARCH = threading.Semaphore(1)
_SEM_BROWSER = threading.Semaphore(2)   # Chromium разом (память ~300МБ каждый); main() переставит из args
# xmlriver лимитирует КАНАЛЫ аккаунта (параллельные слоты). Заливаем 500+ — отдаёт
# «Нет свободных каналов». Держим concurrency ≤ числа каналов. Настраивается под аккаунт
# (XMLRIVER_CHANNELS); дефолт 4 — консервативно, чтобы массовый прогон не выбивал лимит.
_SEM_XMLRIVER = threading.Semaphore(max(1, int(os.environ.get('XMLRIVER_CHANNELS', '4'))))
# Повтор к xmlriver (владелец 11.08.2026, при переходе на 30 одновременных батчей):
# «если ошибка у хмл ривера, запрос повторно идёт через 3 сек». Раньше пауза росла
# (1.5 -> 3 -> 4.5) и попыток было три — при 30 процессах, дерущихся за 16 каналов
# аккаунта, этого не хватает: запрос отваливался, а компания оставалась без сайта.
# Теперь ровно 3 секунды и больше попыток: ждать очередь дешевле, чем терять строку.
_XMLRIVER_TRIES = max(1, int(os.environ.get('XMLRIVER_TRIES', '12')))
_XMLRIVER_PAUZA = float(os.environ.get('XMLRIVER_PAUSE', '3'))

# счётчики трат по сервисам (для сметы пилота) — потокобезопасно
_COST = {'xmlriver': 0, 'provider_calls': 0, 'prov_in_chars': 0, 'prov_out_chars': 0,
         'capmonster': 0, 'twocaptcha': 0}
_COST_LOCK = threading.Lock()

# браузер-фолбэк (Chromium+капча) — бесплатный, но МЕДЛЕННЫЙ (семафор 2). На массовом
# прогоне лучше выключить и гонять отдельным проходом. main() ставит из args.
# Читаем ещё и из окружения: ops-скрипты запускают модуль импортом, а не через
# main(), и другого способа выключить браузер у них не было.
_NO_BROWSER = os.environ.get('NO_BROWSER', '') not in ('', '0', 'false', 'False')
# list-org/DDG фолбэк поиска сайта — под семафором=1 (сериализует ВСЕ воркеры) +
# хардкод-паузы: на массовом прогоне это главный тормоз. xmlriver и так основной канал.
_USE_FALLBACK = True
_RETURN_TEXT = False    # вернуть сырой текст сайта в результат (для офлайн модель-сравнения)
# Dolphin-фолбэк: реальный антидетект-браузер для защищённых крупных сайтов (пробивает
# managed Cloudflare/SmartCaptcha, что голый Chromium не может). Включается передачей
# dolphin_token+dolphin_profiles в args; профили ротируются по кругу.
_DOLPHIN_TOKEN = ''
_DOLPHIN_PROFILES = []
_DOLPHIN_IDX = [0]
_DOLPHIN_LOCK = threading.Lock()


# два расположения runner-secrets.env: локальный (иногда удаляется) и стабильный на дропе.
_SECRET_FILES = (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runner-secrets.env'),
                 r'C:\seostat\drop\drop-storage\runner-secrets.env')


def _read_secret(key):
    """Значение секрета: env ИЛИ любой из runner-secrets.env файлов (первый непустой).
    Для DOLPHIN_TOKEN — САМЫЙ СВЕЖИЙ JWT из всех источников: env службы затенял обновлённый
    владельцем файл на drop-storage старым (удалённым из дашборда) токеном → вечный 401."""
    if key == 'DOLPHIN_TOKEN':
        import base64 as _b64
        def _iat(tok):
            try:
                mid = tok.split('.')[1]
                return float(json.loads(_b64.urlsafe_b64decode(mid + '=' * (-len(mid) % 4))).get('iat') or 0)
            except Exception:  # noqa: BLE001
                return 0.0
        cands = []
        if os.environ.get(key):
            cands.append(os.environ[key])
        for p in _SECRET_FILES:
            try:
                for line in open(p, encoding='utf-8-sig'):
                    line = line.strip()
                    if line.startswith(key + '='):
                        val = line.split('=', 1)[1].strip()
                        if val and not val.startswith('<'):
                            cands.append(val)
            except Exception:  # noqa: BLE001
                continue
        if cands:
            return max(cands, key=_iat)
    v = os.environ.get(key)
    if v:
        return v
    for p in _SECRET_FILES:
        try:
            if not os.path.exists(p):
                continue
            for line in open(p, encoding='utf-8-sig'):
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, val = line.split('=', 1)
                if k.strip() == key:
                    val = val.strip()
                    if val and not val.startswith('<'):
                        return val
        except Exception:  # noqa: BLE001
            continue
    return ''


def _parse_profile_ids(raw):
    """Список ID из строки (перевод строки/запятая/пробел) или уже-списка. Комменты '#' и пустое — вон."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw]
    else:
        items = re.split(r'[\s,;]+', str(raw))
    out = []
    for it in items:
        it = it.strip()
        if not it or it.startswith('#'):
            continue
        it = it.split('#', 1)[0].strip()
        if it:
            out.append(it)
    # уникальные с сохранением порядка
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _cached_dolphin_profiles():
    """20 ID профилей из dolphin-profiles.txt: локальные копии → HTTP с дропа. Пусто если нигде нет."""
    paths = (os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dolphin-profiles.txt'),
             r'C:\seostat\drop\drop-storage\dolphin-profiles.txt')
    for p in paths:
        try:
            if os.path.exists(p):
                ids = _parse_profile_ids(open(p, encoding='utf-8-sig').read())
                if ids:
                    return ids
        except Exception:  # noqa: BLE001
            continue
    # фолбэк: скачать с дропа
    try:
        url = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/') + '/dolphin-profiles.txt'
        req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = _parse_profile_ids(r.read().decode('utf-8', 'replace'))
            if ids:
                return ids
    except Exception:  # noqa: BLE001
        pass
    return []


def _resolve_dolphin_profiles(args_profiles, token):
    """Профили дельфина в порядке надёжности: (1) явные из args → (2) live-список dolphin_list(token) →
    (3) закэшированный dolphin-profiles.txt (20 ID владельца). Живёт даже если токен протух (401)."""
    ids = _parse_profile_ids(args_profiles)
    if ids:
        return ids
    if token:
        try:
            import browser_probe as BP
            listed = BP.dolphin_list(token)
            live = [str(p.get('id')) for p in (listed or []) if p.get('id')]
            if live:
                return live
        except Exception:  # noqa: BLE001
            pass
    return _cached_dolphin_profiles()


def _opo_worker(profile, token, chunk, out_path, sleep_ms=0, start_delay=0.0):
    """ОТДЕЛЬНЫЙ ПРОЦЕСС (Playwright sync не потокобезопасен → только mp.Process): один
    дельфин-профиль, ОДНА сессия на всю пачку. checko /licenses/data?source=07 -> РТН-ОПО.
    start_delay: каскадный старт профилей (не все разом); sleep_ms: пауза между компаниями."""
    import browser_probe as _BP
    import re as _re
    import json as _json
    import random as _rnd
    from playwright.sync_api import sync_playwright
    if start_delay:
        time.sleep(start_delay)
    RTN = _re.compile(r'взрывопожароопасн|химически\s+опасн|эксплуатац\w*\s+\w*\s*опасн\w+\s+производствен|'
                      r'опасн\w+\s+производствен\w+\s+объект|маркшейдер|горн\w+\s+работ|'
                      r'гидротехническ\w+\s+сооружен', _re.I)
    # НАСТОЯЩИЙ сигнал под компрессоры (наводка владельца): вид работ "оборудование, работающее
    # под давлением >0,07 МПа" / "нагрев воды >115°C". Лицензия ВП только на горючие вещества
    # компрессоры НЕ подразумевает (напр. ДорСтрой ВП-01-003701) — а Газпром ВП-00-010849 да.
    PRESSURE = _re.compile(r'давлени\w*\s+более\s+0[.,]07|нагрева\s+воды\s+более\s+115|'
                           r'оборудован\w*,?\s*работающ\w*\s+под\s+давлением|'
                           r'сосуд\w*,?\s*работающ\w*\s+под\s+давлением|под\s+давлением\s+более', _re.I)
    LICNUM = _re.compile(r'(?:№\s*)?(?:ВП|ВХ|ЭВ|ПМ|ОТ|ГС)-\d{2}-\d{5,6}', _re.I)
    local = {}
    try:
        cdp, _port = _BP.dolphin_start(profile, headless=False, token=token)
        with sync_playwright() as pw:
            br = pw.chromium.connect_over_cdp(cdp, timeout=40000)
            ctx = br.contexts[0] if br.contexts else br.new_context()
            try:
                ctx.add_init_script(_BP._CF_INIT_JS); ctx.add_init_script(_BP._YSC_INIT_JS)
            except Exception:  # noqa: BLE001
                pass
            page = ctx.new_page()
            first = True
            for c in chunk:
                if not first and sleep_ms:
                    time.sleep(sleep_ms / 1000.0 + _rnd.uniform(0, 1.2))
                first = False
                ogrn = str(c.get('ogrn') or '').strip()
                if not ogrn:
                    local[c.get('inn', '?')] = {'error': 'нет OGRN'}; continue
                url = f'https://checko.ru/company/{ogrn}/licenses/data?source=07'
                try:
                    page.goto(url, timeout=45000, wait_until='domcontentloaded')
                    page.wait_for_timeout(2500)
                    html, cap = _BP.handle_captcha(page, url)
                    if cap or _looks_blocked(html):
                        # капча пройдена/блок: перезагружаем ЦЕЛЕВУЮ страницу (клик по
                        # «Подтвердить» не всегда возвращает на неё) и пробуем ещё раз
                        page.goto(url, timeout=45000, wait_until='domcontentloaded')
                        page.wait_for_timeout(2000)
                        html, cap = _BP.handle_captcha(page, url)
                    txt = _re.sub(r'\s+', ' ', _re.sub(r'<[^>]+>', ' ',
                                  _re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=_re.S | _re.I)))
                    local[ogrn] = {'inn': c.get('inn'), 'name': (c.get('name') or '')[:40],
                                   'sector': c.get('sector', ''), 'rtn_opo': bool(RTN.search(txt)),
                                   'pressure_equip': bool(PRESSURE.search(txt)),
                                   'lic_nums': list(set(LICNUM.findall(txt)))[:5], 'captcha': cap,
                                   'blocked': _looks_blocked(html)}
                except Exception as e:  # noqa: BLE001
                    local[ogrn] = {'inn': c.get('inn'), 'error': str(e).splitlines()[0][:80]}
            _BP.dolphin_close_tabs(br)  # не оставлять вкладки в сессии профиля (грузятся при след. старте)
            try:
                br.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        for c in chunk:
            local[str(c.get('ogrn') or c.get('inn'))] = {'error': f'session: {str(e)[:70]}'}
    finally:
        try:
            _BP.dolphin_stop(profile, token=token)
        except Exception:  # noqa: BLE001
            pass
    try:
        _json.dump(local, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def _next_dolphin_profile(skip_busy=True):
    """Следующий профиль по кругу. skip_busy: пропустить ЗАПУЩЕННЫЕ (открытые вручную/др.
    джобом) — не плодим окна и не ломимся в EBUSY (наводка владельца 2026-07-23). Проверяем
    до len(profiles) кандидатов; если все заняты — вернём очередной (пусть штатный stop-start)."""
    # VK-пин ИСКЛЮЧЁН из общей ротации: 12 браузер-воркеров держали его занятым ->
    # VK-вызовы ловили 500/EBUSY на старте (владелец закрывал окно, а оно возвращалось).
    pool = [p for p in _DOLPHIN_PROFILES if str(p) != str(_VK_PIN_PROFILE)] or _DOLPHIN_PROFILES
    if not pool:
        return None
    n = len(pool)
    for _ in range(n if skip_busy else 1):
        with _DOLPHIN_LOCK:
            i = _DOLPHIN_IDX[0] % n
            _DOLPHIN_IDX[0] += 1
        pid = pool[i]
        if not skip_busy:
            return pid
        try:
            import browser_probe as _BP
            if _BP.dolphin_is_running(pid, token=_DOLPHIN_TOKEN) is True:
                continue   # занят -> следующий
        except Exception:  # noqa: BLE001
            pass
        return pid
    return pool[_DOLPHIN_IDX[0] % n]  # все заняты -> штатный (stop-start освободит)
_SKIP_PROVIDER = False  # не звать provider (только краул+regex) — быстрый сбор текстов
_NO_STAFF_SEARCH = False  # не искать staff-страницу через SERP (экономия xmlriver-квоты)
_NO_DIR_LOOKUP = False    # не искать контакты в бизнес-справочниках для компаний без сайта (#7)
_OPO_CHECK = False        # эвристическая проверка ОПО Ростехнадзора (скоринг центробежных)
_DISCOVERY_ONLY = False   # фаза-1: только найти сайт (xmlriver), краул отдельной фазой
_HH_CHECK = False         # адресная hh-проверка «ищет ли ЭТА компания компрессорщиков»
_NO_SITE_CACHE = False    # не брать сайт из кэша enrich.db (обход при ошибках кэша)
_NO_SITE_CONFIRM = False  # не звать SERP вторым свидетелем к сайту из базы (экономия квоты)
_NO_REKV_SEARCH = False   # не искать страницу реквизитов на домене (добор жёсткого ИНН)
_NO_VK_LOOKUP = False     # не искать VK-группу компании (источник vk-group)
_ZAKUPKI_CHECK = False    # тянуть контакт закупщика из ЕИС в enrich_one (флаг: дорого для массы)
_SMTP_CHECK = False       # SMTP-верификация ящиков в enrich_one (флаг: сетевые пробы, дорого)


def _bump(k, n=1):
    with _COST_LOCK:
        _COST[k] = _COST.get(k, 0) + n

# переиспользуем инфраструктуру verify_company (в той же папке)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_company as VC  # _fetch, _detect_block, _provider_call_stdlib, UA

AGGREGATORS = ('otc.ru', 'rts-tender', 'roseltorg', 'sberbank-ast', 'etp-ets', 'tender',
               'zakupki', 'b2b-center', 'gz-spb', 'torgi.gov',
               'cataloxy', 'find-org', 'orgpage', 'productcenter', 'pulscen', 'tiu.ru',
               'blizko', 'firmika', 'spr.ru', 'yp.ru', 'bizly', 'rustelemarket',
               'list-org', 'rusprofile', 'checko', 'zachestnyibiznes', 'sbis.ru',
               'audit-it', 'spark-interfax', 'rbc.ru', 'sberbank', 'nalog',
               'gogov', 'kontur', 'tbank', 'saby.ru', 'openweb', 'vbankcenter',
               'wikipedia', 'yandex.', 'google.', 'youtube', '2gis', 'zoon',
               # контент-платформы/блоги — НЕ сайт компании (инцидент: dzen.ru принят
               # за сайт ООО и покраулен dzen.ru/company/staff/)
               'dzen.ru', 'vc.ru', 'tenchat', 'pikabu', 'habr', 'rutube', 'youla',
               'zen.yandex', 'т-ж.рф', 'journal.tinkoff', 'dprom.online', 'vbr.ru',
               'hh.ru', 'avito', 'flamp', 'yell.ru', 'orgpage', 'duckduckgo',
               # vk.ru — тот же ВКонтакте после переезда на второй домен.
               # В списке был только vk.com, поэтому vk.ru спокойно попал в
               # кандидаты как «сайт» ООО (ИНН 7743500983). Токен с точкой
               # сверяется как хост/суффикс, живые домены вроде spvk.ru он
               # не заденет.
               'bing.', 'mail.ru', 'vk.com', 'vk.ru', 'telegram',
               'wildberries', 'ozon',
               'rusbase', 'list-org.com', 'gis', 'dadata', 'buhonline', 'klerk',
               'audit-it', 'glavbukh', 'nalog-nalog', 'regfile', 'egrul',
               'sravni', 'banki.ru', 'consultant', 'garant', 'zakupki.gov',
               'ppt.ru', 'regforum', 'buhguru', 'nalog.gov', 'assessor.ru',
               'testfirm', 'e-ecolog', 'kompass', 'rusbizinform', 'sbis.ru',
               'rusprofile', 'spark', 'seldon', 'kartoteka', 'b2b-center',
               'export-base', 'compromat', 'otzyv', 'zoon', 'profi.ru',
               # ГОССАЙТЫ/РЕГУЛЯТОРЫ — никогда не сайт компании (владелец: «как центробанк
               # сюда попал?» — cbr.ru из SERP-упоминания в реестрах ЦБ):
               'cbr.ru', '.gov.ru', 'government.ru', 'sudrf.ru', 'arbitr.ru', 'fedresurs',
               'gks.ru', 'rosstat', 'fssp.ru', 'genproc', 'kremlin.ru',
               'duma.ru', 'council.gov', 'minpromtorg', 'minfin', 'rostrud', 'mintrud',
               'rospotrebnadzor', 'roszdravnadzor', 'rosminzdrav', 'customs.ru', 'fas.gov',
               # gosuslugi НЕ целиком: у госкомпаний (МУП/водоканал) официальные страницы
               # на ПОДДОМЕНАХ *.gosuslugi.ru (Госвеб) с контактами — владелец видел такие.
               # Блокируем только главный портал (спец-кейс в _is_own_site).
               # ложные привязки, пойманные аудитом вывода (домен на десятки-сотни РАЗНЫХ ИНН —
               # заведомо не сайт компании: реклама/энциклопедии/словари/агрегаторы/реестры):
               'sky.pro', 'skyeng', 'optimalgroup.ru', 'bigenc.ru', 'sinonim.org',
               'b2b.house', 'xfirm.ru', 'subscribe.ru', 'cons.ru', 'ruwiki.ru',
               'ppt.ru', 'star-pro.ru', 'respectrb.ru', 'bar.ru', 'work5.ru',
               'sravni.ru', 'glavkniga', 'wiki2.', 'academic.ru', 'dic.academic',
               'synapsenet.ru', 'vsem-podryad', 'companium.ru', 'comfex.ru',
               'check.tochka', 'pd.rkn.gov.ru', 't.me', 'reputation.ru',
               'prima-inform', 'instroyproject.ru', 'vk-portal', 'stacks.vk',
               # аудит общих сайтов 2026-07-26: сервисы проверки контрагентов и портал
               # раскрытия Интерфакса разошлись по 13 разным ИНН как «сайт компании»
               'credinform', 'birweb', '1prime.ru', 'example.com')
CONTACT_HINTS = ('contact', 'kontakt', 'контакт', 'about', 'o-kompanii', 'o-nas',
                 'company', 'zakup', 'снабж', 'закуп', 'requisites', 'rekvizity',
                 'rukovodstvo', 'руковод', 'komanda', 'team', 'sotrudniki', 'управлен',
                 'menedzh', 'director', 'otdel', 'otdely', 'подразделен', 'prodazh',
                 'sales', 'kommerch', 'коммерч', 'filial', 'branch', 'предста', 'ofis',
                 'office', 'сбыт', 'poставщик', 'postavshchik', 'kontakty',
                 # staff-страницы (задача владельца 2026-07-23): персональные контакты по ролям
                 'staff', 'сотрудник', 'персонал', 'kollektiv', 'коллектив', 'employees')
# маркеры ИМЕННО staff-страниц (подмножество hints) — для приоритизации и решения о пробах
# Разбор 29.07 (seo-texts/engineers-lens): страница «Руководство» на сайте
# заказчика — ЛУЧШИЙ источник инженеров: полное ФИО, ТЕКУЩАЯ должность, прямой
# телефон и почта одним GET. Семь главных инженеров группы «Россети Волга»
# сняты примерно за 12 запросов. Поэтому слаги руководства/менеджмента и блока
# главного инженера добавлены и в хинты, и в пробы путей.
_STAFF_HINTS = ('staff', 'sotrudniki', 'сотрудник', 'персонал', 'kollektiv', 'коллектив',
                'komanda', 'team', 'rukovodstvo', 'руковод', 'employees',
                'menedzhment', 'менеджмент', 'management', 'apparat', 'аппарат',
                'glavnyy-inzhener', 'glavnogo-inzhenera', 'администрац',
                'administrac', 'podrazdelen', 'подразделен', 'filial', 'филиал')
# типовые пути staff-страниц (Bitrix-канон и частые слаги) — пробуем, если с главной
# на staff никто не ссылается; кап на пробы держит паузы под контролем
_STAFF_PROBE_PATHS = ('/company/staff/', '/staff/', '/rukovodstvo/',
                      '/o-kompanii/rukovodstvo/', '/about/management/',
                      '/company/management/', '/menedzhment_filiala/')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
# Разделители: обычный дефис, типографские тире (U+2010..U+2015, U+2212),
# неразрывный дефис и точка. Дизайнерские сайты пишут «+7–342–292–14–60»
# длинным тире, и такой номер регуляркой НЕ находился: он не создавал окна
# в умной обрезке, не попадал в добор и вдобавок запускал лишний рендер
# браузером (условие «телефонов не найдено»).
_PH_SEP = r'[\s\-\u2010-\u2015\u2212\u00a0().]'
# (?<!\d) — обязательно. Без него регулярка выкусывает «телефон» ИЗ СЕРЕДИНЫ
# реквизитов: в «ОГРН 1083801006860» с третьей цифры читается 83801006860, и
# ОГРН оседает в phone_contacts как номер. Поймано 29.07 на живой странице
# synapsenet (разведка _ops_agg_probe2), а ОГРН стоит в подвале почти каждого
# сайта компании, так что это не единичный случай. Хвостовой (?!\d) НЕ ставлю
# сознательно: номера со слипшимся добавочным («74112408009 1216» без пробела)
# тогда перестали бы находиться вовсе, а их чинит phones_clean.починить.
# Форма номера. Прежняя жёстко требовала код из ТРЁХ цифр и разбивку 3+3+2+2,
# поэтому «8 (3812) 39-45-67» и «8 (81368) 5-12-34» не находились ВООБЩЕ — а это
# код Омска и код райцентра, то есть ровно те заводы, ради которых базу и
# собирали. Без разделителей такой номер регулярка ловила (8 и 10 цифр подряд
# ложатся в 3+3+2+2), с разделителями — нет, и потеря выглядела случайной.
# Теперь жёстко задан только КОД (3–5 цифр подряд сразу после кода страны) —
# он и служит якорем, — а хвост берётся посимвольно до полных десяти цифр, так
# что любая разбивка годится, включая «363-0-363». Совсем свободную форму
# «десять цифр через что угодно» не делаю: без якоря она склеивает соседние
# числа таблицы в мнимый телефон.
_ХВОСТ = '(?:' + _PH_SEP + r'*\d)'
_PHONE_SITE = re.compile(
    r'(?<!\d)(?:\+7|8)' + _PH_SEP + r'*(?:'
    + r'\d{5}' + _ХВОСТ + '{5}|'
    + r'\d{4}' + _ХВОСТ + '{6}|'
    + r'\d{3}' + _ХВОСТ + '{7})')
# Второй рубеж против реквизитов: подпись перед номером. Ловит то, что не ловит
# (?<!\d) — 12-значный ИНН, начинающийся с восьмёрки, и «р/с 8...». Смотрим
# 24 символа перед совпадением: метка стоит вплотную.
_РЕКВ_ПЕРЕД = re.compile(
    r'(?:ИНН|ОГРН(?:ИП)?|КПП|БИК|ОКПО|ОКТМО|р/?с|к/?с|сч[её]т)'
    r'\s*[:№]?\s*\d*$', re.I)


# ВЕКТОРНАЯ ГРАФИКА, ПРИТВОРЯЮЩАЯСЯ ТЕЛЕФОНОМ. Разделителями в номере
# считаются пробел и точка, а inline-SVG несёт атрибут d="M8892 7.44042 1…" —
# после нормализации это ровно ДЕСЯТЬ цифр, поэтому ни проверка длины, ни
# рубеж реквизитов такое не ловят. Перекрауливание 29.07 записало так 3815
# «телефонов», и каждый выглядел рабочим номером.
# Отличает сырая форма: у настоящего номера группы по 2–3 цифры, у координаты
# после точки идёт 4 и больше. Добавочный отрезаем ПЕРВЫМ — иначе под правило
# попадает живой «+7 495 287-85-36 доб.7704», а это самые ценные записи.
_ДОБ_ХВОСТ = re.compile(r'\s*(?:доб|вн|внутр)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_КООРДИНАТА = re.compile(r'\.\d{4,}|\d+\.\d+\s+\d+\.\d+')
# сама графика и скрипты: вырезаем целиком, чтобы до разбора не доходили
_РАЗМЕТКА_ШУМ = re.compile(
    r'<svg\b.*?</svg>|<script\b.*?</script>|<style\b.*?</style>|'
    r'\sd\s*=\s*"[^"]{40,}"|\spoints\s*=\s*"[^"]{20,}"|'
    r'\sviewBox\s*=\s*"[^"]*"', re.S | re.I)


def без_графики(html):
    """Убрать из разметки SVG, скрипты и стили ДО поиска контактов."""
    return _РАЗМЕТКА_ШУМ.sub(' ', html or '')


# ГОРОДСКОЙ НОМЕР БЕЗ КОДА СТРАНЫ: «тел. (8482) 56-10-44».
# У _PHONE_SITE обязателен ведущий «+7» или «8», и на такой записи он
# промахивается дважды: восьмёрку он съедает как код страны, а после неё
# остаётся девять цифр вместо десяти. Между тем это самая обычная запись на
# сайте завода — код города в скобках, дальше местный номер.
# Соседняя сессия намерила 38 таких уникальных номеров на 867 страницах, 23
# из них новые. Якорь тут крепкий — код города В СКОБКАХ, поэтому ложных
# срабатываний на датах и суммах не будет: без скобок правило не работает.
_PHONE_SKOBKA = re.compile(
    r'(?<![\d+])\((\d{3,5})\)' + _PH_SEP + r'*(\d' + _ХВОСТ + r'{4,6})(?!\d)')


def phones_in(txt):
    """Совпадения _PHONE_SITE, из которых выкинуты реквизиты и координаты.

    Единая точка: любой разбор, который пишет телефон в базу, должен ходить
    сюда, а не звать _PHONE_SITE напрямую — иначе рубеж работает не везде.
    """
    t = txt or ''
    занято = []
    for m in _PHONE_SITE.finditer(t):
        if _РЕКВ_ПЕРЕД.search(t[max(0, m.start() - 24):m.start()]):
            continue
        if _КООРДИНАТА.search(_ДОБ_ХВОСТ.sub('', m.group(0))):
            continue
        занято.append((m.start(), m.end()))
        yield m
    for m in _PHONE_SKOBKA.finditer(t):
        # ровно десять цифр — иначе это не номер, а скобка с числом
        if len(re.sub(r'\D', '', m.group(0))) != 10:
            continue
        if _РЕКВ_ПЕРЕД.search(t[max(0, m.start() - 24):m.start()]):
            continue
        # не отдаём то, что уже нашла основная регулярка (номер с «8» перед
        # скобкой попадает под оба правила, и в базу ушёл бы дважды)
        if any(a <= m.start() < b or a < m.end() <= b for a, b in занято):
            continue
        yield m


def phones_list(txt):
    """То же, что phones_in, но СПИСКОМ совпадений.

    `phones_in` — генератор, и `phones_in(t)[:4]` роняет прогон с «generator
    object is not subscriptable». На этом уже потерян один прогон раннера.
    Просто вернуть список нельзя: пять мест зовут `next(phones_in(...), None)`,
    и на списке это сломается. Поэтому обёртка, а не смена типа.
    """
    return list(phones_in(txt))


def phone_strings(txt, cap=None):
    """Нормализованные строки номеров без дублей — то, что нужно почти всем."""
    из = sorted({re.sub(r'[\s\-()]', '', m.group(0)) for m in phones_in(txt)})
    return из[:cap] if cap else из
# добавочные номера отделов («доб. 122», «вн. 15») — якорь контактной зоны: в таблицах
# контактов добавочный часто стоит В ДРУГОЙ ЯЧЕЙКЕ, далеко от самого номера телефона
_EXT_RE = re.compile(r'(?:доб|вн|внутр)\.?\s*[:№]?\s*\d{1,5}', re.I)
# реквизиты («ИНН 5905062274») — якорь для верификации verified='inn' по возвращённому тексту
_REKV_RE = re.compile(r'(?:ИНН|ОГРН)\s*[:№]?\s*\d{9,15}', re.I)
# ДОЛЖНОСТИ — якорь для умной обрезки: зона с должностью обязана доехать до
# модели вместе с номером, иначе телефон приходит обезличенным. Раньше окна
# ставились только вокруг email/телефона, и подпись «Главный энергетик» в
# соседней ячейке таблицы вылетала из бюджета.
_POST_RE = re.compile(
    r'(?:главн\w*\s+(?:инженер|энергетик|механик|технолог)|гл\.?\s*(?:инженер|энергетик|механик|технолог)'
    r'|техническ\w*\s+директор|директор\s+по\s+(?:производств|техни)\w*'
    r'|начальник\w*\s+(?:производств|цеха|отдела|службы|управления)'
    r'|руководител\w*\s+(?:производств|отдела|службы|направления)'
    r'|отдел\s+(?:снабжения|закупок|главного)|служба\s+главного'
    r'|КИПиА|АСУ\s*ТП|ОГЭ|ОГМ|ОМТС)', re.I)
# статика — НЕ страницы: contacts.css из <link href> ловилась хинтом 'contact' и краулилась
_STATIC_EXT_RE = re.compile(
    r'\.(?:css|js|svg|png|jpe?g|gif|webp|ico|woff2?|ttf|eot|pdf|zip|mp4|webm'
    # вложения-документы: краул декодировал их как текст и выкусывал псевдоадреса
    # из бинарной каши (h0iprl@nn.zz из shtaket-rasprodazha.docx, живой случай)
    r'|docx?|xlsx?|pptx?|rtf|odt|ods|csv|rar|7z|gz|tar)(?:[?#]|$)')

# --- добор контактов из МЕСТ, которые теряет tag-strip: mailto/tel-ссылки, JSON-LD,
# обфусцированные адреса (info [at] domain (точка) ru, &#64;, (собака)). ---
_MAILTO_RE = re.compile(r'mailto:([^"\'?>\s]+)', re.I)
_TEL_RE = re.compile(r'tel:([+\d\s\-()]{7,})', re.I)
_JSONLD_RE = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DEOBF = [(re.compile(p, re.I), r) for p, r in (
    (r'&#0?64;|&commat;|＠|\s*[\[({]\s*(?:at|собака|эт)\s*[\])}]\s*', '@'),
    (r'\s*[\[({]\s*(?:dot|точка|тчк)\s*[\])}]\s*|\s+\(?точка\)?\s+', '.'),
)]
_IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')

# Домены платформ-конструкторов сайтов и сервисов, чьи СЛУЖЕБНЫЕ адреса сидят в подвале
# шаблона компании и ложно берутся как контакт компании (владелец: «приходит мусор»):
# help@creatium.io у сайта на Creatium, @tilda/@wix и т.п. Плюс заведомо не-контактные локали.
_JUNK_EMAIL_DOMAINS = ('creatium.io', 'tilda.cc', 'tilda.ws', 'tildacdn.com', 'wix.com',
                       'wixpress.com', 'ukit.com', 'ukit.me', 'nethouse.ru', 'insales.ru',
                       'bitrix24.ru', 'sentry.io', 'sentry-cdn.com', 'wordpress.com',
                       'squarespace.com', 'godaddy.com', 'shopify.com', 'flexbe.com',
                       'craftum.com', 'reg.ru', 'nic.ru', 'beget.com', 'example.com',
                       # хостеры и площадки, найденные проверкой 12.08: их адреса
                       # приходили вместо контактов компании (support@majordomo.ru
                       # с 403-страницы хостера, вакансии с rabota.ru)
                       'majordomo.ru', 'timeweb.ru', 'timeweb.com', 'sprinthost.ru',
                       'hostland.ru', 'jino.ru', 'masterhost.ru', 'ihc.ru', 'rf.ru',
                       'rabota.ru', 'hh.ru', 'superjob.ru', 'avito.ru', 'zarplata.ru',
                       'example.org', 'domain.com', 'yourdomain.com', 'sentry.wixpress.com',
                       # почты рекламы/сервисов/справочников, попавшие как «контакт компании»
                       # (аудит вывода: один адрес на десятки-сотни разных ИНН):
                       'skyeng.ru', 'sky.pro', 'optimalgroup.ru', 'subscribe.ru', 'cons.ru',
                       'rusprofile.ru', 'ruwiki.ru', 'list-org.com', 'rbc.ru', 'ppt.ru',
                       'synapsenet.ru', 'b2b.house', 'companium.ru', 'comfex.ru',
                       'vsem-podryad.ru', 'prima-inform.ru', 'instroyproject.ru',
                       'vk-portal.net', 'reputation.ru')
_JUNK_EMAIL_LOCAL = ('noreply', 'no-reply', 'no.reply', 'donotreply', 'do-not-reply',
                     'mailer-daemon', 'mailerdaemon')

# СЛУЖЕБНЫЕ ЯЩИКИ — не контакт для коммерческого письма ни при какой роли.
# Случайная выборка 14.08 вынесла наверх anticorruption@rzd-med.ru с ролью
# «общий»: это горячая линия по коррупции. Письмо с предложением компрессора
# туда — удар по репутации, а не промах разметки, поэтому такие адреса
# отбрасываются вместе с noreply, а не размечаются.
_SLUZHEBNYE_YASHCHIKI = (
    'anticorruption', 'anti-corruption', 'stop-corruption', 'stopcorruption',
    'corruption', 'compliance', 'whistleblow', 'hotline', 'hot-line',
    'goryachaya', 'doverie', 'trustline', 'security', 'abuse',
    'privacy', 'gdpr', 'pdn', 'personaldata', 'spam', 'phishing',
    'postmaster', 'webmaster', 'hostmaster', 'dmarc', 'dkim')
# короткие имена, которые нельзя искать по началу — только целиком
_SLUZHEBNYE_TOCHNO = ('sb', 'ssb', 'kb')


# Зоны, которые встречаются у живых российских компаний. Проверка нужна, потому что
# краул парсит вложения как текст и выкусывает из бинарной каши псевдоадреса:
# на живом сайте так появился h0iprl@nn.zz (из shtaket-rasprodazha.docx).
_ZHIVYE_ZONY = ('ru', 'com', 'net', 'org', 'su', 'рф', 'by', 'kz', 'ua', 'pro', 'info',
                'biz', 'io', 'me', 'online', 'site', 'store', 'tech', 'group', 'company',
                'moscow', 'spb', 'travel', 'name', 'edu', 'gov', 'int', 'mil', 'tv', 'cc',
                'de', 'fr', 'it', 'es', 'pl', 'cz', 'fi', 'se', 'no', 'nl', 'be', 'ch',
                'at', 'uk', 'us', 'cn', 'jp', 'kr', 'in', 'tr', 'ae', 'am', 'ge', 'uz',
                'kg', 'tj', 'md', 'lv', 'lt', 'ee')


# Технические поддомены, а не домены: список выше сверяется по меткам целиком и
# «sentry.io» не ловит ни sentry.mos.ru, ни sentry.spectrumdata.tech — это DSN
# системы слежения за ошибками, которую вёрстка держит прямо в разметке. В
# выгрузке 14.08 такие уехали в контакты предприятий (20 адресов), а у АО «УЭХК»
# лучшим контактом оказался dmca@telegram.org с ролью «гл.энергетик».
_TEHNICHESKIE_PODDOMENY = re.compile(
    r'(?:^|\.)(?:sentry|jivosite|jivo|bitrix24|cloudflare|sendgrid|mailchimp|amazonses)'
    r'[.\-]', re.I)
# площадки, где адрес принадлежит САМОЙ площадке, а не предприятию
# ya.ru СЮДА НЕЛЬЗЯ: это почтовый домен Яндекса, на нём сидят живые компании
# (sarmat-159@ya.ru — реальный контакт, снесённый моей же чисткой 14.08 и
# восстановленный из журнала). Площадка — это домен, где адрес принадлежит
# самой площадке, а не предприятию.
_PLOSHCHADKI = ('telegram.org', 't.me', 'vk.company', 'timeweb.tech')


def _is_junk_email(e):
    """True — адрес НЕ контакт компании: домен платформы-конструктора/сервиса или noreply."""
    el = (e or '').lower().strip()
    _d = el.partition('@')[2]
    if _d and (_TEHNICHESKIE_PODDOMENY.search(_d) or _d in _PLOSHCHADKI):
        return True
    if '@' not in el or el.endswith(_IMG_EXT):
        return True
    _zona = el.rsplit('.', 1)[-1] if '.' in el.split('@')[-1] else ''
    if _zona not in _ZHIVYE_ZONY:
        return True
    local, _, dom = el.partition('@')
    # по меткам домена, а не подстрокой: «nic.ru» из списка совпадал внутри
    # technic.ru / mechanic.ru, «reg.ru» — внутри stroyreg.ru, и живой
    # корпоративный адрес выбрасывался до всякого извлечения
    if _dom_hits(dom, _JUNK_EMAIL_DOMAINS):
        return True
    if any(local.startswith(j) for j in _JUNK_EMAIL_LOCAL):
        return True
    # ТОЧНЫЕ короткие имена сверяем целиком, длинные — по началу. Иначе «sb»
    # съедает sbyt@/sbut@/sbit@/sbo- — это СБЫТ, то есть отдел продаж, ровно те,
    # кому мы и пишем (поймано на 256 отброшенных 14.08, из них четыре таких).
    if local in _SLUZHEBNYE_TOCHNO or any(
            local.startswith(j) for j in _SLUZHEBNYE_YASHCHIKI):
        return True
    return False


# Приоритет ролей для холодного письма — ниже индекс = лучше. Объявлен в
# промпте разбора сайта, но применяется КОДОМ (задача 57): свободный ответ
# модели этот порядок регулярно нарушал.
# Решение владельца 29.07: ТЕХНИЧЕСКИЕ ЛПР ВЫШЕ ЗАКУПОК. По компрессорам
# выбор делает служба главного инженера/энергетика, снабжение только оформляет
# уже принятое решение — письмо снабженцу приходит на готовое ТЗ конкурента.
# Порядок общий для почт и телефонов; канон имён ролей — enrich_db._ROLE_CANON.
_ROLE_RANK = {
    # Верх — решение владельца 05.08: «инженера главного ставьте первым».
    'гл.инженер': 0, 'гл.энергетик': 1, 'гл.механик': 2, 'техдиректор': 3,
    # Состав по линзе 02 (lens-02-roles.md): роли, которых в каноне не было.
    'нач.КС': 4, 'дир.эксплуатации': 5, 'зам.гл.мех/энерг': 6, 'нач.ОГМ': 7,
    'инж.надёжности': 8, 'нач.РМЦ': 9,
    'нач.производства': 10, 'гл.технолог': 11, 'нач.цеха': 12, 'АСУ/КИПиА': 13,
    'гл.конструктор': 14, 'техконтакт': 15, 'инженер (не главный)': 16,
    # НИЗ РАЗВЕДЁН ЯВНО. 05.08 мой сдвиг парами (16→17, 17→18 …) каскадом
    # прогнал все семь нижних ролей в одно число 23: снабжение сравнялось с
    # бухгалтерией и общим, и письмо уходило в бухгалтерию вместо закупок.
    # Поэтому словарь пишется ЦЕЛИКОМ и правится только целиком.
    'снабжение/закупки': 17, 'директор': 18, 'продажи': 19, 'приёмная': 20,
    # ОБЩИЙ ВЫШЕ КАДРОВ И БУХГАЛТЕРИИ (проверка агентами 12.08). Было наоборот, и
    # у Сергиево-Посадского мясокомбината для холодного письма про компрессоры
    # выбрался kadry@spmk.ru при живом info@spmk.ru. Логика: общий ящик компании
    # хотя бы попадёт к секретарю, который переправит; кадры и бухгалтерия — тупик
    # и вдобавок повод пометить письмо спамом. Они остаются в шкале (роль надо
    # уметь НАЗВАТЬ), но для выбора адресата стоят ниже общего.
    'общий': 21, 'бухгалтерия': 22, 'кадры': 23,
    # Начальник ОТ и ПБ на компрессорной — частый согласующий, а канон его не знал:
    # «Начальник отдела охраны труда, промышленной и пожарной безопасности» падал
    # в «общий» (поймано на osoran.com). Ставим рядом с техконтактом.
    'охрана труда/ПБ': 15}
# роль, которой нет в таблице, не должна случайно обойти известные
# ЗАСЛОН ПРОТИВ СИРОТ. Роль, которую канон умеет вернуть, ОБЯЗАНА иметь ранг.
# Трижды за неделю бывало иначе: `гл.конструктор`, `техконтакт`,
# `инженер (не главный)` канон возвращал, а шкала о них не знала, и адрес молча
# уходил в фолбэк «неизвестной» — 185 адресов, из них 105 технических.
# Пока это держится на внимательности, сироты будут заводиться снова: добавить
# правило в канон и забыть строку в шкале — одно движение.
# Недостающие роли добираются САМИ и встают ЧУТЬ ВЫШЕ «общего»: наверх молча
# никто не попадёт, но и ниже честного info@ новая роль не провалится.
try:
    import enrich_db as _EDB_rank
    _РОЛИ_КАНОНА = {r for _, r in getattr(_EDB_rank.EnrichDB, '_ROLE_CANON', ())}
    _СИРОТЫ = sorted(_РОЛИ_КАНОНА - set(_ROLE_RANK))
    for _с in _СИРОТЫ:
        _ROLE_RANK[_с] = _ROLE_RANK['общий'] - 1
except Exception:  # noqa: BLE001
    _СИРОТЫ = []

_ROLE_RANK_MISS = 99
# та же шкала — одной строкой для промпта извлечения (порядок = приоритет)
_ROLES_FOR_PROMPT = '|'.join(sorted(_ROLE_RANK, key=_ROLE_RANK.get))


def _norm_phone_roles(raw):
    """Ответ модели по телефонам -> (список словарей, список голых строк).

    Два формата живут одновременно: до 29.07 модель отдавала телефоны голыми
    строками, теперь — объектами с ролью. Принимаем оба, иначе один устаревший
    ответ терял бы все номера компании. Голые строки возвращаем ОТДЕЛЬНО:
    ими кормится companies.phones и старые отчёты, где ждут список строк.
    """
    out = []
    for p in (raw or []):
        if isinstance(p, dict):
            num = str(p.get('phone') or p.get('number') or '').strip()
            rec = {'phone': num,
                   'role': str(p.get('role') or '').strip(),
                   'person': str(p.get('person') or '').strip(),
                   'dept': str(p.get('dept') or '').strip()}
        elif p:
            rec = {'phone': str(p).strip(), 'role': '', 'person': '', 'dept': ''}
        else:
            continue
        if rec['phone']:
            out.append(rec)
    return out[:12], [r['phone'] for r in out[:12]]


_НЕ_ЧЕЛОВЕК = re.compile(
    r'^\s*(?:отдел|служба|управлени|департамент|дирекци|сектор|бюро|группа|'
    r'респ\b|обл\b|край\b|г\.|город|филиал|ооо|оао|зао|пао|ао\b|ип\b|'
    r'приёмная|приемная|бухгалтери|секретар)', re.I)



# --- РОЛЬ ПО ОКРУЖЕНИЮ АДРЕСА (правило, а не вера модели) --------------------------
# Две проверки на живом потоке (13.08, 347 компаний со страницами):
#   * поставленные роли верны в 90% — но 38 выдуманы там, где рядом СПИСОК отделов,
#     а адрес один: модель цепляет ближайший отдел («manager_icm@» -> техконтакт при
#     соседях «снабжение, логистика, контроль качества»);
#   * пропусков БОЛЬШЕ, чем выдумок: 92 адреса получили «общий», хотя рядом стояла
#     ровно одна должность. Среди потерянных — три главных инженера.
# Механизм у обеих бед один: сколько РАЗНЫХ должностей стоит рядом с адресом.
# Поэтому правим правилом: 0 -> общий, 1 -> эта роль, >=3 -> общий (не гадаем),
# 2 -> оставляем ответ модели, если он среди найденных.
_ROL_PRIZNAKI = [
    (re.compile(r'главн\w+ инженер', re.I), 'гл.инженер'),
    (re.compile(r'главн\w+ энергетик', re.I), 'гл.энергетик'),
    (re.compile(r'главн\w+ механик', re.I), 'гл.механик'),
    (re.compile(r'техническ\w+ директор', re.I), 'техдиректор'),
    (re.compile(r'начальник\w* производств|директор по производств', re.I), 'нач.производства'),
    (re.compile(r'отдел\w* снабжен|отдел\w* закупок|снабжени|закупк|тендерн', re.I), 'снабжение/закупки'),
    (re.compile(r'отдел\w* продаж|менеджер по продаж|сбыт|коммерческ\w+ директор', re.I), 'продажи'),
    (re.compile(r'генеральн\w+ директор|руководител\w+ предприятия', re.I), 'директор'),
    (re.compile(r'главн\w+ бухгалтер|бухгалтери', re.I), 'бухгалтерия'),
    (re.compile(r'отдел\w* кадров|по персоналу|подбор персонала', re.I), 'кадры'),
    (re.compile(r'секретар|приемн\w+|приёмн\w+', re.I), 'приёмная'),
    (re.compile(r'сервисн\w+ (?:служб|отдел|центр)|техническ\w+ (?:служб|поддержк)', re.I), 'техконтакт'),
]



# --- РОЛЬ ИЗ ИМЕНИ ЯЩИКА (последний источник, когда на странице её нет) ------------
# Владелец открыл bkzt.ru/contacts глазами (13.08) и показал то, чего не видно ни
# модели, ни судье: названия отделов там НАРИСОВАНЫ КАРТИНКАМИ. «ОТДЕЛ СНАБЖЕНИЯ»,
# «ОТДЕЛ ПРОДАЖ», «ОТДЕЛ КАДРОВ» — это jpg в рамке, а в тексте страницы только
# «Свяжитесь с нами», телефон и почта. Проверил alt картинок — там тоже
# «Свяжитесь с нами». То есть текстового источника роли не существует вовсе, и
# единственное, что её несёт, — само имя ящика: snab@, sale@, kadry@.
# Поэтому правило применяется ТОЛЬКО когда роль пуста или «общий»: подсказка
# страницы всегда сильнее подсказки адреса.
_ROL_PO_YASHCHIKU = [
    (re.compile(r'^(snab|snabzhenie|zakup|zakupki|purchase|procurement|tender|'
                r'mto|omts)\b'), 'снабжение/закупки'),
    (re.compile(r'^(sale|sales|prodazh|prodaji|sbyt|zakaz|order|opt|manager|'
                r'commerce|kommerc)\b'), 'продажи'),
    (re.compile(r'^(buh|buhg|buhgalter|glavbuh|account|finance|fin)\b'), 'бухгалтерия'),
    (re.compile(r'^(kadr|kadry|hr|personal|rabota|vacancy|job|career)\b'), 'кадры'),
    (re.compile(r'^(sekretar|secretar|priemn|reception|office)\b'), 'приёмная'),
    (re.compile(r'^(service|servis|support|tech|texn|tehn|remont)\b'), 'техконтакт'),
    (re.compile(r'^(director|direktor|gendir|ceo|dir)\b'), 'директор'),
    (re.compile(r'^(glaving|glavniy_inzhener|chief_eng)\b'), 'гл.инженер'),
    (re.compile(r'^(energetik|glavenergo)\b'), 'гл.энергетик'),
]


def rol_iz_imeni_yashchika(email):
    """Роль по локальной части адреса. Пусто — значит не опознали, и это нормально."""
    mesto = str(email or '').split('@')[0].lower()
    mesto = re.sub(r'[._-]+', '_', mesto).strip('_')
    for rx, imya in _ROL_PO_YASHCHIKU:
        if rx.match(mesto):
            return imya
    return ''


def utochnit_roli_po_stranice(emails, tekst, okno=500):
    """Уточнить роли по окружению адреса на странице. Возвращает (список, счётчики)."""
    if not tekst or not emails:
        return emails, {}
    t = re.sub(r'\s+', ' ', str(tekst)).lower().replace('ё', 'е')
    schet = {'поставили_по_странице': 0, 'сбросили_в_общий': 0, 'оставили': 0,
             'адреса_нет_на_странице': 0}
    for e in emails:
        adr = str(e.get('email') or '').lower()
        if not adr:
            continue
        mest = [m.start() for m in re.finditer(re.escape(adr), t)]
        if not mest:
            schet['адреса_нет_на_странице'] += 1
            continue
        okr = ''
        for poz in mest[:3]:
            okr += ' ' + t[max(0, poz - okno):poz + okno]
        nashli = []
        for rx, imya in _ROL_PRIZNAKI:
            if rx.search(okr) and imya not in nashli:
                nashli.append(imya)
        bylo = (e.get('role') or '').strip()
        obshchiy_yashchik = bool(re.match(
            r'(info|mail|office|zakaz|order|sale|shop|post|adm|reception|'
            r'secretar|priem|contact|kontakt)', adr.split('@')[0]))
        # СТАВИТЬ роль по окружению НЕЛЬЗЯ — проверено глазами на живых
        # перестановках: 4 ошибки из 8. Окно в 500 знаков захватывает соседние
        # карточки людей, и должность приклеивается к чужому адресу:
        # i.starikova@engso.ru получила «нач.производства», хотя Старикова —
        # старший менеджер, а начальник производства это СЛЕДУЮЩИЙ человек в
        # списке; azn33@mail.ru стал «директором», стоя под начальником отдела
        # маркетинга. Это тот же дефект, который мы ловим у модели, только без
        # её здравого смысла. Оставляем ТОЛЬКО сброс — он проверяем и безопасен.
        if (len(nashli) >= 3 and obshchiy_yashchik and bylo
              and bylo != 'общий'):
            # ОДИН ОБЩИЙ ящик среди списка отделов: модель цепляет ближайший отдел
            # и выдумывает роль. Именные ящики не трогаем — там должность читается
            # верно, и первая версия правила снесла 183 годные роли на страницах
            # сотрудников (kravchenkoaa@ «директор» -> «общий»). Своя ошибка дороже.
            e['role'] = 'общий'
            schet['сбросили_в_общий'] += 1
        elif not bylo or bylo == 'общий':
            # страница молчит — пробуем имя ящика (у БКЗТ отделы нарисованы картинками)
            po_imeni = rol_iz_imeni_yashchika(adr)
            if po_imeni:
                e['role'] = po_imeni
                schet['по_имени_ящика'] = schet.get('по_имени_ящика', 0) + 1
            else:
                schet['оставили'] += 1
        else:
            schet['оставили'] += 1
    return emails, schet


_ФИО_МУСОР = re.compile(
    r'отдел|направлен|служб|департамент|контакт на сайте|единственн|приёмн|приемн|'
    r'бухгалтер|снабжен|закупк|менеджер по|горячая лин|техподдержк|не указан|'
    r'неизвест|н/д|нет данных', re.I)


def _chistoe_fio(znachenie, tekst_stranicy='', email='', istochnik=''):
    """ФИО для приветствия: либо чистое имя, либо пусто. Полумер не бывает.

    Два правила, оба из замера 13.08 на 4000 записей:
      1. Скобки и пояснения СРЕЗАЕМ, а если после этого остался не человек —
         возвращаем пусто. В базе лежало «Отдел детского направления»,
         «Озерова (отдел экспорта)», «Бикмуллин Рамиль Камилевич (директор —
         единственный контакт на сайте)». Такое уходит прямо в приветствие.
      2. Фамилия ОБЯЗАНА встречаться на странице (владелец: «она в принципе
         должна быть на странице»). Иначе это чужой человек, приклеенный к
         адресу: bikkuzinaym@bashneft.ru -> «Пантюшина Ю.М».
    """
    s = ' '.join(str(znachenie or '').split())
    if not s:
        return ''
    s = re.sub(r'\s*[\(\[].*?[\)\]]\s*', ' ', s)          # пояснения в скобках
    s = re.sub(r'\s*[-—–]\s*.*$', '', s)                   # хвост через тире
    s = ' '.join(s.split())
    if not s or _ФИО_МУСОР.search(s) or not _pohozh_na_cheloveka(s):
        return ''
    # ЕСЛИ ИМЯ СОГЛАСОВАНО С АДРЕСОМ — оставляем без всяких страниц. voronin.av@,
    # khalin-vv@, senchaav@ несут фамилию прямо в ящике; первый заход обнулил их
    # заодно со всеми и снёс 1323 годные записи. Своя ошибка дороже чужой.
    if _fio_iz_yashchika(s, email):
        return s
    # Страничная сверка — ТОЛЬКО для контактов, взятых с САЙТА. У справочниковых
    # почт страницы сайта не было вовсе, и требовать там фамилию бессмысленно.
    if tekst_stranicy and (not istochnik or _s_sayta_li(istochnik)):
        chasti = [c for c in re.split(r'[\s.]+', s) if len(c) > 3]
        familiya = chasti[0] if chasti else ''
        if familiya:
            # ищем без окончания: на странице фамилия бывает в другом падеже
            koren = familiya.lower().replace('ё', 'е')[:-1]
            if koren and koren not in tekst_stranicy.lower().replace('ё', 'е'):
                return ''
    return s


# Транслитерация ТЕРПИМАЯ: у одной буквы бывает два-три написания, и строгая
# таблица давала ложные «не сходится» (solokhin/solohin, zhiljaeva/zhilyaeva).
_TRANSLIT = {'а': ['a'], 'б': ['b'], 'в': ['v', 'w'], 'г': ['g'], 'д': ['d'],
             'е': ['e', 'ye', 'je'], 'ё': ['e', 'yo', 'jo'], 'ж': ['zh', 'j', 'g'],
             'з': ['z'], 'и': ['i', 'y'], 'й': ['y', 'i', 'j'], 'к': ['k', 'c'],
             'л': ['l'], 'м': ['m'], 'н': ['n'], 'о': ['o'], 'п': ['p'], 'р': ['r'],
             'с': ['s', 'c'], 'т': ['t'], 'у': ['u'], 'ф': ['f'],
             'х': ['h', 'kh', 'x'], 'ц': ['c', 'ts', 'tc'], 'ч': ['ch'],
             'ш': ['sh'], 'щ': ['sch', 'shch'], 'ъ': [''], 'ы': ['y', 'i'],
             'ь': [''], 'э': ['e'], 'ю': ['yu', 'ju', 'u'], 'я': ['ya', 'ja', 'a']}


def _fio_iz_yashchika(fio, email):
    """Фамилия из ФИО читается в имени ящика? Тогда имя подтверждено адресом."""
    if not email or '@' not in str(email or ''):
        return False
    yashchik = re.sub(r'[^a-z]', '', str(email).split('@')[0].lower())
    if len(yashchik) < 4:
        return False
    chasti = [c for c in re.split(r'[\s.]+', fio) if len(c) > 3]
    if not chasti:
        return False
    familiya = chasti[0].lower().replace('ё', 'е')
    # строим все правдоподобные латинские написания первых пяти букв
    varianty = ['']
    for ch in familiya[:5]:
        hvosty = _TRANSLIT.get(ch, [ch])
        varianty = [v + h for v in varianty for h in hvosty][:64]
    return any(v and v in yashchik for v in varianty)


def _s_sayta_li(istochnik):
    s = str(istochnik or '').lower()
    return 'site' in s or 'сайт' in s or s == 'zenno' or 'own-site' in s


def _pohozh_na_cheloveka(знач):
    """ФИО ли это. Одного слова мало: «Ирина» из подписи письма человеком не делает.

    72 записи из 5 341 в `emails.person` — не люди: отделы, регионы, одно имя.
    Ключ Р-004 опирается на это, поэтому проверка живёт рядом с ним, а не в
    голове у того, кто правило писал.
    """
    с = ' '.join(str(знач or '').split())
    if len(с) < 5 or _НЕ_ЧЕЛОВЕК.match(с):
        return False
    части = [ч for ч in с.split() if len(ч) > 1]
    return len(части) >= 2


# --------------------------------------------------------------------------
# НАДЁЖНОЕ ИМЯ (владелец: «надёжные имена контактов»). Именное приветствие
# «Здравствуйте, Иван Петрович» бьёт по репутации сильнее, чем помогает, если
# имя взято не из первых рук. В базе 8 423 записи с именем, и 1 836 из них — из
# ЧУЖИХ сборников: справочники 713, zakupki:eis 619, tender.pro 504. Там имя
# могло устареть на годы или относиться к другому юрлицу с тем же адресом.
# Имя считаем пригодным для приветствия, только если выполнено ВСЁ:
#   1) источник — НАШ обход сайта компании (а не сборник и не доска вакансий);
#   2) есть ссылка на страницу, где имя стояло — иначе проверить нечем;
#   3) это похоже на ФИО (две части, не отдел, не регион, не форма собственности).
_IMYA_ISTOCHNIKI = ('own-site', 'enrich', 'mass', 'panel-run', 'recheck', 'top1000',
                    'сайт:обход', 'сайт:руководство', 'pereobhod')
_IMYA_CHUZHIE = ('checko', 'справочник', 'zakupki', 'tender', 'вакансии', 'hh',
                 'news', 'sales-base', 'база обзвона')


def imya_nadezhno(source, person, source_url=''):
    """Можно ли обращаться к человеку по имени. Все три условия обязательны."""
    ist = str(source or '').lower()
    if not ist or any(m in ist for m in _IMYA_CHUZHIE):
        return False
    if not any(ist.startswith(m) or m in ist for m in _IMYA_ISTOCHNIKI):
        return False
    if not str(source_url or '').strip():
        return False
    return _pohozh_na_cheloveka(person)


_FREEMAIL_DOM = ('mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
                 'inbox.ru', 'rambler.ru', 'internet.ru', 'mail.com', 'icloud.com',
                 'outlook.com', 'hotmail.com')


# ---------------------------------------------------------------------------
# СВЕРКА РЕГИОНА (12.08). Проверка агентами показала: чаще всего чужой сайт выдаёт
# себя не именем, а географией — у «ГСМ» ИНН 7204 (Тюмень), а на странице юрадрес
# «350022, Краснодар»; у «ТехСтройИнвеста» ИНН 0276 (Уфа), сайт про Чехов и Подольск.
# Проверка дешёвая: первые две цифры ИНН = код субъекта, на странице есть город,
# индекс и телефонный код. Это СИГНАЛ, а не приговор: филиалы и переезды бывают,
# поэтому расхождение лишь понижает доверие к вердикту модели, но ничего не удаляет.
_KOD_REGIONA = {
    '01': 'адыге', '02': 'башкорт|уф[аы]', '03': 'бурят|улан-удэ', '04': 'алтай|горно-алтайск',
    '05': 'дагестан|махачкал', '06': 'ингушет|магас', '07': 'кабардино|нальчик',
    '08': 'калмык|элист', '09': 'карачаево|черкесск', '10': 'карел|петрозаводск',
    '11': 'коми|сыктывкар', '12': 'марий|йошкар', '13': 'мордов|саранск',
    '14': 'саха|якут', '15': 'осети|владикавказ', '16': 'татарстан|казан|челны',
    '17': 'тыва|кызыл', '18': 'удмурт|ижевск', '19': 'хакас|абакан', '20': 'чечен|грозн',
    '21': 'чуваш|чебоксар', '22': 'алтайск|барнаул|бийск', '23': 'краснодар|сочи|новороссийск',
    '24': 'краснояр', '25': 'приморск|владивосток', '26': 'ставропол|пятигорск',
    '27': 'хабаровск|комсомольск', '28': 'амурск|благовещенск', '29': 'архангельск|северодвинск',
    '30': 'астрахан', '31': 'белгород|старый оскол', '32': 'брянск', '33': 'владимир|ковров',
    '34': 'волгоград|волжск', '35': 'вологод|череповец', '36': 'воронеж', '37': 'иванов',
    '38': 'иркутск|ангарск|братск', '39': 'калининград', '40': 'калуж|обнинск',
    '41': 'камчат|петропавловск', '42': 'кемеров|кузбасс|новокузнецк', '43': 'киров',
    '44': 'костром', '45': 'курган', '46': 'курск', '47': 'ленинградск|гатчин|выборг',
    '48': 'липецк', '49': 'магадан', '50': 'московск|подольск|мытищ|химк|балаших|люберц',
    '51': 'мурманск', '52': 'нижегородск|нижний новгород|дзержинск|арзамас',
    '53': 'новгородск|великий новгород', '54': 'новосибирск', '55': 'омск', '56': 'оренбург',
    '57': 'орлов|орёл|орел', '58': 'пензен', '59': 'пермск|пермь', '60': 'псков',
    '61': 'ростов|таганрог|шахты', '62': 'рязан', '63': 'самар|тольятти|сызран',
    '64': 'саратов|энгельс', '65': 'сахалин|южно-сахалинск', '66': 'свердловск|екатеринбург|нижний тагил',
    '67': 'смоленск', '68': 'тамбов', '69': 'тверск|тверь', '70': 'томск', '71': 'тульск|тула',
    '72': 'тюмен', '73': 'ульяновск', '74': 'челябинск|магнитогорск|миасс', '75': 'забайкал|чита',
    '76': 'ярославск|ярославль|рыбинск', '77': 'москв', '78': 'петербург|спб', '79': 'еврейск|биробиджан',
    '83': 'ненецк|нарьян', '86': 'ханты|югра|сургут|нижневартовск', '87': 'чукот|анадырь',
    '89': 'ямал|новый уренгой|ноябрьск', '91': 'крым|симферопол', '92': 'севастопол',
    '99': 'москв',
}
_KOD_TELEFONA = {
    '495': '77', '499': '77', '498': '50', '812': '78', '831': '52', '343': '66',
    '383': '54', '846': '63', '843': '16', '351': '74', '863': '61', '473': '36',
    '381': '55', '391': '24', '342': '59', '861': '23', '844': '34', '3452': '72',
    '3412': '18', '4012': '39', '8452': '64', '4852': '76', '3822': '70', '4212': '27',
}


_RODNYA = ({'77', '50', '97', '99'},      # Москва и Московская область
           {'78', '47'},                  # Санкт-Петербург и Ленинградская область
           {'23', '93'},                  # Краснодарский край
           {'66', '96'}, {'74', '75'}, {'16', '116'}, {'02', '102'})


def _rodnya(a, b):
    return any(a in gr and b in gr for gr in _RODNYA)


_INDEKS_RE = re.compile(r'\b\d{6}\b')


def _adresnye_okna(niz, radius=90):
    """Куски текста ВОКРУГ ПОЧТОВОГО ИНДЕКСА — то есть настоящие адреса, а не витрина.

    Замер 12.08 на 360 живых страницах, три правила на одном и том же тексте:
      * искать чужой регион по ВСЕМУ тексту — 8 ошибок на 120 доказанно своих сайтов
        (6,7%) при 35 попаданиях на 120 чужих (29,2%);
      * рядом с «г./город/пгт» — 4 ошибки (3,3%) при 20 попаданиях (16,7%);
      * ТОЛЬКО рядом с индексом — 2 ошибки (1,7%) при 15 попаданиях (12,5%).
    Ловит вдвое меньше, зато почти не портит верное — взят третий. Причина ошибок
    первых двух видна в разборе: «доставка по России: Казань, Киров, Москва» и
    «наши филиалы» — перечисления городов, к юридической прописке отношения не
    имеющие. Рядом с индексом стоит именно адрес."""
    return ' | '.join(niz[max(0, m.start() - radius):m.end() + radius]
                      for m in list(_INDEKS_RE.finditer(niz))[:60])


def _kod_po_regionu(region, adres=''):
    """Код субъекта по НАЗВАНИЮ региона из выгрузки: «Тюменская обл» -> '72'.

    Берём самое длинное совпадение, иначе «Московская обл» поймается шаблоном
    Москвы ('москв') и подмосковная фирма станет столичной.
    """
    niz = ' '.join(str(region or '').split()).lower() + ' ' + str(adres or '')[:120].lower()
    if not niz.strip():
        return ''
    luchshiy, dlina = '', 0
    for kod, shabl in _KOD_REGIONA.items():
        m = re.search(shabl, niz)
        if m and len(m.group(0)) > dlina:
            luchshiy, dlina = kod, len(m.group(0))
    return luchshiy


def region_sverka(inn, tekst, region='', adres=''):
    """Согласуется ли география страницы с регионом компании.

    Замечание владельца 12.08: код в ИНН — это регион ПОСТАНОВКИ НА УЧЁТ, а не место
    работы. Компания регистрируется в Москве и держит завод в Кемерове; при переезде
    ИНН не меняется вовсе. Поэтому ГЛАВНЫЙ источник — регион и адрес из выгрузки базы
    обзвона, а код ИНН остаётся запасным, когда их не передали.

    Возврат: 'сходится' | 'расходится' | 'расходится(слабо)' | 'не видно'.

    ЗАМЕР НА ЖИВЫХ СТРАНИЦАХ (12.08, 186 компаний из кэша обхода) — почему разделены
    сильное и слабое расхождение. Первая редакция решала «расходится» ВСЕГДА по коду
    ИНН, и все 15 срабатываний пришли именно оттуда. Против доказанных сайтов (ИНН
    компании найден на самой странице — сайт точно свой) это дало 3 ошибки на 52,
    5,8%; против сайтов, признанных чужими, — 3 на 22, 13,6%. Обогащение всего в 2,4
    раза: слишком слабо, чтобы что-то на этом понижать. Поэтому слабый канал теперь
    ЛИШЬ ПОМЕЧАЕТ ('расходится(слабо)'), а решение принимает канал базы — регион из
    выгрузки, у которого на тех же данных не было ни одной ошибки.
    """
    if not tekst:
        return 'не видно'
    niz = tekst.lower()[:20000]
    # 1) прямое сравнение с тем, что записано в базе: город и область из адреса
    slova = []
    for ist in (region, adres):
        for kus in re.split(r'[,;]', str(ist or '')):
            kus = re.sub(r'\b(обл|область|край|респ|республика|г|город|р-н|район|ул|улица|'
                         r'д|дом|стр|корп|пр-кт|проспект|пер|шоссе|влд|пом|оф|офис|этаж|кв)\b\.?',
                         ' ', kus.strip().lower())
            kus = re.sub(r'[^а-яё\- ]', ' ', kus).strip()
            for w in kus.split():
                if len(w) >= 5:
                    slova.append(w[:-2] if len(w) > 6 else w)
    if slova and any(w in niz for w in slova[:6]):
        return 'сходится'
    # 2) свой код субъекта: сначала по названию региона из базы, и лишь если базы
    #    не дали — по первым цифрам ИНН (регион учёта, а не работы)
    kod = _kod_po_regionu(region, adres)
    silno = bool(kod)                     # решает канал базы, ему и верим
    if not kod:
        kod = str(inn or '')[:2]
    shabl = _KOD_REGIONA.get(kod)
    if not shabl:
        return 'не видно'
    if re.search(shabl, niz):
        return 'сходится'
    for tk, reg in _KOD_TELEFONA.items():
        if re.search(r'[(+ ]' + tk + r'[) ]', niz) and reg == kod:
            return 'сходится'
    # чужой регион засчитываем ТОЛЬКО в адресном контексте (рядом с индексом):
    # иначе «доставка по России: Казань, Киров, Москва» выдаёт себя за прописку
    pole = _adresnye_okna(niz)
    chuzhie = [k for k, v in _KOD_REGIONA.items()
               if k != kod and not _rodnya(k, kod) and re.search(v, pole)]
    if not chuzhie:
        return 'не видно'
    return 'расходится' if silno else 'расходится(слабо)'


def _best_by_role(emails, model_pick=''):
    """Лучший адрес по порядку ролей: техЛПР > закупки > директор > продажи > общий.
    Ответ модели (model_pick) — только разрешение ничьей внутри одной роли."""
    rows = [e for e in (emails or [])
            if isinstance(e, dict) and (e.get('email') or '').strip()]
    if not rows:
        return model_pick or ''
    mp = (model_pick or '').strip().lower()

    def _key(e):
        raw = (e.get('role') or '').strip().lower()
        rank = _ROLE_RANK.get(raw)
        if rank is None:
            # Модель пишет роль вольно («гл. инженер», «отдел снабжения»), и
            # точное сравнение давало таким ранг хуже, чем «общему» — лучшим
            # адресом становился info@. Приводим к канону тем же правилом,
            # что и запись в базу.
            try:
                import enrich_db as _EDBr
                rank = _ROLE_RANK.get(_EDBr.EnrichDB._canon_role(raw))
            except Exception:  # noqa: BLE001
                rank = None
        # неизвестная роль — между конкретикой и «общим», а не хуже всех
        # Неизвестная роль. Р-004, ключ 2-й сессии: не форма адреса (она же
        # опровергла его своим числом — 297 и 163, и враньё внутри), а ФАКТ
        # записанного человека. Но не «person непустой»: 72 записи из 5 341 —
        # это отделы, регионы и ОДНО СЛОВО вместо ФИО («Респ Татарстан»,
        # «Ирина»). Ключ — «похож на человека»: минимум две части, не отдел,
        # не регион, не форма собственности.
        if rank is None:
            rank = (_ROLE_RANK['общий'] - 1 if _pohozh_na_cheloveka(e.get('person'))
                    else _ROLE_RANK['общий'] + 1)
        # Ничья по роли (12.08, проверка агентами): корпоративный ящик лучше
        # бесплатного — у «Энергоактива» рядом стояли sko@enactive.ru и
        # pokovka18@mail.ru. Доставляемость письма с корпоративного домена выше,
        # да и адрес переживёт смену человека.
        _adr = (e.get('email') or '').strip().lower()
        _dom = _adr.split('@')[-1]
        return (rank,
                0 if _adr == mp else 1,
                1 if _dom in _FREEMAIL_DOM else 0)

    return sorted(rows, key=_key)[0]['email']


# ---------------------------------------------------------------------------
# СТРУКТУРНЫЙ РАЗБОР СТРАНИЦЫ (владелец 11.08.2026: «название отдела бывает вообще
# не возле емейла»). Замер на 20 страницах-источниках подтвердил: заголовок раздела
# стоит от адреса на медиане 1142 знака, у 76% — дальше 250, то есть НИКАКИМ окном
# по знакам его не взять. При этом «взять ближайший заголовок выше» тоже не работает
# (+1% к покрытию): на живой странице последним перед адресом обычно оказывается
# «Контакты» или «Появились вопросы?», а настоящий «Отдел закупа сырья» остаётся
# выше по дереву. Отличить одно от другого можно только по СТРУКТУРЕ.
#
# Здесь стек тегов: для каждого адреса берём (1) блок-карточку — ближайшего блочного
# предка разумного размера, то есть ровно одного человека без соседей, и (2) заголовок
# СВОЕГО раздела — последний h1-h4/th/caption, закрывшийся до начала блока И висящий
# на одном из предков этого блока. Тогда «Отдел закупа сырья» прилипает к своим шести
# адресам, а «Появились вопросы?» из подвала — ни к одному.
from html.parser import HTMLParser as _HTMLParser

_BLOK_TEGI = {'tr', 'li', 'dd', 'td', 'article', 'div', 'section', 'p', 'figure',
              'blockquote', 'aside', 'main', 'table', 'tbody', 'ul', 'ol', 'dl', 'body',
              'footer', 'header', 'nav', 'form', 'fieldset'}
# контейнеры: годятся в ПРЕДКИ (по ним ищется раздел), но карточкой человека быть не
# могут — иначе «карточкой» станет вся страница, а вместе с ней и чужие разделы
_NE_KARTOCHKA = {'body', 'main', 'table', 'tbody', 'ul', 'ol', 'dl', 'form', 'nav'}
_ZAG_TEGI = {'h1', 'h2', 'h3', 'h4', 'h5', 'th', 'caption', 'legend', 'summary'}
_PROPUSK_TEGI = {'script', 'style', 'noscript', 'svg', 'template', 'iframe'}
# Заголовки, которые роли НЕ задают: «Контакты», «Появились вопросы?» и прочая навигация.
# Замер 11.08: такие прилипали к 15% адресов. Пустой раздел лучше ложного — модель не
# должна видеть слово «отдел» там, где его нет.
_MUSOR_RAZDEL = re.compile(
    r'^(контакт\w*|наши контакты|обратная связь|появились вопросы|остались вопросы|'
    r'напишите нам|свяжитесь с нами|меню|поиск|навигац\w*|главная|о компании|о нас|'
    r'новости|услуги|продукция|каталог|адрес\w*|реквизиты|как нас найти|карта сайта|'
    r'войти|корзина|подписка|соцсети|мы в соцсетях|информация|документы)\W*$', re.I)
# график работы, телефон, адрес — это не отдел. «Пн-Пт 08:00 - 17:00; Сб 08:00 - 14:00»
# прилипало разделом к контактам «Кровельных систем» (поймано проверкой 12.08).
_RASPISANIE = re.compile(
    r'(пн|вт|ср|чт|пт|сб|вс|понедельн|вторн|сред|четв|пятн|суббот|воскрес)\W{0,3}'
    r'(пт|сб|вс|\d)|\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}[:.]\d{2}|'
    r'^\+?\d[\d\s()\-]{8,}$|выходной', re.I)


class _Struktura(_HTMLParser):
    """HTML -> плоский текст + дерево элементов с границами в этом тексте."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.kuski = []
        self.dlina = 0
        self.stek = []        # индексы открытых элементов
        self.elementy = []    # {tag, nachalo, konec, rodit}
        self.zagolovki = []   # {tekst, konec, rodit}
        self._propusk = 0
        self._zhdu_pochtu = ''   # адрес из href — чтобы не записать его вторым разом

    def _pishi(self, s):
        if not s:
            return
        self.kuski.append(s)
        self.dlina += len(s)

    def handle_starttag(self, tag, attrs):
        if tag in _PROPUSK_TEGI:
            self._propusk += 1
            return
        if tag == 'br':
            self._pishi(' ')
            return
        if tag == 'a':
            # mailto/tel живут только в href — вносим их В ТЕКСТ, иначе адрес
            # не попадёт ни в карточку, ни в поиск по тексту
            for k, v in attrs:
                if k == 'href' and v:
                    vl = v.strip()
                    if vl.lower().startswith('mailto:'):
                        _adr = vl[7:].split('?')[0]
                        self._pishi(' ' + _adr + ' ')
                        self._zhdu_pochtu = _adr.strip().lower()
                    elif vl.lower().startswith('tel:'):
                        self._pishi(' ' + vl[4:] + ' ')
        if tag in _BLOK_TEGI or tag in _ZAG_TEGI:
            self.elementy.append({'tag': tag, 'nachalo': self.dlina, 'konec': None,
                                  'rodit': self.stek[-1] if self.stek else None,
                                  'idx': len(self.elementy)})
            self.stek.append(len(self.elementy) - 1)
        else:
            self._pishi(' ')

    def handle_endtag(self, tag):
        if tag == 'a':
            self._zhdu_pochtu = ''
        if tag in _PROPUSK_TEGI:
            self._propusk = max(0, self._propusk - 1)
            return
        if tag not in _BLOK_TEGI and tag not in _ZAG_TEGI:
            return
        # разметка бывает кривой: закрываем ближайший подходящий, лишние не трогаем
        for i in range(len(self.stek) - 1, -1, -1):
            if self.elementy[self.stek[i]]['tag'] == tag:
                for j in range(len(self.stek) - 1, i - 1, -1):
                    el = self.elementy[self.stek[j]]
                    if el['konec'] is None:
                        el['konec'] = self.dlina
                        if el['tag'] in _ZAG_TEGI:
                            t = ''.join(self.kuski)[el['nachalo']:el['konec']]
                            t = re.sub(r'\s+', ' ', t).strip()
                            if 2 < len(t) <= 160:
                                self.zagolovki.append({'tekst': t, 'konec': el['konec'],
                                                       'rodit': el['rodit']})
                del self.stek[i:]
                return

    def handle_data(self, d):
        if self._propusk:
            return
        if self._zhdu_pochtu and d.strip().lower() == self._zhdu_pochtu:
            self._zhdu_pochtu = ''    # текст ссылки повторяет её же href — не дублируем
            return
        self._pishi(d)

    def zakryt(self):
        for i in self.stek:
            if self.elementy[i]['konec'] is None:
                self.elementy[i]['konec'] = self.dlina
        self.stek = []
        return ''.join(self.kuski)


def karty_kontaktov(html, url='', cap_blok=700):
    """[{email, razdel, kartochka, url}] — по одной записи на адрес со страницы.

    razdel — заголовок раздела, которому адрес подчинён по дереву; kartochka — текст
    ближайшего блока разумного размера (одна строка таблицы / один пункт списка)."""
    if not html or len(html) > 3_000_000:
        return []
    try:
        pr = _Struktura()
        pr.feed(html)
        tekst = pr.zakryt()
    except Exception:  # noqa: BLE001
        return []
    if not tekst:
        return []
    elementy, zagolovki = pr.elementy, pr.zagolovki
    # элементы, годные в карточку: с текстом, но не гигантские
    kandidaty = [e for e in elementy
                 if e['konec'] is not None and e['tag'] not in _ZAG_TEGI
                 and e['tag'] not in _NE_KARTOCHKA
                 and 8 <= (e['konec'] - e['nachalo']) <= cap_blok]
    out, vidano = [], set()
    for m in EMAIL_RE.finditer(tekst):
        adr = m.group(0).lower()
        if adr in vidano or adr.endswith(_IMG_EXT):
            continue
        vidano.add(adr)
        # 1) КАРТОЧКА. Самый тесный блок не годится: в таблице это <td> с одним
        # адресом, а ФИО и «менеджер» лежат в соседних ячейках той же строки. Порог
        # по длине тоже не годится — короткая строка таблицы его не проходит, и блок
        # раздувается на всю страницу вместе с чужими людьми. Верный признак ровно
        # один: В КАРТОЧКЕ ДОЛЖЕН БЫТЬ ОДИН АДРЕС. Поднимаемся от самого тесного блока
        # вверх, пока адрес в блоке остаётся единственным; на первом блоке со вторым
        # адресом останавливаемся и берём предыдущий.
        svoi = [e for e in kandidaty if e['nachalo'] <= m.start() and e['konec'] >= m.end()]
        svoi.sort(key=lambda e: e['konec'] - e['nachalo'])
        blok = None
        for e in svoi:
            if len({x.lower() for x in EMAIL_RE.findall(tekst[e['nachalo']:e['konec']])}) > 1:
                break
            blok = e
        if blok is None and svoi:
            blok = svoi[0]      # даже в самом тесном блоке несколько адресов — берём его
        # 2) цепочка предков — по ней и определяем «свой» раздел
        predki = set()
        if blok:
            i = blok['idx']
            while i is not None:
                predki.add(i)
                i = elementy[i]['rodit']
            nachalo_bloka = blok['nachalo']
        else:
            nachalo_bloka = m.start()
            for i, e in enumerate(elementy):
                if e['konec'] is not None and e['nachalo'] <= m.start() <= e['konec']:
                    predki.add(i)
        # Заголовок «свой», если висит на одном из предков блока ИЛИ на самом блоке
        # (подвал: <footer><h3>Появились вопросы?</h3><p>info@...</p></footer> — заголовок
        # ВНУТРИ блока, и правило «закрылся до начала блока» его отбрасывало).
        podhod = [z for z in zagolovki
                  if z['konec'] <= m.start() and (z['rodit'] in predki or z['rodit'] is None)]
        razdel = ''
        for z in sorted(podhod, key=lambda z: -z['konec']):
            _t = z['tekst'].strip()
            if _MUSOR_RAZDEL.match(_t) or _RASPISANIE.search(_t):
                continue
            razdel = _t
            break
        kart = re.sub(r'\s+', ' ', tekst[blok['nachalo']:blok['konec']]).strip() if blok \
            else re.sub(r'\s+', ' ', tekst[max(0, m.start() - 120):m.end() + 120]).strip()
        out.append({'email': adr, 'razdel': razdel, 'kartochka': kart[:cap_blok],
                    'url': url})
    return out


def karty_v_tekst(karty, cap=6000):
    """Карточки -> блок для провайдера. Каждая строка — один контакт с его разделом."""
    if not karty:
        return ''
    stroki, dl = [], 0
    for k in karty:
        s = '· %s%s — %s' % (
            ('[раздел: %s] ' % k['razdel']) if k.get('razdel') else '',
            k['email'], (k.get('kartochka') or '')[:300])
        if dl + len(s) > cap:
            break
        stroki.append(s)
        dl += len(s)
    return ('[КАРТОЧКИ КОНТАКТОВ СО СТРАНИЦ: под каждым адресом — раздел сайта, '
            'которому он подчинён, и его карточка целиком]\n' + '\n'.join(stroki)
            + '\n[КОНЕЦ КАРТОЧЕК] ')


def _harvest_from_html(blob, srcmap=None):
    """Достать email/телефоны из мест, которые не переживают вырезание тегов.
    srcmap (опц. dict) — помечает КАКИМ методом впервые найден каждый email
    (mailto/jsonld/deobf) для аналитики разметок; первый источник не перетираем."""
    emails, phones = set(), set()

    def _mark(e, method):
        if srcmap is not None and e not in srcmap:
            srcmap[e] = method
    for m in _MAILTO_RE.findall(blob or ''):
        e = m.split('?')[0].strip().lower()
        if EMAIL_RE.fullmatch(e) and not e.endswith(_IMG_EXT):
            emails.add(e)
            _mark(e, 'mailto')
    for t in _TEL_RE.findall(blob or ''):
        d = re.sub(r'\D', '', t)
        if 10 <= len(d) <= 12:
            phones.add(d)
    for js in _JSONLD_RE.findall(blob or ''):
        for e in EMAIL_RE.findall(js):
            if not e.lower().endswith(_IMG_EXT):
                emails.add(e.lower())
                _mark(e.lower(), 'jsonld')
        for t in re.findall(r'"telephone"\s*:\s*"([^"]+)"', js):
            d = re.sub(r'\D', '', t)
            if 10 <= len(d) <= 12:
                phones.add(d)
    # деобфускация: 'deobf' помечаем ТОЛЬКО email, которых в сыром тексте НЕ было,
    # а после разворачивания [at]/(точка)/&#64; появились (иначе обычные email ложно = deobf).
    raw_text = re.sub(r'<[^>]+>', ' ', blob or '')
    raw_found = set(e.lower() for e in EMAIL_RE.findall(raw_text))
    deob = raw_text
    for rx, rep in _DEOBF:
        deob = rx.sub(rep, deob)
    for e in EMAIL_RE.findall(deob):
        el = e.lower()
        if not el.endswith(_IMG_EXT):
            if el not in raw_found and el not in emails:
                _mark(el, 'deobf')
            emails.add(el)
    emails = {e for e in emails if not _is_junk_email(e)}   # отсев платформенных/noreply
    return emails, phones


def _PACE(a=6.0, b=14.0):
    return random.uniform(a, b)


def _domain(url):
    m = re.match(r'https?://([^/]+)', url or '')
    # lstrip('www.') снимал ЛЮБЫЕ символы из набора «w», «.» — westgroup.ru
    # превращался в estgroup.ru, wodokanal.ru в odokanal.ru. Все относительные
    # ссылки строятся как http://{dom}{путь}, поэтому у таких сайтов обход
    # уходил на несуществующий хост и до контактов не доходил вовсе.
    return re.sub(r'^www\.', '', (m.group(1) if m else '').lower())


def site_domain(site):
    """Домен из значения companies.site, где схемы обычно НЕТ.

    _domain требует «http://» и на голом «cryogenmash.ru» отдаёт пустоту. По
    коду это уже обходили вручную в десятке мест выражением
    `_domain(s if s.startswith('http') else 'http://' + s)`, а где забыли —
    получали тихий ноль: способ А8 (схема почты) отчитался «схема не выведена
    ни у одной компании», хотя на деле у ВСЕХ сорока доменом оказалась пустая
    строка. Отдельная функция, чтобы забыть было негде.
    """
    s = str(site or '').strip()
    if not s:
        return ''
    if not s.startswith(('http://', 'https://')):
        s = 'http://' + s
    return _domain(s)


_ОПФ_ПОЛНАЯ = re.compile(
    r'^\s*(?:(?:ПУБЛИЧНОЕ|НЕПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ)\s+)?'
    r'(?:АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ'
    r'|ПРОИЗВОДСТВЕННЫЙ\s+КООПЕРАТИВ|ГОСУДАРСТВЕННОЕ\s+УНИТАРНОЕ\s+ПРЕДПРИЯТИЕ'
    r'|МУНИЦИПАЛЬНОЕ\s+(?:\w+\s+)?ПРЕДПРИЯТИЕ|АКЦИОНЕРНАЯ\s+КОМПАНИЯ)'
    r'(?:\s+(?:ФИРМА|КОМПАНИЯ|ЗАВОД|КОМБИНАТ))?\s*', re.I)
_ОПФ_КРАТКАЯ = re.compile(r'^(?:ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|КАО|ГК|НПО|НПП|ФГУП|'
                          r'ГУП|МУП|АК|ПК)\s+', re.I)


def hh_страница_наша(html, company):
    """Страница hh относится ИМЕННО к этой компании?

    Проверка появилась после реального промаха: по бренду «Криогенмаш»
    запасной путь открыл работодателя «Завод Химического и Криогенного
    машиностроения» из Екатеринбурга, и шесть телефонов его кадровиков были
    записаны АО «Криогенмаш» из Балашихи. Названия делят слово «криоген», так
    что совпадение по КОРНЮ ничего не доказывает.

    Считаем доказательством только жёсткие признаки: ИНН компании на странице
    либо домен её сайта. Если их нет — принимаем лишь ПОЛНОЕ совпадение
    бренда с названием работодателя, а не вхождение куска.
    """
    h = html or ''
    if not h:
        return False, 'пусто'
    inn = str(company.get('inn') or '').strip()
    if inn and re.search(r'\b' + re.escape(inn) + r'\b', h):
        return True, 'инн на странице'
    d = site_domain(company.get('site') or '')
    if d and d in h:
        return True, 'домен сайта на странице'
    бренд = бренд_компании(company.get('name'), company.get('site')).lower()
    бренд = re.sub(r'[^0-9a-zа-яё]+', '', бренд)
    if len(бренд) < 4:
        return False, 'бренд слишком короткий'
    # У hh ключа "employer" НЕТ — работодатель лежит в "company":{"name":...}.
    # Прежняя регулярка возвращала пустоту, и рубеж рубил живые совпадения:
    # у ПАО «КАМАЗ» он отказал, потому что нашёл только плейсхолдер шаблона
    # «{0}» и имя с ОПФ. Сравниваем БРЕНДЫ, а не сырые строки.
    имена = re.findall(r'"(?:employer|company)"\s*:\s*\{[^{}]{0,300}?'
                       r'"name"\s*:\s*"([^"]{2,90})"', h)
    имена += re.findall(r'работа в компании ([^<"\n]{2,80})', h)
    for имя in имена[:8]:
        if '{0}' in имя or len(имя.strip()) < 3:
            continue          # плейсхолдер шаблона страницы, не работодатель
        если = re.sub(r'[^0-9a-zа-яё]+', '',
                      бренд_компании(имя, '').lower())
        if если == бренд:
            return True, 'название работодателя совпало полностью'
    return False, f'не подтверждено (нашли: {sorted(set(имена))[:2]})'


# Счётчик молчаливых отказов выдачи. Наружу его читает любой прогон, чтобы
# отличить «источник пуст» от «нас не пустили».
_СЕРП_ОТКАЗЫ = {'занято': 0, 'ошибка': 0, 'пусто': 0, 'ок': 0}


def _serp_urls(запрос, n=10, попыток=3):
    """Адреса из выдачи xmlriver. Вынесено из трёх копий одного и того же кода.

    РАНЬШЕ ОТКАЗ БЫЛ НЕОТЛИЧИМ ОТ ПУСТОТЫ, и это молча портило замеры. xmlriver
    на исчерпании лимита отвечает `<error>Заняты все доступные вам каналы</error>`
    кодом 200; тегов `<url>` в таком ответе нет, функция возвращала пустой
    список — ровно то же, что при честном «ничего не найдено». Предыдущая
    сессия поймала это на живых данных: шесть запросов из восьми были отказами,
    и дыра стоила времени дважды за один день.

    Теперь отказ виден: ретрай с паузой, счётчик наружу, и «пусто» отделено от
    «не пустили». Это частный случай общего правила — ноль надо доказывать так
    же тщательно, как находку.
    """
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return []
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(запрос))
    for попытка in range(попыток):
        _bump('xmlriver')
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
        except Exception:  # noqa: BLE001
            _СЕРП_ОТКАЗЫ['ошибка'] += 1
            time.sleep(2 * (попытка + 1))
            continue
        ош = re.search(r'<error[^>]*>(.*?)</error>', xml, re.S)
        if ош:
            текст = ош.group(1).strip()[:90]
            # «заняты все каналы» и «превышен лимит» — временные, ретраим.
            # Ловим по СМЫСЛУ, а не по точной фразе: прежний ретрай в соседнем
            # скрипте отлавливал одну формулировку и пропускал эту.
            if re.search(r'занят|лимит|превыш|попроб|busy|limit', текст, re.I):
                _СЕРП_ОТКАЗЫ['занято'] += 1
                time.sleep(3 * (попытка + 1))
                continue
            _СЕРП_ОТКАЗЫ['ошибка'] += 1
            return []
        адреса = [x.strip().replace('&amp;', '&')
                  for x in re.findall(r'<url>(.*?)</url>', xml, re.S)][:n]
        _СЕРП_ОТКАЗЫ['ок' if адреса else 'пусто'] += 1
        return адреса
    return []


def серп_отказы():
    """Сводка отказов выдачи — печатать в итоге ЛЮБОГО прогона по SERP."""
    return dict(_СЕРП_ОТКАЗЫ)


def бренд_компании(name, site=''):
    """Рабочее имя компании: то, под которым её знают, а не уставное.

    hh ищет работодателя по НАЗВАНИЮ, и полное уставное имя из ЕГРЮЛ его
    ломает: по «АКЦИОНЕРНОЕ ОБЩЕСТВО КРИОГЕННОГО МАШИНОСТРОЕНИЯ» не находится
    ничего, хотя страница работодателя «Криогенмаш» на hh есть. Прежний срез
    снимал только КОРОТКИЕ формы («ООО », «АО »), а в базе половина имён
    записана словами — для них поиск молча возвращал ноль.

    Порядок: имя в кавычках, если оно есть; иначе имя без ОПФ; и как последняя
    подсказка — домен сайта, потому что бренд обычно и есть домен
    (cryogenmash.ru -> cryogenmash), а уставное имя может не содержать бренда
    ВООБЩЕ, как раз случай Криогенмаша.
    """
    сыр = str(name or '').strip()
    m = re.search(r'[«"]([^«»"]{3,60})[»"]', сыр)
    if m:
        return m.group(1).strip()
    # Имя из выгрузки бывает ОБРЕЗАНО и теряет закрывающую кавычку:
    # «АКЦИОНЕРНОЕ ОБЩЕСТВО "АНГАРСКИЙ ЭЛЕКТРОЛИЗНЫЙ ХИМИЧЕСКИЙ КОМ». Без этой
    # ветки бренд не выделялся вовсе, и hh искал по всей длинной строке — то
    # есть не находил ничего и молча.
    m = re.search(r'[«"]([^«»"]{3,60})$', сыр)
    if m:
        сыр = m.group(1).strip()
    без = _ОПФ_ПОЛНАЯ.sub('', сыр)
    без = _ОПФ_КРАТКАЯ.sub('', без).strip().strip('"«»')
    d = site_domain(site)
    корень = d.split('.')[0] if d else ''
    # уставное имя в родительном падеже («КРИОГЕННОГО МАШИНОСТРОЕНИЯ») как
    # запрос бесполезно — тогда лучше домен
    if корень and len(корень) > 3 and re.search(r'(ого|ой|ых|ния)\b', без, re.I):
        return корень
    # Слишком длинное имя как запрос к hh бесполезно («АНГАРСКИЙ ЭЛЕКТРОЛИЗНЫЙ
    # ХИМИЧЕСКИЙ КОМБИНАТ» не совпадёт с карточкой «АЭХК»), а домен — это то,
    # под чем компанию знают. Порог 26 символов: короче обычно настоящий бренд.
    if корень and len(корень) > 3 and len(без) > 26:
        return корень
    return без or корень


def _dom_hits(d, tokens):
    """Домен d попадает в список tokens — по МЕТКАМ, а не подстрокой.

    Подстрочное сравнение резало живые сайты: короткие токены («gis», «tender»,
    «spark», «kontur», «nic.ru») встречаются внутри нормальных имён —
    logistika-nn.ru и energis.ru содержат «gis», tenderstroy.ru — «tender»,
    konturplast.ru — «kontur», technic.ru — «nic.ru». Такие компании выпадали
    из обхода целиком, молча. Правило: токен с точкой — это хост или суффикс
    (otc.ru, .rbc.ru), токен без точки — совпадение с ЦЕЛОЙ меткой домена.
    """
    d = (d or '').lower().strip('.')
    if not d:
        return False
    labels = set(d.split('.'))
    for a in tokens:
        a = (a or '').lower().strip().strip('.')
        if not a:
            continue
        if '.' in a:
            if d == a or d.endswith('.' + a):
                return True
        elif a in labels:
            return True
    return False


def _is_own_site(url):
    d = _domain(url)
    if not d:
        return False
    # Госвеб: у госкомпаний (МУП/водоканал/ГУП) официальная страница на ПОДДОМЕНЕ
    # *.gosuslugi.ru с контактами (владелец видел такие) — это валидный «сайт».
    # Блокируем только сам портал gosuslugi.ru (страницы услуг — не сайт компании).
    if d.endswith('.gosuslugi.ru'):
        return True
    if d in ('gosuslugi.ru', 'www.gosuslugi.ru'):
        return False
    return not _dom_hits(d, AGGREGATORS)


def find_site_via_listorg(company):
    """Сайт компании с карточки list-org (без поисковика, надёжно).

    СПРАВОЧНИК — значит МОБИЛЬНЫЙ канал (правило владельца). list-org режет
    датацентр-адреса и отдаёт капчу либо пустоту; мобильный адрес проходит.
    Массовый обход сайтов компаний при этом остаётся на 78 обычных адресах."""
    q = company.get('inn') or f"{company.get('name','')} {company.get('city','')}"
    with VC.mobilnyy():
        html, method, meta = VC._fetch(f'https://www.list-org.com/search?type=inn&val={urllib.parse.quote(q)}')
    if not html or meta.get('captcha_type'):
        return None, f'listorg-block:{meta.get("captcha_type") or method}'
    ids = re.findall(r'/company/(\d+)', html)
    if not ids:
        return None, 'listorg-no-card'
    time.sleep(_PACE())
    with VC.mobilnyy():
        h2, m2, meta2 = VC._fetch(f'https://www.list-org.com/company/{ids[0]}')
    if not h2 or meta2.get('captcha_type'):
        return None, f'listorg-card-block:{meta2.get("captcha_type") or m2}'
    # внешние ссылки-домены, не агрегаторы
    for u in re.findall(r'href="(https?://[^"]+)"', h2):
        if _is_own_site(u):
            return f'http://{_domain(u)}', 'listorg-card'
    return None, 'listorg-no-site'


def find_site_via_search(company):
    """Фолбэк: поисковик (DuckDuckGo HTML) по имени+городу -> первый свой домен."""
    q = f"{company.get('name','')} {company.get('city','')} официальный сайт"
    url = 'https://html.duckduckgo.com/html/?q=' + urllib.parse.quote(q)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': VC.UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return None, f'search-err:{str(e)[:40]}'
    for u in re.findall(r'uddg=([^"&]+)', html):
        real = urllib.parse.unquote(u)
        if _is_own_site(real):
            return f'http://{_domain(real)}', 'search'
    for u in re.findall(r'href="(https?://[^"]+)"', html):
        if _is_own_site(u):
            return f'http://{_domain(u)}', 'search'
    return None, 'search-no-site'


# Прямой opener БЕЗ прокси — xmlriver это их инфра (капчи/банов нет), гнать через
# мобильный socks5 незачем и вредно (лишняя латентность/сбои).
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _parse_kg(xml):
    """Карточка компании (блок knowledge_graph — правая колонка Яндекса) -> dict|{}.
    Теги по доке xmlriver: type/name/website/phone/address/rating/countReviews/mapurl/id.
    email добавлен на случай, если Яндекс его отдаёт (проверяется kg_probe)."""
    m = re.search(r'<knowledge_graph\b[^>]*>(.*?)</knowledge_graph>', xml, re.S)
    if not m:
        return {}
    body = m.group(1)
    card = {}
    for tag in ('type', 'name', 'website', 'phone', 'address', 'email',
                'rating', 'countReviews', 'mapurl', 'id', 'category', 'hours'):
        mm = re.search(r'<' + tag + r'>(.*?)</' + tag + r'>', body, re.S)
        if mm:
            v = mm.group(1).strip().replace('&amp;', '&')
            if v:
                card[tag] = v
    return card


def find_site_via_xmlriver(company):
    """ОСНОВНОЙ канал: сайт компании через xmlriver (Яндекс-SERP как XML) — без капчи и
    прокси. Браузерный Яндекс/Bing с нашего IP закрыты капчей, поэтому SERP-API надёжнее.
    Один запрос с additional=knowledge_graph_y тянет И органику, И карточку компании
    (правая колонка): официальный сайт из карточки точнее первого органик-результата
    (тот бывает агрегатором/конкурентом). Возврат: (site|None, source, card_dict)."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None, 'no-xmlriver-key', {}
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    q = f'{nm} {company.get("city", "")} официальный сайт'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&additional=knowledge_graph_y&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    # «Нет свободных каналов» — это ЛИМИТ КАНАЛОВ аккаунта (не транзиент): при заливе он
    # держится, и агрессивный backoff только копит секунды и валит job по таймауту. Поэтому
    # concurrency держим низким (_SEM_XMLRIVER), а ретрай — ЛЁГКИЙ (пара попыток, короткий
    # сон на случай кратковременной конкуренции с другими окнами того же аккаунта).
    xml = None
    last = ''
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                last = 'no-free-channels'
                xml = None
                time.sleep(_XMLRIVER_PAUZA)
                continue
            break
        except Exception as e:  # noqa: BLE001
            last = str(e)[:40]
            time.sleep(_XMLRIVER_PAUZA)
    if xml is None:
        return None, f'xmlriver-err:{last}', {}
    card = _parse_kg(xml)
    # 1) официальный сайт прямо из карточки (правая колонка) — самый точный источник
    site_kg = card.get('website', '')
    if site_kg and _is_own_site(site_kg):
        return f'http://{_domain(site_kg)}', 'xmlriver-kg', card
    # 2) фолбэк — первый «свой» домен из органической выдачи
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        if _is_own_site(u):
            return f'http://{_domain(u)}', 'xmlriver', card
    err = re.search(r'<error[^>]*>(.*?)</error>', xml)
    return None, ('xmlriver:' + err.group(1)[:50]) if err else 'xmlriver-no-site', card


# бизнес-справочники, публикующие контакты фирм (для компаний БЕЗ своего сайта, хвост 78%).
# НЕ гос-ЭТП и НЕ финсводки (там контактов нет) — только каталоги с телефоном/почтой.
_DIR_SOURCES = ('orgpage', 'cataloxy', 'pulscen', 'tiu.ru', 'blizko', 'flamp', 'zoon',
                'yell.ru', 'spr.ru', 'firmika', 'bizly', 'rusprofile', 'list-org', '2gis')
# СНЯТО. Здесь была своя регулярка телефона:
#   (?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}
# и в ней жили ОБЕ ошибки, которые считались вылеченными ещё 29.07, — просто
# этот слой ходил мимо `phones_in` и починку не получил:
#   * код города строго из ТРЁХ цифр, поэтому «8 (34764) 6 42 27» не находился
#     ВООБЩЕ (тот же дефект, что стоил 720 номеров на 201 странице кэша);
#   * ни `(?<!\d)`, ни вето по подписи, поэтому на строке «ОГРН 1083801006860»
#     регулярка выдавала «83801006860» как телефон.
# Единая точка входа — `phones_in`. Ровно это правило («рубеж ставить в
# ЕДИНСТВЕННУЮ точку входа») выведено из инцидента, где починка стояла в
# `add_phone`, а соседние слои звали базу напрямую и рубеж пережили.


def _dir_phones(txt):
    """Телефоны со страницы справочника — через общий разбор, а не свой."""
    return sorted({re.sub(r'[\s\-()]', '', m.group(0)) for m in phones_in(txt or '')})


# Маскированный контакт: справочники вроде saby печатают «vm ** 50@bk.ru» и
# «(812) 71 ** 06». EMAIL_RE на такой строке возвращает «50@bk.ru» — адрес
# синтаксически валидный и полностью выдуманный. Сегодня ни один живой источник
# из _DIR_SOURCES масок не ставит, но добавление такого справочника молча
# наполнило бы базу несуществующими адресами — а они, как и сфабрикованный
# номер, выглядят рабочими.
#
# Ищем звёздочку ВНУТРИ САМОГО КОНТАКТА, а не любую на строке: маркер списка
# «* Доставка» и сноска «Цена * без НДС» к контактам отношения не имеют, и
# широкий шаблон выбрасывал бы вместе с масками живые строки.
_МАСКА_ПОЧТЫ = re.compile(r'[\w.\-]*\s*[*•·]{1,}\s*[\w.\-]*@|@\s*[\w.\-]*[*•·]')
_МАСКА_ТЕЛ = re.compile(r'\d\s*[*•·]{1,}\s*\d|\)\s*[\d\s\-]{1,6}[*•·]')


def _маскирован(строка):
    return bool(_МАСКА_ПОЧТЫ.search(строка) or _МАСКА_ТЕЛ.search(строка))


def _egrul_emails_by_inn(inn):
    """Email из ЕГРЮЛ (юрзначимые уведомления) через dadata findById. С 2025 поле
    обязательное - покрытие высокое. Источник помечается egrul:dadata (директива владельца)."""
    tok = _read_secret('DADATA_TOKEN')
    if not (tok and inn):
        return []
    try:
        body = json.dumps({'query': str(inn)}).encode()
        req = urllib.request.Request(
            'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
            data=body, method='POST', headers={'Content-Type': 'application/json',
            'Accept': 'application/json', 'Authorization': f'Token {tok}'})
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
        sugg = (d.get('suggestions') or [])
        if not sugg:
            return []
        return [e.get('value') for e in (sugg[0].get('data', {}).get('emails') or [])
                if isinstance(e, dict) and e.get('value')][:3]
    except Exception:  # noqa: BLE001
        return []


_SITE_CACHE_DAYS = 90


_DOMENY_BAZY = None
_DOMENY_LOCK = threading.Lock()
# домены, которые НЕ являются сайтом компании: закрепление за ИНН в базе тут ничего
# не доказывает (в базе, например, vk.ru записан сайтом «Гросбахера»)
_NE_SAYT = ('vk.com', 'vk.ru', 'ok.ru', 't.me', 'telegram.me', 'instagram.com',
            'facebook.com', 'youtube.com', 'zen.yandex.ru', 'wa.me', 'avito.ru',
            'api.whatsapp.com', 'wixsite.com', 'tilda.ws', 'narod.ru', 'ucoz.ru',
            # Бесплатная почта в поле «сайт» выгрузки (12.08): в базе обзвона у части
            # юрлиц сайтом записан `mail.ru`, и карта доменов честно считала его
            # «закреплённым» за ними. Последствие не косметическое: домен с несколькими
            # хозяевами запускает перенос контактов чужому владельцу, то есть контакты
            # компании уехали бы к случайному юрлицу, у которого в выгрузке тот же
            # `mail.ru`. Сайтом это быть не может ни при каких условиях.
            'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
            'inbox.ru', 'rambler.ru', 'internet.ru', 'icloud.com', 'outlook.com')


_INN_RE = re.compile(r'(?<!\d)(\d{10}|\d{12})(?!\d)')


def _inn_verno(s):
    """Контрольная цифра ИНН. Без неё в кандидаты лезут телефоны, артикулы и
    номера лицензий — на пробе таких было больше, чем настоящих ИНН.
    """
    if len(s) == 10:
        k = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        return int(s[9]) == sum(int(s[i]) * k[i] for i in range(9)) % 11 % 10
    if len(s) == 12:
        k1 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        k2 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        return (int(s[10]) == sum(int(s[i]) * k1[i] for i in range(10)) % 11 % 10
                and int(s[11]) == sum(int(s[i]) * k2[i] for i in range(11)) % 11 % 10)
    return False


def inn_so_stranicy(tekst, svoy_inn=''):
    """ИНН, найденные НА САМОЙ странице, кроме нашего. Ими опознаётся хозяин
    чужого сайта: разбор 600 таких случаев дал ИНН на странице у 215 (36%),
    тогда как закрепление домена в выгрузке — лишь у 17.
    """
    svoy = re.sub(r'\D', '', str(svoy_inn or ''))
    out = []
    for x in _INN_RE.findall(str(tekst or '')[:60000]):
        if x != svoy and _inn_verno(x) and x not in out:
            out.append(x)
    return out[:5]


def _domeny_bazy():
    """{домен: (множество ИНН, имя первого владельца)} из индекса базы обзвона.

    Нужна для случая «сайт признан чужим» (владелец 11.08.2026): вердикт модели —
    ещё не приговор контактам. Если домен закреплён в базе за ЭТИМ ЖЕ ИНН, спорит
    с реестровой выгрузкой уже модель; если за ДРУГОЙ компанией из базы — контакты
    не мусор, у них просто другой хозяин, и он тоже наш лид. Разбор на 2674 таких
    строках: за этим же ИНН 80, за другой компанией 226 (1611 контактов), нет в
    базе вовсе 2368. Карта строится один раз на процесс (35 тыс. строк, доли секунды)."""
    global _DOMENY_BAZY
    if _DOMENY_BAZY is not None:
        return _DOMENY_BAZY
    with _DOMENY_LOCK:
        if _DOMENY_BAZY is not None:
            return _DOMENY_BAZY
        karta = {}
        put = os.environ.get('OBZVON_INDEX', r'C:\sender\obzvon-index.db')
        try:
            import sqlite3 as _sq
            cx = _sq.connect('file:%s?mode=ro' % put.replace('\\', '/'), uri=True)
            for inn, s, ns, nf in cx.execute(
                    "select inn, sites, name_short, name_full from obzvon where sites<>''"):
                for kus in re.split(r'[|,;\s]+', str(s or '')):
                    d = _domain(kus if str(kus).startswith('http') else 'http://' + str(kus))
                    if not d or '.' not in d or any(d == m or d.endswith('.' + m)
                                                    for m in _NE_SAYT):
                        continue
                    if d not in karta:
                        karta[d] = [set(), (ns or nf or '')[:200]]
                    karta[d][0].add(str(inn))
            cx.close()
        except Exception:  # noqa: BLE001
            karta = {}
        _DOMENY_BAZY = karta
        return _DOMENY_BAZY


_GEO_BAZY = None
_GEO_LOCK = threading.Lock()


def _geo_bazy():
    """{ИНН: (регион, адрес)} из выгрузки базы обзвона — для сверки географии.

    Владелец 12.08: код в ИНН — это регион ПОСТАНОВКИ НА УЧЁТ, а не место работы,
    поэтому сверять надо с регионом ИЗ ВЫГРУЗКИ. Он есть у 6112 из 8209 компаний с
    сайтом (74%), у остальных сверка молча остаётся слабой пометкой. Карта строится
    один раз на процесс, как и карта доменов рядом."""
    global _GEO_BAZY
    if _GEO_BAZY is not None:
        return _GEO_BAZY
    with _GEO_LOCK:
        if _GEO_BAZY is not None:
            return _GEO_BAZY
        karta = {}
        put = os.environ.get('OBZVON_INDEX', r'C:\sender\obzvon-index.db')
        try:
            import sqlite3 as _sq
            cx = _sq.connect('file:%s?mode=ro' % put.replace('\\', '/'), uri=True)
            for inn, reg, adr in cx.execute(
                    "select inn, coalesce(region,''), coalesce(address,'') from obzvon"):
                if reg or adr:
                    karta[str(inn)] = ((reg or '')[:120], (adr or '')[:200])
            cx.close()
        except Exception:  # noqa: BLE001
            karta = {}
        _GEO_BAZY = karta
        return _GEO_BAZY


def _site_cache_get(inn):
    """КЭШ ИНН->сайт из enrich.db (владелец 2026-07-23: повторные компании не жгут SERP).
    TTL 90д; сайт прогоняется через _is_own_site - плохой кэш (агрегатор/контент-платформа
    из старых инцидентов) самоизлечивается. Помечается site_source=cache:enrich-db."""
    if not inn:
        return None
    try:
        import enrich_db as EDB
        import datetime as _dt
        cx = EDB.EnrichDB().cx
        row = cx.execute("SELECT site, updated_at FROM companies WHERE inn=? AND site!='' AND site IS NOT NULL",
                         (str(inn),)).fetchone()
        if not row:
            return None
        site, upd = row
        try:
            age = (_dt.datetime.now() - _dt.datetime.fromisoformat(str(upd)[:19])).days
        except Exception:  # noqa: BLE001
            age = 0
        if age > _SITE_CACHE_DAYS:
            return None
        d = _domain(str(site) if str(site).startswith('http') else 'http://' + str(site))
        if d and _is_own_site('http://' + d):
            return 'http://' + d
    except Exception:  # noqa: BLE001
        return None
    return None


_HH_COMP_KW = ('компрессор', 'воздуходув', 'компрессорн')


def find_hh_compressor(company):
    """АДРЕСНАЯ hh-проверка (владелец 2026-07-23): ищет ли ЭТА компания компрессорщиков.
    ВАЖНО: эндпоинт /employers запрещён hh ВСЕМ без авторизации (forbidden даже с домашнего
    РФ-IP - проверено владельцем). Используем ПУБЛИЧНЫЙ /vacancies: ищем вакансии
    «<компания> компрессор/воздуходув», матч работодателя по токену имени.
    Возврат: {'employer','total','compressor_vacancies':[...]} | None."""
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|КАО|ГК)\s+', '', str(company.get('name') or '')
                ).strip().strip('"«»')
    if len(nm) < 3:
        return None
    tok = next((t.lower() for t in re.findall(r'[А-Яа-яЁёA-Za-z]{4,}', nm)), '')
    if not tok:
        return None
    _HH_UA = os.environ.get('HH_USER_AGENT', 'RuspromLeadEnrich/1.0 (kirillrand4@gmail.com)')
    def _hh_get(u):
        try:
            req = urllib.request.Request(u, headers={'User-Agent': _HH_UA, 'Accept': 'application/json'})
            d = json.loads(_DIRECT.open(req, timeout=15).read())
            if not (isinstance(d, dict) and d.get('errors')):
                return d
        except Exception:  # noqa: BLE001
            pass
        # фолбэк через дельфин (если /vacancies тоже режет IP сервера)
        try:
            import browser_probe as BP
            _dtok = _read_secret('DOLPHIN_TOKEN')
            _dp = _resolve_dolphin_profiles(None, _dtok)
            out = BP.probe({'url': u, 'return_html': True, 'html_cap': 200000, 'wait_ms': 3000,
                            'screenshot': False, 'solve': True,
                            'dolphin_profile': (_dp[0] if _dp else None), 'dolphin_token': _dtok})
            body = (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', out.get('html') or '')
            m = re.search(r'\{.*\}', body, re.S)
            return json.loads(m.group(0)) if m else {}
        except Exception:  # noqa: BLE001
            return {}
    # поиск компрессорных вакансий ИМЕННО этой компании (публичный /vacancies)
    q = f'{nm} (компрессор OR воздуходувк OR пневмат)'
    url = ('https://api.hh.ru/vacancies?text=' + urllib.parse.quote(q)
           + '&search_field=company_name&per_page=20&period=90')
    d = _hh_get(url)
    items = (d or {}).get('items') or []
    out = {'employer': None, 'total': (d or {}).get('found', 0), 'compressor_vacancies': []}
    KW = ('компрессор', 'воздуходув', 'пневмат')
    for v in items:
        emp = (v.get('employer') or {}).get('name') or ''
        if tok not in emp.lower():
            continue          # чужая компания-тёзка
        out['employer'] = out['employer'] or emp
        blob = ((v.get('name') or '') + ' '
                + str((v.get('snippet') or {}).get('requirement') or '')
                + str((v.get('snippet') or {}).get('responsibility') or '')).lower()
        if any(k in blob for k in KW):
            out['compressor_vacancies'].append({'name': v.get('name'),
                                                'url': v.get('alternate_url'),
                                                'area': (v.get('area') or {}).get('name'),
                                                'published': v.get('published_at', '')[:10]})
        if len(out['compressor_vacancies']) >= 5:
            break
    return out if out['employer'] else None


# ЕИС (zakupki.gov.ru): прямой доступ БЕЗ прокси (туннель режет госсайты) и без
# верификации TLS (Russian Trusted CA) - как в news_scan._get (проверено, работает с сервера)
_EIS_OPENER = None


def _url_квота(u):
    """Процентное квотирование НЕ-ASCII в ссылке.

    У ЕИС имя файла нередко попадает прямо в путь ссылки кириллицей, а
    `urllib` отправить такой адрес не может — падает на ascii-кодировании ещё
    до сети. Снаружи это выглядело как «документ пуст»: `doc_text` ловит любое
    исключение и возвращает пустую строку. После квотирования тот же PDF
    отдаёт 24 тысячи символов.

    В `safe` оставлен '%', чтобы уже закодированные ссылки не кодировались
    вторично («%D0%9F» -> «%25D0%259F» ломает адрес так же надёжно).
    """
    try:
        p = urllib.parse.urlsplit(u)
        if all(ord(c) < 128 for c in u):
            return u
        return urllib.parse.urlunsplit((
            p.scheme, p.netloc,
            urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;=~"),
            urllib.parse.quote(p.query, safe="=&%:@!$'()*+,;/~?"),
            urllib.parse.quote(p.fragment, safe="%")))
    except Exception:  # noqa: BLE001
        return u


def _eis_get(url, timeout=30, raw=False):
    global _EIS_OPENER
    if _EIS_OPENER is None:
        import ssl as _ssl
        _ctx = _ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = _ssl.CERT_NONE
        _EIS_OPENER = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=_ctx))
    req = urllib.request.Request(_url_квота(url),
                                 headers={'User-Agent': VC.UA, 'Accept': '*/*',
                                          'Accept-Language': 'ru-RU,ru'})
    blob = _EIS_OPENER.open(req, timeout=timeout).read()
    # raw нужен для ДОКУМЕНТОВ закупки (.docx это zip): декодировать их в текст
    # нельзя, содержимое станет мусором ещё до разбора
    return blob if raw else blob.decode('utf-8', 'replace')


# Должности в контактных блоках ЕИС/сайтов. Отдельно от _POST_RE (тот — якорь
# для обрезки текста): здесь нужно ВЫРЕЗАТЬ должность как значение.
#
# Окна слов расширены с 2 до 4 (владелец увидел в выгрузке обрубки): шаблон
# «начальник + 2 слова» резал «Начальник отдела закупок и логистики» на
# «Начальник отдела закупок и», а «заместитель X по Y» — «заместитель
# директора по» без самого направления. Обрубок хуже пустого поля: продажник
# читает его как готовую должность. Хвостовой мусор, который ловится вместе с
# лишними словами («… снабжения тел», «… по МТО факс»), снимает _clean_post.
# СЛ — одно слово должности: дефис внутри слова не разрыв. Без этого
# «материально-техническог о снабжения» рвалось на «материально» и остаток
# должности терялся («Начальник отдела закупок и материально»).
_СЛ = r'[а-яё]+(?:-[а-яё]+)*'
_POST_VAL_RE = re.compile(
    # «Заместитель главного инженера по эксплуатации» — раньше первым срабатывал
    # шаблон «главный инженер» с середины строки, и должность теряла «заместитель»
    r'(заместител\w+\s+главн\w+\s+(?:инженер|энергетик|механик|технолог|бухгалтер)\w*'
    r'(?:\s+по\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,2})?'
    # «Заместитель директора», «Заместитель начальника отдела» — без «по». Без
    # этих двух веток шаблон директор\w*/начальник\w* срабатывал с середины и
    # должность теряла «заместитель» (autodor.pskov.ru: 6 замов стали
    # «директора»/«начальника отдела»)
    r'|заместител\w+\s+(?:генеральн\w+\s+|исполнительн\w+\s+|первы\w+\s+)?директор\w*'
    r'(?:\s+по\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,2})?'
    r'|заместител\w+\s+начальник\w+(?:\s+' + _СЛ + r'){0,3}'
    r'|заместител\w+\s+' + _СЛ + r'\s+по\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,2}'
    r'|главн\w+\s+(?:инженер|энергетик|механик|технолог|бухгалтер)\w*(?:-' + _СЛ + r')?'
    r'|техническ\w+\s+директор\w*'
    r'|начальник\w*\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,4}'
    r'|руководител\w*\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,4}'
    r'|директор\w*(?:\s+по\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,3})?'
    r'|специалист\w*(?:-' + _СЛ + r')?(?:\s+по\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,2})?'
    r'|инженер\w*(?:-' + _СЛ + r')?(?:\s+' + _СЛ + r'){0,3}'
    r'|контрактн\w+\s+управляющ\w+'
    # рабочие титулы, которых в словаре не было вовсе: на странице структуры
    # «Эксперт дорожного хозяйства» уходил в пустую должность и подменялся
    # заголовком отдела
    r'|эксперт\w*(?:\s+' + _СЛ + r'){0,3}'
    r'|мастер\w*(?:\s+' + _СЛ + r'){0,3}'
    r'|бухгалтер\w*(?:\s+' + _СЛ + r'){0,2}'
    r'|юрисконсульт\w*|диспетчер\w*(?:\s+' + _СЛ + r'){0,2}'
    r'|энергетик\w*|механик\w*(?:\s+' + _СЛ + r'){0,2}'
    r'|экономист\w*|менеджер\w*(?:\s+по\s+' + _СЛ + r'(?:\s+' + _СЛ + r'){0,2})?)', re.I)
# ФИО в ЕИС пишут и полностью («Петров Игорь Львович»), и сокращённо
# («Потапова О.Ю.», «Иванов И. И.») — второй вариант в 223-ФЗ основной,
# и на строгом шаблоне «Фамилия Имя» контактное лицо терялось совсем.
_FIO_RE = re.compile(
    r'([А-ЯЁ][а-яё]+\s+(?:[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?'
    r'|[А-ЯЁ]\.\s?[А-ЯЁ]?\.?))')
# служебные слова страницы ЕИС, которые сами по себе выглядят как «Имя Фамилия»
# («Должность Главный», «Контактное Лицо») и уезжали в ФИО
_FIO_STOP = re.compile(
    r'должност|телефон|контактн|ответствен|электрон|почт|информац|организац|лицо'
    r'|адрес|заказчик|поставщик|наименован|сведени|дополнительн|факс|время|график'
    r'|российск|федерац|област|район|город|улиц|закупк|извещен', re.I)
_EIS_TEL_RE = re.compile(r'(?:Телефон|тел)\D{0,20}((?:\+?7|8)[\d\s\-()]{9,20})', re.I)
# Подписи полей на страницах ЕИС. Значение поля кончается там, где начинается
# ЛЮБАЯ следующая подпись — иначе в ФИО уезжает половина соседней колонки.
_EIS_PERSON_LBL = re.compile(
    r'(?:Ответственн\w+\s+должностн\w+\s+лиц\w+|Контактн\w+\s+лиц\w+'
    r'|ФИО\s+ответственн\w+\s+лица|Фамилия,?\s*имя,?\s*отчество)\s*[:\-]?\s*', re.I)
# именно «Должность», а не «Должност\w*»: иначе подпись матчилась внутри
# «Ответственное ДОЛЖНОСТНОЕ лицо» и в должность уезжало ФИО
_EIS_POST_LBL = re.compile(r'Должность\b\s*[:\-]?\s*', re.I)
_EIS_TEL_LBL = re.compile(
    r'(?:Контактн\w+\s+телефон|Телефон(?:\s+для\s+связи)?|Номер\s+контактного\s+телефона)'
    r'\s*[:\-]?\s*', re.I)
_EIS_MAIL_LBL = re.compile(
    r'(?:Адрес\s+электронн\w+\s+почты|Электронн\w+\s+почт\w*|E-?mail)\s*[:\-]?\s*', re.I)
# любая подпись — граница значения
_EIS_ANY_LBL = re.compile(
    r'(?:Ответственн\w+\s+должностн\w+\s+лиц\w+|Контактн\w+\s+лиц\w+|Должност\w*'
    r'|Контактн\w+\s+телефон|Телефон|Факс|Адрес\s+электронн\w+\s+почты'
    r'|Электронн\w+\s+почт\w*|E-?mail|Почтов\w+\s+адрес|Мест\w*\s+нахожден\w+'
    r'|Организаци\w+|Наименовани\w+|Дополнительн\w+|Рабочее\s+время|Регион)', re.I)


def _eis_value(сег, подпись, кап=90):
    """Значение поля: текст после подписи до следующей ЛЮБОЙ подписи."""
    m = подпись.search(сег)
    if not m:
        return ''
    хвост = сег[m.end():m.end() + 300]
    nx = _EIS_ANY_LBL.search(хвост)
    val = хвост[:nx.start()] if nx else хвост
    return re.sub(r'\s+', ' ', val).strip(' .,;:–—-')[:кап]


# хвост, который приезжает из соседней ячейки таблицы вместе с должностью:
# подписи полей в сокращённой форме («тел», «факс», «эл»), их _FIO_STOP не ловит
_ХВОСТ_ПОДПИСЬ = re.compile(
    r'(?:[\s,;.]+(?:тел|телефона?|факс|эл|email|e|mail|почт\w*|адрес\w*|моб|'
    r'доб|каб|кабинет|оф|офис|приём|прием|часы|график|контакт\w*))+$', re.I)
# висящий предлог/союз на конце — след обрезки шаблоном: «…закупок и»
# без re.I: заглавный хвост — это чаще аббревиатура отдела («Инженер снабжения
# и ОБ», «инженер ОТ»), а не предлог, и re.I её съедала
_СЛУЖ_СЛОВА = (r'и|или|по|в|во|с|со|на|для|от|к|ко|при|за|над|под|о|об|у|из|до')
_ХВОСТ_СЛУЖ = re.compile(r'[\s,]+(?:' + _СЛУЖ_СЛОВА + r')$')
_ХВОСТ_СЛУЖ_КАПС = re.compile(r'[\s,]+(?:' + _СЛУЖ_СЛОВА.upper() + r')$')
_ЕСТЬ_СТРОЧНЫЕ = re.compile(r'[а-яё]')
# ФИО, прилипшее к должности с конца: окно расширили до 5 слов, и там, где ФИО
# из текста заранее не вырезано, в хвост уезжает «… снабжения Петров П.П.».
# Режем только однозначные формы — с отчеством или с инициалами.
_ХВОСТ_ФИО = re.compile(
    r'[\s,]+(?:[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.?'
    r'|[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]*'
    r'(?:ович|евич|ьич|овна|евна|ична|инична)'
    r'|[А-ЯЁ][а-яё]*(?:ович|евич|ьич|овна|евна|ична|инична)'
    r'|[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.?){1,2})$')
# одно-два слова с большой буквы после строчного слова — это прилипшее имя
# («Эксперт дорожного хозяйства Пашков»). Строчная буква перед пробелом важна:
# в «Заместитель Генерального Директора» хвост тоже с большой, но резать его
# нельзя — там вся должность в титульном регистре.
_СЛОВО_ИМЯ = re.compile(r'[А-ЯЁ][а-яё]+$')
_СЛОВО_СТРОЧН = re.compile(r'[а-яё]+$')


def _снять_имя(s):
    т = s.split()
    n = 0
    while n < 2 and len(т) - n > 2 and _СЛОВО_ИМЯ.match(т[-1 - n]):
        n += 1
    if n and _СЛОВО_СТРОЧН.match(т[-1 - n]):
        return ' '.join(т[:len(т) - n])
    return s
# название организации в хвосте должности («Начальник отдела продаж ООО Ромашка»)
_ХВОСТ_ОРГ = re.compile(r'[\s,]+(?:ООО|ОАО|АО|ПАО|ЗАО|НАО|ГУП|МУП|ФГУП|ИП)\b.*$')


def _clean_post(s):
    """Обрезать должность по служебному слову страницы: шаблон «начальник +
    N слов» иначе прихватывает «Телефон»/«Электронная почта» из соседней
    строки таблицы («Начальник отдела снабжения Телефон»).

    Второй проход — хвосты. Сокращённые подписи полей («тел», «факс») мимо
    _FIO_STOP проходят, а висящий предлог на конце («…отдела закупок и»)
    остаётся от самой обрезки: лучше отдать «Начальник отдела закупок», чем
    строку, которая читается как оборванная.
    """
    s = re.sub(r'\s+', ' ', (s or '')).strip(' .,;:')
    m = _FIO_STOP.search(s)
    if m and m.start() > 0:
        s = s[:m.start()].strip(' .,;:')
    for _ in range(4):
        было = s
        s = _ХВОСТ_ПОДПИСЬ.sub('', s).strip(' .,;:')
        s = _ХВОСТ_ОРГ.sub('', s).strip(' .,;:')
        s = _ХВОСТ_ФИО.sub('', s).strip(' .,;:')
        s = _снять_имя(s).strip(' .,;:')
        s = _ХВОСТ_СЛУЖ.sub('', s).strip(' .,;:')
        if not _ЕСТЬ_СТРОЧНЫЕ.search(s):   # должность целиком капсом
            s = _ХВОСТ_СЛУЖ_КАПС.sub('', s).strip(' .,;:')
        if s == было:
            break
    return s


def _eis_contact_block(txt):
    """Кусок страницы ЕИС с контактами. Регулярки по всей странице тащат чужие
    номера (баннеры техподдержки), поэтому сперва сужаем до блока."""
    m = re.search(r'Контактн\w+\s+информаци\w+(.{0,2500})', txt, re.S | re.I)
    if m:
        return m.group(1)
    m = re.search(r'(?:Контактное лицо|Ответственн\w+ должностн\w+ лиц\w+)(.{0,1500})',
                  txt, re.S | re.I)
    return m.group(1) if m else txt[:2500]


def _eis_people(txt):
    """[{person, post, phone, email}] из контактного блока ЕИС.

    Раньше брали ОДНО ФИО, ОДИН телефон и первый попавшийся email со всей
    страницы, а должность не искали вовсе — хотя в 44-ФЗ есть «Ответственное
    должностное лицо» с должностью, и это прямой путь к технарю, а не к
    снабженцу.
    """
    blob = _eis_contact_block(txt)
    # Разбор ПО ПОДПИСЯМ ПОЛЕЙ, а не поиском «Слово Слово» с большой буквы:
    # свободный поиск ФИО тащил из вёрстки «Опросы Статистика Карта» и
    # «Регион Тамбовская». На страницах ЕИС у каждого значения есть подпись,
    # и значение кончается там, где начинается следующая подпись.
    люди = []
    места = list(_EIS_PERSON_LBL.finditer(blob))
    for i, m in enumerate(места):
        кон = места[i + 1].start() if i + 1 < len(места) else len(blob)
        сег = blob[m.start():кон][:1200]
        фио = _eis_value(сег, _EIS_PERSON_LBL)
        # значение поля должно быть похоже на ФИО и не быть служебным
        # словом вёрстки («Регион Тамбовская», «Опросы Статистика»)
        фио = (фио if (_FIO_RE.fullmatch(фио or '')
                       and not _FIO_STOP.search(фио or '')) else '')
        должность = _clean_post(_eis_value(сег, _EIS_POST_LBL))
        тел = _eis_value(сег, _EIS_TEL_LBL)
        tm = _EIS_TEL_RE.search('Телефон ' + тел) if тел else None
        почта = _eis_value(сег, _EIS_MAIL_LBL)
        em = [x for x in EMAIL_RE.findall(почта or сег)
              if 'zakupki' not in x.lower() and not _is_junk_email(x)]
        if not (фио or должность or tm or em):
            continue
        люди.append({'person': фио, 'post': должность,
                     'phone': (re.sub(r'\s+', ' ', tm.group(1)).strip() if tm else ''),
                     'email': (em[0].lower() if em else '')})
        if len(люди) >= 6:
            break
    # общий телефон/почта блока — тем, у кого своих не нашлось
    общий_т = _EIS_TEL_RE.search(blob)
    общий_e = [e for e in EMAIL_RE.findall(blob)
               if 'zakupki' not in e.lower() and not _is_junk_email(e)]
    for ч in люди:
        if not ч['phone'] and общий_т:
            ч['phone'] = re.sub(r'\s+', ' ', общий_т.group(1)).strip()
        if not ч['email'] and общий_e:
            ч['email'] = общий_e[0].lower()
    if not люди and (общий_т or общий_e):
        люди.append({'person': '', 'post': '',
                     'phone': (re.sub(r'\s+', ' ', общий_т.group(1)).strip()
                               if общий_т else ''),
                     'email': (общий_e[0].lower() if общий_e else '')})
    return люди


# --------------------------------------------------------- гриф «УТВЕРЖДАЮ»
# Способ А5 из разбора engineers-lens: техническую документацию закупки
# УТВЕРЖДАЕТ главный инженер, и его должность с ФИО стоят на титульном листе.
# Работает даже там, где состав закупочной комиссии не публикуется. Приёма не
# было ни в одной из четырнадцати линз — он нашёлся только на живых документах.
_ДОК_ИНТЕРЕС = re.compile(
    r'техническ\w*\s*задани|документац|извещени|тз|требовани', re.I)
# PDF в списке С 29.07: до этого его отсекали здесь же, потому что читать было
# нечем. Именно из-за этого способ «гриф УТВЕРЖДАЮ» дал всего одного человека
# на 555 компаний — техническое задание в ЕИС чаще всего выкладывают в PDF.
# xlsx добавлен: реестры заключений ЭПБ территориальные управления
# Ростехнадзора выкладывают таблицей, и без него источник невидим целиком
_ДОК_ФОРМАТ = re.compile(r'\.(docx|doc|xlsx|xls|rtf|txt|pdf)(?:\W|$)', re.I)
_УТВ = re.compile(r'УТВЕРЖДАЮ', re.I)
# технические должности — их ищем в окне первыми
_POST_TECH_RE = re.compile(
    r'((?:заместител\w+\s+[а-яё]+\s+[а-яё]*\s*[-–—]\s*)?'
    r'(?:главн\w+\s+(?:инженер\w*|энергетик\w*|механик\w*|технолог\w*)'
    r'|техническ\w+\s+директор\w*|директор\w*\s+по\s+(?:производств|техни)\w*'
    r'|начальник\w*\s+(?:производств\w*|цеха)))', re.I)
# «М.Ю. Юнин» — инициалы впереди, типовая подпись под грифом
_ИО_ФАМ = re.compile(r'([А-ЯЁ])\.\s?([А-ЯЁ])\.\s?([А-ЯЁ][а-яё]{2,})')
# «Юнин М.Ю.» — фамилия впереди
_ФАМ_ИО = re.compile(r'([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ])\.\s?([А-ЯЁ])\.')


def eis_documents(notice_url):
    """[(имя файла, ссылка)] со вкладки документов извещения ЕИС."""
    try:
        h = _eis_get(notice_url)
    except Exception:  # noqa: BLE001
        return []
    # Вкладок у карточки семь, и «Протоколы» живёт по СВОЕМУ адресу
    # (protocols.html), а не под словом documents. Прежний код брал первую
    # ссылку с «documents» — то есть документы ИЗВЕЩЕНИЯ — и вкладку протоколов
    # не открывал никогда. Проверяющий агент: протокол есть у 9 закупок из 10,
    # и у всех девяти приложен файл.
    ссылки = []
    for rx in (r'href="([^"]*protocols?[^"]*)"', r'href="([^"]*documents[^"]*)"'):
        for u in re.findall(rx, h):
            if u not in ссылки:
                ссылки.append(u)
    if not ссылки:
        return []
    # Читаем ОБЕ вкладки и склеиваем разметку: файлы протокола и файлы
    # извещения нужны одинаково, а какая вкладка попадётся первой — случайность
    # порядка ссылок на странице.
    куски = []
    for сыр in ссылки[:2]:
        du = сыр.replace('&amp;', '&')
        if du.startswith('/'):
            du = 'https://zakupki.gov.ru' + du
        try:
            time.sleep(0.8 + random.uniform(0, 0.7))
            куски.append(_eis_get(du))
        except Exception:  # noqa: BLE001
            continue
    if not куски:
        return []
    hd = '\n'.join(куски)
    # имя файла и ссылка лежат рядом в разметке; связываем по позиции блока
    из = []
    # берём ТЕКСТ ссылки, а не всё подряд после href: атрибуты вроде
    # data-tooltip уезжали в имя файла и ломали и приоритет чтения, и отчёт
    for m2 in re.finditer(
            r'<a\b[^>]*href="(https://zakupki\.gov\.ru/[^"]*filestore[^"]*)"[^>]*>'
            r'(.*?)</a>', hd, re.S):
        имя = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m2.group(2))).strip()
        # у ЕИС имя файла иногда лежит в title самой ссылки
        if not _ДОК_ФОРМАТ.search(имя):
            tm = re.search(r'title="([^"]{4,120})"', m2.group(0))
            if tm and _ДОК_ФОРМАТ.search(tm.group(1)):
                имя = tm.group(1)
        # ИМЯ ЧИСТИМ. Разбор цеплял хвост разметки, и в отчёты уезжало
        # «Протокол_подвения_итогов.pdf ' > Протокол_подвения_итогов.pdf» —
        # такое имя ломает и отбор по слову «протокол», и приоритет чтения.
        # Обрезаем по первому расширению документа: всё после него — мусор.
        м_расш = re.search(r'^(.*?\.(?:docx?|rtf|txt|pdf|xlsx?|zip|rar))',
                           имя, re.I)
        if м_расш:
            имя = м_расш.group(1)
        имя = re.sub(r'''[\s'"><]+$''', '', имя).strip()
        из.append((имя[:120], m2.group(1).replace('&amp;', '&')))
    return из


def _xlsx_text(blob, строк=8000):
    """Текст из .xlsx без сторонних библиотек: это zip с общими строками и листами.

    Понадобилось для реестров Ростехнадзора: заключения экспертизы промышленной
    безопасности территориальные управления выкладывают именно таблицей, а не
    документом, и там лежит то, чего нет больше нигде — регистрационный номер
    ОПО, класс опасности и перечень оборудования по ИНН эксплуатирующей
    организации. До этого `_ДОК_ФОРМАТ` таблицы просто не пускал, и источник
    был невидим целиком.

    Разбор ручной, без openpyxl: на сервере библиотеки может не оказаться, а
    формат простой. Текст ячеек лежит в `sharedStrings.xml`, а на листе стоят
    ссылки на индексы; числа и даты хранятся прямо в ячейке.
    """
    try:
        import io as _io
        import zipfile
        with zipfile.ZipFile(_io.BytesIO(blob)) as z:
            имена = z.namelist()
            общие = []
            if 'xl/sharedStrings.xml' in имена:
                ss = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
                # <si> может содержать несколько <t> (форматированный текст) —
                # склеиваем их, иначе ячейка рвётся на куски
                for si in re.findall(r'<si>(.*?)</si>', ss, re.S):
                    общие.append(''.join(re.findall(r'<t[^>]*>(.*?)</t>', si, re.S)))
            куски = []
            листы = [n for n in имена if re.match(r'xl/worksheets/sheet\d+\.xml$', n)]
            for лист in sorted(листы):
                xml = z.read(лист).decode('utf-8', 'replace')
                for i, стр in enumerate(re.findall(r'<row[^>]*>(.*?)</row>', xml, re.S)):
                    if i >= строк:
                        break
                    ячейки = []
                    for яч in re.findall(r'<c\b([^>]*)>(.*?)</c>', стр, re.S):
                        атр, тело = яч
                        v = re.search(r'<v>(.*?)</v>', тело, re.S)
                        if 't="s"' in атр and v:
                            try:
                                ячейки.append(общие[int(v.group(1))])
                            except Exception:  # noqa: BLE001
                                pass
                        elif 't="inlineStr"' in атр:
                            ячейки.append(''.join(
                                re.findall(r'<t[^>]*>(.*?)</t>', тело, re.S)))
                        elif v:
                            ячейки.append(v.group(1))
                    if ячейки:
                        # столбцы разделяем ТАБОМ: строка таблицы должна остаться
                        # одной строкой, иначе ФИО, должность и организация
                        # разъезжаются и разбор перестаёт их связывать
                        куски.append('\t'.join(ячейки))
    except Exception:  # noqa: BLE001
        return ''
    из = '\n'.join(куски)
    из = из.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return из.replace('&quot;', '"').replace('&#39;', "'")


def _docx_text(blob):
    """Текст из .docx без сторонних библиотек: это zip с word/document.xml."""
    try:
        import zipfile
        import io as _io
        with zipfile.ZipFile(_io.BytesIO(blob)) as z:
            xml = z.read('word/document.xml').decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return ''
    # абзацы разделяем переводом строки: гриф и подпись стоят разными абзацами,
    # и без разделителя они слипаются в одну кашу
    xml = re.sub(r'</w:p>', '\n', xml)
    return re.sub(r'[ \t]+', ' ', re.sub(r'<[^>]+>', '', xml))


def _раскодировать(raw, ctype=''):
    """Байты страницы в текст С УЧЁТОМ ЗАЯВЛЕННОЙ КОДИРОВКИ.

    САМЫЙ ДОРОГОЙ ДЕФЕКТ ДНЯ: раньше здесь стояло `raw.decode('utf-8',
    'replace')` без разбора кодировки, и на сайтах в windows-1251 кириллица
    гибла ДО всякого разбора — регулярки физически не могли сработать.
    Проверяющий агент показал живьём: на tenderguru.ru страница отдаёт
    charset=windows-1251, при чтении как utf-8 получается 6480 символов-замен и
    ноль контактных окон, а на тех же байтах в cp1251 читается
    «Контактное лицо организатора Гоголев Е. А., zakupki@lorp.ru,
    +7 (4112) 408009 доб. 1287».

    Радиус шире агрегаторов: это ОБЩИЙ краулер сайтов компаний, и примерно 8%
    сайтов базы обходились вслепую. Отсюда часть «на сайте контактов нет».

    Порядок: charset из заголовка, затем из <meta>, затем utf-8, затем cp1251.
    Последний рубеж — если кириллицы в utf-8-варианте подозрительно мало, а в
    cp1251 её много, берём cp1251: сервер мог соврать в заголовке.
    """
    if not raw:
        return ''
    import re as _re

    def _кир(t):
        return len(_re.findall(r'[а-яёА-ЯЁ]', t or ''))

    зая = ''
    m = _re.search(r'charset=["\']?([\w\-]+)', ctype or '', _re.I)
    if m:
        зая = m.group(1).lower()
    if not зая:
        головa = raw[:4000].decode('latin-1', 'replace')
        m = _re.search(r'charset=["\']?([\w\-]+)', головa, _re.I)
        if m:
            зая = m.group(1).lower()
    порядок = []
    if зая:
        порядок.append('cp1251' if зая in ('windows-1251', 'cp1251', 'win-1251')
                       else зая)
    порядок += ['utf-8', 'cp1251']
    лучший, счёт = '', -1
    for код in порядок:
        try:
            t = raw.decode(код, 'replace')
        except Exception:  # noqa: BLE001
            continue
        # штрафуем за символы-замены: именно они и есть погибшая кириллица
        оценка = _кир(t) - t.count('\ufffd') * 2
        if оценка > счёт:
            лучший, счёт = t, оценка
        if код == порядок[0] and t.count('\ufffd') == 0 and _кир(t):
            return t
    return лучший


def _rtf_text(blob):
    r"""Текст из .rtf: снимаем управляющие слова и раскрываем \uNNNN."""
    s = blob.decode('cp1251', 'replace')
    s = re.sub(r'\\u(-?\d+)\??', lambda m: chr(int(m.group(1)) % 65536), s)
    # \'XX — шестнадцатеричный байт, и русский RTF пишет кириллицу ИМЕННО так.
    # Без этой строки разбор отдавал 0% кириллицы: на живом протоколе ЕИС
    # выходило 32337 «символов» вида «\* 02020603050405020304 Times New Roman»,
    # а починенный разбор на том же файле дал живых людей — «Баязитов Данил
    # Шамильевич», «Потапова Оксана Юрьевна». Поймано проверяющим агентом.
    s = re.sub(r"\\'([0-9a-fA-F]{2})",
               lambda m: bytes([int(m.group(1), 16)]).decode('cp1251', 'replace'),
               s)
    s = re.sub(r'\\[a-zA-Z]+-?\d*\s?', ' ', s)
    return re.sub(r'[{}]', ' ', s)


# Предмет закупки, у которого подписант документации — ТЕХНАРЬ.
# Разведка 29.07 показала, почему это важно: гриф «УТВЕРЖДАЮ» ставит не
# «главный инженер вообще», а руководитель ПО ПРЕДМЕТУ закупки. Техзадание на
# пескосоляную смесь утвердил директор филиала, на изучение недр —
# руководитель департамента экологии. Значит и главного энергетика надо искать
# на закупках его зоны: воздух, азот, энергетика, КИП, ремонт оборудования.
_ЗАКУПКА_НАШ_ПРОФИЛЬ = re.compile(
    r'компрессор|воздуходув|осушител|сжат\w*\s+воздух|пневмо|воздухоразделит'
    r'|генератор\w*\s+(?:азот|кислород)|азотн\w+\s+станц|кислородн\w+\s+станц',
    re.I)
_ЗАКУПКА_ТЕХНИЧЕСКАЯ = re.compile(
    r'компрессор|воздуходув|осушител|сжат\w*\s+воздух|пневмо|воздухоразделит'
    r'|генератор\w*\s+(?:азот|кислород)|энергет|электроснабж|теплоснабж'
    r'|котельн|котл\w+|турбин|насос|вентиляц|кондиционир|КИПиА|КИП\s+и\s+А'
    r'|АСУ\s*ТП|автоматизац|ремонт\w*\s+оборудован|техническ\w+\s+обслуживан'
    r'|модернизац\w*\s+оборудован|запасн\w+\s+част|подшипник|электродвигател',
    re.I)


def _pdf_text(blob, страниц=25):
    """Текст из PDF. Раньше PDF пропускались честно, но пропускались — а это
    ровно техдокументация закупок с грифом «УТВЕРЖДАЮ» и годовые отчёты АО,
    где правление и совет директоров названы поимённо.

    Библиотека pypdf на чистом питоне, компилятор не нужен. Проверено на живом
    отчёте АО «Криогенмаш»: 21 страница, 15832 символа, доля кириллицы 1.0 —
    русские шрифты со своей кодировкой она разбирает верно, а это главный риск
    для PDF на русском.

    Сканы (текстового слоя нет) отдают здесь пустоту — и это по-прежнему
    правильный ответ ИМЕННО ДЛЯ ЭТОЙ функции: она читает текстовый слой. Но
    молчание тут больше не конец пути: с 30.07 у `doc_text` есть запасной ход
    через распознавание (`ocr_lib`), и замер показал, почему он нужен — среди
    PDF закупочной документации сканы не исключение, а половина.
    """
    try:
        import pypdf
    except Exception:  # noqa: BLE001
        return ''
    try:
        import io as _io
        r = pypdf.PdfReader(_io.BytesIO(blob))
        куски = []
        for стр in r.pages[:страниц]:
            try:
                куски.append(стр.extract_text() or '')
            except Exception:  # noqa: BLE001
                continue
        return re.sub(r'[ \t]+', ' ', '\n'.join(куски)).strip()
    except Exception:  # noqa: BLE001
        return ''


# Ниже какой длины текстовый слой PDF считаем отсутствующим. У титульного листа
# с грифом это сотни символов; сотня отделяет «пусто» от «что-то есть».
_OCR_ПОРОГ = int(os.environ.get('DOC_OCR_MIN', '200'))
# распознавание можно выключить переменной, если источник заведомо текстовый:
# OCR медленный, и гонять его на тысяче договоров незачем
_OCR_ВКЛ = os.environ.get('DOC_OCR', '1') != '0'


def _pdf_с_ocr(blob, страниц=2):
    """Текстовый слой PDF, а если его нет — распознавание картинки.

    Половина закупочной документации в ЕИС выложена сканами: лист печатают,
    подписывают, кладут в сканер и заливают картинкой. Для `_pdf_text` такой
    файл пуст, и до 30.07 он был для нас невидим — а замер протоколов комиссии
    показал, что сканами оказались ЧЕТЫРЕ документа из шести.

    Порог, а не «пусто»: у сканов часто есть тонкий текстовый слой в пару
    десятков символов (колонтитул, номер листа, штамп электронной подписи), и
    проверка `if not текст` его принимает за прочитанный документ.
    """
    т = _pdf_text(blob)
    if not _OCR_ВКЛ or len((т or '').strip()) >= _OCR_ПОРОГ:
        return т
    try:
        import ocr_lib
        р = ocr_lib.разбор_pdf(blob, слой=т, страниц=страниц)
        нов = (р.get('текст') or '').strip()
        # OCR принимаем только если он дал БОЛЬШЕ слоя: распознавание пустой
        # страницы возвращает шум, и заменять им живой текст нельзя
        if len(нов) > len((т or '').strip()):
            return р['текст']
    except Exception:  # noqa: BLE001
        pass
    return т


def doc_text(url, cap=8000000):
    """Текст документа по ссылке: docx, rtf, txt и PDF (сканы — через OCR).

    КАП ПОДНЯТ с 800 КБ до 8 МБ, и это не косметика. Обрезка применялась к
    БАЙТАМ ДО разбора, а у PDF таблица перекрёстных ссылок лежит В КОНЦЕ файла:
    любой документ тяжелее капа становился нечитаем в принципе. Замерено на
    протоколе ЕИС в 987195 байт — полный файл даёт 2 страницы, обрезанный
    роняет pypdf с PdfStreamError. То же касается docx: это zip, его каталог
    тоже в хвосте.
    """
    try:
        blob = _eis_get(url, raw=True)
    except Exception:  # noqa: BLE001
        return ''
    if not blob:
        return ''
    blob = blob[:cap]
    if blob[:2] == b'PK':
        # И docx, И xlsx — оба zip и оба начинаются с «PK», поэтому таблица
        # молча уходила в разбор Word, не находила word/document.xml и
        # возвращала пустоту. Смотрим, ЧТО внутри, а не как назван файл:
        # расширение врёт (у 33 «документов» из 69 внутри лежал HTML), и
        # Content-Type врёт вместе с ним.
        try:
            import io as _io2
            import zipfile as _zip2
            with _zip2.ZipFile(_io2.BytesIO(blob)) as _z:
                _имена = _z.namelist()
            if any(n.startswith('xl/') for n in _имена):
                return _xlsx_text(blob)
        except Exception:  # noqa: BLE001
            pass
        return _docx_text(blob)
    if blob[:5] == b'{\\rtf':
        return _rtf_text(blob)
    if blob[:4] == b'%PDF':
        return _pdf_с_ocr(blob)
    try:
        текст = blob.decode('utf-8')
    except Exception:  # noqa: BLE001
        текст = blob.decode('cp1251', 'replace')
    # Формат не опознан (не zip, не rtf, не PDF) — значит это может быть архив
    # или бинарь, и декодирование даёт мусор. Поймано на живом прогоне: файл
    # «Документация о закупке ДЗО.rar» отдавал 254 тысячи «символов», начиная
    # с «Rar!», и этот мусор уезжал в модель, съедая вызов и возвращая ноль.
    # Считаем долю печатного: у настоящего документа она близка к единице.
    проба = текст[:4000]
    if проба:
        печатных = sum(1 for c in проба
                       if c.isprintable() or c in '\n\r\t')
        if печатных / len(проба) < 0.85:
            return ''
    return текст


def utverzhdayu(txt):
    """[{person, post}] из блоков «УТВЕРЖДАЮ» документа.

    Что видно на живом титульном листе: гриф, под ним должность в одну-две
    строки, затем подпись «М.Ю. Юнин» или «Юнин М.Ю.». Берём окно после грифа
    и ищем в нём обе формы записи ФИО; должность — по тому же словарю, что и
    везде, чтобы роль легла в общий канон.
    """
    из = []
    for m in _УТВ.finditer(txt or ''):
        окно = (txt or '')[m.end():m.end() + 500]
        фио = ''
        m1 = _ИО_ФАМ.search(окно)
        m2 = _ФАМ_ИО.search(окно)
        # выбираем ту форму, что встретилась РАНЬШЕ: на титульном листе подпись
        # одна, и вторая регулярка может зацепить постороннее сокращение ниже
        if m1 and (not m2 or m1.start() <= m2.start()):
            фио = f'{m1.group(3)} {m1.group(1)}.{m1.group(2)}.'
        elif m2:
            фио = f'{m2.group(1)} {m2.group(2)}.{m2.group(3)}.'
        должность = ''
        # ТЕХНИЧЕСКАЯ должность имеет приоритет: типовой титул звучит как
        # «Заместитель генерального директора — главный инженер», и общий
        # шаблон хватал «генерального директора», теряя ровно то, за чем
        # мы сюда пришли.
        # ФИО из окна убираем ДО поиска должности: шаблон должности берёт до
        # пяти слов и без этого дотягивается до самой подписи («начальник
        # отдела снабжения Петров П.П.»)
        окно_бф = окно
        for _m in (m1, m2):
            if _m:
                окно_бф = окно_бф.replace(_m.group(0), ' ')
        pm = _POST_TECH_RE.search(окно_бф) or _POST_VAL_RE.search(окно_бф)
        if pm:
            должность = _clean_post(pm.group(1))
        if фио or должность:
            из.append({'person': фио, 'post': должность})
        if len(из) >= 4:
            break
    # один и тот же гриф печатают на каждом листе — схлопываем
    свод = {}
    for x in из:
        свод[(x['person'], x['post'])] = x
    return list(свод.values())


def find_zakupki_org(inn):
    """Карточка ОРГАНИЗАЦИИ в реестре ЕИС: контакты заказчика есть даже когда
    активных извещений нет. Прежде мы ходили только в RSS по извещениям, и
    компания без свежих процедур давала ноль контактов."""
    inn = str(inn or '').strip()
    if not inn.isdigit():
        return None
    out = {'inn': inn, 'people': [], 'url': ''}
    try:
        h = _eis_get('https://zakupki.gov.ru/epz/organization/search/results.html'
                     '?searchString=' + inn + '&morphology=on&pageNumber=1')
    except Exception as e:  # noqa: BLE001
        return {'inn': inn, 'error': f'search: {type(e).__name__}: {str(e)[:70]}'}
    m = re.search(r'href="(/epz/organization/view/info\.html\?organizationId=\d+)', h)
    if not m:
        return out
    out['url'] = 'https://zakupki.gov.ru' + m.group(1).replace('&amp;', '&')
    try:
        time.sleep(1.0 + random.uniform(0, 1.0))
        p = _eis_get(out['url'])
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                     re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', p, flags=re.S | re.I)))
        out['people'] = _eis_people(txt)
    except Exception as e:  # noqa: BLE001
        out['error'] = f'card: {type(e).__name__}: {str(e)[:70]}'
    return out


# Профили дельфина с ПРИВАТНЫМИ МОБИЛЬНЫМИ прокси (владелец 29.07). Нужны
# там, где серверный IP помечен: hh отдаёт капчу на обычной выдаче.
# Переопределяется переменной окружения HH_DOLPHIN_PROFILES.
# Только профили, В КОТОРЫХ ВЛАДЕЛЕЦ ВОШЁЛ НА HH (29.07): контакты вакансии
# анонимному посетителю не показывают, поэтому профиль без входа тут бесполезен —
# он вернёт вакансию с пустым contactInfo и мы решим, что контактов нет.
# 829115332 намеренно исключён: входа в нём нет.
# Владелец выдал ТРИ профиля с разными мобильными прокси (829115353,
# 829115344, 829115332), в дефолте лежали только два. Третий добавлен 29.07:
# профили делятся по кругу, и на пакетном прогоне лишний IP снижает и капчу,
# и «HTTP 500» от занятого профиля.
_HH_DOLPHIN_DEF = '829115344,829115353,829115332'
_hh_prof_lock = threading.Lock()
_hh_prof_i = [0]


def _hh_prof_next():
    """Круговой выбор профиля: три мобильных прокси делим между воркерами,
    чтобы не бить с одного IP."""
    with _hh_prof_lock:
        _hh_prof_i[0] += 1
        return _hh_prof_i[0]


_HH_LPR_QUERIES = (
    'главный энергетик', 'главный механик', 'главный инженер',
    'начальник компрессорной станции', 'инженер КИПиА', 'начальник производства',
    'машинист компрессорных установок', 'оператор компрессорной установки')


# Роли, которые контактное лицо вакансии называет ЯВНО. Комментарий к
# телефону — единственное место, где hh говорит, кому звонить.
_HH_ROLE_HINT = re.compile(
    r'инженер|энергетик|механик|технолог|производств|цех|кипиа|асу|техни'
    r'|снабж|закуп|начальник|руководител|директор|главн', re.I)


def _hh_post(comment, vacancy_title):
    """Должность КОНТАКТНОГО ЛИЦА вакансии — честно, а не по заголовку.

    Ловушка, на которой конвейер соврал бы молча: контакт в вакансии «Инженер-
    технолог» — это РЕКРУТЁР, который её ведёт, а не инженер-технолог. Первый же
    боевой прогон дал «Мазурова Ольга, должность инженер-технолог» и
    «Альчина Мария Михайловна, секретарь» — если бы название вакансии шло в
    роль, база наполнилась бы фальшивыми инженерами.
    Роль берём только из комментария к телефону («звонить гл. инженеру»), и
    только если он на роль похож. Сама вакансия остаётся в поле vacancy — как
    повод для разговора, а не как должность человека.

    РАНЬШЕ в отсутствие комментария ставилось «кадры», и это оказалось не
    осторожностью, а утверждением факта, которого у нас нет. Замер 29.07:
    комментарий пуст в 15 случаях из 15, то есть метка ВСЕГДА была выдумкой —
    включая контакт вакансии «Главный энергетик». Цена выдумки прямая: в
    скоринге писем `ROLE_DENY` содержит «кадр» и даёт -1000, так что ложная
    метка вычёркивала из адресатов КАЖДЫЙ hh-контакт, в том числе технического.
    Теперь при пустом комментарии возвращается пустая должность: неизвестное
    честно остаётся неизвестным, а ранжирование само кладёт роль без имени
    между конкретикой и «общим».
    """
    c = (comment or '').strip()
    if c and _HH_ROLE_HINT.search(c):
        return c
    return ''


def hh_lpr_contacts(company, max_vac=8):
    """Контакты из ВАКАНСИЙ компании на hh: ФИО, телефон и комментарий к нему.

    Ценность именно для этой задачи: в вакансии «главный энергетик» или
    «инженер КИПиА» контактным лицом часто идёт сам технарь или его
    руководитель, а комментарий к телефону («звонить гл. инженеру») прямо
    называет роль. Раньше hh использовался только как сигнал «нанимает» —
    страницу вакансии не открывали ни разу.

    Ходим по ПУБЛИЧНОЙ выдаче: api.hh.ru отдаёт с сервера 403 без токена
    приложения, а обычная выдача с серверного IP — капчу. Поэтому вся пачка
    (выдача + страницы вакансий) берётся ОДНОЙ сессией дельфина на мобильном
    прокси: профиль стартует один раз и дальше просто переходит по адресам
    (наводка владельца — старт/стоп на каждый URL стоит десятки секунд и
    упирается в слоты профилей).
    """
    nm = бренд_компании(company.get('name'), company.get('site'))
    if len(nm) < 3:
        return None
    tok = next((t.lower() for t in re.findall(r'[А-Яа-яЁёA-Za-z]{4,}', nm)), '')
    if not tok:
        return None

    def _state(body):
        m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', body or '', re.S)
        if not m:
            return {}
        try:
            import html as _h
            return json.loads(_h.unescape(m.group(1)))
        except Exception:  # noqa: BLE001
            return {}

    def _ids(body):
        """id вакансий из стейта, иначе из разметки (разметку могло обрезать капом)."""
        st = _state(body)
        ids = re.findall(r'"vacancyId"\s*:\s*"?(\d+)', json.dumps(st, ensure_ascii=False)) if st else []
        if not ids:
            ids = re.findall(r'/vacancy/(\d+)', body or '')
        видели, чисто = set(), []
        for i in ids:
            if i not in видели:
                видели.add(i)
                чисто.append(i)
        return чисто

    # ИСКАТЬ НАДО ТОЛЬКО ПО ИМЕНИ КОМПАНИИ: search_field=company_name
    # применяет весь text к полю «название работодателя», и запрос
    # «Уралэлектромедь главный энергетик» не находил ничего. Должности
    # отбираем уже среди вакансий этого работодателя.
    поиск = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(nm)
             + '&search_field=company_name&items_on_page=50')

    def _пачка(urls):
        """Одна дельфин-сессия: первый URL + переходы по остальным."""
        if _NO_BROWSER or not urls:
            return {}
        try:
            import browser_probe as BP
            tokd = _read_secret('DOLPHIN_TOKEN')
            профили = [x for x in re.split(r'[,\s]+',
                       os.environ.get('HH_DOLPHIN_PROFILES', _HH_DOLPHIN_DEF)) if x]
            if not (tokd and профили):
                return {}
            pid = профили[_hh_prof_next() % len(профили)]
            with _SEM_BROWSER:
                return BP.probe({'url': urls[0], 'urls': urls, 'return_html': True,
                                 'html_cap': 2500000, 'urls_cap': max_vac + 1,
                                 'wait_ms': 6000, 'urls_wait_ms': 2500,
                                 'screenshot': False, 'solve': True,
                                 'dolphin_profile': pid, 'dolphin_token': tokd})
        except Exception:  # noqa: BLE001
            return {}

    r = _пачка([поиск])
    body = (r or {}).get('html') or ''
    if '/vacancy/' not in body:
        # Поиск по названию работодателя промахивается, когда бренда нет в
        # уставном имени: у «АКЦИОНЕРНОГО ОБЩЕСТВА КРИОГЕННОГО МАШИНОСТРОЕНИЯ»
        # страница на hh называется «Криогенмаш», и по имени она не находится
        # НИКОГДА. Спрашиваем у выдачи прямой адрес работодателя и открываем
        # его список вакансий — он же и подтверждает, что это та компания.
        eid = ''
        try:
            for u in _serp_urls(f'{nm} site:hh.ru работа в компании', 8):
                m = re.search(r'hh\.ru/employer/(\d+)', u)
                if m:
                    eid = m.group(1)
                    break
        except Exception:  # noqa: BLE001
            eid = ''
        if eid:
            r = _пачка([f'https://hh.ru/employer/{eid}'])
            наш, почему = hh_страница_наша((r or {}).get('html') or '', company)
            if наш:
                body = (r or {}).get('html') or ''
            else:
                # чужой работодатель — лучше ноль, чем чужие контакты в базе
                return {'employer': None, 'vacancies': [], 'contacts': [],
                        'отказ': f'страница работодателя не подтверждена: {почему}'}
    # приоритет — вакансии с технической должностью в названии: именно там
    # контактным лицом идёт технарь, а не отдел кадров
    ключи = ('энергетик', 'механик', 'инженер', 'кипиа', 'кип и а', 'асу',
             'компрессор', 'производств', 'технолог', 'цеха', 'энергет')
    st_all = _state(body)
    названия = {}
    if st_all:
        сырое = json.dumps(st_all, ensure_ascii=False)
        for vid, наз in re.findall(
                r'"vacancyId"\s*:\s*"?(\d+)"?[^{}]{0,400}?"name"\s*:\s*"([^"]{3,120})"',
                сырое):
            названия.setdefault(vid, наз)
    все_id = _ids(body)
    тех = [i for i in все_id
           if any(k in (названия.get(i, '') or '').lower() for k in ключи)]
    ids = (тех + [i for i in все_id if i not in тех])[:max_vac]
    out = {'employer': None, 'vacancies': [], 'contacts': []}
    if not ids:
        return None
    # вторая сессия — сразу все страницы вакансий одним заходом
    r2 = _пачка([f'https://hh.ru/vacancy/{i}' for i in ids])
    страницы = [{'url': (r2 or {}).get('url'), 'html': (r2 or {}).get('html')}]
    страницы += list((r2 or {}).get('pages') or [])
    for стр in страницы:
        vb, url = стр.get('html') or '', стр.get('url') or ''
        if not vb:
            continue
        vv = (_state(vb).get('vacancyView') or {})
        emp = ((vv.get('company') or {}).get('name') or '')
        # Рубеж принадлежности ЗАКРЫТ ПО УМОЛЧАНИЮ. Прежнее условие
        # «if emp and tok not in emp» пропускало страницу, когда имя
        # работодателя не прочиталось из стейта, — и ровно так шесть телефонов
        # кадровиков «Завода Химического и Криогенного машиностроения»
        # (Екатеринбург) осели у АО «Криогенмаш» (Балашиха). Общее слово
        # «криоген» тут ничего не доказывает, поэтому проверяем ИНН, домен или
        # ПОЛНОЕ совпадение названия.
        наш, почему = hh_страница_наша(vb, company)
        if not наш and emp:
            наш = (re.sub(r'[^0-9a-zа-яё]+', '', emp.lower())
                   == re.sub(r'[^0-9a-zа-яё]+', '', nm.lower()))
            почему = 'название совпало полностью' if наш else почему
        if not наш:
            out.setdefault('пропущено', []).append(
                {'url': url, 'работодатель': emp, 'почему': почему})
            continue
        title = vv.get('name') or ''
        out['employer'] = out['employer'] or emp
        out['vacancies'].append({'name': title, 'url': url})
        c = vv.get('contactInfo') or {}
        имя = ' '.join(x for x in (c.get('lastName'), c.get('firstName'),
                                   c.get('middleName')) if x).strip() or (
            c.get('fio') or '').strip()
        почта = (c.get('email') or '').strip().lower()
        тел_список = c.get('phones')
        if isinstance(тел_список, dict):
            тел_список = тел_список.get('phones') or []
        добавлен_номер = False
        for ph in (тел_список or []):
            if not isinstance(ph, dict):
                continue
            цифры = re.sub(r'\D', '', str(ph.get('number') or ''))
            if not цифры:
                continue
            добавлен_номер = True
            out['contacts'].append({
                'person': имя,
                'phone': '+{}{}{}'.format(ph.get('country') or '7',
                                          ph.get('city') or '', цифры),
                'post': _hh_post(ph.get('comment'), title),
                'email': почта, 'url': url, 'vacancy': title})
        # РАНЬШЕ: «if почта and not тел_список» — и человек терялся, когда
        # список телефонов НЕ ПУСТ, но номера в нём нет. У hh это штатный
        # случай: при включённом callTracking приходит {"country":"7"} без
        # number. Проверяющий агент показал на трёх вакансиях КАМАЗа: ФИО есть
        # у всех трёх, номер у одной — двое молча пропадали.
        if (имя or почта) and not добавлен_номер:
            out['contacts'].append({'person': имя, 'phone': '',
                                    'post': _hh_post(None, title),
                                    'email': почта, 'url': url, 'vacancy': title})
    return out if (out['employer'] or out['contacts']) else None


def find_zakupki_supplier(inn, max_cards=6):
    """Контакты компании из закупок, где она ПОСТАВЩИК, а не заказчик.

    Мысль владельца 29.07: «а если исходить от обратного — искать компании,
    которым была поставка от нашей цели?». Это закрывает дыру, которую я
    считал непреодолимой: до сих пор ЕИС спрашивали ТОЛЬКО про заказчика, и
    компания, не подпадающая под 44/223-ФЗ, для нас в ЕИС не существовала
    вовсе. Ровно так вышло с АО «Криогенмаш»: «в ЕИС не заказчик, карточек 0»,
    хотя госзаказчикам он поставляет постоянно.

    Что даёт карточка контракта: блок поставщика с его ИНН, адресом и — вот
    ради чего всё — контактным телефоном и почтой, которые поставщик подал В
    СВОЕЙ ЗАЯВКЕ. Это контакт САМОЙ нашей цели, добытый из чужой закупки.

    Честное ожидание: роль такого контакта обычно сбыт или контрактная служба,
    а не главный инженер. Но для компании, по которой у нас нет ничего, живой
    названный человек с номером — это разница между нулём и зацепкой.

    Побочно карточка называет ЗАКАЗЧИКА, то есть клиента нашей цели. Для
    расширения базы это отдельная тема, здесь мы её не трогаем.
    """
    inn = str(inn or '').strip()
    if not inn.isdigit():
        return None
    out = {'inn': inn, 'cards': [], 'customers': []}
    rss = ''
    for адрес in (
        # supplierTitle, а НЕ searchString: второе ищет свободным текстом по
        # всей карточке, и у КАМАЗа давало ноль контрактов при полной странице
        # по фильтру поставщика. У Ростелекома семь «находок» оказались
        # артефактом — его ИНН буквально входит в НОМЕР контракта.
        'https://zakupki.gov.ru/epz/contract/search/rss.html?supplierTitle='
        + inn + '&morphology=on&fz44=on&contractStageList_0=on'
        + '&contractStageList_1=on&contractStageList_2=on'
        + '&contractStageList_3=on&recordsPerPage=_50',
        # реестр договоров 223-ФЗ мы не спрашивали ВООБЩЕ, а для поставщика
        # госкорпорациям он основной: у Ростелекома там 50 против 7 по 44-ФЗ
        'https://zakupki.gov.ru/epz/contractfz223/search/rss.html?supplierTitle='
        + inn + '&recordsPerPage=_50',
        'https://zakupki.gov.ru/epz/contract/search/rss.html?searchString=' + inn,
    ):
        try:
            куск = _eis_get(адрес)
        except Exception as ex:  # noqa: BLE001
            out['error'] = f'rss: {type(ex).__name__}: {str(ex)[:70]}'
            continue
        if re.search(r'<(?:rss|channel)\b', куск or '', re.I):
            # СОБИРАЕМ СО ВСЕХ РЕЕСТРОВ, А НЕ С ПЕРВОГО ОТВЕТИВШЕГО.
            # Раньше здесь стоял `break`, и реестр договоров 223-ФЗ не
            # спрашивался НИ РАЗУ: 44-ФЗ идёт первым и отвечает всегда.
            # Из-за этого мой замер «клиенты наших целей» получил ноль
            # промышленных заказчиков и я закрыл идею — а по 44-ФЗ заказчик
            # бюджетное учреждение ПО ОПРЕДЕЛЕНИЮ ЗАКОНА, промышленный мог
            # прийти только из 223-го. Проверено на Ростелекоме: реестр 223
            # отдаёт 51 ссылку, а функция возвращала 8 карточек и все 44-ФЗ.
            rss += куск
            out.setdefault('rss_источников', 0)
            out['rss_источников'] += 1
    if not rss:
        out.setdefault('error', 'rss контрактов: ответ не похож на RSS')
        return out
    items = re.findall(r'<item>(.*?)</item>', rss, re.S)
    out['rss_items'] = len(items)
    # чередуем источники, чтобы кап max_cards не съедался первым реестром
    _по_223 = [x for x in items if 'contractfz223' in x]
    _по_44 = [x for x in items if 'contractfz223' not in x]
    items = [x for пара in zip_longest(_по_223, _по_44) for x in пара if x]
    for it in items[:max_cards]:
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
        if not lm:
            continue
        url = lm.group(1)
        # В RSS КОНТРАКТОВ ссылка ОТНОСИТЕЛЬНАЯ («/epz/contract/...»), а в RSS
        # извещений — абсолютная. Из-за этой разницы карточки скачивались с
        # ошибкой «unknown url type», прогон отдавал девять карточек и ноль
        # контактов, и это выглядело как пустой источник.
        if url.startswith('/'):
            url = 'https://zakupki.gov.ru' + url
        карта = {'url': url}
        try:
            h = _eis_get(url)
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                         re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                flags=re.S | re.I)))
            # Блок поставщика: берём окно ПОСЛЕ подписи и только если рядом
            # стоит НАШ ИНН. Без этой проверки в контакты уехал бы заказчик —
            # он на той же странице и выше по тексту.
            люди = []
            for m in re.finditer(r'(?:Информация о поставщик\w+|Поставщик\w*|'
                                 r'Сведения о поставщик\w+)(.{0,1600})', txt, re.I):
                окно = m.group(1)
                if inn not in окно:
                    continue
                люди += _eis_people(окно)
                if not люди:
                    # подписи «Контактное лицо» может не быть, но телефон и
                    # почта в блоке есть — берём их без имени, чем терять
                    поч = [x.lower() for x in EMAIL_RE.findall(окно)
                           if not _is_junk_email(x)]
                    тм = next(phones_in(окно), None)
                    if поч or тм:
                        люди.append({'person': '', 'post': '',
                                     'email': (поч[0] if поч else ''),
                                     'phone': (тм.group(0).strip() if тм else '')})
                break
            карта['people'] = люди
            зм = re.search(r'Заказчик\s*[:\-]?\s*([^,;]{6,120})', txt)
            if зм:
                карта['customer'] = зм.group(1).strip()
                out['customers'].append(карта['customer'])
        except Exception as ex:  # noqa: BLE001
            карта['error'] = f'{type(ex).__name__}: {str(ex)[:60]}'
        out['cards'].append(карта)
        time.sleep(1.0 + random.uniform(0, 0.8))
    return out


def find_zakupki_contacts(inn, max_cards=12):
    """Контакты из закупок ЕИС (директива владельца 2026-07-23). МЕХАНИКА:
    (1) RSS-поиск извещений по ИНН заказчика: /epz/order/extendedsearch/rss.html?searchString=ИНН
    (2) по ссылке каждого извещения открываем КАРТОЧКУ закупки, в ней обязательный блок
        «Контактная информация»: ФИО контактного лица, email, телефон (это снабженец/ОМТС)
    (3) тянем: ФИО + email + телефон + название закупки + ссылку карточки (source_url).
    Двойная ценность: живой контакт закупщика + сигнал «покупает» (если предмет - наше)."""
    inn = str(inn or '').strip()
    if not inn.isdigit():
        return None
    try:
        # Этапы af/ca/pc/pa: без них выдача показывает только АКТУАЛЬНЫЕ
        # процедуры, и компания, закупавшая компрессор год назад, давала ноль —
        # хотя контакт снабженца в завершённой закупке тот же самый.
        rss = _eis_get('https://zakupki.gov.ru/epz/order/extendedsearch/rss.html?searchString='
                       + inn + '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on'
                       + '&recordsPerPage=_50&sortBy=UPDATE_DATE')
    except Exception as e:  # noqa: BLE001
        return {'inn': inn, 'error': f'rss: {type(e).__name__}: {str(e)[:80]}'}
    items = re.findall(r'<item>(.*?)</item>', rss, re.S)
    # Пустой список — не всегда «нет закупок»: ЕИС отдаёт HTML-заглушку при
    # лимите или ошибке, и раньше это молча уходило в резюм как успех, закрывая
    # ИНН навсегда. Считаем результатом только похожий на RSS ответ.
    if not items and not re.search(r'<(?:rss|channel)\b', rss or '', re.I):
        return {'inn': inn, 'error': 'rss: ответ не похож на RSS (заглушка/лимит)'}
    out = {'inn': inn, 'rss_items': len(items), 'cards': []}
    for it in items[:max_cards]:
        lm = re.search(r'<link>\s*(\S+?)\s*</link>', it, re.S)
        tm = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', it, re.S)
        if not lm:
            continue
        url = lm.group(1)
        card = {'url': url, 'title': re.sub(r'\s+', ' ', (tm.group(1) if tm else ''))[:160]}
        try:
            h = _eis_get(url)
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                         re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
            # ВСЕ контактные лица блока с должностями, а не одно ФИО и один
            # телефон со всей страницы: в 44-ФЗ рядом с «Контактным лицом»
            # стоит «Ответственное должностное лицо» с должностью, и это как
            # раз путь к технарю. Первый человек остаётся в старых полях —
            # чтобы вызывающий код, читающий card['phone'], не сломался.
            # ПРЕДМЕТ закупки берём со страницы, а не из заголовка RSS: там
            # только способ и номер («Иной способ №31603811035»), предмета нет
            # ВООБЩЕ. Проверено глазами на десяти карточках — отбор по предмету
            # из-за этого отсекал все 590 карточек прогона до единой.
            # «закупк\w+» НЕ ловит «закупок»: в родительном множественного у
            # слова беглая гласная. Грабля от второй сессии — у них такой
            # шаблон терял все счётчики, кроме оканчивающихся на 1–4
            # («22 закупки» ловилось, «46 закупок» нет). Пишем основу короче.
            пм = re.search(r'(?:Наименование|Предмет|Объект)\s+(?:закуп\w+|'
                           r'договор\w+|контракт\w+)\s*[:\-]?\s*(.{6,220})',
                           txt, re.I)
            card['subject'] = (пм.group(1).strip() if пм else '')
            # ДОКАЗАТЕЛЬСТВО ПРИВЯЗКИ, а не «нашлось по запросу». Страница уже
            # скачана и разобрана — грех не проверить: RSS-поиск по ИНН выдаёт
            # и карточки уполномоченных органов, где наш заказчик лишь упомянут.
            # Прежний брак источника zakupki:eis (телефон площадки под видом
            # телефона компании) вырос ровно из отсутствия этой строки.
            card['inn_на_странице'] = bool(inn in txt)
            люди = _eis_people(txt)
            card['people'] = люди
            if люди:
                card['contact_person'] = люди[0].get('person') or ''
                card['post'] = люди[0].get('post') or ''
                if люди[0].get('email'):
                    card['email'] = люди[0]['email']
                if люди[0].get('phone'):
                    card['phone'] = люди[0]['phone']
        except Exception as e:  # noqa: BLE001
            card['error'] = f'{type(e).__name__}: {str(e)[:60]}'
        out['cards'].append(card)
        time.sleep(1.0 + random.uniform(0, 1.0))
    return out


_VK_PIN_PROFILE = os.environ.get('VK_DOLPHIN_PROFILE', '829115401')  # профиль, к IP которого привязан VK_TOKEN_USER


def _vk_api_via_dolphin(method, params, token):
    """Вызов VK API через дельфин. IP у ВСЕХ профилей один (владелец 2026-07-23) -> токен,
    привязанный к этому IP, работает через ЛЮБОЙ профиль. Ретраим по РАЗНЫМ профилям
    (обходим флапающий отдельный) до валидного ответа. Возврат: dict VK-ответа или {}."""
    import browser_probe as BP
    tokd = _read_secret('DOLPHIN_TOKEN')
    params = dict(params); params.update(access_token=token, v='5.199')
    u = f'https://api.vk.com/method/{method}?' + urllib.parse.urlencode(params)
    # ТОЛЬКО закреплённый VK-профиль: токен привязан к ЕГО IP (владелец: этот профиль по IP
    # не трогаем, остальным меняем). Один профиль -> не плодим окна. Стоп ПОСЛЕ вызова.
    pid = _VK_PIN_PROFILE
    last = {}
    errs = []   # ГРОМКО (владелец): каждый отказ дельфин-пути фиксируем, не глотаем
    for _try in range(2):   # ретрай тем же профилем (дельфин интермиттентный)
        try:
            r = BP.probe({'url': u, 'return_html': True, 'html_cap': 200000, 'wait_ms': 2500,
                          'screenshot': False, 'dolphin_profile': pid, 'dolphin_token': tokd})
            if r.get('error'):
                errs.append(f'probe:{str(r["error"])[:60]}')
            # разбор: text и html-стрип раздельно; raw_decode берёт ПЕРВЫЙ валидный объект
            # (в склейке text+html JSON встречается дважды -> 'Extra data' у json.loads)
            d = None
            for cand in ((r.get('text') or ''), re.sub(r'<[^>]+>', ' ', r.get('html') or '')):
                st = cand.find('{')
                if st < 0:
                    continue
                try:
                    d, _end = json.JSONDecoder().raw_decode(cand[st:])
                    break
                except Exception as pe:  # noqa: BLE001
                    errs.append(f'parse:{type(pe).__name__}:{str(pe)[:40]}')
            if d is not None:
                if 'response' in d or (d.get('error') or {}).get('error_code') == 5:
                    last = d; break
                if d.get('error'):
                    errs.append(f'vk-api:{(d["error"] or {}).get("error_msg", "")[:60]}')
                last = d
            elif not r.get('error'):
                errs.append('probe:пустой ответ (нет JSON)')
        except Exception as e:  # noqa: BLE001
            errs.append(f'exc:{type(e).__name__}:{str(e)[:50]}')
    try:
        BP.dolphin_stop(pid, token=tokd)   # закрыть профиль после VK-вызова
    except Exception:  # noqa: BLE001
        pass
    if not last and errs:
        last = {'_err': ' | '.join(errs[-2:])}
    return last


# Ссылка на сообщество в разметке сайта: footer, шапка, блок соцсетей.
# Ловим и vk.com, и vk.ru, и m.vk.com; служебные пути (share, away, id123)
# отсекаем — нам нужен слаг сообщества.
_VK_LINK_RE = re.compile(
    r'(?:https?:)?//(?:m\.|www\.)?vk\.(?:com|ru)/(?!share|away|widget|video|id\d)'
    r'([A-Za-z0-9_.]{2,64})', re.I)
_VK_SLUG_DENY = {'vk', 'feed', 'im', 'login', 'help', 'about', 'dev', 'apps',
                 'search', 'audio', 'photo', 'wall', 'topic', 'club', 'public',
                 # ВИДЖЕТ И ПИКСЕЛЬ. На сайте с виджетом ВК в <head> стоит
                 # «//vk.com/js/api/openapi.js», а счётчик ретаргетинга бьёт в
                 # «vk.com/rtrg?p=...». Оба матчатся как слаг и стоят в разметке
                 # ВЫШЕ настоящей ссылки в подвале, а поиск берёт ПЕРВОЕ
                 # совпадение — то есть реальная группа не находилась вовсе.
                 # Замер 29.07 на 60 компаниях с кэшем: три мусорных слага,
                 # расширение списка возвращает 4 группы (26 -> 30).
                 'js', 'rtrg', 'widget', 'share', 'away', 'doc', 'docs',
                 'images', 'img', 'static'}


def vk_slug_from_site(company):
    """Слаг сообщества со СТРАНИЦЫ САЙТА компании.

    Зачем в обход groups.search: поиск сообществ доступен только
    пользовательскому токену, а его VK этому приложению выдаёт максимум на
    сутки и без refresh — значит владельцу пришлось бы логиниться каждый день.
    Ссылка на VK при этом лежит в подвале почти каждого сайта, а сами страницы
    у нас уже скачаны в кэш (pagecache), так что путь бесплатный: слаг из
    разметки -> groups.getById сервисным ключом, который работает и так.
    """
    inn = str(company.get('inn') or '')
    html = ''
    # 1) кэш скачанных страниц — сети не трогаем вовсе
    кэш = os.path.join(os.environ.get('PAGECACHE_DIR',
                                      r'C:\seostat\drop\pagecache'), f'{inn}.json.gz')
    if inn and os.path.exists(кэш):
        try:
            import gzip
            with gzip.open(кэш, 'rb') as f:
                d = json.loads(f.read().decode('utf-8', 'replace'))
            html = ' '.join((p.get('html') or '') for p in (d.get('pages') or []))
        except Exception:  # noqa: BLE001
            html = ''
    # 2) кэша нет — одна закачка главной
    if not html:
        сайт = str(company.get('site') or '').strip()
        if not сайт:
            return ''
        if not сайт.startswith('http'):
            сайт = 'http://' + сайт
        try:
            html, _m, _mt = _fetch_site(сайт)
        except Exception:  # noqa: BLE001
            return ''
    for m in _VK_LINK_RE.finditer(html or ''):
        слаг = m.group(1).strip('.').lower()
        if слаг and слаг not in _VK_SLUG_DENY and not слаг.isdigit():
            return слаг
    return ''


# ---------------------------------------------------------------- руководство
# Разбор страниц «Руководство»/«Менеджмент филиала» ПО РАЗМЕТКЕ, а не по плоскому
# тексту. Причина — ловушка В2 из engineers-lens: должность и телефон лежат в
# одной ячейке таблицы, ФИО в соседней, и парсер, идущий по порядку текста,
# смещает привязку на одного человека. Тег-стрип эту структуру уничтожает.
_TR_RE = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.S | re.I)
_TD_RE = re.compile(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', re.S | re.I)
# карточки: типовые блоки сотрудника в вёрстке без таблиц
_CARD_RE = re.compile(
    r'<(?:div|li|article|section)\b[^>]*'
    r'(?:class|id)="[^"]*(?:person|employee|staff|manager|leader|rukovod|card|item|'
    r'people|team|contact)[^"]*"[^>]*>(.*?)</(?:div|li|article|section)>',
    re.S | re.I)
# фамилия капсом — распространённая вёрстка таблиц руководства («КОРОТКИХ
# Сергей Александрович» на yupgpz.ru): без этой формы в базу уезжали только
# имя с отчеством, без фамилии
_ФИО_ПОЛН = re.compile(
    r'\b((?:[А-ЯЁ][а-яё]{2,}|[А-ЯЁ]{3,})\s+[А-ЯЁ][а-яё]{2,}'
    r'(?:\s+[А-ЯЁ][а-яё]{2,})?)\b')
_ФИО_ИНИЦ = re.compile(r'\b([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.?)')
_ЧИСТ_ТЕГ = re.compile(r'<[^>]+>')


def _текст(html):
    s = _ЧИСТ_ТЕГ.sub(' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html or '',
                                  flags=re.S | re.I))
    s = s.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"')
    return re.sub(r'\s+', ' ', s).strip()


# Отчество — самый надёжный признак, что это человек, а не два слова с большой
# буквы подряд. Без него «Формула Дома», «Работниками Предприятия» и
# «Обязанности Оперативное» проходили как ФИО (поймано глазами на первом же
# прогоне: 317 «людей», среди них куски маркетингового текста).
_ОТЧЕСТВО = re.compile(r'(?:ович|евич|ьич|иевич|овна|евна|ична|инична|кызы|оглы)$',
                       re.I)
# должность, прилипшая к ФИО СЗАДИ: «Виктор Викторович Начальник» уезжал в базу
# как имя человека (11 таких записей на 14.08), потому что проверка на отчество
# срабатывала раньше и возвращала кандидата целиком. Режем только хвост: спереди
# такое слово бывает настоящей фамилией («Бухгалтер Яна Евгеньевна» — живая
# запись из списка РТН).
_СЛУЖ_В_ФИО = re.compile(
    r'^(?:начальник\w*|заместител\w*|директор\w*|руководител\w*|менеджер\w*'
    r'|инженер\w*|специалист\w*|главн\w*|мастер\w*|эксперт\w*|экономист\w*)$', re.I)
# слова, которых в ФИО не бывает; дополняют _FIO_STOP, там термины страниц ЕИС
_НЕ_ИМЯ = re.compile(
    r'предприят|работник|обязанн|формул|оперативн|компан|общест|завод|фабрик'
    r'|комбинат|холдинг|групп|систем|решени|услуг|продукц|оборудован|проект'
    r'|управлен|департамент|служб|отдел|участок|цех|филиал|представит'
    r'|водоканал|энерго|нефт|газ|строй|торг|пром\b', re.I)


def _фио(текст):
    """ФИО из куска текста. Строгий отбор: два слова с большой буквы подряд
    встречаются в вёрстке постоянно, поэтому принимаем либо форму с отчеством,
    либо «Фамилия И.О.», либо два слова, ни одно из которых не похоже на
    название организации или на служебное слово."""
    for rx in (_ФИО_ПОЛН, _ФИО_ИНИЦ):
        for m in rx.finditer(текст or ''):
            кандидат = m.group(1).strip()
            if _FIO_STOP.search(кандидат) or _НЕ_ИМЯ.search(кандидат):
                continue
            слова = кандидат.split()
            while len(слова) > 1 and _СЛУЖ_В_ФИО.match(слова[-1]):
                слова.pop()
            if слова and слова[0].isupper() and len(слова[0]) > 2:
                слова[0] = слова[0].capitalize()   # «КОРОТКИХ» -> «Коротких»
            кандидат = ' '.join(слова)
            # с отчеством — принимаем сразу
            if any(_ОТЧЕСТВО.search(w) for w in слова):
                return кандидат
            # Три слова БЕЗ отчества — почти всегда к ФИО прилип предлог места
            # или должности: «Руководитель представительства в Москве Тимошенко
            # Анатолий» давало «Москве Тимошенко Анатолий» (поймано глазами на
            # карточке Себряковцемента). Берём последние два слова.
            # НО НЕ У ФОРМЫ С ИНИЦИАЛАМИ: там третий «токен» — это ВТОРОЙ
            # ИНИЦИАЛ, и обрезка съедала саму ФАМИЛИЮ. «Контактное лицо
            # организатора Гоголев Е. А.» давало «Е. А.», а живьём на прогоне
            # 29.07 это стоило контакта на tenderguru.ru/tender/77192897:
            # человек уехал в базу как «Б. Б.» — с настоящей почтой
            # csp_shvsm@mail.ru и телефоном +7 (4922) 541290, но без фамилии.
            # Прилипнуть спереди к этой форме нечему: регулярка _ФИО_ИНИЦ
            # начинается ровно с фамилии, поэтому режем только там, где точек
            # нет вовсе — то есть у формы из трёх ПОЛНЫХ слов.
            if len(слова) == 3 and '.' not in кандидат:
                кандидат = ' '.join(слова[-2:])
                слова = слова[-2:]
            # «Фамилия И.О.» — тоже однозначно человек
            if len(слова) >= 2 and '.' in слова[-1]:
                return кандидат
            # Два слова с большой буквы БЕЗ отчества и без инициалов не
            # принимаем. Правило стоило нам редких иностранных имён вроде
            # «Калимерис Василиос», но без него в людей уезжали «Технополис
            # Москва» и «Сертификаты Наши» — поймано глазами на прогоне.
            # Ложный человек в базе дороже пропущенного: по нему звонят.
    return ''


# страницы, где «люди» это соискатели и HR, а не руководство
_НЕ_СТРАНИЦА = re.compile(r'/(?:vacanc|vakans|career|karier|rabota|job|hr)', re.I)


def _блоки(html):
    """Куски разметки, каждый — про ОДНОГО человека: строки таблиц, затем карточки.

    Порядок важен: если страница табличная, карточный разбор на ней даст мусорные
    пересечения, поэтому таблицы имеют приоритет и карточки берутся только когда
    строк не нашлось.
    """
    строки = [(m.group(1), m.start()) for m in _TR_RE.finditer(html or '')]
    годные = [(s, p) for s, p in строки if _фио(_текст(s))]
    if годные:
        return [('таблица', s, p) for s, p in годные]
    карточки = [(m.group(1), m.start()) for m in _CARD_RE.finditer(html or '')]
    return [('карточка', c, p) for c, p in карточки if _фио(_текст(c))]


# Заголовок раздела над карточкой человека. Нужен там, где у самой карточки
# должности нет: на ozm.ru «Титова Светлана Васильевна» стоит под заголовком
# «Коммерческий отдел», и без него человек уезжал в базу с пустой должностью и
# пустой ролью (1535 таких записей на 14.08). Отдел — не должность, но для
# письма он и решает: по нему видно, к кому мы обращаемся.
_ЗАГОЛОВОК_RE = re.compile(
    r'<(?:h[1-6]|strong|b|legend|caption|div|p|td|span|li)\b[^>]*>\s*([^<]{4,70}?)\s*</',
    re.I)
# только слова-подразделения целиком: по обрывкам вроде «склад» в рубрику
# уезжали пункты каталога («Складские стеллажи» — поймано на ozm.ru)
_ОТДЕЛ_СЛОВА = re.compile(
    r'\b(?:отдел\w*|служб\w*|управлени\w*|дирекци\w*|департамент\w*'
    r'|бухгалтери\w*|цех\w*|приёмн\w*|приемн\w*)\b', re.I)
# заголовки-рубрикаторы: слово «отдел» в них есть, а отдела за ними — нет
_НЕ_ОТДЕЛ = re.compile(
    r'руководител\w*\s+отдел|начальник\w*\s+отдел|сотрудник|контакт|команда'
    r'|структур|наши\b|все\s|список|перечень', re.I)
# рубрикатор — заголовок-обобщение, который печатают ПЕРЕД группой карточек и
# который затекает в текст первой из них; вырезаем только такие, а не любые
# заголовки: в тех же тегах на странице лежит и личная должность человека
_РУБРИКАТОР = re.compile(
    r'(?:руководител\w*|начальник\w*)\s+отделов\b|сотрудник|команда|структур'
    r'|наши\b|список|перечень', re.I)


def _разделы(html):
    """[(позиция, заголовок, годен_как_должность)].

    Негодные тоже нужны: рубрикатор «Руководители отделов» попадает в текст
    карточки и уезжал в должность («Руководители отделов Начальник отдела
    продаж» — поймано на ozm.ru), поэтому такие заголовки мы из карточки
    вырезаем, а как должность не ставим.
    """
    из = []
    for m in _ЗАГОЛОВОК_RE.finditer(html or ''):
        t = re.sub(r'\s+', ' ', m.group(1)).strip(' .:;–—-')
        if len(t) < 4 or not _ОТДЕЛ_СЛОВА.search(t) or _фио(t):
            continue
        из.append((m.start(), t, not _НЕ_ОТДЕЛ.search(t)))
    return из


def people_from_html(html, url=''):
    # со страниц вакансий люди тоже извлекаются, но это соискатели и кадровики,
    # а не руководство — на прогоне оттуда приехали «Обязанности Оперативное»
    if url and _НЕ_СТРАНИЦА.search(url):
        return []
    """[{person, post, phone, email, kind}] со страницы руководства.

    Внутри блока (строка таблицы / карточка) привязка уже однозначна: чей блок —
    того и должность с телефоном. Именно поэтому режем по разметке.
    """
    люди = []
    разделы = _разделы(html)
    заголовки = sorted({t for _p, t, _g in разделы if _РУБРИКАТОР.search(t)},
                       key=len, reverse=True)
    for вид, блок, поз in _блоки(html):
        txt = _текст(блок)
        фио = _фио(txt)
        if not фио:
            continue
        # должность ищем в ТОМ ЖЕ блоке и вырезаем из неё само ФИО, чтобы
        # «Главный инженер Петров Игорь» не осело в должность целиком
        без_фио = txt.replace(фио, ' ')
        for з in заголовки:      # рубрикатор страницы, попавший внутрь карточки
            без_фио = без_фио.replace(з, ' ')
        pm = _POST_VAL_RE.search(без_фио)
        тел = ''
        for m in phones_in(txt):
            тел = re.sub(r'\s+', ' ', m.group(0)).strip()
            break
        доб = _EXT_RE.search(txt)
        if тел and доб:
            тел = f'{тел} {доб.group(0)}'
        em = [x.lower() for x in EMAIL_RE.findall(блок) if not _is_junk_email(x)]
        if not (pm or тел or em):
            continue
        должность = _clean_post(pm.group(1)) if pm else ''
        if not должность:
            # рубрика МОЖЕТ ЛЕЖАТЬ ВНУТРИ карточки: обёртка секции у ozm.ru
            # начинается раньше заголовка, и «Коммерческий отдел» оказывается
            # первыми словами блока
            внутри = [t for _p, t, g in разделы if g and txt.startswith(t)]
            # 4000 знаков — предохранитель от размазывания: если ближайший
            # заголовок далеко, между ним и карточкой почти наверняка была
            # своя рубрика, которую разбор не увидел, и человек получил бы
            # чужой отдел
            если_выше = [t for p, t, g in разделы if g and 0 <= поз - p <= 4000]
            if внутри:
                должность = внутри[0]
            elif если_выше:
                должность = если_выше[-1]
        люди.append({'person': фио, 'post': должность,
                     'phone': тел, 'email': (em[0] if em else ''),
                     'kind': вид, 'url': url})
    # один человек может встретиться и в шапке, и в таблице — схлопываем по ФИО,
    # оставляя запись с наибольшим числом заполненных полей
    лучшие = {}
    for ч in люди:
        к = ч['person'].lower()
        вес = sum(1 for п in ('post', 'phone', 'email') if ч.get(п))
        if к not in лучшие or вес > лучшие[к][0]:
            лучшие[к] = (вес, ч)
    return [v[1] for v in лучшие.values()]


# ссылки на страницы филиалов/подразделений — вход в обход группы (А3)
_BRANCH_HINTS = ('filial', 'филиал', 'branch', 'otdelen', 'отделен', 'predstavit',
                 'представит', 'region', 'регион', 'podrazdelen', 'подразделен',
                 'menedzhment', 'менеджмент', 'rukovodstvo', 'руководств',
                 'struktura', 'структур', 'management')


def branch_links(html, dom):
    """URL страниц филиалов/подразделений с одной страницы. Для холдинга это и
    есть вход: список филиалов -> страница руководства каждого."""
    из = []
    for m in re.finditer(r'href="([^"]+)"', html or ''):
        l = m.group(1)
        if l.startswith(('mailto:', 'tel:', '#', 'javascript:')):
            continue
        ll = l.lower()
        if _STATIC_EXT_RE.search(ll) or not any(h in ll for h in _BRANCH_HINTS):
            continue
        full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/" + l}'
        if _domain(full) == dom and full not in из:
            из.append(full)
    return из


def find_vk_group_contacts(company):
    """VK-группа компании (директива владельца 2026-07-23: 70% МСБ живёт в VK).
    groups.search по имени -> верификация (сайт группы == известный сайт компании ИЛИ
    токены имени в названии/описании) -> контакты: блок «Контакты» группы (люди с РОЛЯМИ),
    email/телефоны из описания. Источник: vk-group + ссылка на группу."""
    # ДВА токена, и порядок важен. VK_TOKEN_USER лежит в runner-secrets и выдан
    # когда-то в браузере — он привязан к чужому IP и с сервера отвечает
    # «access_token was given to another ip address». VK_TOKEN — сервисный ключ
    # приложения, к IP не привязан и с сервера работает (проверено 29.07:
    # groups.getById с fields=contacts отдаёт данные). Поэтому пользовательский
    # держим первым только ради groups.search, а при отказе авторизации
    # автоматически переходим на сервисный, вместо того чтобы терять компанию.
    tok_user = _read_secret('VK_TOKEN_USER')
    tok_srv = _read_secret('VK_TOKEN')
    tok = tok_user or tok_srv
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|КАО|ГК)\s+', '', str(company.get('name') or '')
                ).strip().strip('"«»')
    if not (tok and len(nm) >= 3):
        return None

    # По умолчанию БЕЗ дельфина. Проверено 29.07 с сервера: имеющийся VK_TOKEN —
    # СЕРВИСНЫЙ ключ приложения, он не привязан ни к какому IP и с серверного
    # адреса работает (groups.getById и users.get отвечают «ок»). Дельфин же
    # завязан на профиль 829115401, у которого протух прокси, — включать его по
    # умолчанию значит гарантированно ломать путь. Вернуть можно VK_USE_DOLPHIN=1.
    _use_dolph = bool(os.environ.get('VK_USE_DOLPHIN', '0') == '1')
    _vk_last_err = {'v': ''}   # ГРОМКО: причина последнего отказа VK-пути

    def _зов(method, token, prm):
        if _use_dolph:
            return _vk_api_via_dolphin(method, dict(prm), token)
        p2 = dict(prm)
        p2.update(access_token=token, v='5.199')
        u = f'https://api.vk.com/method/{method}?' + urllib.parse.urlencode(p2)
        return json.loads(_DIRECT.open(
            urllib.request.Request(u, headers={'User-Agent': VC.UA}), timeout=20).read())

    def _vk(method, **prm):
        d = _зов(method, tok, prm)
        # токен привязан к чужому IP — молча повторяем сервисным ключом
        сооб = ((d.get('error') or {}).get('error_msg') or '') if isinstance(d, dict) else ''
        if сооб and 'authorization failed' in сооб.lower() and tok_srv and tok_srv != tok:
            d = _зов(method, tok_srv, prm)
        if d.get('_err'):
            _vk_last_err['v'] = d['_err']
        elif d.get('error'):
            _vk_last_err['v'] = f"vk-api:{(d['error'] or {}).get('error_msg', '')[:60]}"
        return d.get('response')

    def _имена(конт):
        """Достать ФИО по user_id блока контактов — ОДНИМ вызовом на группу.

        В блоке «Контакты» сообщества ВК у человека есть подпись должности
        («и.о. Директора по персоналу», «Пресс-секретарь») и user_id, а имени
        нет. Раньше user_id извлекался и тут же выбрасывался — в базу человек
        уезжал как должность без имени, то есть звонить было некому. Один
        users.get превращает такую запись в «ФИО + должность».
        """
        ids = [str(c.get('user_id')) for c in конт if c.get('user_id')]
        if not ids:
            return
        try:
            люди = _vk('users.get', user_ids=','.join(ids[:20])) or []
        except Exception:  # noqa: BLE001
            return
        по_ид = {}
        for u in (люди if isinstance(люди, list) else []):
            if not isinstance(u, dict):
                continue
            фио = ' '.join(x for x in ((u.get('first_name') or '').strip(),
                                       (u.get('last_name') or '').strip()) if x)
            if фио:
                по_ид[str(u.get('id'))] = фио
        # Не всякое имя из users.get — человек. Компании заводят аккаунты,
        # названные собой: прогон 29.07 вернул «Mezhdunarodny Kontsern
        # Dorkhan» и «Stil Tekhnolodzhi» как ФИО контактных лиц. Это витрина,
        # а не человек: звать по такому имени некого. Отбрасываем всё, что
        # совпадает с названием компании, — сравниваем по латинице, потому что
        # VK отдаёт имена в транслите.
        def _не_человек(фио):
            низ = re.sub(r'[^a-zа-яё]', '', (фио or '').lower())
            комп = re.sub(r'[^a-zа-яё]', '', (nm or '').lower())
            if not низ:
                return True
            if комп and len(комп) >= 5 and (комп[:8] in низ or низ[:8] in комп):
                return True
            # удалённая страница ВК отдаётся как имя «DELETED» / «BANNED»
            if низ in ('deleted', 'banned', 'deactivated'):
                return True
            # два одинаковых слова («Ilya Ilya») — заглушка, а не имя
            сл = (фио or '').split()
            return len(сл) >= 2 and сл[0].lower() == сл[1].lower()

        for c in конт:
            if c.get('user_id') and not c.get('person'):
                кто = по_ид.get(str(c['user_id']), '')
                c['person'] = '' if _не_человек(кто) else кто

    # СНАЧАЛА ссылка с сайта: она точнее поиска по названию (никаких тёзок) и
    # не требует пользовательского токена. Поиск остаётся запасным вариантом.
    слаг = ''
    try:
        слаг = vk_slug_from_site(company)
    except Exception:  # noqa: BLE001
        слаг = ''
    if слаг:
        по_слагу = _vk('groups.getById', group_ids=слаг,
                       fields='contacts,site,description') or {}
        груп = (по_слагу.get('groups') if isinstance(по_слагу, dict) else None) or (
            по_слагу if isinstance(по_слагу, list) else [])
        if груп:
            info = груп[0]
            # РУБЕЖ ПРИНАДЛЕЖНОСТИ. Ссылка на сообщество, стоящая на сайте
            # компании, НЕ доказывает, что сообщество — её. Живой пример с
            # прогона 29.07: ИНН 7422000795 со своего сайта ссылается на
            # хоккейный клуб «Маяк-Гранит», который он спонсирует, и в базу
            # поехали «старший по выездным матчам» и «фотограф/видеооператор».
            # Такая же история с медцентром у другой компании. Требуем
            # доказательства: домен сообщества совпал с доменом компании ЛИБО
            # имя компании читается в названии/описании группы. Рубеж закрыт
            # по умолчанию — не подтвердилось, значит не наша.
            _гдом = _domain(str(info.get('site') or '')) if info.get('site') else ''
            _наш = site_domain(company.get('site') or '')
            _низ = ' '.join(str(info.get(k) or '')
                            for k in ('name', 'description')).lower()
            _ток = [t for t in re.findall(r'[а-яёa-z]{4,}', nm.lower())][:3]
            if not ((_гдом and _наш and _гдом == _наш)
                    or (_ток and all(t in _низ for t in _ток[:2]))):
                _bump('vk_чужая_группа')
                return {'error': f'vk:группа {слаг} не подтверждена как наша '
                        f'(домен {_гдом or "-"} против {_наш or "-"})'}
            blob = ' '.join(str(info.get(k) or '')
                            for k in ('name', 'description', 'site'))
            emails = [x.lower() for x in EMAIL_RE.findall(blob)]
            phones = sorted({re.sub(r'[\s\-()]', '', m1.group(0))
                             for m1 in phones_in(blob)})[:4]
            cont = []
            for c in (info.get('contacts') or [])[:8]:
                if not isinstance(c, dict):
                    continue
                cont.append({'desc': c.get('desc') or '', 'phone': c.get('phone') or '',
                             'email': (c.get('email') or '').lower(),
                             'user_id': c.get('user_id')})
                if c.get('email'):
                    emails.append(c['email'].lower())
                if c.get('phone'):
                    phones.append(re.sub(r'[\s\-()]', '', c['phone']))
            if emails or phones or cont:
                _имена(cont)
                _bump('vk_ok')
                return {'group': слаг, 'url': f'https://vk.com/{слаг}',
                        'verified_by': 'site-link', 'emails': sorted(set(emails))[:4],
                        'phones': sorted(set(phones))[:4], 'contacts': cont,
                        'group_site': _domain(str(info.get('site') or ''))}

    try:
        found = (_vk('groups.search', q=nm, count=5, type='group') or {}).get('items') or []
        # Сервисному ключу groups.search недоступен («Access denied») — это НЕ
        # сбой сети и не протухший токен, а ограничение метода: нужен
        # пользовательский токен (как получить — server/VK-AUTH.md).
        if not found and 'Access denied' in (_vk_last_err['v'] or ''):
            _vk_last_err['v'] = ('vk:groups.search недоступен сервисному ключу — '
                                 'нужен пользовательский токен, см. VK-AUTH.md')
    except Exception as e:  # noqa: BLE001
        _bump('vk_fail')
        return {'error': f'vk:search-exc:{type(e).__name__}:{str(e)[:50]}'}
    if not found:
        _bump('vk_fail' if _vk_last_err['v'] else 'vk_none')
        return {'error': _vk_last_err['v'] or f'vk:0-групп по «{nm[:30]}»'}
    tokset = [t for t in re.findall(r'[а-яёa-z]{4,}', nm.lower())][:3]
    known_dom = _domain('http://' + str(company.get('site') or '').replace('http://', '')
                        ) if company.get('site') else ''
    for g in found:
        gid = g.get('id')
        scr = g.get('screen_name') or f'club{gid}'
        try:
            info = _vk('groups.getById', group_id=gid,
                       fields='contacts,site,description,city') or []
            if isinstance(info, dict):
                info = info.get('groups') or []
            info = info[0] if info else {}
        except Exception:  # noqa: BLE001
            continue
        blob = ' '.join(str(info.get(k) or '') for k in ('name', 'description', 'site'))
        low = blob.lower()
        gdom = _domain(str(info.get('site') or '')) if info.get('site') else ''
        site_ok = bool(known_dom and gdom and gdom == known_dom)
        name_ok = bool(tokset) and all(t in low for t in tokset[:2])
        if not (site_ok or name_ok):
            continue
        emails = [e.lower() for e in EMAIL_RE.findall(blob)]
        phones = sorted({re.sub(r'[\s\-()]', '', m1.group(0))
                         for m1 in phones_in(blob)})[:3]
        cont = []
        for c in (info.get('contacts') or [])[:6]:
            if not isinstance(c, dict):
                continue
            cont.append({'desc': c.get('desc') or '', 'phone': c.get('phone') or '',
                         'email': (c.get('email') or '').lower(), 'user_id': c.get('user_id')})
            if c.get('email'):
                emails.append(c['email'].lower())
            if c.get('phone'):
                phones.append(re.sub(r'[\s\-()]', '', c['phone']))
        if not (emails or phones or cont):
            continue
        _имена(cont)
        _bump('vk_ok')
        return {'group': scr, 'url': f'https://vk.com/{scr}',
                'verified_by': 'site' if site_ok else 'name',
                'emails': sorted(set(emails))[:4], 'phones': sorted(set(phones))[:4],
                'contacts': cont, 'group_site': gdom}
    _bump('vk_none')
    return {'error': _vk_last_err['v'] or f'vk:группы есть, но ни одна не верифицирована ({nm[:30]})'}


def _org_page_probe(u, wait_ms=7000):
    """JS-тяжёлая страница организации (Я.Карты по mapurl / 2ГИС / zoon): рендер браузером
    (дельфин с решателем капч, если доступен) -> (text, html). Пусто при ошибке."""
    try:
        import browser_probe as BP
        pargs = {'url': u, 'return_html': True, 'html_cap': 150000,
                 'wait_ms': wait_ms, 'screenshot': False, 'solve': True}
        dpid = _next_dolphin_profile()
        if dpid and _DOLPHIN_TOKEN:
            pargs['dolphin_profile'] = dpid
            pargs['dolphin_token'] = _DOLPHIN_TOKEN
        with _SEM_BROWSER:
            out = BP.probe(pargs)
        html = out.get('html') or ''
        txt = re.sub(r'\s+', ' ', (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', html))
        return txt, html
    except Exception:  # noqa: BLE001
        return '', ''


def find_directory_contacts(company):
    """#7-фолбэк для компаний БЕЗ своего сайта: находим карточку фирмы в бизнес-справочнике
    (orgpage/cataloxy/pulscen/2gis/…) через xmlriver-SERP и извлекаем email+телефон оттуда.
    Возврат: {'source':'directory','dir_url':..,'emails':[..],'phones':[..]} | None."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    if not nm:
        return None
    q = f'{nm} {company.get("city", "")} контакты телефон email'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(_XMLRIVER_PAUZA)
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(_XMLRIVER_PAUZA)
    if xml is None:
        return None
    inn = str(company.get('inn') or '')
    # якоря идентичности: имя (первые значимые токены) + известные телефоны из базы
    name_tokens = [t for t in re.findall(r'[а-яёa-z]{4,}', nm.lower())][:3]
    base_phones = [re.sub(r'\D', '', str(p))[-10:] for p in (company.get('phones') or [])
                   if len(re.sub(r'\D', '', str(p))) >= 10]
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        if not any(d in u.lower() for d in _DIR_SOURCES):
            continue
        html, _m, meta = _fetch_site(u)
        if not html or (isinstance(meta, dict) and meta.get('captcha_type')):
            # JS-тяжёлые площадки (2ГИС/zoon/Я.Карты) статикой не отдаются — рендер
            # браузером (дельфин+решатель капч). Владелец 2026-07-23: «идёт искать
            # в яндекс карты и 2гис».
            if any(d in u.lower() for d in ('2gis', 'zoon', 'yandex')):
                _t2, html = _org_page_probe(u)
            if not html:
                continue
        txt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html,
                                             flags=re.S | re.I))
        low = txt.lower()
        page_phones = ''.join(p[-10:] for p in _dir_phones(txt))
        # ВЕРИФИКАЦИЯ (не тёзка): ИНН на странице ИЛИ известный телефон ИЛИ имя+все токены.
        # Справочники с email часто без ИНН -> телефон/имя как якорь обязательны.
        inn_ok = bool(inn) and inn in txt.replace(' ', '')
        phone_ok = any(bp in page_phones for bp in base_phones)
        name_ok = bool(name_tokens) and all(tok in low for tok in name_tokens)
        if not (inn_ok or phone_ok or name_ok):
            continue
        # строки с маской («vm ** 50@bk.ru») выбрасываем ДО извлечения: иначе
        # EMAIL_RE соберёт из обрубка синтаксически годный выдуманный адрес
        чистый = '\n'.join(s for s in txt.splitlines() if not _маскирован(s))
        emails = sorted({e.lower() for e in EMAIL_RE.findall(чистый)
                         if not e.lower().endswith(_IMG_EXT)})
        phones = _dir_phones(чистый)
        if emails or phones:
            return {'source': 'directory', 'dir_url': u, 'verified_by':
                    'inn' if inn_ok else ('phone' if phone_ok else 'name'),
                    'emails': emails[:5], 'phones': phones[:3]}
    return None


# ОПО Ростехнадзора: рег-номер объекта (А##-#####[-####]) + типы «компрессорных» объектов.
_OPO_NUM = re.compile(r'\bА\d{2}[-\s]?\d{4,6}(?:[-\s]?\d{2,4})?\b')
_OPO_OBJ = re.compile(
    r'(компрессорн\w+\s+станц\w+|станц\w+\s+компрессорн\w+|воздухоразделит\w+|'
    r'площадк\w+\s+компрессорн\w+|газоперекачив\w+|сеть\s+газопотреблен\w+|'
    r'станц\w+\s+газораспределит\w+)', re.I)


def find_opo_signal(company):
    """Эвристический маркер ОПО Ростехнадзора (скоринг центробежных): SERP по компании +
    маркеры опасного производственного объекта. Ловит рег-номер и тип объекта из сниппетов.
    Возврат: {'opo':True,'opo_object':..,'opo_reg':..,'source_url':..} | None. НЕ авторитетно —
    буст приоритета для кандидатов, найденных hh/ЕИС/ОКВЭД."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key):
        return None
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', company.get('name', '')).strip().strip('"«»')
    if not nm:
        return None
    q = f'{nm} {company.get("city","")} опасный производственный объект компрессорная станция реестр Ростехнадзор'.strip()
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(_XMLRIVER_PAUZA)
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(_XMLRIVER_PAUZA)
    if xml is None:
        return None
    # ВАЖНО (владелец: «приходит пустой/обрезанный, а ты видишь крутится»): разбираем ОТДЕЛЬНЫЕ
    # результаты, а не общий свал сниппетов. Тип объекта И контекст «опасн/ОПО/Ростехнадзор»
    # должны быть в ОДНОМ результате, и источник — НЕ обобщённая юр-справка (закон/приказ
    # ОПРЕДЕЛЯЕТ термин «площадка компрессорной станции», но не доказывает ОПО у ЭТОЙ компании).
    LAW_REF = ('sudact.ru/law', 'consultant.ru', 'garant.ru', 'cntd.ru', 'kodeks',
               'pravo.gov', 'normativ', 'zakonbase', 'legalacts', 'base.garant',
               '/law/', 'zakonrf', 'gostrf', 'docs.cntd', 'ohranatruda')
    AUTH = ('e-ecolog.ru', 'gosnadzor', 'rusprofile.ru', 'checko.ru', 'list-org',
            'audit-it', 'zachestnyibiznes')   # авторитетнее как доказательство ОПО
    _ctx_re = re.compile(r'опасн\w+\s+производствен|ОПО|Ростехнадзор|промышленн\w+\s+безопасн', re.I)
    # разбиваем выдачу на per-результатные куски по границам <url> (устойчиво к тому, обёрнуты
    # ли результаты в <doc>/<group> или нет — иначе легко получить 0 из-за формата, а не данных).
    parts = re.split(r'(?=<url>)', xml)
    best = None
    for dm in parts:
        um = re.search(r'<url>(.*?)</url>', dm, re.S)
        if not um:
            continue
        u = um.group(1).strip(); ul = u.lower()
        if any(l in ul for l in LAW_REF):
            continue   # юр-справка/определение термина — не доказательство ОПО у компании
        sn = re.sub(r'<[^>]+>', ' ', dm)
        obj = _OPO_OBJ.search(sn)
        if not obj:
            continue
        is_auth = any(a in ul for a in AUTH)
        # авторитетный источник (e-ecolog/gosnadzor/rusprofile) + тип объекта = принимаем;
        # прочие — только если контекст «опасн/ОПО/Ростехнадзор» в ЭТОМ ЖЕ результате.
        if not (is_auth or _ctx_re.search(sn)):
            continue
        num = _OPO_NUM.search(sn)
        cand = {'opo': True, 'opo_object': obj.group(0),
                'opo_reg': num.group(0) if num else '', 'source_url': u}
        if is_auth:
            best = cand
            break
        if best is None:
            best = cand
    # ГРАДАЦИЯ ДОСТОВЕРНОСТИ (владелец открыл source_url и не нашёл там фразы: сниппет
    # Яндекса != страница — JS-блоки/SPA/старый индекс). Подтверждаем страницей: скачать
    # source_url и проверить, есть ли тип объекта РЕАЛЬНО в её тексте.
    if best:
        best['opo_confidence'] = 'сниппет'
        try:
            html, _m, _meta = VC._fetch(best['source_url'])
            if html:
                ptxt = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S | re.I)
                ptxt = re.sub(r'<[^>]+>', ' ', ptxt)
                if _OPO_OBJ.search(ptxt):
                    best['opo_confidence'] = 'страница'
        except Exception:  # noqa: BLE001
            pass
        if best.get('opo_reg'):
            best['opo_confidence'] = 'рег№'   # рег-номер ОПО в сниппете — сильное доказательство
    return best


def find_staff_via_search(company, dom):
    """Поисковый этап (2026-07-23): найти страницу СОТРУДНИКОВ/КОМАНДЫ компании через
    xmlriver-SERP, даже если она нестандартно названа и не слинкована с главной.

    Правка владельца 11.08.2026: запрос ограничен ДОМЕНОМ (`site:dom`). Раньше искали
    «<название> команда сотрудники руководство» по всему интернету и лишь потом
    отсеивали чужие домены — если своя страница команды в общей выдаче не поднималась
    (а у завода с расхожим именем она и не поднимается), мы не видели её вовсе, хотя
    домен уже знали. Возврат: список URL (0-3)."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key and dom):
        return []
    q = f'site:{dom} команда сотрудники руководство контакты отдела'
    return _serp_na_domene(user, key, dom, q, hints=_STAFF_HINTS + (
        'kontakt', 'контакт', 'about', 'company'), cap=3)


def find_rekvizity_via_search(company, dom):
    """Страница РЕКВИЗИТОВ на своём домене — чтобы подтвердить сайт ИНН'ом с документа,
    а не суждением модели. Замер 11.08: у «Чебоксарского агрегатного» ИНН на сайте есть,
    но страница не слинкована с главной, и краул до неё не доходил. Возврат: 0-2 URL."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key and dom):
        return []
    inn = str(company.get('inn') or '')
    q = f'site:{dom} реквизиты ИНН ОГРН' + (f' {inn}' if inn else '')
    return _serp_na_domene(user, key, dom, q, hints=(
        'rekvizit', 'реквизит', 'requisites', 'kontakt', 'контакт', 'about',
        'o-kompanii', 'company', 'info'), cap=2, brat_lyubye=True)


def _serp_na_domene(user, key, dom, q, hints, cap=3, brat_lyubye=False):
    """Один запрос к xmlriver, из выдачи — только URL на домене dom.

    brat_lyubye: если ни один адрес не подошёл по подсказкам, взять первые
    результаты как есть (запрос и так ограничен доменом, чужого не придёт) —
    страница реквизитов часто зовётся непредсказуемо («/info/», «/o-nas/»)."""
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(q))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(_XMLRIVER_PAUZA)
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(_XMLRIVER_PAUZA)
    if xml is None:
        return []
    na_domene = []
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        if _domain(u) == dom and u not in na_domene:   # site: не абсолютная гарантия
            na_domene.append(u)
    out = [u for u in na_domene if any(h in u.lower() for h in hints)][:cap]
    if not out and brat_lyubye:
        # корень домена не берём: главную краул и так качает первой
        out = [u for u in na_domene
               if urllib.parse.urlsplit(u).path.strip('/')][:cap]
    return out


def find_leadership_via_search(company, dom, max_urls=5):
    """Страницы руководства ЧЕРЕЗ ПОИСК, а не по ссылкам с главной.

    Наводка владельца 29.07: «все ли страницы руководства мы посмотрели?».
    Обход находит только то, на что ссылается главная, а блок руководства часто
    лежит на странице, не слинкованной из меню, — её видит поисковый индекс, но
    не краулер.

    Отличие от find_staff_via_search: тот требовал ПОДСКАЗКУ В АДРЕСЕ и потому
    отбрасывал ровно то, ради чего писался, — страницы с нестандартным слагом
    («/nashi-lyudi/», «/otdel-prodazh/lica/»). Здесь берём любой URL на домене
    компании, а годность решает уже разбор разметки.
    """
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    if not (user and key and dom):
        return []
    nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО|КАО|ГК)\s+', '',
                str(company.get('name') or '')).strip().strip('"«»')
    if len(nm) < 3:
        return []
    из = []
    for запрос in (f'{nm} руководство', f'{nm} главный инженер контакты'):
        if len(из) >= max_urls:
            break
        url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
               + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
               + '&query=' + urllib.parse.quote(запрос))
        _bump('xmlriver')
        xml = None
        for att in range(_XMLRIVER_TRIES):
            try:
                with _SEM_XMLRIVER:
                    xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
                if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                    xml = None
                    time.sleep(_XMLRIVER_PAUZA)
                    continue
                break
            except Exception:  # noqa: BLE001
                time.sleep(_XMLRIVER_PAUZA)
        if xml is None:
            continue
        for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
            u = u.strip().replace('&amp;', '&')
            # только домен самой компании: выдача полна карточек справочников
            if _domain(u) != dom or u in из:
                continue
            из.append(u)
            if len(из) >= max_urls:
                break
    return из


# Тендерные агрегаторы (способ А7): по разбору engineers-lens они публикуют
# «контактное лицо» заказчика вместе с ЛИЧНОЙ корпоративной почтой.
#
# ЗАМЕР 29.07 НА 109 КОМПАНИЯХ БАЗЫ ПРОДАЖНИКОВ: НОЛЬ КОНТАКТОВ. Это не сбой
# кода — проверено поштучно (_ops_agg_probe.py, _ops_agg_probe2.py): выдача
# отдаёт 3–4 ссылки на агрегаторы по каждому ИНН, страницы качаются без капчи
# (58–145 КБ), ИНН на странице присутствует. Пусто СОДЕРЖИМОЕ:
#   * rostender  — только описание тендера и кнопки «поделиться», ни почты, ни
#     телефона, ни подписи «контактное лицо»;
#   * synapsenet — «Войти», «зарегистрироваться»: контакты за регистрацией,
#     почт на листе ноль;
#   * tenderguru — почты есть, но СВОИ (info@tenderguru.ru) и телефон 8-800.
# То есть за анонимный доступ агрегаторы контакты заказчика больше не отдают.
# Функцию оставляю: она рабочая и стоит копейки, если у владельца появится
# платный доступ к одному из них — источник оживёт сменой куки. В конвейер по
# умолчанию НЕ включена (только явным --src agg).
#
# В блок-лист сайтов компании эти домены попадают справедливо (это не сайт
# заказчика), поэтому нужен отдельный список.
_АГРЕГАТОРЫ_ТЕНДЕР = ('rostender.info', 'zakupki360.ru', 'tenderguru.ru',
                      'bicotender.ru', 'synapsenet.ru', 'tenderplan.ru',
                      'seldon.ru', 'tbank.ru')


def find_tender_aggregator_contacts(inn, name='', max_pages=3):
    """[{person, email, phone, url}] со страниц тендерных агрегаторов по ИНН."""
    user = os.environ.get('XMLRIVER_USER', '')
    key = os.environ.get('XMLRIVER_KEY', '')
    inn = str(inn or '').strip()
    if not (user and key and inn.isdigit()):
        return []
    запрос = f'{inn} тендер контактное лицо'
    url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
           + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
           + '&query=' + urllib.parse.quote(запрос))
    _bump('xmlriver')
    xml = None
    for att in range(_XMLRIVER_TRIES):
        try:
            with _SEM_XMLRIVER:
                xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
            if 'свободных каналов' in xml or 'no free channel' in xml.lower():
                xml = None
                time.sleep(_XMLRIVER_PAUZA)
                continue
            break
        except Exception:  # noqa: BLE001
            time.sleep(_XMLRIVER_PAUZA)
    if xml is None:
        return []
    страницы = []
    for u in re.findall(r'<url>(.*?)</url>', xml, re.S):
        u = u.strip().replace('&amp;', '&')
        d = _domain(u)
        if any(d == a or d.endswith('.' + a) for a in _АГРЕГАТОРЫ_ТЕНДЕР):
            if u not in страницы:
                страницы.append(u)
        if len(страницы) >= max_pages:
            break
    из = []
    for u in страницы:
        h, _m, mt = _fetch_site(u)
        if not h or mt.get('captcha_type'):
            continue
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                     re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                            flags=re.S | re.I)))
        # берём окно вокруг подписи, а не всю страницу: у агрегатора на листе
        # висят и его собственные контакты, и телефоны поддержки
        for m in re.finditer(r'Контактн\w+\s+лиц\w+\s*[:\-]?\s*(.{0,260})',
                             txt, re.I):
            окно = m.group(1)
            фио = _фио(окно)
            письма = [x.lower() for x in EMAIL_RE.findall(окно)
                      if not _is_junk_email(x)
                      and not any(a.split('.')[0] in x.lower()
                                  for a in _АГРЕГАТОРЫ_ТЕНДЕР)]
            тм = next(phones_in(окно), None)
            # Телефон БЕЗ ФИО — тоже контакт. Раньше окно выбрасывалось, если
            # имени и почты в нём нет, и терялся номер заказчика, стоящий под
            # подписью «Контактный телефон». Поймано проверяющим агентом на
            # tenderguru, где в одном окне лежат и ФИО, и почта, и номер, но
            # бывают и окна с одним номером.
            if not (фио or письма or тм):
                continue
            из.append({'person': фио, 'email': (письма[0] if письма else ''),
                       'phone': (тм.group(0).strip() if тм else ''), 'url': u})
            if len(из) >= 6:
                break
        time.sleep(0.8 + random.uniform(0, 0.7))
    # один и тот же человек повторяется на нескольких листах агрегатора
    свод = {}
    for x in из:
        свод[(x['person'], x['email'])] = x
    return list(свод.values())


def _contact_cap(t, cap=24000):
    """Умная обрезка склеенного текста: контактные зоны выживают ВСЕГДА.

    Тупой t[:28000] терял таблицы контактов больших шаблонных страниц (Bitrix
    aspro: меню+SVG съедают лимит, а таблица телефонов с добавочными живёт в
    КОНЦЕ /contacts/) — владелец поймал на robotech.digital: вытянут только
    info@, потеряны sales@ и все доб. номера отделов. Кап 24000 согласован с
    text[:24000] в промпте extract_roles — чтобы провайдер видел ВСЁ, что вернули.
    Схема: head страницы + окна ±130 симв. вокруг каждого email / телефона /
    «доб. N» из хвоста, окна сливаются, суммарный бюджет соблюдается."""
    if len(t) <= cap:
        return t
    # приоритет окон (robotech-урок: бюджет съедали повторы футера с телефонами на КАЖДОЙ
    # из 20 страниц, а таблица «доб.» на /contacts/ в конец не влезла): email и «доб.» —
    # самое ценное (0), реквизиты (1), телефоны без контекста (2).
    spans = []
    for pri, rx in ((0, EMAIL_RE), (0, _EXT_RE), (0, _POST_RE), (1, _REKV_RE),
                    (1, _PHONE_SITE)):
        for m in rx.finditer(t):
            if rx is _PHONE_SITE:
                # цифровой хвост (таймстампы style.css?17308080...) — не телефон
                if (m.start() > 0 and t[m.start() - 1].isdigit()) or \
                   (m.end() < len(t) and t[m.end()].isdigit()):
                    continue
            # Окно шире прежних ±130: в табличной вёрстке между должностью
            # («Главный энергетик») и номером стоят ФИО, почта и разметка,
            # и подпись не доезжала до модели — телефон приходил без роли.
            # Телефон поднят с приоритета 2 на 1: смысл прогона — роли у
            # ТЕЛЕФОНОВ, а на приоритете 2 их окна вылетали из бюджета первыми.
            spans.append((max(0, m.start() - 300), min(len(t), m.end() + 200), pri))
    if not spans:
        return t[:cap]
    spans.sort(key=lambda s: (s[0], s[1]))
    merged = []   # [a, b, pri] — при слиянии приоритет = лучший из членов
    for a, b, pri in spans:
        if merged and a <= merged[-1][1] + 60:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2] = min(merged[-1][2], pri)
        else:
            merged.append([a, b, pri])
    head_cap = 6000
    head = t[:head_cap]
    budget = cap - head_cap - 100
    chosen, used, seen_norm = [], 0, set()
    # бюджет раздаём ПО ПРИОРИТЕТУ (внутри приоритета — по позиции), повторы
    # (одинаковый футер с 20 страниц) режем дедупом нормализованного текста
    for a, b, pri in sorted(merged, key=lambda s: (s[2], s[0])):
        if b <= head_cap:
            continue   # окно уже целиком в head
        seg = t[max(a, head_cap):b]
        norm = re.sub(r'\s+', ' ', seg).strip().lower()
        if norm in seen_norm:
            continue
        if used + len(seg) + 3 > budget:
            # Плотная таблица контактов сливается в ОДНО большое окно; раньше
            # такое окно отбрасывалось целиком, chosen оставался пустым и
            # функция скатывалась к тупому t[:cap] — то есть к меню главной.
            # Теперь берём столько, сколько влезает: обрезанный кусок таблицы
            # лучше, чем ноль контактов.
            остаток = budget - used - 3
            if остаток < 400:
                continue
            seg = seg[:остаток]
            norm = re.sub(r'\s+', ' ', seg).strip().lower()
        seen_norm.add(norm)
        chosen.append((a, seg))
        used += len(seg) + 3
    if not chosen:
        return t[:cap]
    chosen.sort()   # сборка в исходном порядке позиций — текст читается связно
    return (head + ' … ' + ' … '.join(s for _a, s in chosen))[:cap]


def _cache_pages(cache_dir, cache_key, site, page_htmls, txt):
    """Сложить скачанные страницы на диск сервера (дроп) одним .json.gz.

    Владелец 29.07: «всё, что скачиваем, складывай на дроп — чтобы можно было
    анализировать быстро без повторного краулинга». Повторный обход стоит
    прокси, капч и часов, а переразметка ролей по уже скачанному HTML — секунды.
    Пишем атомарно (во временный файл и переименование), чтобы прерванный
    прогон не оставил половину архива.
    """
    if not cache_dir or not cache_key:
        return ''
    try:
        import gzip
        os.makedirs(cache_dir, exist_ok=True)
        pages = []
        всего = 0
        обрезано = 0
        for u, h in (page_htmls or []):
            полн = len(h or '')
            h = (h or '')[:300000]
            if всего + len(h) > 2500000:
                обрезано += 1
                continue      # не break: короткие страницы после длинной влезут
            всего += len(h)
            pages.append({'url': u, 'html': h, 'html_full_len': полн,
                          'html_truncated': полн > 300000})
        blob = json.dumps({'key': str(cache_key), 'site': site,
                           'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                           # сколько страниц не влезло в бюджет кэша — молчать
                           # об усечении нельзя, иначе разбор ищет несуществующие
                           # ошибки разметки вместо потерянного куска
                           'pages_dropped': обрезано,
                           'pages': pages, 'text': (txt or '')[:200000]},
                          ensure_ascii=False).encode('utf-8')
        dst = os.path.join(cache_dir, f'{cache_key}.json.gz')
        tmp = dst + '.part'
        with gzip.open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, dst)
        return dst
    except Exception:  # noqa: BLE001
        return ''   # кэш — удобство, а не условие успеха прогона


# Шаблонные «описания», которые ставит движок сайта, а не владелец: попадая в базу
# как «чем занимается компания», они не просто бесполезны — они ВРУТ. Замер 11.08:
# у «Байкальской энергетической компании» meta description = «1С-Битрикс: Управление
# сайтом». Такое отбрасываем, лучше пусто, чем ложь.
_META_MUSOR = re.compile(
    r'^\s*(1с[- ]?битрикс|bitrix|joomla|wordpress|drupal|opencart|modx|tilda|wix|'
    r'создание сайта|разработка сайта|интернет[- ]магазин на|powered by|'
    r'главная( страница)?|добро пожаловать|описание( сайта)?|site description|'
    r'your website description|just another \w+ site)\b', re.I)


def _meta_ochistka(s, n=300):
    """HTML-обрывок -> человеческая строка (теги, мнемоники, пробелы)."""
    if not s:
        return ''
    s = re.sub(r'<[^>]+>', ' ', s)
    for a, b in (('&nbsp;', ' '), ('&mdash;', '-'), ('&ndash;', '-'), ('&amp;', '&'),
                 ('&quot;', '"'), ('&laquo;', '«'), ('&raquo;', '»'), ('&#039;', "'"),
                 ('&apos;', "'"), ('&gt;', '>'), ('&lt;', '<')):
        s = s.replace(a, b)
    s = re.sub(r'&[a-zA-Z#0-9]{2,8};', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()[:n]


def page_meta(html, url=''):
    """Заголовок и описание страницы — СНИМАЮТСЯ ДО СРЕЗАНИЯ ТЕГОВ.

    Зачем отдельно (владелец 11.08.2026): дальше по конвейеру html превращается в
    текст двумя `re.sub`, и meta description исчезает бесследно — она живёт в
    АТРИБУТЕ content, а атрибуты уходят вместе с тегом. Title формально выживает, но
    тонет в общей склейке всех страниц и до провайдера доходит как случайный кусок.
    Замер на 13 подтверждённых сайтах: title 13/13, description 9/13, og 2/13, h1 5/13.

    Возвращает {'title','description','og','h1','url'} — пустые ключи не кладутся."""
    if not html:
        return {}
    t = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    d = (re.search(r'<meta[^>]+name=["\']?description["\']?[^>]*?content=["\']([^"\']{8,600})',
                   html, re.I)
         or re.search(r'<meta[^>]+content=["\']([^"\']{8,600})["\'][^>]*?name=["\']?description',
                      html, re.I))
    og = re.search(r'<meta[^>]+(?:property|name)=["\']og:description["\']'
                   r'[^>]*?content=["\']([^"\']{8,600})', html, re.I)
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S | re.I)
    out = {}
    for klyuch, m, dlina in (('title', t, 200), ('description', d, 400),
                             ('og', og, 400), ('h1', h1, 200)):
        v = _meta_ochistka(m.group(1) if m else '', dlina)
        if v and not _META_MUSOR.match(v):
            out[klyuch] = v
    # description, дословно повторяющая title, ничего не добавляет — но и не мешает;
    # убираем только полный дубль, чтобы не раздувать промпт пустотой.
    if out.get('description') and out['description'] == out.get('title'):
        out.pop('description')
    if out.get('og') and out['og'] in (out.get('description'), out.get('title')):
        out.pop('og')
    if out and url:
        out['url'] = url
    return out


def meta_blok(meta):
    """Блок для провайдера: первоисточник о деятельности, помеченный явно."""
    if not meta:
        return ''
    ch = []
    for klyuch, podpis in (('title', 'заголовок'), ('description', 'описание'),
                           ('og', 'og:description'), ('h1', 'заголовок H1')):
        if meta.get(klyuch):
            ch.append('%s: %s' % (podpis, meta[klyuch]))
    if not ch:
        return ''
    return ('[ЗАГОЛОВОК И ОПИСАНИЕ ГЛАВНОЙ СТРАНИЦЫ %s] %s [КОНЕЦ БЛОКА] '
            % (meta.get('url', ''), ' | '.join(ch)))


def crawl_contacts(site, pace=(6.0, 14.0), extra_pages=None,
                   cache_dir=None, cache_key='', inn='', ogrn=''):
    """Домашняя + страницы контактов/сотрудников -> объединённый текст (кап по объёму).

    П-staff (2026-07-23): по каждой странице ДО склейки извлекаем email отдельно,
    чтобы знать URL-источник каждого контакта (url_first); staff-ссылки идут в
    обход первыми; если главная на staff не ссылается — пробуем типовые пути.
    extra_pages — URL staff-страниц, найденные ПОИСКОМ (find_staff_via_search):
    покрывают сайты, где страница названа нестандартно и не слинкована с главной.

    КЭШ ПО УМОЛЧАНИЮ (владелец 12.08). Правило от 29.07 — «всё, что скачиваем,
    складывай, чтобы анализировать без повторного краулинга» — не работало: ни один
    вызов не передавал cache_dir, и на 18 947 компаний в кэше лежало 202 файла.
    Из-за этого любой пересчёт задним числом (роли, разделы, сверка региона) стоил
    нового обхода вместо секунд по диску. Теперь папка и ключ берутся сами: та же
    `PAGECACHE_DIR`, из которой кэш ЧИТАЕТСЯ, ключ — ИНН. Замер места: средний файл
    189 КБ, на всю базу это 3,4 ГБ при 187 ГБ свободных. Выключается `PAGECACHE_OFF=1`.
    """
    if cache_dir is None and not os.environ.get('PAGECACHE_OFF'):
        cache_dir = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
    if not cache_key:
        # ИНН — тот же ключ, по которому кэш ищет читающая сторона (vk_group_email);
        # без ИНН кладём по домену, иначе страницы просто некуда положить
        cache_key = re.sub(r'\D', '', str(inn or '')) or re.sub(
            r'[^a-z0-9.-]', '_', _domain(site if str(site).startswith('http')
                                         else 'http://' + str(site)) or '')[:60]
    pages, texts = [], []
    if not site.startswith('http'):
        site = 'http://' + site   # страховка: _domain на голом домене даёт пустой netloc
    home, method, meta = _fetch_site(site)
    if not home or meta.get('captcha_type'):
        # ДЫРА закрыта (владелец 2026-07-23): сайт закрыт капчей/антиботом С ПОРОГА —
        # раньше бросали с пометкой «блок». Теперь рендер браузером с решателем капч
        # (дельфин): решённая главная даёт и текст, и ссылки для обычного обхода.
        if not _NO_BROWSER:
            _bt, _bh = _org_page_probe(site, wait_ms=9000)
            if _bh and not _looks_blocked(_bh):
                home, method, meta = _bh, 'browser-solved', {}
    if not home or meta.get('captcha_type'):
        return '', [], f'site-block:{meta.get("captcha_type") or method}', {}
    dom = _domain(site)
    # заголовок и описание снимаем ЗДЕСЬ — на сыром html главной, до всех замен
    smeta = page_meta(home, f'http://{dom}/')
    texts.append(home)
    page_htmls = [(f'http://{dom}/', home)]   # (url, html) — для атрибуции email->страница
    links = re.findall(r'href="([^"]+)"', home)
    picked = []
    # найденные поиском staff-URL — В НАЧАЛО (высший приоритет, покрывают любые вариации)
    for u in (extra_pages or []):
        if _domain(u) == dom and u not in picked:
            picked.append(u)
    # Кандидатов собираем ВСЕХ, режем до 10 уже ПОСЛЕ сортировки по приоритету.
    # Раньше «break на 10» срабатывал в порядке HTML: верхнее меню «О компании»
    # (/company/news, /company/vacancy, /company/history…) занимало все слоты,
    # а /kontakty/ из футера в обход не попадала вовсе.
    for l in links:
        ll = l.lower()
        if l.startswith(('mailto:', 'tel:', '#', 'javascript:')):
            continue   # не страницы; «#contacts» ещё и качал главную повторно
        if _STATIC_EXT_RE.search(ll):
            continue   # НЕ страница: contacts.css/style.js из <link href> ловились хинтом
        if any(h in ll for h in CONTACT_HINTS):
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/"+l}'
            if _domain(full) == dom and full not in picked:
                picked.append(full)
    # приоритет обхода (владелец 2026-07-23): staff (персональные контакты) ->
    # закупки/снабжение/поставщикам (контакты закупщиков - целевые ЛПР) -> остальное.
    # Сортировка стабильная - внутри групп порядок ссылок сайта сохраняется.
    _PROC_HINTS = ('zakup', 'закуп', 'снабж', 'постав', 'postav', 'tender', 'тендер')
    _CONT_HINTS = ('kontakt', 'контакт', 'contact')
    def _crawl_prio(u):
        ul = u.lower()
        if any(h in ul for h in _STAFF_HINTS):
            return 0
        if any(h in ul for h in _PROC_HINTS):
            return 1
        # страница «Контакты» — отдельной ступенью выше прочих: именно там
        # лежит таблица телефонов по отделам
        if any(h in ul for h in _CONT_HINTS):
            return 2
        return 3
    picked.sort(key=_crawl_prio)
    picked = picked[:10]   # кап ПОСЛЕ приоритизации, а не в порядке HTML
    _ugadannye = set()      # адреса, которых на сайте нет — мы их придумали
    # с главной на staff никто не ссылается -> пробуем типовые пути (Bitrix-канон);
    # неудачная проба вернёт пусто из _fetch_site и просто не попадёт в texts
    # КАРТА САЙТА — раньше угадок: она перечисляет РЕАЛЬНЫЕ страницы, а не
    # придуманные нами адреса, и стоит один лёгкий заход.
    for _su in _iz_sitemap(dom):
        if _su not in picked:
            picked.append(_su)
    if not any(any(h in u.lower() for h in _STAFF_HINTS) for u in picked):
        for p in _STAFF_PROBE_PATHS:
            full = f'http://{dom}{p}'
            if full not in picked:
                picked.append(full)
                _ugadannye.add(full)
    for u in picked:
        time.sleep(_PACE(*pace))
        # УГАДАННЫЙ адрес — лёгкий заход (владелец 12.08: «может проверочный заход
        # сначала»). Типовые пути мы ПРИДУМАЛИ, на сайте таких ссылок нет, и в
        # девяти случаях из десяти их там нет вовсе. Гонять ради них полную цепочку
        # (прямо -> прокси -> мобильный -> браузер -> дельфин) — самая дорогая
        # ошибка обхода: на «транснефть.рф» семь угадок съели 358 секунд при нуле
        # находок, а средний краул вышел 116 с. Ссылки, НАЙДЕННЫЕ на самой странице,
        # по-прежнему идут полной цепочкой: они существуют, за них стоит бороться.
        if u in _ugadannye:
            h = _lyogkiy_zahod(u)
            mt = {}
        else:
            h, m, mt = _fetch_site(u)
        if h and not mt.get('captcha_type'):
            texts.append(h)
            pages.append(u)
            page_htmls.append((u, h))
    # ВТОРОЙ УРОВЕНЬ (владелец 2026-07-23): проваливаемся ВНУТРЬ страниц контактов/staff —
    # мульти-офисные сайты держат карточки офисов/отделов/филиалов на ПОДстраницах
    # (/contacts/moscow, /contacts/otdel-prodazh), с главной на них ссылок нет. Со всех
    # собранных страниц берём ссылки с теми же хинтами, которых ещё не обходили. Бюджет +8.
    lvl2 = []
    _seen_u = {x[0] for x in page_htmls}
    for _u, _h in list(page_htmls[1:]):
        for l in re.findall(r'href="([^"]+)"', _h):
            if l.startswith(('mailto:', 'tel:', '#', 'javascript:')):
                continue
            ll = l.lower()
            if _STATIC_EXT_RE.search(ll):
                continue   # css/js/картинки — не страницы
            if not any(h2 in ll for h2 in CONTACT_HINTS):
                continue
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/" + l}'
            if _domain(full) == dom and full not in _seen_u and full not in lvl2:
                lvl2.append(full)
    # ПРАВИЛО ОСТАНОВКИ (владелец 11.08.2026): не «первые восемь», а «пока приносят
    # новые контакты» — ровно так уже устроена пагинация списков сотрудников ниже.
    # Замер по 8614 компаниям: страницы сотрудников есть у 61%, но в восьмёрку упирались
    # лишь 3% (294 компании) — именно у них на странице «Руководство» лежат списками
    # главные инженеры и энергетики, и восьмёрка их обрезала. Остальных правило не
    # трогает: обход останавливается сам раньше кэпа. Цена при восьми параллельных
    # компаниях — секунды три-четыре на компанию в среднем по прогону.
    def _pochty_stranicy(h):
        _es, _ = _harvest_from_html(h)
        _t = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                            flags=re.S | re.I))
        for _e in EMAIL_RE.findall(_t):
            _es.add(_e.lower())
        return {e for e in _es if not e.endswith(_IMG_EXT)}

    _bylo = set()
    for _u2, _h2 in page_htmls:
        _bylo |= _pochty_stranicy(_h2)
    # staff-карточки идут первыми: именно ради них правило и меняется, и они не должны
    # отсекаться тремя пустыми, набранными на прочих подстраницах
    lvl2.sort(key=lambda u: 0 if any(h2 in u.lower() for h2 in _STAFF_HINTS) else 1)
    _pusto_podryad = 0
    for u in lvl2[:40]:            # потолок — страховка от сайта-каталога, не рабочий предел
        if _pusto_podryad >= 3:
            break                  # три подряд без новых контактов — дальше пусто
        time.sleep(_PACE(*pace))
        h, m, mt = _fetch_site(u)
        if not h or mt.get('captcha_type'):
            _pusto_podryad += 1
            continue
        _novye = _pochty_stranicy(h) - _bylo
        texts.append(h)
        pages.append(u)
        page_htmls.append((u, h))
        if _novye:
            _bylo |= _novye
            _pusto_podryad = 0
        else:
            # одна пустая — не сигнал: у человека может не быть личной почты,
            # а у следующего в списке есть
            _pusto_podryad += 1
    # П-staff: ПАГИНАЦИЯ списков сотрудников (Bitrix ?PAGEN_n=2, ?page=2, /page/2/).
    # Идём по страницам, пока КАЖДАЯ даёт новые email: Bitrix за концом диапазона
    # отдаёт первую страницу заново — дубль не даст новых и остановит обход. Кап 5.
    def _page_emails(h):
        _es, _ = _harvest_from_html(h)
        _t = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h,
                                            flags=re.S | re.I))
        for _e in EMAIL_RE.findall(_t):
            _es.add(_e.lower())
        return {e for e in _es if not e.endswith(_IMG_EXT)}
    seen_pg = set()
    for _u, _h in page_htmls:
        seen_pg |= _page_emails(_h)
    for src_u, src_h in list(page_htmls[1:]):   # пагинация доп-страниц (staff/контакты)
        pag = re.findall(r'href="([^"]*(?:PAGEN_\d+=\d+|[?&]page=\d+|/page/\d+/?)[^"]*)"',
                         src_h)
        cands, added = [], 0
        for l in pag:
            l = l.replace('&amp;', '&')
            full = l if l.startswith('http') else f'http://{dom}{l if l.startswith("/") else "/" + l}'
            if _domain(full) == dom and full not in cands:
                cands.append(full)
        for pu in cands[:6]:
            if any(pu == x[0] for x in page_htmls):
                continue
            time.sleep(_PACE(*pace))
            ph, _pm, pmt = _fetch_site(pu)
            if not ph or pmt.get('captcha_type'):
                continue
            new = _page_emails(ph) - seen_pg
            if not new:
                continue   # дубль первой страницы / пустая — стоп-сигнал, не копим
            seen_pg |= new
            texts.append(ph)
            pages.append(pu)
            page_htmls.append((pu, ph))
            added += 1
            if added >= 5:
                break
    # атрибуция ДО склейки: email -> URL первой страницы, где он найден. Порядок обхода
    # (главная -> staff -> контакты) даёт правильный источник: info@ атрибутируется
    # главной, персональные — staff-странице.
    url_first = {}
    # ВСЕ страницы, где адрес встретился (владелец 12.08). Первая страница
    # отвечает на «откуда взяли», но не на «где ещё это подтверждается»:
    # адрес со страницы «Контакты» и он же в карточке отдела — разный вес,
    # а видно было только одно. Порядок сохраняем — первая остаётся первой.
    url_vse = {}
    # ТО ЖЕ для телефонов (владелец 29.07: «кликабельная страница по номеру»).
    # Раньше атрибуция строилась только для email, а всем телефонам компании
    # проставлялась одна страница — первая из обойденных. Ключ — последние
    # 10 цифр: один номер на сайте пишут и «+7 (495) …», и «8 495 …».
    phone_url_first = {}
    for _u, _h in page_htmls:
        _pe, _ph = _harvest_from_html(_h)
        _pt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', _h,
                                             flags=re.S | re.I))
        for _e in EMAIL_RE.findall(_pt):
            _pe.add(_e.lower())
        for _e in _pe:
            if not _e.endswith(_IMG_EXT):
                url_first.setdefault(_e, _u)
                _sp = url_vse.setdefault(_e, [])
                if _u not in _sp and len(_sp) < 8:
                    _sp.append(_u)
        for _p in phones_in(_pt):
            _ph.add(re.sub(r'\D', '', _p.group(0)))
        for _p in _ph:
            _d10 = re.sub(r'\D', '', _p)[-10:]
            if len(_d10) == 10:
                phone_url_first.setdefault(_d10, _u)
    # склеиваем текст, режем теги, кап.
    # П-staff: ДО вырезания тегов инлайним mailto/tel В ТЕКСТ рядом с местом ссылки —
    # иначе email из href исчезает и провайдер не может связать «ФИО + должность + email»
    # (на staff-страницах контакты живут ТОЛЬКО в href, текст ссылки часто «написать»).
    texts = [re.sub(r'<a\s[^>]*href="mailto:([^"?]+)[^"]*"[^>]*>', r' [email: \1] <a>', t)
             for t in texts]
    texts = [re.sub(r'<a\s[^>]*href="tel:([^"]+)"[^>]*>', r' [тел: \1] <a>', t)
             for t in texts]
    blob = ' '.join(texts)
    txt = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', blob, flags=re.S | re.I)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt)
    # ДОБОР из мест, которые теряет tag-strip: mailto/tel-ссылки, JSON-LD, обфускация.
    # srcmap помечает КАКИМ методом найден каждый email (для разбора разметок).
    srcmap = {}
    h_emails, h_phones = _harvest_from_html(blob, srcmap)
    for e in set(EMAIL_RE.findall(txt)):   # обычный видимый текст — базовый метод
        el = e.lower()
        if not el.endswith(_IMG_EXT):
            srcmap.setdefault(el, 'text')
    if h_emails or h_phones:
        txt = txt + ' Контакты(добор): ' + ' '.join(sorted(h_emails)) + ' ' + ' '.join(sorted(h_phones))
    # JS-email: если email НЕ найден НИГДЕ (ни в тексте, ни в доборе) — он мог отрисоваться
    # скриптом → рендерим главную в браузере (Playwright исполнит JS).
    # ИЛИ телефонов: раньше условие смотрело только на почту, и типовой сайт
    # («info@ статикой в футере, номера подставляет коллтрекинг») браузером не
    # рендерился вовсе — телефоны терялись все до одного.
    if (not h_emails and not EMAIL_RE.search(txt)
            or not h_phones and next(phones_in(txt), None) is None) and not _NO_BROWSER:
        try:
            import browser_probe as BP
            pargs = {'url': site, 'return_html': True, 'html_cap': 130000,
                     'wait_ms': 5000, 'screenshot': False, 'solve': True}
            dpid = _next_dolphin_profile()
            if dpid and _DOLPHIN_TOKEN:
                # Dolphin: пробивает защиту крупных сайтов (свой fingerprint+socks5)
                pargs['dolphin_profile'] = dpid
                pargs['dolphin_token'] = _DOLPHIN_TOKEN
                pargs['wait_ms'] = 8000
            with _SEM_BROWSER:
                out = BP.probe(pargs)
            if out.get('captcha_solved') or out.get('cf_solved'):
                _bump('twocaptcha' if out.get('captcha_type') == 'smartcaptcha' else 'capmonster')
            bhtml = out.get('html') or ''
            btxt = (out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', bhtml)
            _harvest_from_html(bhtml, srcmap)  # дораскладываем источники из JS-рендера
            for e in set(EMAIL_RE.findall(btxt)):
                el = e.lower()
                if not el.endswith(_IMG_EXT):
                    srcmap.setdefault(el, 'js-render')
            txt = re.sub(r'\s+', ' ', txt + ' ' + btxt)
        except Exception:  # noqa: BLE001
            pass
    from collections import Counter as _C
    csrc = dict(_C(srcmap.values()))
    # по каждому email: метод-источник + local-part + контекст вокруг (±70 симв) —
    # чтобы офлайн понять, извлекается ли РОЛЬ скриптом (local-part/метка) или это «каша».
    low = txt.lower()
    per = {}
    home_url = f'http://{dom}/'
    for e in srcmap:
        pos = low.find(e)
        ctx = re.sub(r'\s+', ' ',
                     txt[max(0, pos - 250):pos + len(e) + 120]).strip() if pos >= 0 else ''
        # url: страница, где email найден впервые; js-render-контакты — с главной
        per[e] = {'src': srcmap[e], 'local': e.split('@')[0], 'ctx': ctx,
                  'url': url_first.get(e, home_url if srcmap[e] == 'js-render' else ''),
                  'urls': url_vse.get(e, [])}
    # СТРУКТУРНЫЙ КОНТЕКСТ: карточка контакта и раздел, которому он подчинён. Окно
    # ±70 знаков брало должность лишь у 46% адресов, а заголовок раздела («Отдел
    # материального снабжения») стоит в среднем за тысячу знаков и окном не берётся
    # вовсе. Здесь контекст режется по дереву разметки, поэтому и соседний человек
    # в него не затекает.
    karty = []
    _vid_kart = set()
    for _u, _h in page_htmls:
        try:
            for _k in karty_kontaktov(_h, _u):
                if _k['email'] in _vid_kart:
                    continue
                _vid_kart.add(_k['email'])
                karty.append(_k)
        except Exception:  # noqa: BLE001
            continue
    _po_adresu = {k['email']: k for k in karty}
    for e in per:
        _k = _po_adresu.get(e)
        if _k:
            per[e]['razdel'] = _k.get('razdel', '')
            if _k.get('kartochka'):
                # A/B 11.08 на 51 адресе: карточка ВМЕСТО окна даёт 69% против 78% у окна —
                # она бывает слишком тесной (границей блока отрезается соседняя ячейка с
                # должностью), и в 5 новых ошибках из 6 роль выходила «общий». Поэтому
                # держим ОБА: карточка точна по принадлежности, окно богаче по словам.
                per[e]['ctx'] = (_k['kartochka'][:300] + ' ⟨вокруг⟩ '
                                 + per[e].get('ctx', ''))[:800]
    csrc['emails'] = per
    csrc['karty'] = len(karty)
    # СТРАНИЦА-ДОКАЗАТЕЛЬСТВО (12.08). Метка verified='inn' говорит «ИНН найден на
    # сайте», но НА КАКОЙ странице — не сохранялось, и проверить подтверждение по
    # выгрузке было нельзя. Я сам на этом обжёгся: принял артефакт своего замера
    # (смотрел только главную) за ошибку базы. Теперь ссылка лежит рядом с меткой.
    if inn or ogrn:
        for _u3, _h3 in page_htmls:
            _t3 = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', _h3,
                                                 flags=re.S | re.I))
            _t3 = re.sub(r'\s+', ' ', _t3)
            if inn and 'inn_url' not in csrc and (
                    re.search(r'\b' + re.escape(str(inn)) + r'\b', _t3)
                    or str(inn) in re.sub(r'\D', '', _h3)):
                csrc['inn_url'] = _u3
            if ogrn and 'ogrn_url' not in csrc and str(ogrn) in re.sub(r'\D', '', _t3):
                csrc['ogrn_url'] = _u3
            if ('inn_url' in csrc or not inn) and ('ogrn_url' in csrc or not ogrn):
                break
    # то же по телефонам: ключ — последние 10 цифр, значение — страница, где
    # номер встретился ВПЕРВЫЕ, и контекст вокруг (в нём обычно и стоит
    # должность: «Главный энергетик — Иванов И.И. — +7 …»)
    per_ph = {}
    digits_txt = None
    for _k, _u in phone_url_first.items():
        if digits_txt is None:
            digits_txt = txt
        ctx = ''
        for m in phones_in(digits_txt):
            if re.sub(r'\D', '', m.group(0))[-10:] == _k:
                ctx = re.sub(r'\s+', ' ',
                             digits_txt[max(0, m.start() - 90):m.end() + 20]).strip()
                break
        per_ph[_k] = {'url': _u, 'ctx': ctx}
    csrc['phones'] = per_ph
    csrc['meta'] = smeta
    csrc['cached'] = _cache_pages(cache_dir, cache_key, site, page_htmls, txt)
    # Порядок для провайдера: заголовок+описание главной, затем КАРТОЧКИ КОНТАКТОВ,
    # затем сплошной текст. Оба блока идут ДО капа, потому что модель читает только
    # начало (text[:24000]), а раньше туда попадало лишь то, что уцелело при отборе.
    # Карточки — главное: в сплошном тексте «Отдел материального снабжения» остаётся
    # за тысячу знаков от адреса, а здесь стоит прямо перед ним.
    return (meta_blok(smeta) + karty_v_tekst(karty) + _contact_cap(txt),
            pages, None, csrc)


def extract_roles(text, company):
    """Провайдер: email С РОЛЯМИ + ЛПР для холодного письма. Фолбэк — regex."""
    key = os.environ.get('PROVIDER_API_KEY', '')
    provider_attempted = False
    if key and EMAIL_RE.search(text):
        provider_attempted = True   # провайдер ДОЛЖЕН был отработать (есть ключ и email в тексте)
        prompt = (
            'Из текста сайта компании извлеки контакты С РОЛЯМИ и ПОДТВЕРДИ, что сайт '
            f'принадлежит именно этой компании. Компания: «{company.get("name","")}»'
            + (f', ИНН {company.get("inn")}' if company.get('inn') else '')
            + (f', город {company.get("city")}' if company.get('city') else '') + '. '
            'В САМОМ НАЧАЛЕ текста может стоять блок [ЗАГОЛОВОК И ОПИСАНИЕ ГЛАВНОЙ '
            'СТРАНИЦЫ ...] — это то, что компания САМА написала о себе в заголовке и '
            'мета-описании сайта. Для поля activity опирайся ПРЕЖДЕ ВСЕГО на него, '
            'остальной текст — уточнение. Если блока нет или он не про деятельность '
            '(одно название, «Главная», реклама движка) — бери activity из текста. '
            'Следом может стоять блок [КАРТОЧКИ КОНТАКТОВ СО СТРАНИЦ]: каждая строка — один '
            'адрес, перед ним в скобках РАЗДЕЛ сайта, которому он подчинён («Отдел '
            'материального снабжения», «Руководство»), дальше его карточка целиком. Раздел '
            'взят по структуре страницы, а не по близости текста, поэтому для роли он '
            'НАДЁЖНЕЕ сплошного текста ниже: там название отдела стоит заголовком в самом '
            'верху таблицы, за сотни знаков от адреса. Роль ставь по карточке и её разделу; '
            'если раздел говорит одно, а карточка другое — верь карточке, она про человека. '
            'Раздел вида «Контакты», «Обратная связь», «Появились вопросы» роли НЕ задаёт. '
            'Также определи по тексту главной, ЧЕМ занимается компания, и НЕ является ли она '
            'нашим КОНКУРЕНТОМ. Конкурент — УЗКО: тот, кто сам производит, продаёт или сдаёт '
            'в аренду ИМЕННО компрессоры и компрессорные станции, генераторы азота/кислорода, '
            'мембранные и адсорбционные установки, фотосепараторы или рентген-инспекцию. '
            'ВСЕ ОСТАЛЬНЫЕ — КЛИЕНТЫ, даже если делают сложное оборудование: котлы, трубы, '
            'насосы, станки, компенсаторы, строительные леса, климатические системы — они '
            'сжатый воздух ПОТРЕБЛЯЮТ у себя на производстве и нам нужны. '
            'При сомнении ставь is_compressor_maker=false (ложный флаг = выброшенный клиент). '
            'Верни СТРОГО JSON без markdown: '
            '{"owner_match":true/false,"owner_reason":"почему сайт этой/не этой компании",'
            '"activity":"1 короткая фраза чем занимается компания (для персонализации письма)",'
            '"is_compressor_maker":true/false,'
            # Список ролей общий для почт и телефонов. Технические ЛПР перечислены
            # ПЕРВЫМИ и разделены по должностям (владелец 29.07): раньше вариантов
            # было семь, всё техническое сваливалось в «гл.инженер», а главный
            # энергетик — тот, кто и решает по компрессорной, — терялся.
            + '"emails":[{"email":"","person":"","role":"' + _ROLES_FOR_PROMPT
            + '","person":"ФИО или пусто"}],'
            # Телефоны СТАЛИ ОБЪЕКТАМИ: до 29.07 это был список голых строк, роль
            # у номера спросить было негде — в базе не оказалось ни одного телефона
            # инженера. Отдел пишем как на сайте: он объясняет роль оператору.
            '"phones":[{"phone":"номер; добавочный СОХРАНИ, напр. +7 342 292-14-60 доб.122",'
            '"role":"та же шкала ролей","person":"ФИО или пусто",'
            '"dept":"как отдел назван на сайте, или пусто"}],'
            '"best_for_outreach":"email ЛПР для холодного письма (приоритет: '
            'гл.инженер/гл.энергетик/гл.механик/техдиректор/нач.производства > '
            'снабжение/закупки > директор > продажи > общий)"}. '
            'РОЛЬ СТАВЬ ПО ТЕКСТУ РЯДОМ С КОНТАКТОМ (должность, название отдела, '
            'заголовок таблицы), а не по адресу почты. Не угадывай: не видно '
            'должности — ставь «общий». До 25 телефонов и до 25 почт. '
            'owner_match=false если сайт — агрегатор/каталог/тёзка/другая фирма. '
            # Прежняя формулировка «только email её домена» отсекала живые
            # контакты: у российских заводов снабжение и инженеры массово сидят
            # на mail.ru/yandex.ru, и такой адрес модель добросовестно не
            # возвращала. Отсекать надо чужие ОРГАНИЗАЦИИ, а не бесплатную почту.
            'Бери контакты ЭТОЙ компании: на её домене ИЛИ на бесплатной почте '
            '(mail.ru, yandex.ru, bk.ru, list.ru, gmail.com, rambler.ru), если они '
            'указаны на её сайте как её контакт. НЕ бери адреса других организаций, '
            'разработчика сайта и платформы. Текст:\n' + text[:24000])
        out = None
        for _ in range(3):
            try:
                out = VC._provider_call_stdlib(prompt)
                _bump('provider_calls')
                _bump('prov_in_chars', len(prompt))
                _bump('prov_out_chars', len(out or ''))
                if out:
                    m = re.search(r'\{.*\}', out, re.S)
                    if m:
                        _d = json.loads(m.group(0))
                        # отсев платформенных/noreply адресов (help@creatium.io и т.п.)
                        _d['emails'] = [e for e in (_d.get('emails') or [])
                                        if isinstance(e, dict) and not _is_junk_email(e.get('email'))]
                        # ЧИСТКА ФИО и УТОЧНЕНИЕ РОЛИ по самой странице.
                        # Оба правила выведены из замеров 13.08 и без вызова здесь
                        # существуют мёртвым кодом — так уже случилось после отката
                        # песочницы, и поймано только сверкой файла с коммитом.
                        for _em in _d['emails']:
                            _em['person'] = _chistoe_fio(_em.get('person'), text,
                                                         _em.get('email'), 'site')
                        _d['emails'], _sch_rol = utochnit_roli_po_stranice(
                            _d['emails'], text)
                        if _sch_rol:
                            _d['роли_уточнены'] = _sch_rol
                        if _is_junk_email(_d.get('best_for_outreach')):
                            _d['best_for_outreach'] = (_d['emails'][0].get('email') if _d['emails'] else '')
                        # приоритет ролей считаем КОДОМ, а не доверяем вольному
                        # ответу модели: она регулярно ставила info@ (общий) при
                        # живом sales@/zakupki@ (пример: БРОКС 3705011046).
                        # Ответ модели — только подсказка при равенстве ролей.
                        _d['best_for_outreach'] = _best_by_role(
                            _d.get('emails'), _d.get('best_for_outreach'))
                        # ЗАПАСНОЙ ВЫБОР (12.08): контакты есть, а лучшего адреса нет —
                        # такое давал отсев ответа модели. Компания с найденным ящиком
                        # не должна оставаться «некому писать».
                        if not (_d.get('best_for_outreach') or '').strip():
                            for _e2 in (_d.get('emails') or []):
                                if (_e2.get('email') or '').strip():
                                    _d['best_for_outreach'] = _e2['email'].strip()
                                    break
                        _d['phone_roles'], _d['phones'] = _norm_phone_roles(
                            _d.get('phones'))
                        return _d, 'provider'
            except Exception:  # noqa: BLE001
                time.sleep(1.5)
    # regex-фолбэк: email без ролей. Если провайдер БЫЛ должен отработать, но упал 3× —
    # помечаем 'regex-provider-fail' → done-set исключит на перепроверку (провайдер лежал).
    emails = sorted(set(e.lower() for e in EMAIL_RE.findall(text)
                        if not e.lower().endswith(('.png', '.jpg', '.gif', '.webp'))
                        and not _is_junk_email(e.lower())))
    how = 'regex-provider-fail' if provider_attempted else 'regex'
    # Телефоны в фолбэке раньше возвращались ПУСТЫМИ — при любом сбое провайдера
    # компания оставалась вообще без номеров, хотя текст с ними уже собран.
    # Ролей тут нет, но номер со ссылкой на страницу лучше, чем ничего.
    ph_fb = []
    for _m in phones_in(text or ''):
        p = _m.group(0).strip()
        if p not in ph_fb:
            ph_fb.append(p)
        if len(ph_fb) >= 12:
            break
    return {'emails': [{'email': e, 'role': 'общий', 'person': ''} for e in emails[:12]],
            'phones': ph_fb,
            'phone_roles': [{'phone': p, 'role': '', 'person': '', 'dept': ''}
                            for p in ph_fb],
            'best_for_outreach': emails[0] if emails else ''}, how


def mx_ok(email):
    """Быстрая проверка MX домена email (nslookup, stdlib-фолбэк)."""
    dom = email.split('@')[-1] if '@' in email else ''
    if not dom:
        return False
    try:
        import subprocess
        out = subprocess.run(['nslookup', '-type=MX', dom], capture_output=True,
                             text=True, timeout=12).stdout.lower()
        return 'mail exchanger' in out or 'mx preference' in out
    except Exception:  # noqa: BLE001
        return None  # не смогли проверить — не роняем


def smtp_verify(email, mail_from='postmaster@parsercompressor.online', timeout=12):
    """SMTP-проба существования ящика через RCPT TO БЕЗ отправки (владелец 2026-07-23).
    Возврат: 'smtp_ok' | 'catch-all' | 'smtp_reject' | 'unknown' | 'no_mx' | 'port25_blocked'.
    catch-all: сервер принимает случайный несуществующий адрес -> проверить нельзя.
    Аккуратно: 1 коннект на домен, короткий таймаут, пауза зовущим кодом."""
    dom = email.split('@')[-1].lower() if '@' in email else ''
    if not dom:
        return 'unknown'
    # MX-хосты домена (nslookup, т.к. dnspython может отсутствовать)
    mxs = []
    try:
        import subprocess
        out = subprocess.run(['nslookup', '-type=MX', dom], capture_output=True,
                             text=True, timeout=10).stdout
        for m in re.findall(r'mail exchanger\s*=\s*(\S+)', out) or re.findall(r'MX preference.*?mail exchanger\s*=\s*(\S+)', out, re.I):
            mxs.append(m.strip().rstrip('.'))
        if not mxs:
            for m in re.findall(r'=\s*\d+\s+(\S+\.\S+)', out):
                mxs.append(m.strip().rstrip('.'))
    except Exception:  # noqa: BLE001
        pass
    if not mxs:
        return 'no_mx'
    import smtplib as _smtp
    import socket as _sock
    host = mxs[0]
    try:
        srv = _smtp.SMTP(timeout=timeout)
        srv.connect(host, 25)
        srv.helo('parsercompressor.online')
        srv.mail(mail_from)
        code_real, _ = srv.rcpt(email)
        # контроль catch-all: заведомо несуществующий ящик того же домена
        import hashlib as _hl
        fake = 'nx' + _hl.md5(email.encode()).hexdigest()[:10] + '@' + dom
        code_fake, _ = srv.rcpt(fake)
        try:
            srv.quit()
        except Exception:  # noqa: BLE001
            pass
        if code_fake in (250, 251):
            return 'catch-all'          # принимает всё -> не показатель
        if code_real in (250, 251):
            return 'smtp_ok'
        if code_real in (550, 551, 553, 554, 501):
            return 'smtp_reject'        # ящика нет -> ВЫКИНУТЬ
        return 'unknown'
    except (_sock.timeout, _smtp.SMTPConnectError, _sock.error, OSError):
        return 'port25_blocked'
    except Exception:  # noqa: BLE001
        return 'unknown'


# Маркеры РЕАЛЬНОЙ страницы-заглушки (интерстишла), а НЕ виджета капчи в форме.
# Важно: 'g-recaptcha'/'cf-turnstile'/'smartcaptcha' часто стоят в форме обратной связи
# на ПОЛНОЦЕННОЙ странице (со всем контентом и email) — это НЕ блок. Блоком считаем
# только когда это интерстишл: короткая страница + маркер проверки браузера.
_INTERSTITIAL = ('just a moment', 'ddos-guard', 'checking your browser', 'attention required',
                 'проверка, что вы', 'подтвердите, что вы человек', 'один момент',
                 'cf-chl', 'challenge-platform')


# Заглушка ПРОКСИ, а не сайта. Разбор 12.08 (почему у прогона №3 пусто): треть
# «пустых» страниц оказалась ответом мёртвого socks5 — 181 байт с текстом
# «Proxy Authentication Required». Конвейер принимал это ЗА СОДЕРЖИМОЕ САЙТА:
# страница «есть», текста нет, контактов нет — компания молча уходила в пустые.
# Ловим по тексту, а не по длине: длинная страница ошибки шлюза прошла бы насквозь.
_PROXY_ZAGLUSHKA = ('proxy authentication required', 'authenticationrequired',
                    '407 proxy', 'proxy error', 'access denied by proxy',
                    'ошибка прокси', 'tunnel connection failed')


def _zaglushka_proxy(html):
    b = (html or '').lower()
    return bool(b) and len(b) < 4000 and any(m in b for m in _PROXY_ZAGLUSHKA)


def _looks_blocked(html):
    b = (html or '').lower()
    if not b or len(b) < 500:
        return True                          # пусто/обрывок — считаем блоком
    if _zaglushka_proxy(b):
        return True                          # ответ прокси, сайт мы вообще не видели
    if any(m in b for m in _INTERSTITIAL):
        return True                          # явная страница-заглушка
    # «вы не робот» как ОСНОВНОЙ контент (короткая страница) — тоже заглушка
    if 'вы не робот' in b and len(b) < 8000:
        return True
    return False                             # виджет-капча в форме на живой странице — не блок


_LOC_RE = re.compile(r'<loc>\s*([^<\s]+)\s*</loc>', re.I)


def _iz_sitemap(dom, cap=6):
    """Контактные страницы ИЗ КАРТЫ САЙТА. Разбор 12.08 показал, чего не хватало:

    страницу контактов ищут тремя способами — ссылки с главной, семь угаданных
    путей и запрос `site:домен` в поиске. Все три промахиваются об одно и то же:
    страница есть, но с главной на неё не ссылаются и названа она непредсказуемо.
    Карта сайта перечисляет её сама, бесплатно и без угадывания. Читаем
    /sitemap.xml и /sitemap_index.xml, разворачиваем вложенные карты на один
    уровень и берём адреса с нашими подсказками — сперва staff, потом контакты.
    """
    if not dom:
        return []
    karty, vidno = [], []
    for imya in ('/sitemap.xml', '/sitemap_index.xml', '/sitemap1.xml'):
        h = _lyogkiy_zahod('http://%s%s' % (dom, imya), timeout=8)
        if h and '<loc' in h.lower():
            karty.append(h)
            break
    if not karty:
        return []
    loc = _LOC_RE.findall(karty[0])
    # карта карт: внутри ссылки не на страницы, а на другие карты — разворачиваем.
    # Считаем ВСЕ вложенные, а обходим первые несколько: сравнивать обрезанный
    # список с полным нельзя — условие не выполнится никогда (поймано на
    # prokompressor.ru: 19 карт в индексе, а сравнивалось с тремя).
    vlozh_vse = [u for u in loc if u.lower().endswith('.xml')]
    if vlozh_vse and len(loc) == len(vlozh_vse):
        for u in vlozh_vse[:4]:
            h2 = _lyogkiy_zahod(u, timeout=8)
            if h2:
                loc += _LOC_RE.findall(h2)
    for u in loc:
        ul = u.lower()
        if ul.endswith('.xml') or _STATIC_EXT_RE.search(ul):
            continue
        if _domain(u) != dom:
            continue
        if any(h in ul for h in _STAFF_HINTS):
            vidno.insert(0, u)
        elif any(h in ul for h in CONTACT_HINTS):
            vidno.append(u)
    out = []
    for u in vidno:
        if u not in out:
            out.append(u)
    return out[:cap]


def _lyogkiy_zahod(url, timeout=8):
    """Быстрая проверка «есть ли вообще такая страница»: один прямой GET.

    Ни прокси, ни браузера, ни дельфина. Нужна там, где адрес мы УГАДАЛИ:
    отсутствующая страница должна стоить секунды, а не полторы минуты.
    Возвращает html или '' — пустое значит «страницы нет, идём дальше».
    """
    try:
        u = VC._norm_url(url)
    except Exception:  # noqa: BLE001
        u = url
    try:
        req = urllib.request.Request(u, headers={
            'User-Agent': VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept': 'text/html,application/xhtml+xml'})
        with _DIRECT.open(req, timeout=timeout) as r:
            raw = r.read(400000)
        html = _раскодировать(raw, '')
    except Exception:  # noqa: BLE001
        return ''
    if not html or _looks_blocked(html) or _zaglushka_proxy(html):
        return ''
    return html


def _fetch_site(url):
    """Краул сайта компании: сперва ПРЯМО (датацентр-IP; сайты компаний его не банят, в
    отличие от поисковиков — надёжнее флаки-socks5, терпит IncompleteRead), при блоке/капче
    — фолбэк на VC._fetch (прокси + CapMonster-решатель Turnstile)."""
    try:
        u = VC._norm_url(url)
    except Exception:  # noqa: BLE001
        u = url
    html = ''
    try:
        req = urllib.request.Request(u, headers={
            'User-Agent': VC.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
            'Accept': 'text/html,application/xhtml+xml'})
        with _DIRECT.open(req, timeout=30) as r:
            try:
                raw = r.read()
            except Exception as e:  # noqa: BLE001  IncompleteRead -> частичное
                raw = getattr(e, 'partial', b'') or b''
            html = _раскодировать(raw, r.headers.get('Content-Type', ''))
    except urllib.error.HTTPError as e:  # noqa: BLE001
        try:
            html = _раскодировать(e.read(),
                                  getattr(e, 'headers', {}).get('Content-Type', '')
                                  if hasattr(e, 'headers') else '')
        except Exception:  # noqa: BLE001
            html = ''
    except Exception as e:  # noqa: BLE001
        html = (getattr(e, 'partial', b'') or b'').decode('utf-8', 'replace')
    if html and not _looks_blocked(html):
        return html, 'direct', {}
    # фолбэк 1: прокси + CapMonster-решатель Turnstile (Cloudflare)
    h2, m2, meta2 = VC._fetch(u)
    # ЗДЕСЬ БЫЛА ДЫРА (найдена 12.08 при разборе пустых прогона №3): проверяли только
    # капчу, а `_looks_blocked` не спрашивали — и 181-байтная заглушка мёртвого прокси
    # «Proxy Authentication Required» возвращалась как содержимое сайта. Дальше конвейер
    # честно не находил в ней контактов и записывал компанию в пустые. На выборке из 400
    # компаний так потерялись 80.
    if h2 and not meta2.get('captcha_type') and not _looks_blocked(h2):
        return h2, m2, meta2
    if _zaglushka_proxy(h2):
        h2 = ''            # не тащим заглушку дальше: пусть решают браузер и дельфин
    # фолбэк 1б: МОБИЛЬНЫЙ адрес. Датацентр-IP режут не только справочники: часть
    # корпоративных сайтов сидит за DDoS-Guard и антиботами, которые пропускают
    # мобильную сеть и молча отдают пустоту датацентру. Пробуем ДО браузера —
    # один GET дешевле рендера страницы, а мобильных адресов мало и они платные,
    # поэтому канал включается только здесь, когда массовый уже не справился.
    if VC.PROXY_POOL_MOBILE:
        try:
            with VC.mobilnyy():
                h3, m3, meta3 = VC._fetch(u)
            if h3 and not (meta3 or {}).get('captcha_type') and not _looks_blocked(h3):
                return h3, (m3 or '') + '+mobile', (meta3 or {})
        except Exception:  # noqa: BLE001
            pass
    # фолбэк 2: рендер в браузере + решатель reCAPTCHA v2 (CapMonster) / Cloudflare —
    # для сайтов за reCAPTCHA/антиботом, которые urllib не проходит (напр. betaren.ru)
    if _NO_BROWSER:
        return (h2 or None), (m2 if h2 else f'site-block:{(meta2 or {}).get("captcha_type") or "no-browser"}'), (meta2 or {})
    try:
        import browser_probe as BP
        with _SEM_BROWSER:
            out = BP.probe({'url': u, 'solve': True, 'return_html': True,
                            'html_cap': 130000, 'wait_ms': 6000, 'screenshot': False})
        if out.get('captcha_solved') or out.get('cf_solved'):
            _bump('twocaptcha' if out.get('captcha_type') == 'smartcaptcha' else 'capmonster')
        bh = out.get('html', '') or ''
        if bh and not _looks_blocked(bh):
            return bh, 'browser-solved', {}
        # фолбэк 3: ДЕЛЬФИН (антидетект-профиль: свой fingerprint + socks5) — пробивает
        # сайты, которые режут обычный Playwright по браузерному отпечатку/датацентр-IP.
        dpid = _next_dolphin_profile()
        if dpid and _DOLPHIN_TOKEN:
            try:
                with _SEM_BROWSER:
                    dout = BP.probe({'url': u, 'solve': True, 'return_html': True,
                                     'html_cap': 130000, 'wait_ms': 8000, 'screenshot': False,
                                     'dolphin_profile': dpid, 'dolphin_token': _DOLPHIN_TOKEN})
                if dout.get('captcha_solved') or dout.get('cf_solved'):
                    _bump('twocaptcha' if dout.get('captcha_type') == 'smartcaptcha' else 'capmonster')
                dh = dout.get('html', '') or ''
                if dh and not _looks_blocked(dh):
                    return dh, 'dolphin-solved', {}
            except Exception:  # noqa: BLE001
                pass
        # Заглушка прокси течёт и ОТСЮДА: браузер ходит через тот же socks5 и,
        # когда адрес мёртв, приносит те же 181 байт «Proxy Authentication
        # Required». Возвращать их наружу нельзя — конвейер примет за страницу.
        if _zaglushka_proxy(bh):
            bh = ''
        return (h2 or bh) or None, f'site-block:{out.get("captcha_type") or "browser"}', \
            {'captcha_type': out.get('captcha_type') or (meta2 or {}).get('captcha_type')}
    except Exception as e:  # noqa: BLE001
        return (h2 or None), (m2 if h2 else f'browser-err:{str(e)[:40]}'), (meta2 or {})


_COMP_OKVED = ('28.13', '28.12')             # производство насосов/компрессоров/пневмо
_COMP_NAME = re.compile(
    r'компрессормаш|компрессорн\w*\s*завод|завод\w*\s*компрессор|'
    r'насосн\w*\s*завод|компрессорн\w*\s*оборудован', re.I)


def _is_competitor(company):
    """Дешёвый пре-фильтр: производитель компрессоров/насосов = конкурент, не покупатель."""
    okv = str(company.get('okved') or '')
    if any(okv.startswith(x) for x in _COMP_OKVED):
        return True
    return bool(_COMP_NAME.search(company.get('name', '') or ''))


def _finalize_smtp(r):
    """SMTP-верификация email результата (флаг _SMTP_CHECK). Каждому email -> поле smtp
    (smtp_ok/catch-all/smtp_reject/...); smtp_reject исключается из best_for_outreach (на
    мёртвые не шлём - защита репутации домена). Кэш по домену: один диалог на домен. Кап 6."""
    ems = r.get('emails') or []
    if not ems:
        return r
    dom_cache = {}
    checked = 0
    for e in ems:
        addr = (e.get('email') or '').lower()
        if not addr or '@' not in addr:
            continue
        dom = addr.split('@')[-1]
        # catch-all определяется по домену -> но RCPT по адресу; кэшируем статус catch-all
        if checked >= 6:
            break
        st = smtp_verify(addr)
        e['smtp'] = st
        checked += 1
        if st == 'catch-all':
            dom_cache[dom] = 'catch-all'
        time.sleep(1.2)
    # best_for_outreach не должен быть заведомо мёртвым
    best = r.get('best_for_outreach')
    if best:
        bmap = {e.get('email', '').lower(): e.get('smtp') for e in ems}
        if bmap.get(best.lower()) == 'smtp_reject':
            alt = next((e['email'] for e in ems
                        if e.get('smtp') in ('smtp_ok', 'catch-all', None, 'unknown', 'port25_blocked')
                        and e.get('email', '').lower() != best.lower()), '')
            r['best_for_outreach'] = alt
            r['smtp_note'] = f'исходный best {best} = smtp_reject, заменён'
    return r


def persist_contacts(db, inn, r, source='конвейер'):
    """Сохранить результат enrich_one целиком. Возвращает счётчики записанного.

    Появилась после находки 29.07: единственный потребитель результата
    (news_scan) сохранял только `emails` и, отдельно, сайт с лучшим адресом.
    Ключи `phone_roles` и `people` не читал НИКТО — то есть телефон человека из
    блока контактов ВК вместе с его должностью не попадал в базу вообще, хотя
    код, который их наполняет, выглядел рабочим.

    Писатель ОДИН на все три вида записей и ходит через `EnrichDB.add_email` /
    `add_phone` / `add_person`, а не через свой SQL. Это прямое следствие
    правила, выведенного из инцидента с чужими телефонами: рубеж обязан стоять
    в единственной точке входа — первая починка стояла в одном писателе, а
    соседние слои звали базу напрямую и рубеж пережили.
    """
    из = {'почт': 0, 'телефонов': 0, 'людей': 0, 'телефонов_отсеяно': 0}
    inn = str(inn or '').strip()
    if not (db and inn and isinstance(r, dict)):
        return из
    for em in (r.get('emails') or []):
        адрес = (em.get('email') or '').strip().lower() if isinstance(em, dict) else ''
        if not адрес:
            continue
        db.add_email(inn, адрес, role=em.get('role') or '',
                     person=em.get('person') or '', mx_ok=em.get('mx_ok'),
                     source=em.get('source') or source,
                     source_url=em.get('source_url') or '')
        из['почт'] += 1
    for ph in (r.get('phone_roles') or []):
        if not isinstance(ph, dict):
            continue
        номер = (ph.get('phone') or '').strip()
        if not номер:
            continue
        if db.add_phone(inn, номер, person=ph.get('person') or '',
                        role=ph.get('role') or ph.get('dept') or '',
                        source=ph.get('source') or source,
                        source_url=ph.get('source_url') or ''):
            из['телефонов'] += 1
        else:
            из['телефонов_отсеяно'] += 1
    # Человек пишется ДАЖЕ БЕЗ контактов: продажник звонит в приёмную и
    # спрашивает по имени. Собираем людей из обоих мест, где они называются, —
    # из явного списка и из телефонов с ФИО.
    люди = list(r.get('people') or [])
    for ph in (r.get('phone_roles') or []):
        if isinstance(ph, dict) and (ph.get('person') or '').strip():
            люди.append({'person': ph['person'], 'post': ph.get('dept')
                         or ph.get('role') or '', 'phone': ph.get('phone') or '',
                         'source': ph.get('source') or source,
                         'source_url': ph.get('source_url') or ''})
    видано = set()
    for ч in люди:
        if not isinstance(ч, dict):
            continue
        фио = (ч.get('person') or '').strip()
        ключ = (фио.lower(), (ч.get('post') or '').strip().lower())
        if not фио or ключ in видано:
            continue
        видано.add(ключ)
        db.add_person(inn, фио, post=ч.get('post') or '',
                      phone=ч.get('phone') or '', email=ч.get('email') or '',
                      source=ч.get('source') or source,
                      source_url=ч.get('source_url') or '')
        из['людей'] += 1
    return из


def enrich_one(company, pace):
    r = {'inn': company.get('inn'), 'name': company.get('name')}
    # пре-фильтр конкурентов (производители компрессоров) — не тратим на них разведку
    if _is_competitor(company):
        r.update({'method': 'competitor-skip', 'is_competitor': True,
                  'error': 'конкурент (производитель компрессоров/насосов)'})
        return r
    # ОПО-сигнал (скоринг центробежных): эвристический маркер опасного производственного
    # объекта. Флаг opo_check; результат — в r['opo'] независимо от того, найдутся ли контакты.
    if _OPO_CHECK:
        try:
            opo = find_opo_signal(company)
            if opo:
                r['opo'] = opo
        except Exception:  # noqa: BLE001
            pass
    # адресный hh-сигнал: у ЭТОЙ компании открыты компрессорные вакансии = оборудование
    # есть/появляется (прямое подтверждение, не «расширение вообще»)
    if _HH_CHECK:
        try:
            hh = find_hh_compressor(company)
            if hh:
                r['hh'] = hh
        except Exception:  # noqa: BLE001
            pass
    # ЕИС-закупки: контакт закупщика (ФИО+email+тел) из карточек госзакупок компании
    # (владелец 2026-07-23: влить в общий конвейер). source zakupki:eis.
    if _ZAKUPKI_CHECK and company.get('inn'):
        try:
            z = find_zakupki_contacts(company['inn'], max_cards=3)
            if z and z.get('cards'):
                r['zakupki'] = z
                _zem = []
                for c in z['cards']:
                    if c.get('email'):
                        _zem.append({'email': c['email'].lower(), 'role': 'закупки (конт. лицо)',
                                     'person': c.get('contact_person') or '', 'mx_ok': mx_ok(c['email']),
                                     'source': 'zakupki:eis', 'source_url': c.get('url') or '',
                                     'verified_by': 'inn'})
                if _zem:
                    r['emails'] = (r.get('emails') or []) + _zem
                    if not r.get('best_for_outreach'):
                        r['best_for_outreach'] = _zem[0]['email']
        except Exception:  # noqa: BLE001
            pass
    site = company.get('site')
    src = 'given'
    card = {}
    tmr = {}
    # САЙТ ИЗ БАЗЫ — ГЛАВНЫЙ (владелец 11.08.2026). Он пришёл с реестровой выгрузкой и
    # привязан к ИНН, поэтому доверия ему больше, чем первому месту в выдаче. Поиск при
    # этом всё равно зовём — ОДНИМ запросом (0,025 ₽) и НЕ как источник, а как ВТОРОГО
    # свидетеля: совпали домены — сайт подтверждён двумя независимыми источниками, и
    # суждение модели уже не нужно. Замер на 250 строках прогона №2: совпало 195 (78%),
    # разошлось 50, и среди разошедшихся поиск приносил откровенный брак
    # (chelny-holod.ru -> check.tochka.com, sahibi.ru -> eb.archive.org).
    if site and _is_own_site(site if site.startswith('http') else 'http://' + site):
        site = site if site.startswith('http') else 'http://' + site
        src = 'base'
        if not _NO_SITE_CONFIRM:
            try:
                _ss, _ssrc, card = find_site_via_xmlriver(company)
                if _ss and _domain(_ss) == _domain(site):
                    r['site_confirm'] = 'base+serp'          # два источника сошлись
                elif _ss:
                    r['site_serp_other'] = _ss               # разошлись — на ручную сверку
            except Exception:  # noqa: BLE001
                pass
    if not site or not _is_own_site(site if site.startswith('http') else 'http://' + site):
        # ОСНОВНОЙ канал — xmlriver (чистый SERP, без капчи/прокси); фолбэки — list-org и
        # DDG под семафором=1 (не грузить один хост). На массовом прогоне фолбэки ЖГУТ
        # время (сериализуют все воркеры + хардкод-паузы) — _USE_FALLBACK их выключает.
        _t0 = time.time()
        # кэш ИНН->сайт: выключается no_site_cache (если полезут ошибки - источник виден
        # по site_source='cache:enrich-db')
        site = None
        if not _NO_SITE_CACHE:
            site = _site_cache_get(company.get('inn'))
            if site:
                src = 'cache:enrich-db'
        if not site:
            site, src, card = find_site_via_xmlriver(company)
        if not site and _USE_FALLBACK:
            with _SEM_LISTORG:
                site, src = find_site_via_listorg(company)
                time.sleep(_PACE(1.5, 4.0))
        if not site and _USE_FALLBACK:
            with _SEM_SEARCH:
                site, src = find_site_via_search(company)
                time.sleep(_PACE(1.5, 4.0))
        if not site and company.get('base_site'):
            # последний фолбэк: известный сайт из базы [20] (news_enrich кладёт его сюда,
            # чтобы первичным был xmlriver, но не терять базовый сайт, если поиск не нашёл)
            bs = company['base_site']
            bsf = bs if bs.startswith('http') else 'http://' + bs
            if _is_own_site(bsf):
                site, src = bsf, 'base-site'
        tmr['discovery'] = round(time.time() - _t0, 1)
    # карточка Яндекса (телефон/адрес/сайт) ценна даже когда собственный сайт не найден —
    # для 73% базы без сайта это готовый контакт для обзвона/рассылки.
    if card:
        r['card'] = card
    if not site:
        r['method'] = src
        # контакты из карточки Яндекса — С ПОДПИСЬЮ источника и ролью «общий» (владелец
        # 2026-07-23: карточный контакт = приёмная, ценность ниже ЛПР — так он и
        # ранжируется: роль без ЛПР-баллов, source виден продажнику в панели)
        if card.get('phone'):
            r['phones'] = [card['phone']]
            r['phones_source'] = 'serp-card:yandex'
        if card.get('email'):
            r['emails'] = [{'email': card['email'], 'role': 'общий', 'person': '',
                            'mx_ok': mx_ok(card['email']),
                            'source': 'serp-card:yandex',
                            'source_url': card.get('mapurl') or '',
                            'verified_by': 'card-name-match'}]
            r['best_for_outreach'] = card['email']
        # Я.КАРТЫ по mapurl из карточки (владелец 2026-07-23): страница организации в Картах
        # (JS) содержит полный набор — все телефоны, официальный сайт, иногда email. Рендерим
        # браузером; найденный там свой сайт вернёт компанию в основной пайплайн краула.
        if card.get('mapurl') and not r.get('best_for_outreach'):
            _mtxt, _mhtml = _org_page_probe(card['mapurl'])
            if _mtxt:
                _m_em = sorted({e.lower() for e in EMAIL_RE.findall(_mtxt)
                                if not e.lower().endswith(_IMG_EXT)})
                _m_ph = sorted(set(re.sub(r'[\s\-()]', '', _q.group(0))
                                   for _q in phones_in(_mtxt)))[:5]
                _m_site = ''
                for _uu in re.findall(r'https?://[^\s"\'<>]+', _mhtml):
                    if _is_own_site(_uu):
                        _m_site = _uu
                        break
                if _m_em:
                    r['emails'] = (r.get('emails') or []) + [
                        {'email': e, 'role': 'общий', 'person': '', 'mx_ok': mx_ok(e),
                         'source': 'maps:yandex', 'source_url': card['mapurl'],
                         'verified_by': 'card-name-match'} for e in _m_em[:3]]
                    r['best_for_outreach'] = r.get('best_for_outreach') or _m_em[0]
                if _m_ph and not r.get('phones'):
                    r['phones'] = _m_ph
                    r['phones_source'] = 'maps:yandex'
                if _m_site:
                    r['maps_site'] = _domain(_m_site)   # кандидат сайта для будущего краула
        # ЕГРЮЛ-email по ИНН (dadata findById, источник egrul:dadata - директива владельца)
        if not r.get('best_for_outreach') and company.get('inn'):
            _ege = _egrul_emails_by_inn(company['inn'])
            if _ege:
                r['emails'] = (r.get('emails') or []) + [
                    {'email': e, 'role': 'юрзначимый (ЕГРЮЛ)', 'person': '', 'mx_ok': mx_ok(e),
                     'source': 'egrul:dadata', 'source_url': '', 'verified_by': 'inn'}
                    for e in _ege]
                r['best_for_outreach'] = _ege[0]
        # VK-группа компании (владелец: «интересная идея, давай») - контакты с ролями
        #
        # РАНЬШЕ стояло «and not r.get('best_for_outreach')», то есть ВК
        # спрашивался ТОЛЬКО у компаний, где почта ещё не нашлась. Это делало
        # его фолбэком вместо прохода и объясняет расхождение отчётов: «слаг у
        # 41 из 194» против измеренного 51% — просто до большинства компаний
        # очередь не доходила. Ценность ВК не в почте (её обычно и так уже
        # нашли), а в НАЗВАННОМ человеке с должностью и прямым телефоном —
        # ровно том, чего базе не хватает. Ходим ко всем.
        if not _NO_VK_LOOKUP:
            try:
                vkc = find_vk_group_contacts(company)
            except Exception:  # noqa: BLE001
                vkc = None
            if vkc:
                r['vk_group'] = vkc
                # В блоке «Контакты» группы у людей стоит ПОДПИСЬ должности
                # («Главный инженер», «Отдел снабжения»). Раньше она извлекалась
                # и тут же терялась: сохранялись только плоские телефоны и почты
                # с ролью «общий». Теперь роль едет вместе с контактом.
                # ФИО берётся из users.get по user_id блока контактов: раньше
                # тут стояло 'person': '' наглухо, и человек с должностью и
                # номером уезжал в базу безымянным.
                for c in (vkc.get('contacts') or []):
                    роль = (c.get('desc') or '').strip()
                    фио = (c.get('person') or '').strip()
                    if c.get('email'):
                        r['emails'] = (r.get('emails') or []) + [
                            {'email': c['email'], 'role': роль or 'общий',
                             'person': фио, 'mx_ok': mx_ok(c['email']),
                             'source': 'vk-group', 'source_url': vkc['url'],
                             'verified_by': vkc['verified_by']}]
                    # Телефон и человек уезжают в `phone_roles` и `people`, и
                    # то и другое теперь сохраняет `persist_contacts`. До неё
                    # эти два ключа не читал НИКТО: потребитель результата брал
                    # только `emails` и плоские `phones`, поэтому телефон
                    # человека из блока контактов ВК вместе с должностью в базу
                    # не попадал вообще, хотя код выглядел рабочим.
                    if c.get('phone'):
                        r.setdefault('phone_roles', []).append(
                            {'phone': c['phone'], 'role': роль, 'person': фио,
                             'dept': роль, 'source': 'vk-group',
                             'source_url': vkc['url']})
                    if фио:
                        r.setdefault('people', []).append(
                            {'person': фио, 'post': роль,
                             'phone': c.get('phone') or '',
                             'email': c.get('email') or '',
                             'source': 'vk-group', 'source_url': vkc['url']})
                if vkc.get('emails'):
                    известные = {(e.get('email') or '').lower()
                                 for e in (r.get('emails') or [])}
                    r['emails'] = (r.get('emails') or []) + [
                        {'email': e, 'role': 'общий', 'person': '', 'mx_ok': mx_ok(e),
                         'source': 'vk-group', 'source_url': vkc['url'],
                         'verified_by': vkc['verified_by']}
                        for e in vkc['emails'] if e not in известные]
                    r['best_for_outreach'] = _best_by_role(
                        r.get('emails'), r.get('best_for_outreach') or vkc['emails'][0])
                if vkc.get('phones') and not r.get('phones'):
                    r['phones'] = vkc['phones']
                    r['phones_source'] = 'vk-group'
        # #7: собственного сайта нет (хвост 78%) -> ищем контакты в бизнес-справочниках
        if not _NO_DIR_LOOKUP and not r.get('best_for_outreach'):
            try:
                dc = find_directory_contacts(company)
            except Exception:  # noqa: BLE001
                dc = None
            if dc:
                r['directory'] = dc
                _dirsrc = f'directory:{_domain(dc["dir_url"])}'
                if dc.get('emails'):
                    r['emails'] = [{'email': e, 'role': 'общий', 'person': '',
                                    'source_url': dc['dir_url'], 'source': _dirsrc,
                                    'verified_by': dc.get('verified_by')} for e in dc['emails']]
                    r['best_for_outreach'] = dc['emails'][0]
                if dc.get('phones') and not r.get('phones'):
                    r['phones'] = dc['phones']
                r['method'] = f'directory:{_domain(dc["dir_url"])}'
                return r
        r['error'] = f'сайт не найден ({src})' + (' [карточка Я есть]' if card else '')
        if _SMTP_CHECK:
            _finalize_smtp(r)
        return r
    if not site.startswith('http'):
        site = 'http://' + site
    r['site'] = _domain(site)
    r['site_source'] = src
    # ФАЗИРОВКА (владелец 2026-07-23): discovery_only = только НАЙТИ сайт (дёшево, чистый
    # xmlriver), краул/staff/провайдер — отдельной фазой позже по готовому списку сайтов.
    if _DISCOVERY_ONLY:
        r['method'] = 'discovery-only'
        return r
    time.sleep(_PACE(*pace))
    # поисковый этап: staff-страница компании через SERP (устойчив к вариациям URL).
    # Выключается флагом no_staff_search (для быстрых прогонов/экономии xmlriver-квоты).
    staff_urls = []
    if not _NO_STAFF_SEARCH:
        try:
            staff_urls = find_staff_via_search(company, _domain(site))
            if staff_urls:
                r['staff_search'] = staff_urls
        except Exception:  # noqa: BLE001
            pass
    _t0 = time.time()
    text, pages, err, csrc = crawl_contacts(site, pace, extra_pages=staff_urls,
                                            inn=str(company.get('inn') or ''),
                                            ogrn=str(company.get('ogrn') or ''))
    tmr['crawl'] = round(time.time() - _t0, 1)
    if csrc:
        r['contact_src'] = csrc   # разбор разметок: метод+local-part+контекст по каждому email
        _sm = csrc.get('meta') or {}
        if _sm:
            # отдельными полями, а НЕ только внутри contact_src: это первоисточник о
            # деятельности, его должно быть видно в карточке и запросом по базе
            r['site_title'] = _sm.get('title', '')
            r['site_description'] = _sm.get('description') or _sm.get('og') or ''
            r['site_meta_url'] = _sm.get('url', '')
    if err:
        r['timings'] = tmr
        r['error'] = err
        return r
    if _RETURN_TEXT:
        r['crawled_text'] = text[:24000]  # для офлайн модель-сравнения экстрактора
    _t0 = time.time()
    if _SKIP_PROVIDER:
        # только краул+regex, без provider (быстрый сбор текстов для модель-теста)
        emails = sorted(set(e.lower() for e in EMAIL_RE.findall(text)
                            if not e.lower().endswith(('.png', '.jpg', '.gif', '.webp'))))
        data, how = {'emails': [{'email': e, 'role': 'общий', 'person': ''} for e in emails[:8]],
                     'phones': [], 'best_for_outreach': emails[0] if emails else ''}, 'regex-skip'
    else:
        data, how = extract_roles(text, company)
    tmr['provider'] = round(time.time() - _t0, 1)
    r['timings'] = tmr
    # --- верификация принадлежности сайта именно этой компании ---
    digits = re.sub(r'\D', '', text)
    inn = str(company.get('inn') or '')
    ogrn = str(company.get('ogrn') or '')
    verified = None
    if inn and re.search(r'\b' + re.escape(inn) + r'\b', text):
        verified = 'inn'                       # ИНН найден на сайте — жёсткое совпадение
        r['verified_url'] = (csrc or {}).get('inn_url', '')
    elif ogrn and ogrn in digits:
        verified = 'ogrn'
        r['verified_url'] = (csrc or {}).get('ogrn_url', '')
    else:
        # ДОБОР РЕКВИЗИТОВ (владелец 11.08.2026). Краул идёт по ссылкам с главной, а
        # страница реквизитов часто не слинкована ниоткуда — замер поймал такое у
        # «Чебоксарского агрегатного»: ИНН на сайте есть, обычной меркой находится, но
        # обход до страницы не доходил. Спрашиваем её у поиска ПРЯМО на домене и
        # смотрим ИНН и в тексте, и в ИСХОДНИКЕ (второй случай замера: ИНН жил только
        # в атрибуте разметки). Зовём ТОЛЬКО когда жёсткого совпадения ещё нет.
        if inn and not _NO_REKV_SEARCH:
            try:
                for _ru in find_rekvizity_via_search(company, _domain(site)):
                    _rh, _rm, _rmt = _fetch_site(_ru)
                    if not _rh:
                        continue
                    _rt = re.sub(r'<[^>]+>', ' ', re.sub(
                        r'<(script|style)[^>]*>.*?</\1>', ' ', _rh, flags=re.S | re.I))
                    if (re.search(r'\b' + re.escape(inn) + r'\b', _rt)
                            or inn in re.sub(r'\D', '', _rh)):
                        verified = 'inn'
                        r['rekvizity_url'] = _ru   # ссылка-доказательство, как везде
                        r['verified_url'] = _ru
                        text = text + ' Реквизиты(добор): ' + re.sub(r'\s+', ' ', _rt)[:4000]
                        break
            except Exception:  # noqa: BLE001
                pass
    if verified is None:
        # телефон из базы совпал с телефоном на сайте?
        base_phones = {re.sub(r'\D', '', p)[-10:] for p in (company.get('phones') or []) if p}
        site_phones = {re.sub(r'\D', '', m1.group(0))[-10:] for m1 in phones_in(text)}
        if base_phones and (base_phones & site_phones):
            verified = 'phone'
        elif data.get('owner_match') is False:
            verified = 'mismatch'              # провайдер читал страницу: чужой сайт
        elif r.get('site_confirm') == 'base+serp':
            # реестровая выгрузка и поисковая выдача назвали ОДИН домен независимо друг
            # от друга. Это доказательство двумя источниками, а не мнение — поэтому выше
            # 'provider'. Ниже 'mismatch': тот, кто прочитал саму страницу, весомее.
            verified = 'base+serp'
        elif data.get('owner_match') is True:
            verified = 'provider'              # провайдер-судья подтвердил
    # СВЕРКА ГЕОГРАФИИ (владелец 12.08). Чужой сайт чаще выдаёт себя не именем, а
    # адресом: у «ГСМ» прописка Тюмень, а на странице «350022, Краснодар». Пишем
    # вердикт ВСЕГДА (это поле для разбора), а понижаем ТОЛЬКО 'provider' — самый
    # слабый из положительных, где за сайт ручается лишь мнение модели. 'inn',
    # 'ogrn', 'base+serp', 'phone' опираются на улику и географией не отменяются:
    # филиалы и переезды бывают, а замер показал 1,7% ложных срабатываний.
    _reg, _adr = (_geo_bazy().get(str(company.get('inn') or '')) or ('', ''))
    _reg = str(company.get('region') or _reg or '')
    _adr = str(company.get('address') or _adr or '')
    r['region_sverka'] = region_sverka(inn, text, region=_reg, adres=_adr)
    if verified == 'provider' and r['region_sverka'] == 'расходится':
        verified = 'спорно'
        r['spor'] = ('на странице адрес другого региона (у компании по выгрузке — %s), '
                     'а за сайт ручается только мнение модели' % (_reg or 'неизвестен'))
    # ВЕРДИКТ «ЧУЖОЙ САЙТ» — ЕЩЁ НЕ ПРИГОВОР КОНТАКТАМ (владелец 11.08.2026).
    # Раньше mismatch стирал ВСЕ найденные контакты. Смотрим, чей домен по базе обзвона:
    #   за этим же ИНН  -> модель спорит с реестровой выгрузкой; контакты оставляем,
    #                      метку ставим 'спорно' (сайт при этом остаётся кандидатом);
    #   за другой фирмой из базы -> контакты не мусор, у них другой хозяин, и он тоже
    #                      наш лид: складываем их ЕМУ (r['perenos']), себе не берём;
    #   домена в базе нет -> вердикт скорее верен, ведём себя как раньше.
    if verified == 'mismatch':
        _d = _domain(site)
        _vlad, _imya = (_domeny_bazy().get(_d) or (set(), ''))
        _moy = str(company.get('inn') or '')
        if _moy and _moy in _vlad:
            verified = 'спорно'
            r['spor'] = 'база закрепляет %s за этим ИНН, а провайдер сказал «чужой»' % _d
        elif len(_vlad) == 1:          # ровно один хозяин: перекладывать безопасно
            _hoz = next(iter(_vlad))
            r['perenos'] = {'inn': _hoz, 'name': _imya, 'domain': _d}
        # ИНН В ПОДВАЛЕ САМОЙ СТРАНИЦЫ — источник сильнее выгрузки (разбор 600
        # чужих сайтов: ИНН на странице у 215, закрепление домена лишь у 17).
        # Если этот ИНН есть в базе обзвона — контакты уезжают ему, как и раньше.
        # Если нет — компания живая, сайт и контакты у нас уже на руках, и мы
        # кладём её отдельно: при расширении базы она прицепится без обхода.
        if not r.get('perenos'):
            for _ci in inn_so_stranicy(text, inn):
                _v = _base_index({_ci})
                if _ci in _v:
                    r['perenos'] = {'inn': _ci, 'name': '', 'domain': _d,
                                    'kak': 'инн-на-странице'}
                else:
                    r['vne_bazy'] = {'inn': _ci, 'domain': _d,
                                     'found_via': 'инн-на-странице',
                                     'site_title': r.get('site_title', '')}
                break
    # конкурент по тексту сайта (сам производит компрессоры/насосы) — не для рассылки
    is_comp = bool(data.get('is_compressor_maker'))
    blocked = (verified == 'mismatch') or is_comp
    emails = data.get('emails', []) if not blocked else []
    if r.get('perenos') and not is_comp:
        # контакты уезжают хозяину домена: собираем их отдельно, себе не пишем.
        # Ссылку на страницу-источник тащим с собой — без неё контакт у чужой
        # компании выглядел бы взявшимся ниоткуда.
        _um = (csrc or {}).get('emails', {})
        _peren = []
        for _e in (data.get('emails') or []):
            if not _e.get('email'):
                continue
            _e = dict(_e)
            _e['source_url'] = (_um.get(_e['email'].lower().strip()) or {}).get('url', '')
            _peren.append(_e)
        r['perenos']['emails'] = _peren
        r['perenos']['phones'] = data.get('phones') or []
    if r.get('vne_bazy') and not is_comp:
        _um2 = (csrc or {}).get('emails', {})
        _sp = []
        for _e in (data.get('emails') or []):
            if not _e.get('email'):
                continue
            _e = dict(_e)
            _es2 = _um2.get(_e['email'].lower().strip()) or {}
            _e['source_url'] = _es2.get('url', '')
            _e['razdel'] = _es2.get('razdel', '')
            _sp.append(_e)
        r['vne_bazy']['emails'] = _sp
    _urlmap = (csrc or {}).get('emails', {})
    for e in emails:
        e['mx_ok'] = mx_ok(e.get('email', ''))
        # провенанс контакта: точная страница-источник + КАНАЛ (метод извлечения),
        # чтобы продажник видел «откуда» без сопоставления с contact_src.
        _es = _urlmap.get((e.get('email') or '').lower().strip()) or {}
        e['source_url'] = _es.get('url', '')
        e['source_urls'] = _es.get('urls') or ([_es['url']] if _es.get('url') else [])
        e['razdel'] = _es.get('razdel', '')   # «Отдел материального снабжения» и т.п.
        # канал: staff-страница / сайт-контакты / главная / js-render — по URL и методу
        _u = (e['source_url'] or '').lower()
        if any(h in _u for h in _STAFF_HINTS):
            e['source'] = 'own-site:staff'
        elif _es.get('src') == 'js-render':
            e['source'] = 'own-site:js'
        else:
            e['source'] = 'own-site'
    # ХОЛДИНГОВЫЙ ДОМЕН (владелец 11.08: «только тех роли прикрепи и подпиши, что это
    # холдинг»). Если сайт закреплён в базе обзвона за НЕСКОЛЬКИМИ юрлицами, то info@,
    # отдел продаж и бухгалтерия принадлежат холдингу вообще, а не этому заводу —
    # письмо про компрессор туда уходит в никуда. Технические роли и снабжение
    # (ранг <= 17) остаются: за оборудование конкретной площадки отвечают именно они.
    # Ничего не удаляем — ставим пометку, по которой выбор адресата их пропускает.
    _hd = _domain(site)
    _hvlad = (_domeny_bazy().get(_hd) or (set(), ''))[0]
    if len(_hvlad) > 1:
        r['holding'] = {'domain': _hd, 'vladelcev': len(_hvlad)}
        for e in emails:
            _rr = _ROLE_RANK.get((e.get('role') or '').strip().lower())
            if _rr is None:
                _rr = (_ROLE_RANK['общий'] - 1 if _pohozh_na_cheloveka(e.get('person'))
                       else _ROLE_RANK['общий'] + 1)
            if _rr <= _ROLE_RANK['снабжение/закупки']:
                e['pometka'] = ('холдинг: %s общий с %d юрлицами; роль техническая — оставлен'
                                % (_hd, len(_hvlad)))
            else:
                e['pometka'] = ('холдинг: %s общий с %d юрлицами; роль «%s» не техническая — '
                                'не использовать'
                                % (_hd, len(_hvlad), e.get('role') or 'не определена'))
        _godn = [e for e in emails if 'не использовать' not in (e.get('pometka') or '')]
        data['best_for_outreach'] = _best_by_role(_godn) if _godn else ''
    r.update({'emails': emails, 'phones': data.get('phones', []),
              'best_for_outreach': data.get('best_for_outreach', '') if not blocked else '',
              'activity': data.get('activity', ''), 'is_competitor': is_comp,
              'pages_crawled': pages, 'extract': how, 'method': 'ok',
              'verified': verified, 'owner_reason': data.get('owner_reason', '')})
    if is_comp:
        r['error'] = 'конкурент (производит компрессоры/насосы — по тексту сайта)'
    elif verified == 'mismatch':
        r['error'] = 'сайт НЕ этой компании (провайдер-судья)'
    elif not emails:
        r['error'] = 'email на сайте не найдены'
    # ДОБОР для компаний С сайтом, но без найденного на нём email (владелец: обогащать
    # как можно полнее). Раньше эти доноры (ЕГРЮЛ/справочник) работали ТОЛЬКО в ветке
    # «сайт не найден» — компании с сайтом, но пустым краулом, бросались без контакта.
    if not blocked and not r.get('best_for_outreach') and company.get('inn'):
        try:
            _ege = _egrul_emails_by_inn(company['inn'])
        except Exception:  # noqa: BLE001
            _ege = None
        if _ege:
            r['emails'] = (r.get('emails') or []) + [
                {'email': e, 'role': 'юрзначимый (ЕГРЮЛ)', 'person': '', 'mx_ok': mx_ok(e),
                 'source': 'egrul:dadata', 'source_url': '', 'verified_by': 'inn'}
                for e in _ege]
            r['best_for_outreach'] = _ege[0]
            r.pop('error', None)
    if not blocked and not r.get('best_for_outreach') and not _NO_DIR_LOOKUP:
        try:
            dc = find_directory_contacts(company)
        except Exception:  # noqa: BLE001
            dc = None
        if dc and dc.get('emails'):
            r['directory'] = dc
            _dirsrc = f'directory:{_domain(dc["dir_url"])}'
            r['emails'] = (r.get('emails') or []) + [
                {'email': e, 'role': 'общий', 'person': '', 'source_url': dc['dir_url'],
                 'source': _dirsrc, 'verified_by': dc.get('verified_by')} for e in dc['emails']]
            r['best_for_outreach'] = dc['emails'][0]
            if dc.get('phones') and not r.get('phones'):
                r['phones'] = dc['phones']
                r['phones_source'] = _dirsrc
            r.pop('error', None)
    if _SMTP_CHECK:
        _finalize_smtp(r)
    return r


def _find_base():
    """Найти obzvon_all*.csv в storage дропа / известных местах."""
    import glob
    _d = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get('BASE_CSV', ''),
             os.path.join(os.environ.get('DROP_DIR', ''), 'obzvon_all_2026-07-16.csv')
             if os.environ.get('DROP_DIR') else '',
             r'C:\seostat\drop\drop-storage\obzvon_all_2026-07-16.csv',
             os.path.join(_d, 'drop-storage', 'obzvon_all_2026-07-16.csv')]
    for c in cands:
        if c and os.path.exists(c):
            return c
    for root in (_d, os.path.dirname(_d), r'C:\sender'):
        try:
            hits = glob.glob(os.path.join(root, '**', 'obzvon_all*.csv'), recursive=True)
            if hits:
                return max(hits, key=os.path.getsize)
        except Exception:  # noqa: BLE001
            continue
    return None


def _get_base(name='obzvon_all_2026-07-16.csv'):
    """Локальный путь к базе; если не найден — скачать с дропа в кэш (канонический источник)."""
    p = _find_base()
    if p:
        return p
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.base_cache.csv')
    if os.path.exists(cache) and os.path.getsize(cache) > 100_000_000:
        return cache
    url = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/') + '/' + name
    req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(req, timeout=900) as r, open(cache, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return cache if os.path.getsize(cache) > 100_000_000 else None


def _base_peek(n=3):
    import csv
    p = _get_base()
    if not p:
        return {'error': 'база не найдена (ни локально, ни на дропе)'}
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')
        header = next(rd, [])
        rows = [next(rd, []) for _ in range(n)]
    cols = [{'i': i, 'name': (header[i] if i < len(header) else ''),
             'samples': [r[i] if i < len(r) else '' for r in rows]} for i in range(len(header))]
    return {'path': p, 'ncols': len(header), 'columns': cols}


def _base_index(inn_set):
    """Один проход по базе → {ИНН: {name, site, city, phones}} для ИНН из inn_set. Нужен
    news_enrich: по новостной компании берём известный сайт [20] из базы (краулим его без
    xmlriver — эффективно), город из юрадреса [9], телефоны [18] для верификации сайта."""
    import csv
    p = _get_base()
    if not p or not inn_set:
        return {}
    INN, KRAT, POLN, ADDR, REG, OKVED, PHONES, SITE, REV = 1, 5, 6, 9, 10, 16, 18, 20, 34
    try:
        csv.field_size_limit(2 ** 18)
    except Exception:  # noqa: BLE001
        pass
    want = set(str(i) for i in inn_set)
    out = {}
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')
        next(rd, None)
        while True:
            try:
                row = next(rd)
            except StopIteration:
                break
            except Exception:  # noqa: BLE001
                continue
            if len(row) <= SITE:
                continue
            inn = (row[INN] or '').strip()
            if inn not in want:
                continue
            addr = row[ADDR] or ''
            mc = re.search(r'(?:\bг\.\s*|\bгород\s+|\bпгт\.?\s*|\bп\.\s*|\bс\.\s*|\bсело\s+|'
                           r'\bдер\.\s*|\bд\.\s*|\bрп\.?\s*|\bстаница\s+)([А-ЯЁ][А-Яа-яЁё-]+)', addr)
            site = re.split(r'[ ,;|]+', (row[SITE] or '').strip())[0]
            out[inn] = {'name': (row[POLN] or row[KRAT] or '').strip(),
                        'site': site if site.startswith('http') else (f'http://{site}' if site else ''),
                        'city': (mc.group(1) if mc else '') or (row[REG] or '').strip(),
                        'okved': (row[OKVED] or '').strip(),
                        'revenue': (row[REV] or '').strip() if len(row) > REV else '',
                        'phones': [x.strip() for x in (row[PHONES] or '').split('|') if x.strip()][:4]}
            if len(out) >= len(want):
                break
    return out


def _base_pick(no_site=True, size_col=None, limit=500, okved_prefixes=None):
    """csv.reader (правильно разбирает ';' ВНУТРИ кавычек — иначе колонка [32] «Найденные
    ОКВЭД» с ';' сдвигает выравнивание и выручку [34]), авто-раскавычивает имена.
    Фильтр (без сайта), ранжируем по size_col (выручка), топ-N."""
    import csv
    p = _get_base()
    if not p:
        return {'error': 'база не найдена'}
    INN, KRAT, POLN, ADDR, REG, DIRECTOR, OKVED, OKVED_ALL, PHONES, SITE = 1, 5, 6, 9, 10, 13, 16, 17, 18, 20
    if size_col is None:
        size_col = 34
    try:
        csv.field_size_limit(2 ** 18)  # 256КБ: легит-поля влезают, «сбежавшие» кавычки
        # быстро дают csv.Error (строка пропускается) вместо буферизации мегабайтов = не тормозим
    except Exception:  # noqa: BLE001
        pass
    picked = []
    scanned = 0
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')  # QUOTE_MINIMAL по умолчанию — корректно
        next(rd, None)  # header
        while True:
            try:
                row = next(rd)
            except StopIteration:
                break
            except Exception:  # noqa: BLE001
                continue  # битая строка — пропускаем, скан не рушим
            scanned += 1
            if len(row) <= size_col:
                continue
            site = (row[SITE] or '').strip()
            if no_site and site:
                continue
            if okved_prefixes and (row[OKVED] or '')[:2] not in okved_prefixes:
                continue
            try:
                sz = float(re.sub(r'[^\d.]', '', (row[size_col] or '0').replace(',', '.')) or 0)
            except Exception:  # noqa: BLE001
                sz = 0.0
            # ГОРОД из полного юрадреса [9] (в базе он точный, ЕГРЮЛ): «г. Чехов», «пгт Х»,
            # «с. Y» — точнее для xmlriver-поиска сайта, чем регион; фолбэк — регион [10].
            addr = (row[ADDR] or '') if len(row) > ADDR else ''
            mc = re.search(r'(?:\bг\.\s*|\bгород\s+|\bпгт\.?\s*|\bп\.\s*|\bс\.\s*|\bсело\s+|'
                           r'\bдер\.\s*|\bд\.\s*|\bрп\.?\s*|\bстаница\s+)([А-ЯЁ][А-Яа-яЁё-]+)', addr)
            city = (mc.group(1) if mc else '') or (row[REG] or '').strip()
            phones = [p.strip() for p in (row[PHONES] or '').split('|') if p.strip()] \
                if len(row) > PHONES else []
            picked.append((sz, {'inn': (row[INN] or '').strip(),
                                'name': (row[POLN] or row[KRAT] or '').strip(),
                                'city': city, 'region': (row[REG] or '').strip(),
                                'director': (row[DIRECTOR] or '').strip() if len(row) > DIRECTOR else '',
                                'phones': phones[:4],
                                'okved': (row[OKVED] or '').strip(),
                                'okved_all': (row[OKVED_ALL] or '').strip()[:600]
                                if len(row) > OKVED_ALL else '',
                                'site': (row[SITE] or '').strip(), 'size': sz}))
    picked.sort(key=lambda t: t[0], reverse=True)
    return {'path': p, 'scanned': scanned, 'total_no_site': len(picked),
            'companies': [c for _s, c in picked[:limit]]}


def _done_inns(dirpath):
    """Множество уже обработанных ИНН из ВСЕХ enrich_stream*.jsonl (резюмируемость массового
    прогона: при рестарте не перекрауливаем сделанное). jsonl устойчив к битым строкам.
    ПЕРЕПРОВЕРКА ПРОВАЙДЕР-ФЕЙЛОВ: запись extract='regex-provider-fail' (провайдер лежал) НЕ
    считается done, пока не набрано _PROVFAIL_CAP попыток → компания переобработается на
    следующих чанках цепочки (провайдер к тому времени ожил → получит роли)."""
    import glob
    _PROVFAIL_CAP = 3
    done = set()
    fails = {}
    for fp in glob.glob(os.path.join(dirpath, 'enrich_stream*.jsonl')):
        try:
            with open(fp, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    inn = str(rec.get('inn') or '')
                    if not inn:
                        continue
                    if rec.get('extract') == 'regex-provider-fail':
                        fails[inn] = fails.get(inn, 0) + 1   # копим попытки, пока НЕ done
                    else:
                        done.add(inn)                        # любой иной исход = done
        except Exception:  # noqa: BLE001
            pass
    for inn, c in fails.items():   # исчерпали лимит попыток → принимаем как есть (не зацикливаемся)
        if c >= _PROVFAIL_CAP:
            done.add(inn)
    return done


def _chain_next(args):
    """Самочейнинг серверного mass-прогона: пишем СЛЕДУЮЩИЙ подписанный job на дроп, чтобы
    раннер продолжил БЕЗ песочницы (она реапит фон-процессы). Пишем в НАЧАЛЕ обработки чанка
    (переживает таймаут раннера). Стоп-флаг НЕЗАВИСИМЫЙ по режиму: news_enrich → news_stop.flag,
    иначе mass_stop.flag (иначе новостное обогащение вставало бы вместе с массовым). Либо пустой
    пул (следующий чанк обработает 0 компаний → не зачейнит). done-set гарантирует отсутствие дублей."""
    import hmac as _h, hashlib as _hl
    drop = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    sec = os.environ.get('JOB_SECRET', '')
    stop_flag = 'news_stop.flag' if args.get('news_enrich') else 'mass_stop.flag'
    if not (drop and tok):
        return 'no-drop-env'
    try:
        req = urllib.request.Request(drop + '/list', headers={'X-Drop-Token': tok})
        files = json.loads(urllib.request.urlopen(req, timeout=30).read())
        if any(f.get('name') == stop_flag for f in files):
            return 'stopped-by-flag'
    except Exception:  # noqa: BLE001
        pass
    jid = f'{int(time.time())}-chain{os.getpid()}'
    job = {'id': jid, 'task': 'enrich_contacts', 'args': args, 'ts': int(time.time())}
    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'],
                        'ts': job['ts']}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    if sec:
        job['sig'] = _h.new(sec.encode(), canon.encode(), _hl.sha256).hexdigest()
    try:
        req = urllib.request.Request(drop + f'/job-{jid}.json',
                                     data=json.dumps(job, ensure_ascii=False).encode('utf-8'),
                                     method='PUT', headers={'X-Drop-Token': tok})
        urllib.request.urlopen(req, timeout=60)
        return jid
    except Exception as e:  # noqa: BLE001
        return f'chain-err:{str(e)[:60]}'


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:
        args = {}
    if args.get('op') == 'news_inn_coverage':
        # Сколько новостных ИНН (signals) есть/нет в базе обзвона — сверка утверждения
        # инженера «139 из 145 вне базы». Возврат: всего сигнальных ИНН, в базе, вне
        # базы, примеры вне базы с названием+ОКВЭД (для решения владельца).
        import enrich_db as _EDBc
        try:
            _cxc = _EDBc.EnrichDB().cx
            if args.get('only_inns'):
                sig_inns = [str(i).strip() for i in args['only_inns'] if str(i).strip()]
            else:
                sig_inns = [str(r[0]) for r in _cxc.execute(
                    "SELECT DISTINCT inn FROM signals WHERE inn!='' AND inn IS NOT NULL").fetchall()]
        except Exception as e:  # noqa: BLE001
            json.dump({'op': 'news_inn_coverage', 'error': f'db: {str(e)[:80]}'},
                      sys.stdout, ensure_ascii=False); return
        idx = _base_index(set(sig_inns))          # только те, что реально в базе обзвона
        in_base = [i for i in sig_inns if i in idx]
        out_base = [i for i in sig_inns if i not in idx]
        # имена вне базы — из enrich.db companies (если есть)
        nm = {}
        try:
            for r in _cxc.execute('SELECT inn,name FROM companies').fetchall():
                nm[str(r[0])] = r[1] or ''
        except Exception:  # noqa: BLE001
            pass
        json.dump({'op': 'news_inn_coverage',
                   'signal_inns_total': len(sig_inns),
                   'in_obzvon_base': len(in_base),
                   'out_of_base': len(out_base),
                   'sample_out': [{'inn': i, 'name': nm.get(i, '')[:50]} for i in out_base[:25]],
                   'sample_in': [{'inn': i, 'name': (idx[i].get('name') or '')[:50],
                                  'okved': idx[i].get('okved', '')} for i in in_base[:10]]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'okved_audit':
        # АУДИТ ОКВЭД по всей базе обзвона (161k): (1) конкуренты — компании с
        # ОКВЭД-производителем оборудования (28.13 подтв. + кандидаты) во ВСЕХ ОКВЭД,
        # они загрязняют рассылку; (2) карта частота↔приоритет каждого ОКВЭД —
        # видно, какие таргет-коды дают мало/много компаний. Владелец: «увидим где
        # база не полная». Читает ВсеОКВЭД (col 17), а не только основной.
        import csv as _csvA
        import enrich_db as _EDBa
        from collections import Counter as _CtA
        p = _get_base()
        if not p:
            json.dump({'op': 'okved_audit', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        INN, OKVED, OKVED_ALL = 1, 16, 17
        try:
            _csvA.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        cand = dict(_EDBa.COMPETITOR_OKVEDS); cand.update(_EDBa.COMPETITOR_OKVEDS_CANDIDATES)
        comp_hit = _CtA()          # код-конкурент -> сколько компаний базы его имеют
        comp13_and_target = 0      # 28.13-конкурент, НО матчит таргет (сейчас шлём ему!)
        cand_and_target = 0        # кандидат-конкурент + таргет (для оценки, если подтвердят)
        code_freq = _CtA()         # каждый ОКВЭД-код (осн+доп) -> частота в базе
        target_via_second = 0      # таргет только в доп-ОКВЭД, в основном нет (скрытый лид)
        sample13 = []              # примеры где 28.13 ОСНОВНОЙ (точно производитель)
        sample13_sec = []          # примеры где 28.13 только вторичный (обычно клиент!)
        total = 0
        _codere = re.compile(r'\d{2}\.\d+(?:\.\d+)?|(?<!\d)\d{2}(?!\d)')
        POLN, KRAT = 6, 5
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csvA.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                if len(row) <= OKVED_ALL:
                    continue
                total += 1
                prim = row[OKVED] or ''
                allo = (row[OKVED] or '') + ' ' + (row[OKVED_ALL] or '')
                comp13, h13 = _EDBa.is_competitor_by_okved(allo)                 # только 28.13
                comp13_prim, _ = _EDBa.is_competitor_by_okved(prim)              # 28.13 в ОСНОВНОМ
                is_cand, hits = _EDBa.is_competitor_by_okved(allo, extra=set(_EDBa.COMPETITOR_OKVEDS_CANDIDATES))
                da, _ = _EDBa.division_for_okveds(allo)
                if comp13:
                    comp_hit['28.13'] += 1
                    if comp13_prim:
                        comp_hit['28.13_primary'] += 1
                    if da:
                        comp13_and_target += 1
                    # примеры: отдельно где основной 28.13 (точно производитель) и где вторичный
                    _bucket = sample13 if comp13_prim else sample13_sec
                    if len(_bucket) < 12:
                        _bucket.append({'inn': (row[INN] or '').strip(),
                                        'name': (row[POLN] or row[KRAT] or '').strip()[:45],
                                        'okved_osn': prim.strip()[:40]})
                for h in hits:
                    if h in _EDBa.COMPETITOR_OKVEDS_CANDIDATES:
                        comp_hit[h] += 1
                if is_cand and da:
                    cand_and_target += 1
                for c in set(_codere.findall(allo)):
                    code_freq[c] += 1
                dp, _ = _EDBa.division_for_okveds(prim)
                if da and not dp:
                    target_via_second += 1
        # карта: для каждого таргет-ОКВЭД — приоритет + сколько компаний в базе
        tgt_map = []
        for k, (d, b) in sorted(_EDBa.OKVED_DIRECTIONS.items()):
            n = sum(v for c, v in code_freq.items() if c == k or c.startswith(k + '.'))
            tgt_map.append({'okved': k, 'div': d, 'budget': b, 'companies_in_base': n})
        json.dump({'op': 'okved_audit', 'base_total': total,
                   'competitor_confirmed': {k: comp_hit.get(k, 0) for k in _EDBa.COMPETITOR_OKVEDS},
                   'competitor_28_13_currently_in_target': comp13_and_target,
                   'competitor_candidates': {k: comp_hit.get(k, 0) for k in _EDBa.COMPETITOR_OKVEDS_CANDIDATES},
                   'candidates_AND_target_if_confirmed': cand_and_target,
                   'target_only_in_secondary_okved': target_via_second,
                   'c28_13_primary': comp_hit.get('28.13_primary', 0),
                   'c28_13_secondary_only': comp_hit.get('28.13', 0) - comp_hit.get('28.13_primary', 0),
                   'sample_28_13_primary': sample13,
                   'sample_28_13_secondary': sample13_sec,
                   'target_map': tgt_map}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'obzvon_fix_base_label':
        # ФИКС метки «База» у добавленных строк: индексатор company_card ждёт
        # «Компрессор Центр» (см. BASE_LABEL map), я записал «КЦ» → 35 строк ушли
        # в division '?'. Меняем значение колонки 0 у строк с База='КЦ'.
        import csv as _csvF
        import shutil as _shF
        p = _get_base()
        try:
            _csvF.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        bak = p + f'.bak-fix-{time.strftime("%Y%m%d-%H%M%S")}'
        _shF.copy2(p, bak)
        tmp = p + '.tmp'
        fixed = 0
        with open(p, encoding='utf-8-sig', newline='') as fi, \
             open(tmp, 'w', encoding='utf-8', newline='') as fo:
            rd = _csvF.reader(fi, delimiter=';')
            w = _csvF.writer(fo, delimiter=';')
            for row in rd:
                if row and (row[0] or '').strip() == 'КЦ':
                    row[0] = 'Компрессор Центр'
                    fixed += 1
                w.writerow(row)
        os.replace(tmp, p)
        json.dump({'op': 'obzvon_fix_base_label', 'fixed': fixed,
                   'backup': os.path.basename(bak)}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'obzvon_append':
        # ЗАПИСЬ строк В БАЗУ ОБЗВОНА (команда владельца 2026-07-24: «запиши их в
        # базу обзвона» — 38 новостных вне базы). Вход: append_file на дропе (CSV ';'
        # с шапкой = хедер базы). Порядок: бэкап базы → дедуп по ИНН → append.
        # Гейт увидит новые строки после перестройки obzvon-index.db — отдельный шаг.
        import csv as _csvO
        import shutil as _shO
        p = _get_base()
        if not p:
            json.dump({'op': 'obzvon_append', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        fn = args.get('append_file', 'obzvon-append-38.csv')
        try:
            blob = _DIRECT.open(urllib.request.Request(
                os.environ.get('DROP_URL', '').rstrip('/') + '/' + fn,
                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}), timeout=60).read()
        except Exception as e:  # noqa: BLE001
            json.dump({'op': 'obzvon_append', 'error': f'download {fn}: {str(e)[:80]}'},
                      sys.stdout, ensure_ascii=False)
            return
        try:
            _csvO.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        new_rows = list(_csvO.reader(blob.decode('utf-8-sig', 'replace').splitlines(), delimiter=';'))
        if len(new_rows) < 2:
            json.dump({'op': 'obzvon_append', 'error': 'append-файл пуст'}, sys.stdout, ensure_ascii=False)
            return
        app_hdr, app_data = new_rows[0], new_rows[1:]
        with open(p, encoding='utf-8-sig', newline='') as f:
            base_hdr2 = next(_csvO.reader(f, delimiter=';'))
        if [h.strip() for h in app_hdr] != [h.strip() for h in base_hdr2]:
            json.dump({'op': 'obzvon_append', 'error': 'шапка append-файла не совпадает с базой',
                       'base_hdr': base_hdr2[:6], 'append_hdr': app_hdr[:6]},
                      sys.stdout, ensure_ascii=False)
            return
        exist = set()
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csvO.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                if len(row) > 1:
                    exist.add((row[1] or '').strip())
        add = [r for r in app_data if len(r) > 1 and (r[1] or '').strip()
               and (r[1] or '').strip() not in exist]
        skipped = len(app_data) - len(add)
        bak = p + f'.bak-{time.strftime("%Y%m%d-%H%M%S")}'
        _shO.copy2(p, bak)
        with open(p, 'a', encoding='utf-8', newline='') as f:
            w = _csvO.writer(f, delimiter=';')
            w.writerows(add)
        json.dump({'op': 'obzvon_append', 'appended': len(add), 'skipped_dup': skipped,
                   'backup': os.path.basename(bak), 'base_path': p,
                   'note': 'гейт увидит после перестройки obzvon-index.db'},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'base_header':
        # хедер базы обзвона с индексами — чтобы точно замапить полезные колонки
        # (оборудование/баллы/категории) в кампанию.
        p = _get_base()
        import csv as _csvB
        with open(p, encoding='utf-8-sig', newline='') as f:
            hdr = next(_csvB.reader(f, delimiter=';'))
        json.dump({'op': 'base_header', 'columns': [{'i': i, 'name': h} for i, h in enumerate(hdr)]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'news_campaign':
        # КАМПАНИЯ по новостным лидам (владелец: «собери чтобы мог отправлять»):
        # подходящие по ОКВЭД вне базы (fit_map: inn->division_proposed из checko) +
        # сигнальные ИНН, что ЕСТЬ в базе обзвона (у них направление точное). Джойн с
        # enrich.db (контакты) + signals (новостной повод) + база (город/направление).
        # Конкуренты и строки без email не идут в кампанию.
        import enrich_db as _EDBc
        import csv as _csvC
        import io as _ioC
        cx = _EDBc.EnrichDB().cx
        fit_map = args.get('fit_map') or {}          # inn -> division_proposed (вне базы)
        sig_inns = [str(r[0]) for r in cx.execute(
            "SELECT DISTINCT inn FROM signals WHERE inn!='' AND inn IS NOT NULL").fetchall()]
        idx = _base_index(set(sig_inns))              # какие сигнальные есть в базе + их данные
        camp_inns = set(fit_map) | set(idx)           # вне-базы-подходящие + в-базе
        rows = []
        for inn in camp_inns:
            comp = cx.execute('SELECT name,best_email,verified,phones,is_competitor,activity '
                              'FROM companies WHERE inn=?', (inn,)).fetchone()
            name = (comp[0] if comp else '') or ''
            best = (comp[1] if comp else '') or ''
            verified = (comp[2] if comp else '') or ''
            phones = (comp[3] if comp else '') or ''
            is_comp = (comp[4] if comp else 0)
            activity = (comp[5] if comp else '') or ''
            if is_comp:
                continue
            ems = cx.execute('SELECT email,role,person,source_url,mx_ok FROM emails WHERE inn=?',
                             (inn,)).fetchall()
            if not best and not ems:
                continue                              # нечем слать — не в кампанию
            # новостной повод: самый свежий сигнал
            sig = cx.execute('SELECT event_type,what,source_url,ts,hotness FROM signals '
                             'WHERE inn=? ORDER BY ts DESC LIMIT 1', (inn,)).fetchone()
            bi = idx.get(inn, {})
            in_base = inn in idx
            # направление: в базе → из базы (точное), иначе proposed из checko
            def _fm_div(x):   # fit_map[inn] может быть строкой-направлением или {division_proposed}
                v = fit_map.get(x)
                if isinstance(v, dict):
                    return v.get('division_proposed') or ''
                return v or ''
            if in_base:
                div, _ = _EDBc.division_for_okveds(bi.get('okved', ''))
                div = div or _fm_div(inn)
                div_src = 'база (точное)'
            else:
                div = _fm_div(inn)
                div_src = 'checko-ОКВЭД (подтвердить)'
            name = name or bi.get('name', '')
            city = bi.get('city', '')
            allc = ' | '.join(f"{e[0]}|{e[1] or 'общий'}|{e[3] or ''}" for e in ems[:6])
            rows.append({
                'inn': inn, 'name': name[:60], 'city': city, 'division': div or '?',
                'division_src': div_src, 'in_base': 'да' if in_base else 'нет',
                'best_email': best or (ems[0][0] if ems else ''),
                'verified': verified, 'phones': phones,
                'all_contacts': allc,
                'news_event': (sig[0] if sig else ''), 'news_what': (sig[1] if sig else ''),
                'news_url': (sig[2] if sig else ''), 'news_ts': (sig[3] if sig else ''),
                'hotness': (sig[4] if sig else ''), 'activity': activity[:100]})
        # приоритет: verified + в базе + hotness
        def _pr(r):
            return (1 if r['verified'] in ('inn', 'ogrn', 'phone', 'base+serp', 'provider') else 0,
                    1 if r['in_base'] == 'да' else 0, int(r.get('hotness') or 0))
        rows.sort(key=_pr, reverse=True)
        # ЕДИНАЯ БАЗА ПО ИНН (владелец 2026-07-24: «одна общая база включающая все базы
        # и всю информацию по 1 ИНН»): к каждой строке кампании приклеиваем ПОЛНУЮ строку
        # базы обзвона (все 36 колонок как есть: директор/учредители/выручка/баллы/
        # оборудование/категории) + checko-коды. Один проход CSV по нужным ИНН.
        base_hdr, base_rows = [], {}
        try:
            p2 = _get_base()
            with open(p2, encoding='utf-8-sig', newline='') as f2:
                rd2 = _csvC.reader(f2, delimiter=';')
                base_hdr = next(rd2, [])
                want2 = {r['inn'] for r in rows}
                for row2 in rd2:
                    if len(row2) > 1 and (row2[1] or '').strip() in want2:
                        base_rows[(row2[1] or '').strip()] = row2
                        if len(base_rows) >= len(want2):
                            break
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'base join skip: {str(e)[:80]}\n')
        checko_codes = args.get('checko_codes') or {}   # inn -> "25.62 28.14 ..." (полные ОКВЭД)
        # ДОЗАПОЛНЕНИЕ вне-базовых (владелец: «оборудование по ОКВЭД дополни сам по
        # примеру базы» + «вдруг есть емайлы»): fit_equipment {inn:{equip_main,categories,
        # links,score_total,score_max}} — из матрицы ОКВЭД→оборудование; dadata_fill —
        # реквизиты (директор/адрес/статус/ОГРН) и email из ЕГРЮЛ для пустых.
        fit_eq = args.get('fit_equipment') or {}
        _dd_on = bool(args.get('dadata_fill'))
        if _dd_on:
            import dadata_client as _DDc
            _DDc.TOKEN = _read_secret('DADATA_TOKEN')
        _hix = {h: i for i, h in enumerate(base_hdr)}
        def _bput(br, col, val):
            i = _hix.get(col)
            if i is not None and val:
                br[i] = val
        buf = _ioC.StringIO(); w = _csvC.writer(buf, delimiter=';')
        cols = ['inn', 'name', 'city', 'division', 'division_src', 'in_base', 'best_email',
                'verified', 'phones', 'all_contacts', 'news_event', 'news_what', 'news_url',
                'news_ts', 'hotness', 'activity', 'checko_okveds_all']
        w.writerow(cols + [f'база:{h}' for h in base_hdr])
        for r in rows:
            br = list(base_rows.get(r['inn'], [''] * len(base_hdr)))
            if r['in_base'] != 'да' and base_hdr:
                eq = fit_eq.get(r['inn']) or {}
                _bput(br, 'ИНН', r['inn'])
                _bput(br, 'Оборудование по основному ОКВЭД', eq.get('equip_main'))
                _bput(br, 'Все категории оборудования', eq.get('categories'))
                _bput(br, 'Найденные ОКВЭД', eq.get('links'))
                _bput(br, 'Итоговый балл приоритета', eq.get('score_total'))
                _bput(br, 'Макс. балл по связке', eq.get('score_max'))
                _bput(br, 'ВсеОКВЭД', checko_codes.get(r['inn'], ''))
                if _dd_on:
                    try:
                        dd = _DDc.lookup(r['inn'])
                        _bput(br, 'Полное', dd.get('full_name'))
                        _bput(br, 'Статус', dd.get('status'))
                        _bput(br, 'Адрес', dd.get('address'))
                        _bput(br, 'Директор', dd.get('mgmt_name'))
                        _bput(br, 'ОсновнойОКВЭД', dd.get('okved'))
                        if dd.get('emails'):
                            _bput(br, 'Emails', '|'.join(dd['emails'][:3]))
                            if not r.get('best_email'):
                                r['best_email'] = dd['emails'][0]
                                r['verified'] = r.get('verified') or 'ЕГРЮЛ-email'
                        if dd.get('phones'):
                            _bput(br, 'Телефоны', '|'.join(dd['phones'][:3]))
                        time.sleep(0.2)
                    except Exception:  # noqa: BLE001
                        pass
            w.writerow([r.get(c, '') if c != 'checko_okveds_all'
                        else checko_codes.get(r['inn'], '') for c in cols] + br)
        out_name = args.get('out', 'news-campaign.csv')
        up = False
        try:
            _D5 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            _D5.open(urllib.request.Request(
                os.environ.get('DROP_URL', '').rstrip('/') + '/' + out_name,
                data=buf.getvalue().encode('utf-8'), method='PUT',
                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}), timeout=120)
            up = True
        except Exception as e:  # noqa: BLE001
            up = f'upload-err:{str(e)[:60]}'
        from collections import Counter as _CtC
        json.dump({'op': 'news_campaign', 'rows': len(rows),
                   'in_base': sum(1 for r in rows if r['in_base'] == 'да'),
                   'out_base': sum(1 for r in rows if r['in_base'] == 'нет'),
                   'verified': sum(1 for r in rows if r['verified'] in ('inn', 'ogrn', 'phone', 'base+serp', 'provider')),
                   'by_division': dict(_CtC(r['division'] for r in rows)),
                   'file': out_name, 'uploaded': up}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'news_funnel':
        # ВОРОНКА новостного пайплайна В ОБРАТНОМ ПОРЯДКЕ (владелец: «где было
        # отсечение и почему всего 9 дошло»). Считает по news_stream.jsonl (события
        # и enrich-строки) + enrich.db (signals/companies/emails). args: lead_inns
        # (список ИНН из news-leads.json) — для них проверяем ТЕКУЩЕЕ наличие
        # контактов в enrich.db (лиды могли обогатиться ПОСЛЕ сборки снапшота).
        import glob as _gN
        import enrich_db as _EDBn
        from collections import Counter as _CtN
        _dirn = os.path.dirname(os.path.abspath(__file__))
        ev_total = 0; ev_capex = 0; ev_nocapex = 0; ev_with_inn = 0; ev_no_inn = 0
        enr_rows = 0; other = 0
        conf = _CtN()
        for fp in _gN.glob(os.path.join(_dirn, 'news_stream*.jsonl')):
            try:
                with open(fp, encoding='utf-8') as f:
                    for ln in f:
                        try:
                            j = json.loads(ln)
                        except Exception:  # noqa: BLE001
                            continue
                        if 'is_capex' in j or 'event_type' in j or 'company' in j:
                            ev_total += 1
                            if j.get('is_capex') is False:
                                ev_nocapex += 1
                            else:
                                ev_capex += 1
                                if j.get('inn'):
                                    ev_with_inn += 1
                                    conf[j.get('inn_confidence') or '?'] += 1
                                else:
                                    ev_no_inn += 1
                        elif 'best' in j or 'emails' in j or 'best_for_outreach' in j:
                            enr_rows += 1
                        else:
                            other += 1
            except Exception:  # noqa: BLE001
                pass
        out = {'op': 'news_funnel',
               'stream': {'events_total': ev_total, 'capex_true': ev_capex,
                          'capex_false_отсев': ev_nocapex,
                          'with_inn': ev_with_inn, 'no_inn_отсев': ev_no_inn,
                          'inn_confidence': dict(conf), 'enrich_rows': enr_rows, 'other': other}}
        try:
            cx = _EDBn.EnrichDB().cx
            out['db_signal_uniq_inn'] = cx.execute(
                "SELECT COUNT(DISTINCT inn) FROM signals WHERE inn!='' AND inn IS NOT NULL").fetchone()[0]
            lead_inns = [str(i) for i in (args.get('lead_inns') or [])]
            if lead_inns:
                q = ','.join('?' * len(lead_inns))
                out['leads_checked'] = len(lead_inns)
                out['leads_with_email_NOW'] = cx.execute(
                    f"SELECT COUNT(DISTINCT inn) FROM emails WHERE inn IN ({q})", lead_inns).fetchone()[0]
                out['leads_with_best_NOW'] = cx.execute(
                    f"SELECT COUNT(*) FROM companies WHERE inn IN ({q}) AND best_email!='' "
                    "AND best_email IS NOT NULL", lead_inns).fetchone()[0]
                out['leads_verified_NOW'] = cx.execute(
                    f"SELECT COUNT(*) FROM companies WHERE inn IN ({q}) AND verified IN "
                    "('inn','ogrn','phone','provider')", lead_inns).fetchone()[0]
                out['leads_competitor_NOW'] = cx.execute(
                    f"SELECT COUNT(*) FROM companies WHERE inn IN ({q}) AND is_competitor=1",
                    lead_inns).fetchone()[0]
                if args.get('want_missing'):
                    _has = {r[0] for r in cx.execute(
                        f"SELECT DISTINCT inn FROM emails WHERE inn IN ({q})", lead_inns).fetchall()}
                    out['missing_email_inns'] = [i for i in lead_inns if i not in _has]
                    # и есть ли эти ИНН в базе обзвона + что там в колонках Emails/Email с сайта
                    _bi = _base_index(set(out['missing_email_inns']))
                    out['missing_in_obzvon'] = len([i for i in out['missing_email_inns'] if i in _bi])
        except Exception as e:  # noqa: BLE001
            out['db_err'] = str(e)[:80]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'hidden_leads':
        # 649 «СКРЫТЫХ ЛИДОВ» (владелец: «тут подробнее»): компании базы, у которых
        # таргет-ОКВЭД есть ТОЛЬКО в доп-кодах, а основной — непрофильный. Если ядро/
        # сегменты отбирались по основному коду — эти компании никогда не попадали в
        # выборку. Полный проход: собираем всё (имя/оба ОКВЭД/сматченные таргет-коды/
        # направление/выручка/сайт/город), CSV на дроп + сводка в ответ.
        import csv as _csvH
        import io as _ioH
        import enrich_db as _EDBh
        from collections import Counter as _CtH
        p = _get_base()
        INN, KRAT, POLN, ADDR, REG, OKVED, OKVED_ALL, PHONES, SITE, REV = \
            1, 5, 6, 9, 10, 16, 17, 18, 20, 34
        try:
            _csvH.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        _codere = re.compile(r'\d{2}\.\d+(?:\.\d+)?')
        rows_out, div_ct, code_ct = [], _CtH(), _CtH()
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csvH.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                if len(row) <= REV:
                    continue
                prim = (row[OKVED] or '').strip()
                allo = prim + ' ' + (row[OKVED_ALL] or '')
                dp, _b1 = _EDBh.division_for_okveds(prim)
                da, budg = _EDBh.division_for_okveds(allo)
                if not da or dp:
                    continue   # интересуют только «таргет ТОЛЬКО в допах»
                # какие именно таргет-коды сматчились в допах
                tcodes = sorted({k for c in set(_codere.findall(allo))
                                 for k in _EDBh.OKVED_DIRECTIONS
                                 if c == k or c.startswith(k + '.')})
                div_ct[da] += 1
                for k in tcodes:
                    code_ct[k] += 1
                rows_out.append([
                    (row[INN] or '').strip(),
                    (row[POLN] or row[KRAT] or '').strip(),
                    da, budg, prim[:80], ' '.join(tcodes),
                    (row[REV] or '').strip(), (row[SITE] or '').strip(),
                    (row[REG] or '').strip()])
        rows_out.sort(key=lambda r: -(int(re.sub(r'\D', '', r[6]) or 0)))
        buf = _ioH.StringIO()
        w = _csvH.writer(buf, delimiter=';')
        w.writerow(['inn', 'name', 'division', 'budget', 'okved_main(непрофильный)',
                    'target_okveds_в_допах', 'revenue_rub', 'site', 'region'])
        w.writerows(rows_out)
        out_name = args.get('out', 'hidden-leads.csv')
        up = False
        try:
            _D4 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            _D4.open(urllib.request.Request(
                os.environ.get('DROP_URL', '').rstrip('/') + '/' + out_name,
                data=buf.getvalue().encode('utf-8'), method='PUT',
                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}), timeout=120)
            up = True
        except Exception as e:  # noqa: BLE001
            up = f'upload-err:{str(e)[:60]}'
        json.dump({'op': 'hidden_leads', 'total': len(rows_out),
                   'by_division': dict(div_ct),
                   'top_target_codes': dict(code_ct.most_common(15)),
                   'top10_by_revenue': [{'inn': r[0], 'name': r[1][:45], 'div': r[2],
                                         'okved_main': r[4][:40], 'target_dop': r[5],
                                         'rev': r[6]} for r in rows_out[:10]],
                   'file': out_name, 'uploaded': up}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'okved_recheck':
        # ПЕРЕСЧЁТ классификации news-пула БЕЗ повторного скрейпа checko (Cloudflare).
        # Чинит последствия бага парсера: основной ОКВЭД берём из dadata, из сохранённого
        # списка кодов выкидываем мусор шапки (коды, встречающиеся почти у ВСЕХ — они не
        # могут быть настоящими ОКВЭД пула). Пишет durable: companies + stage_log.
        import enrich_db as _EDBr
        import dadata_client as _DDr
        _DDr.TOKEN = _read_secret('DADATA_TOKEN')
        db = _EDBr.EnrichDB()
        rows = db.cx.execute("SELECT inn, detail FROM stage_log WHERE stage='checko'").fetchall()
        stored = {}
        for inn, detail in rows:
            p = dict(x.split('=', 1) for x in str(detail or '').split(';') if '=' in x)
            stored[str(inn)] = [c for c in (p.get('all') or '').split(',') if c]
        # мусор шапки: код есть у >=90% компаний пула (реальный ОКВЭД так не распределён)
        from collections import Counter as _Cr
        freq = _Cr()
        for cs in stored.values():
            freq.update(set(cs))
        n_all = max(1, len(stored))
        junk = sorted(c for c, n in freq.items() if n >= 0.9 * n_all)
        limit = int(args.get('limit') or 0)
        only = [str(i) for i in (args.get('inns') or [])]
        targets = only or sorted(stored)
        if limit:
            targets = targets[:limit]
        res = {'op': 'okved_recheck', 'мусорные_коды': junk, 'пул': len(stored),
               'обработано': 0, 'конкуренты': [], 'fit': 0, 'не_целевые': 0,
               'по_дивизиону': {}, 'dd_err': 0}
        for inn in targets:
            codes = [c for c in stored.get(inn, []) if c not in junk]
            main = ''
            try:
                dd = _DDr.lookup(inn)
                main = (dd.get('okved') or '').strip()
            except Exception:  # noqa: BLE001
                res['dd_err'] += 1
            is_comp, ccode = _EDBr.is_competitor_primary(main)
            # вторичный 28.13/28.12 — не блок по правилу владельца, но помечаем
            _s, sec = _EDBr.is_competitor_by_okved(' '.join(codes))
            all_txt = ' '.join(([main] if main else []) + codes)
            d_all, budg = _EDBr.division_for_okveds(all_txt)
            tgt = [c for c in (([main] if main else []) + codes)
                   if _EDBr.division_for_okveds(c)[0]]
            fit = bool(tgt) and not is_comp
            db.upsert_company(inn, okved=main, division=d_all, is_competitor=is_comp)
            db.mark_stage(inn, 'okved_v2',
                          f'main={main[:20]};comp={int(is_comp)};sec={",".join(sec)};'
                          f'div={d_all};tgt={len(tgt)};fit={int(fit)}')
            res['обработано'] += 1
            if is_comp:
                res['конкуренты'].append({'inn': inn, 'main': main[:40], 'code': ccode})
            elif fit:
                res['fit'] += 1
                res['по_дивизиону'][d_all] = res['по_дивизиону'].get(d_all, 0) + 1
            else:
                res['не_целевые'] += 1
        res['конкуренты_всего'] = len(res['конкуренты'])
        res['конкуренты'] = res['конкуренты'][:40]
        json.dump(res, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'checko_okveds':
        # Полный список ОКВЭД компаний через checko.ru (dadata на нашем тарифе доп-ОКВЭД
        # НЕ отдаёт). URL checko.ru/company/<ОГРН>/activity — таблица «Виды деятельности».
        # ОГРН берём из dadata (по ИНН) или из args. Каждый ОКВЭД проверяем: таргет? конкурент?
        import enrich_db as _EDBk
        import dadata_client as _DDk
        inns = [str(i).strip() for i in (args.get('inns') or []) if str(i).strip()]
        _DDk.TOKEN = _read_secret('DADATA_TOKEN')
        out = []
        for inn in inns:
            row = {'inn': inn}
            ogrn = ''
            dd_okved = ''          # основной ОКВЭД из dadata (источник истины, см. ниже)
            try:
                dd = _DDk.lookup(inn)
                row['name'] = dd.get('full_name')
                ogrn = dd.get('ogrn') or ''
                dd_okved = (dd.get('okved') or '').strip()
            except Exception as e:  # noqa: BLE001
                row['dd_err'] = str(e)[:50]
            # dadata_client.lookup не возвращал ogrn — берём из сырья повторным вызовом
            if not ogrn:
                try:
                    body = json.dumps({'query': inn}).encode()
                    req = urllib.request.Request(_DDk.API, data=body, method='POST', headers={
                        'Content-Type': 'application/json', 'Accept': 'application/json',
                        'Authorization': f'Token {_DDk.TOKEN}'})
                    dj = json.loads(urllib.request.urlopen(req, timeout=25).read())
                    sg = (dj.get('suggestions') or [])
                    ogrn = (sg[0].get('data', {}) if sg else {}).get('ogrn') or ''
                    if sg and not row.get('name'):
                        row['name'] = sg[0].get('value')
                except Exception:  # noqa: BLE001
                    pass
            row['ogrn'] = ogrn
            codes = []
            if ogrn:
                url = f'https://checko.ru/company/{ogrn}/activity'
                # ПРОВЕРЕНО НА ДАННЫХ 26.07 (12 ОГРН из базы, 12/12 успех, 0 капчи):
                # страница видов деятельности отдаётся ОБЫЧНЫМ HTTP за доли секунды.
                # Браузер (Дельфин) держали зря — он и был причиной часовых прогонов
                # и простоев «нет открытых профилей». Теперь браузер только как
                # фолбэк, если checko действительно закроется.
                html, _m, meta = _fetch_site(url)
                _blocked = (not html
                            or (isinstance(meta, dict) and meta.get('captcha_type'))
                            or 'just a moment' in (html or '').lower()[:4000])
                if _blocked and not globals().get('_NO_BROWSER'):
                    _t2, html = _org_page_probe(url, wait_ms=8000)   # фолбэк: браузер
                if html:
                    txt = re.sub(r'<[^>]+>', ' ', html)
                    # БАГ (найден 25.07): регексом по ВСЕЙ странице в коды попадал мусор
                    # шапки checko («12.5», «22.5» — они лезли первыми у всех 473), из-за
                    # чего okved_main = мусор и гейт конкурента (по основному) не срабатывал
                    # НИ РАЗУ. Режем текст по заголовку раздела видов деятельности.
                    mcut = re.search(r'(Виды\s+деятельности|Основной\s+вид\s+деятельности|ОКВЭД)',
                                     txt)
                    if mcut:
                        txt = txt[mcut.start():]
                    seen_c = []
                    for c in re.findall(r'\b\d{2}\.\d{1,2}(?:\.\d{1,2})?\b', txt):
                        if c not in seen_c:
                            seen_c.append(c)
                    codes = seen_c
                    row['checko_ok'] = True
                else:
                    row['checko_ok'] = False
            row['okveds_all'] = codes
            # основной ОКВЭД — из dadata (надёжно), страница checko только для ПОЛНОГО
            # списка; codes[0] как основной больше не доверяем (см. баг выше)
            row['okved_main'] = dd_okved or (codes[0] if codes else '')
            d_all, budg = _EDBk.division_for_okveds(' '.join(codes))
            # ПРАВИЛО ВЛАДЕЛЬЦА: конкурент = 28.13/28.12 в ОСНОВНОМ (первый код);
            # вторичные 28.1х — только информативная пометка (решает провайдер-судья)
            is_comp, ccode = _EDBk.is_competitor_primary(row['okved_main'])
            _sec, sec_codes = _EDBk.is_competitor_by_okved(' '.join(codes[1:]))
            tgt_codes = [c for c in codes if _EDBk.division_for_okveds(c)[0]]
            row.update({'division_by_full_okved': d_all or '', 'budget': budg,
                        'competitor': is_comp, 'competitor_codes': [ccode] if ccode else [],
                        'secondary_28x_info': sec_codes,
                        'target_codes_found': tgt_codes})
            # DURABLE (урок рестарта 2026-07-25): классификация checko — СРАЗУ в enrich.db,
            # не только в возвращаемый файл. stage_log('checko') = резюм переживает рестарт;
            # okved_all/division/конкурент — в companies + отдельный слот. Ставим стадию
            # ТОЛЬКО при успехе (codes есть) — dd_err/без-ОГРН переретраятся.
            if codes:
                try:
                    _dbc = _EDBk.EnrichDB()
                    _dbc.upsert_company(inn, name=row.get('name'),
                                        okved=row['okved_main'] or None,
                                        division=d_all or None, is_competitor=is_comp)
                    _dbc.mark_stage(inn, 'checko',
                                    f"div={d_all or '-'};comp={int(is_comp)};"
                                    f"tgt={len(tgt_codes)};all={','.join(codes[:20])}")
                except Exception:  # noqa: BLE001
                    pass
            out.append(row)
            time.sleep(0.3)
        json.dump({'op': 'checko_okveds', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'checko_targets':
        # Реконструкция целей out-of-base news-пула + фильтр уже-классифицированных
        # (stage_log 'checko'). Возврат: список ИНН на (пере)классификацию checko.
        # Базу обзвона читаем прямо на сервере (колонка 1 = ИНН).
        import csv as _csvt
        import enrich_db as _EDBt
        _db = _EDBt.EnrichDB()
        base = set()
        _bp = _get_base()
        if _bp:
            try:
                _csvt.field_size_limit(2 ** 22)
            except Exception:  # noqa: BLE001
                pass
            with open(_bp, encoding='utf-8-sig', errors='replace', newline='') as _bf:
                _rd = _csvt.reader(_bf, delimiter=';')
                next(_rd, None)
                for _r in _rd:
                    if len(_r) > 1 and _r[1].strip():
                        base.add(_r[1].strip())
        cur = _db.cx.execute("SELECT DISTINCT s.inn, co.name FROM signals s "
                             "JOIN companies co ON co.inn=s.inn WHERE s.inn!=''")
        done = set(r[0] for r in _db.cx.execute("SELECT inn FROM stage_log WHERE stage='checko'"))
        todo = []
        for inn, name in cur.fetchall():
            if inn in base or inn in done:
                continue
            todo.append({'inn': inn, 'name': name or ''})
        json.dump({'op': 'checko_targets', 'todo': todo, 'уже_классиф': len(done)},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'provider_probe':
        # СЕЛФТЕСТ провайдерского API С СЕРВЕРА: короткий вызов по каждой модели,
        # ошибка НАРУЖУ дословно (extract_roles их глотает — инцидент 2026-07-24:
        # regex-provider-fail на пробах, причина не видна). args: models, prompt_len.
        import verify_company as _VCp
        out = {'op': 'provider_probe', 'models': {}}
        _plen = int(args.get('prompt_len', 0))
        if args.get('pad_file'):
            # реалистичный паддинг (код этого файла): gzip-сжатие ~3.5-4× как у живых
            # промптов, а не в ноль как у повторов одного символа
            _srcp = open(os.path.abspath(__file__), encoding='utf-8', errors='replace').read()
            pad = (_srcp * (_plen // len(_srcp) + 1))[:_plen]
        else:
            pad = str(args.get('pad_char', 'х')) * _plen   # и длинный промпт
        # ОБХОД деградации маршрута (2026-07-24: тела >~2КБ до шлюза рвутся с сервера,
        # RemoteDisconnected): опционально гоним вызов через socks5 одного из прокси,
        # проставленных владельцем в профилях Дельфина. Монки-патч socket только на пробу.
        _sock_patch = None
        if args.get('via_dolphin_proxy'):
            try:
                import socks as _px
                import socket as _sk
                import browser_probe as _BPp
                _d = _BPp._dolphin_remote('GET', '/browser_profiles?limit=100',
                                          token=_read_secret('DOLPHIN_TOKEN'))
                _items = (_d.get('data') if isinstance(_d, dict) else None) or []
                if isinstance(_items, dict):
                    _items = _items.get('items') or []
                _want = str(args.get('proxy_profile') or '')
                _pxc = None
                for _p in _items:
                    if _want and str(_p.get('id')) != _want:
                        continue
                    _c = _p.get('proxy') or {}
                    if _c.get('host') and _c.get('port'):   # бывает host без порта — пропуск
                        _pxc = _c
                        break
                if not _pxc:
                    out['proxy'] = 'профиль с прокси не найден'
                else:
                    out['proxy'] = f"socks5://{_pxc.get('host')}:{_pxc.get('port')}"
                    _px.set_default_proxy(_px.SOCKS5, _pxc.get('host'), int(_pxc.get('port')),
                                          username=_pxc.get('login') or None,
                                          password=_pxc.get('password') or None)
                    _sock_patch = (_sk, _sk.socket)
                    _sk.socket = _px.socksocket
            except ImportError:
                out['proxy'] = 'PySocks не установлен (pip install pysocks)'
            except Exception as e:  # noqa: BLE001
                out['proxy'] = f'proxy-setup err: {str(e)[:120]}'
        def _call_trickle(prompt, mdl):
            # chunked-передача мелкими кусками с паузами: проверка «душат по burst-объёму
            # аплоада или по суммарному размеру». http.client, Transfer-Encoding: chunked.
            import http.client as _hc
            import gzip as _gz
            key = os.environ.get('PROVIDER_API_KEY', '')
            base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
            host = base.split('//', 1)[-1].split('/')[0]
            raw = json.dumps({'model': mdl, 'max_tokens': 1500, 'stream': True,
                              'messages': [{'role': 'user', 'content': prompt}]},
                             ensure_ascii=False).encode('utf-8')
            gz = _gz.compress(raw, 6)
            def _gen():
                step = int(args.get('trickle_chunk', 1200))
                slp = float(args.get('trickle_sleep', 0.15))
                for i in range(0, len(gz), step):
                    yield gz[i:i + step]
                    time.sleep(slp)
            cn = _hc.HTTPSConnection(host, timeout=240)
            try:
                cn.request('POST', '/v1/messages', body=_gen(), headers={
                    'x-api-key': key, 'anthropic-version': '2023-06-01',
                    'content-type': 'application/json', 'content-encoding': 'gzip',
                    'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
                rs = cn.getresponse()
                if rs.status != 200:
                    raise RuntimeError(f'HTTP {rs.status}: {rs.read(300).decode("utf-8","replace")}')
                parts = []
                for rawl in rs:
                    line = rawl.decode('utf-8', 'replace').strip()
                    if not line.startswith('data:'):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except Exception:  # noqa: BLE001
                        continue
                    if ev.get('type') == 'content_block_delta':
                        parts.append((ev.get('delta') or {}).get('text', ''))
                return ''.join(parts) or None
            finally:
                cn.close()
        def _call_gzip(prompt, mdl):
            # проба gzip-тела: русский 24К-промпт сжимается ~5×, ниже порога душения
            import gzip as _gz
            key = os.environ.get('PROVIDER_API_KEY', '')
            base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
            raw = json.dumps({'model': mdl, 'max_tokens': 1500, 'stream': True,
                              'messages': [{'role': 'user', 'content': prompt}]},
                             ensure_ascii=False).encode('utf-8')
            gz = _gz.compress(raw, 6)
            req = urllib.request.Request(
                base + '/v1/messages', data=gz, method='POST',
                headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                         'content-type': 'application/json', 'content-encoding': 'gzip',
                         'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
            parts = []
            with urllib.request.urlopen(req, timeout=240) as r:
                for rawl in r:
                    line = rawl.decode('utf-8', 'replace').strip()
                    if not line.startswith('data:'):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except Exception:  # noqa: BLE001
                        continue
                    if ev.get('type') == 'content_block_delta':
                        parts.append((ev.get('delta') or {}).get('text', ''))
                    elif ev.get('type') == 'error':
                        raise RuntimeError(f'stream error: {str(ev)[:150]}')
            return ''.join(parts) or None
        for mdl in (args.get('models') or ['claude-fable-5', 'claude-haiku-4-5']):
            t0 = time.time()
            row = {}
            try:
                if args.get('trickle'):
                    r = _call_trickle('Ответь строго: ok' + pad, mdl)
                elif args.get('gzip'):
                    r = _call_gzip('Ответь строго: ok' + pad, mdl)
                else:
                    r = _VCp._provider_call_stdlib('Ответь строго: ok' + pad, model=mdl)
                row['ok'] = bool(r)
                row['resp'] = (r or '')[:80]
            except Exception as e:  # noqa: BLE001
                b = ''
                try:
                    b = e.read().decode('utf-8', 'replace')[:200]
                except Exception:  # noqa: BLE001
                    pass
                row['ok'] = False
                row['error'] = f'{type(e).__name__}: {str(e)[:150]}' + (f' | {b}' if b else '')
            row['took_sec'] = round(time.time() - t0, 1)
            out['models'][mdl] = row
        if _sock_patch:
            _sock_patch[0].socket = _sock_patch[1]
        out['key_set'] = bool(os.environ.get('PROVIDER_API_KEY'))
        out['base'] = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap')
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_cleanup':
        # Закрыть ЗАВИСШИЕ профили (владелец #7: «4 висят открытыми, не забудь закрыть»).
        # Проходит по настроенным профилям; у запущенных — stop (окно Dolphin закрывается).
        # Безопасно вызывать МЕЖДУ батчами (когда обогащение не держит браузер).
        import browser_probe as BP
        tokd = args.get('dolphin_token') or _read_secret('DOLPHIN_TOKEN')
        profs = [str(x) for x in (args.get('dolphin_profiles') or _resolve_dolphin_profiles(None, tokd))]
        closed, running_before, errors = [], [], []
        for pid in profs:
            run = None
            try:
                run = BP.dolphin_is_running(pid, token=tokd)
            except Exception as e:  # noqa: BLE001
                errors.append(f'{pid}:isrun:{str(e)[:40]}')
            if run:
                running_before.append(pid)
                try:
                    BP.dolphin_stop(pid, token=tokd)
                    closed.append(pid)
                except Exception as e:  # noqa: BLE001
                    errors.append(f'{pid}:stop:{str(e)[:40]}')
        json.dump({'op': 'dolphin_cleanup', 'profiles': len(profs),
                   'running_before': running_before, 'closed': closed, 'errors': errors},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_conn1':
        # ЧИСТЫЙ тест: РОВНО один старт профиля + connect + открыть страницу (без повторных стартов).
        import browser_probe as BP
        import json as _j
        from playwright.sync_api import sync_playwright
        tokd = _read_secret('DOLPHIN_TOKEN')
        pid = str((args.get('dolphin_profiles') or ['?'])[0])
        _opd = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        r = {'op': 'dolphin_conn1', 'profile': pid}
        try:
            rq = urllib.request.Request(f'{BP.DOLPHIN_BASE}/browser_profiles/{pid}/start?automation=1',
                                        headers={'Authorization': 'Bearer ' + tokd} if tokd else {})
            sd = _j.loads(_opd.open(rq, timeout=30).read())
            au = sd.get('automation') or {}
            r['start'] = sd.get('success'); port = au.get('port'); ws = au.get('wsEndpoint') or ''
            cdp = f'ws://127.0.0.1:{port}{ws}' if ws else f'http://127.0.0.1:{port}'
            r['port'] = port
            with sync_playwright() as pw:
                br = pw.chromium.connect_over_cdp(cdp, timeout=35000)
                ctx = br.contexts[0] if br.contexts else br.new_context()
                # сколько вкладок профиль ПРИТАЩИЛ из прошлой сессии (доказательство фикса
                # dolphin_close_tabs: после чистого стопа тут должно быть 0-1 about:blank)
                r['tabs_at_connect'] = sum(len(c.pages) for c in br.contexts)
                pg = ctx.new_page()
                pg.goto('https://example.com', timeout=30000, wait_until='domcontentloaded')
                r['connect'] = 'OK'; r['title'] = (pg.title() or '')[:50]
                BP.dolphin_close_tabs(br)
                try:
                    br.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            b = ''
            try:
                b = e.read().decode('utf-8', 'replace')[:150]
            except Exception:  # noqa: BLE001
                pass
            r['error'] = str(e).splitlines()[0][:100] + (f' | {b}' if b else '')
        finally:
            try:
                BP.dolphin_stop(pid, token=tokd)
            except Exception:  # noqa: BLE001
                pass
        json.dump(r, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_diag':
        # ДИАГНОСТИКА дельфина: list -> start (headless И обычный) -> connect_over_cdp (30с).
        # Пинпоинтит, где рвётся: API / старт профиля / рендер браузера (headless на серверах без GUI).
        import browser_probe as BP
        from playwright.sync_api import sync_playwright
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = [str(x) for x in (args.get('dolphin_profiles') or [])]
        listed = []
        try:
            listed = BP.dolphin_list(tokd)
        except Exception as e:  # noqa: BLE001
            listed = [{'err': str(e)[:80]}]
        if not profs:
            profs = [p['id'] for p in listed if p.get('id')]
        if not profs:  # токен протух (401) -> кэш dolphin-profiles.txt
            profs = _cached_dolphin_profiles()
        pid = profs[0] if profs else None
        res = {'op': 'dolphin_diag', 'token_present': bool(tokd),
               'list_count': len([x for x in listed if x.get('id')]),
               'list_raw': str(listed)[:200], 'profile_tested': pid, 'modes': {}}
        # сырое тело 500 со старта + сырой ответ list (точная причина от Dolphin)
        _opd = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for label, path in (('start', f'browser_profiles/{pid}/start?automation=1'),
                            ('list', 'browser_profiles?limit=100')):
            try:
                rq = urllib.request.Request(f'{BP.DOLPHIN_BASE}/{path}',
                                            headers={'Authorization': 'Bearer ' + tokd} if tokd else {})
                body = _opd.open(rq, timeout=30).read().decode('utf-8', 'replace')
                res[f'raw_{label}'] = body[:280]
            except Exception as e:  # noqa: BLE001
                b = ''
                try:
                    b = e.read().decode('utf-8', 'replace')[:280]
                except Exception:  # noqa: BLE001
                    pass
                res[f'raw_{label}'] = f'{str(e)[:60]} | body: {b}'
        # РЕШАЮЩИЙ ТЕСТ: сырой старт (БЕЗ stop-first) -> connect_over_cdp -> открыть страницу
        try:
            import json as _j
            rq = urllib.request.Request(f'{BP.DOLPHIN_BASE}/browser_profiles/{pid}/start?automation=1',
                                        headers={'Authorization': 'Bearer ' + tokd} if tokd else {})
            sd = _j.loads(_opd.open(rq, timeout=30).read())
            au = sd.get('automation') or {}
            port = au.get('port'); ws = au.get('wsEndpoint') or ''
            cdp = f'ws://127.0.0.1:{port}{ws}' if ws else f'http://127.0.0.1:{port}'
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                br = pw.chromium.connect_over_cdp(cdp, timeout=35000)
                ctx = br.contexts[0] if br.contexts else br.new_context()
                pg = ctx.new_page()
                pg.goto('https://example.com', timeout=30000, wait_until='domcontentloaded')
                res['e2e'] = {'connect': 'OK', 'title': (pg.title() or '')[:50], 'port': port}
                BP.dolphin_close_tabs(br)
                try:
                    br.close()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            res['e2e'] = {'connect': 'FAIL', 'err': str(e).splitlines()[0][:120]}
        finally:
            try:
                BP.dolphin_stop(pid, token=tokd)
            except Exception:  # noqa: BLE001
                pass
        for hl in (True, False):
            r = {}
            try:
                cdp, port = BP.dolphin_start(pid, headless=hl, token=tokd)
                r['start_ok'] = True; r['port'] = port; r['cdp'] = str(cdp)[:70]
                with sync_playwright() as p:
                    try:
                        b = p.chromium.connect_over_cdp(cdp, timeout=30000)
                        r['cdp_connect'] = 'OK'; r['contexts'] = len(b.contexts)
                        BP.dolphin_close_tabs(b)
                        try:
                            b.close()
                        except Exception:  # noqa: BLE001
                            pass
                    except Exception as e:  # noqa: BLE001
                        r['cdp_connect'] = 'FAIL: ' + str(e).splitlines()[0][:90]
            except Exception as e:  # noqa: BLE001
                r['start_ok'] = False; r['err'] = str(e)[:140]
            finally:
                try:
                    BP.dolphin_stop(pid, token=tokd)
                except Exception:  # noqa: BLE001
                    pass
            res['modes']['headless' if hl else 'gui'] = r
        json.dump(res, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_batch':
        # БОЕВОЙ ОПО-прогон: N профилей ПАРАЛЛЕЛЬНО, каждый в ОДНОЙ сессии гонит свою пачку
        # компаний (goto по каждой, капча решается по ходу через handle_captcha), в конце stop.
        # Вход: companies [{ogrn,inn,name,sector,...}], dolphin_profiles [id...]. Выход -> csv на дроп.
        import multiprocessing as _mp
        tokd = _read_secret('DOLPHIN_TOKEN')
        profiles = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        comps = args.get('companies') or []
        if not profiles or not comps:
            json.dump({'op': 'opo_batch', 'error': 'нужны dolphin_profiles и companies'}, sys.stdout, ensure_ascii=False)
            return
        nprof = min(len(profiles), int(args.get('max_profiles', 20)))
        profiles = profiles[:nprof]
        # разложить компании по профилям (round-robin)
        buckets = [[] for _ in range(nprof)]
        for i, c in enumerate(comps):
            buckets[i % nprof].append(c)
        # каждый профиль — ОТДЕЛЬНЫЙ ПРОЦЕСС (Playwright sync не потокобезопасен, паттерн dolphin_pool)
        _d = os.path.dirname(os.path.abspath(__file__))
        # разнос по времени (наводка владельца: 20 разом = профили не успевают прогрузиться
        # + rate-limit чеко): старт профилей каскадом раз в stagger_sec, пауза между
        # компаниями внутри сессии sleep_ms (+джиттер).
        stag = float(args.get('stagger_sec', 5))
        slp = int(args.get('sleep_ms', 2000))
        procs, outs = [], []
        for i in range(nprof):
            outp = os.path.join(_d, f'.opo_out_{i}.json')
            outs.append(outp)
            pr = _mp.Process(target=_opo_worker,
                             args=(profiles[i], tokd, buckets[i], outp, slp, i * stag))
            pr.start(); procs.append(pr)
        for pr in procs:
            pr.join(timeout=int(args.get('total_timeout', 1500)))
        results = {}
        for outp in outs:
            try:
                results.update(json.load(open(outp, encoding='utf-8')))
                os.remove(outp)
            except Exception:  # noqa: BLE001
                pass
        # выгрузка csv на дроп
        import io as _io2
        import csv as _csvb
        buf = _io2.StringIO(); w = _csvb.writer(buf, delimiter=';')
        w.writerow(['ogrn', 'inn', 'name', 'sector', 'rtn_opo', 'pressure_equip', 'lic_nums',
                    'captcha', 'blocked', 'error'])
        n_opo = 0; n_press = 0
        for ogrn, r in results.items():
            if r.get('rtn_opo'):
                n_opo += 1
            if r.get('pressure_equip'):
                n_press += 1
            w.writerow([ogrn, r.get('inn', ''), r.get('name', ''), r.get('sector', ''),
                        r.get('rtn_opo', ''), r.get('pressure_equip', ''),
                        '|'.join(r.get('lic_nums', []) or []),
                        r.get('captcha', '') or '', r.get('blocked', ''), r.get('error', '')])
        try:
            _D3 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tk = os.environ.get('DROP_TOKEN', '')
            fn = args.get('out_file', 'checko-opo.csv')
            _D3.open(urllib.request.Request(drop + '/' + fn, data=buf.getvalue().encode('utf-8'),
                     method='PUT', headers={'X-Drop-Token': tk}), timeout=90)
            uploaded = fn
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:70]}'
        errs = sum(1 for r in results.values() if r.get('error'))
        blk = sum(1 for r in results.values() if r.get('blocked'))
        json.dump({'op': 'opo_batch', 'profiles_used': nprof, 'companies': len(comps),
                   'processed': len(results), 'with_rtn_opo': n_opo,
                   'with_pressure_equip': n_press, 'errors': errs, 'blocked': blk,
                   'uploaded': uploaded,
                   'sample_pressure': [{'name': r.get('name'), 'lic': r.get('lic_nums')}
                                       for r in results.values() if r.get('pressure_equip')][:5],
                   'sample_opo': [{'name': r.get('name'), 'lic': r.get('lic_nums')}
                                  for r in results.values() if r.get('rtn_opo')][:5]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_licenses':
        # ОПО через ЛИЦЕНЗИИ Ростехнадзора на checko: /company/{OGRN}/licenses/data?source=07
        # (наводка владельца). Дельфин-профили автоподтяжкой по токену. Возвращает per-OGRN
        # маркеры + сырой сниппет первой для верификации парсера.
        import browser_probe as BP
        _dtoken = _read_secret('DOLPHIN_TOKEN')
        _dprofiles = _resolve_dolphin_profiles(args.get('dolphin_profiles'), _dtoken)
        # маркеры лицензии Ростехнадзора на эксплуатацию ОПО
        RTN = re.compile(r'взрывопожароопасн|химически\s+опасн|эксплуатац\w+\s+\w*\s*опасн|'
                         r'Ростехнадзор|горн\w+\s+работ|I,?\s*II\b.*класс\w*\s+опасн', re.I)
        PRESSURE = re.compile(r'давлени\w*\s+более\s+0[.,]07|нагрева\s+воды\s+более\s+115|'
                              r'оборудован\w*,?\s*работающ\w*\s+под\s+давлением|'
                              r'сосуд\w*,?\s*работающ\w*\s+под\s+давлением|под\s+давлением\s+более', re.I)
        LIC_NUM = re.compile(r'№?\s*[А-Я]{1,3}-?\d{2}-\d{5,6}|ВХ-\d{2}-\d{5,6}', re.I)
        out = {}; first_snip = None
        for i, c in enumerate(args.get('companies') or []):
            ogrn = str(c.get('ogrn') or '').strip()
            if not ogrn:
                out[c.get('inn', '?')] = {'error': 'нет OGRN'}; continue
            url = f'https://checko.ru/company/{ogrn}/licenses/data?source=07'
            try:
                pargs = {'url': url, 'solve': True, 'return_html': True,
                         'html_cap': 200000, 'wait_ms': 9000, 'screenshot': False}
                if _dprofiles and _dtoken:
                    pargs.update(dolphin_profile=str(_dprofiles[i % len(_dprofiles)]), dolphin_token=_dtoken)
                pr = BP.probe(pargs)
                html = pr.get('html', '') or ''
                txt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I))
                txt = re.sub(r'\s+', ' ', txt)
                has = bool(RTN.search(txt))
                out[ogrn] = {'inn': c.get('inn'), 'name': (c.get('name') or '')[:40],
                             'rtn_license': has, 'pressure_equip': bool(PRESSURE.search(txt)),
                             'lic_nums': list(set(LIC_NUM.findall(txt)))[:4],
                             'blocked': _looks_blocked(html), 'captcha': pr.get('captcha_type'),
                             'html_len': len(html)}
                if first_snip is None and html:
                    first_snip = txt[:600]
            except Exception as e:  # noqa: BLE001
                out[ogrn] = {'error': str(e)[:100]}
        json.dump({'op': 'opo_licenses', 'dolphin_profiles': len(_dprofiles),
                   'results': out, 'first_snippet': first_snip}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'base_header':
        import csv as _csv
        p = _get_base()
        if not p:
            json.dump({'error': 'база не найдена'}, sys.stdout, ensure_ascii=False); return
        try:
            _csv.field_size_limit(2 ** 18)
        except Exception:  # noqa: BLE001
            pass
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csv.reader(f, delimiter=';')
            hdr = next(rd, [])
            sample = next(rd, [])
        cols = [{'i': i, 'name': (h or '')[:40], 'sample': (sample[i] if i < len(sample) else '')[:50]}
                for i, h in enumerate(hdr)]
        json.dump({'op': 'base_header', 'path': p, 'ncols': len(hdr), 'columns': cols},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') in ('centrifugal_inns', 'centrifugal_export'):
        # ОКВЭД-воронка центробежных компрессоров из обзвон-базы (уже checko+) -> ГОТОВАЯ
        # выгрузка с контактами и выручкой на дроп. Матч по основному [16] И доп. [17] ОКВЭД.
        import csv as _csv
        import io as _io
        # ПОРОГ ВЫРУЧКИ СВОЙ ПО ОТРАСЛЯМ (изучено по исследованию центробежников):
        # ядро=машины гарантированно; чем крупнее типовой парк, тем выше порог (режем шум).
        # Спец-исключения: промгазы (спецы мельче, но ЦБК точно есть) — низкий порог;
        # водоканалы/очистные — порог 0 (решает инвестпрограмма/концессия, не выручка).
        # code -> (floor_₽, sector, tier). Матч по префиксу кода в основном+доп ОКВЭД.
        SECTOR = {
            # --- ЯДРО ---
            '06.10': (3e9, 'добыча нефти', 'core'),
            '06.20': (3e9, 'добыча газа', 'core'),
            '49.50.21': (2e9, 'транспорт газа', 'core'),
            '49.50.11': (2e9, 'транспорт нефти', 'core'),
            '52.10.22': (1e9, 'хранение газа (ПХГ)', 'core'),
            '19.20': (3e9, 'НПЗ/нефтепродукты', 'core'),
            '19.10': (2e9, 'кокс', 'core'),
            '20.14': (1.5e9, 'орг.химия/нефтехимия', 'core'),
            '20.16': (1.5e9, 'пластмассы', 'core'),
            '20.17': (1.5e9, 'синт.каучук', 'core'),
            '20.15': (1.5e9, 'удобрения/аммиак', 'core'),
            '20.11': (0.4e9, 'промышленные газы', 'core'),   # спецы мельче, машины точно есть
            '24.10': (2e9, 'чёрная металлургия', 'core'),
            # --- ВТОРОЙ КОНТУР ---
            '20.13': (1.5e9, 'неорг.химия', 'second'),
            '24.42': (2e9, 'алюминий', 'second'),
            '24.43': (2e9, 'свинец-цинк-олово', 'second'),
            '24.44': (2e9, 'медь', 'second'),
            '24.45': (2e9, 'цветмет проч.', 'second'),
            '05.10': (2e9, 'уголь', 'second'),
            '07.10': (2e9, 'ГОК железорудный', 'second'),
            '07.29': (2e9, 'ГОК цветной', 'second'),
            '35.11': (1.5e9, 'энергетика (генерация)', 'second'),
            '35.30': (1e9, 'пар/горячая вода', 'second'),
            '37.00': (0.1e9, 'очистные/сточные', 'water'),   # владелец: водоканалы от 100 млн
            '36.00': (0.1e9, 'водоканал', 'water'),          # владелец: водоканалы от 100 млн
            '17.11': (2e9, 'ЦБК (целлюлоза)', 'second'),
            '23.51': (1.5e9, 'цемент', 'second'),
            '10.81': (1e9, 'сахар', 'second'),
            '09.10': (1e9, 'нефтесервис', 'second'),
        }
        include_second = args.get('include_second', True)
        codes = tuple(c for c, (_f, _s, t) in SECTOR.items() if include_second or t != 'second')
        floor_mult = float(args.get('floor_mult', 1.0) or 1.0)   # множитель порогов (ужесточить/смягчить)
        p = _get_base()
        if not p:
            json.dump({'op': 'centrifugal_export', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        (INN, OGRN, KRAT, POLN, ADDR, REG, OKVED, OKVED_ALL, PHONES, EMAILS, SITES,
         PHONES_S, EMAIL_S, PRIORITY, EQUIP, REV_NUM) = (1, 2, 5, 6, 9, 10, 16, 17, 18, 19, 20, 21, 22, 28, 30, 34)
        try:
            _csv.field_size_limit(2 ** 18)
        except Exception:  # noqa: BLE001
            pass
        seen = set(); picked = []
        by_tier = {'core': 0, 'second': 0, 'water': 0}
        by_sector = {}
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = _csv.reader(f, delimiter=';')
            next(rd, None)
            while True:
                try:
                    row = next(rd)
                except StopIteration:
                    break
                except Exception:  # noqa: BLE001
                    continue
                if len(row) <= REV_NUM:
                    continue
                inn = (row[INN] or '').strip()
                if not inn or inn in seen:
                    continue
                hay = (row[OKVED] or '') + ' ' + (row[OKVED_ALL] or '')
                matched = [c for c in codes if c in hay]
                if not matched:
                    continue
                try:
                    rev = float(re.sub(r'[^\d.]', '', (row[REV_NUM] or '0')) or 0)
                except Exception:  # noqa: BLE001
                    rev = 0.0
                if rev <= 0:
                    continue   # владелец: компании без выручки пока не интересны
                # проходит, если по ЛЮБОЙ из отраслей-матчей выручка >= её порога (× floor_mult).
                # Отрасль лида = та, по которой прошёл с наименьшим порогом (самая релевантная/мягкая).
                ok = None
                for c in matched:
                    fl, sec, tr = SECTOR[c]
                    if rev >= fl * floor_mult:
                        if ok is None or (fl * floor_mult) < ok[0]:
                            ok = (fl * floor_mult, sec, tr, c)
                if ok is None:
                    continue
                _fl, sector, tier, _code = ok
                seen.add(inn)
                emails = ((row[EMAILS] or '') + ' | ' + (row[EMAIL_S] or '')).strip(' |')
                phones = ((row[PHONES] or '') + ' | ' + (row[PHONES_S] or '')).strip(' |')
                picked.append({
                    'inn': inn, 'ogrn': (row[OGRN] or '').strip(),
                    'name': (row[POLN] or row[KRAT] or '').strip(),
                    'region': (row[REG] or '').strip(), 'okved_main': (row[OKVED] or '').strip(),
                    'revenue_rub': rev, 'tier': tier, 'sector': sector,
                    'phones': phones, 'emails': emails, 'site': (row[SITES] or '').strip(),
                    'priority': (row[PRIORITY] or '').strip(), 'equipment': (row[EQUIP] or '').strip()[:120],
                })
                by_tier[tier] = by_tier.get(tier, 0) + 1
                by_sector[sector] = by_sector.get(sector, 0) + 1
        # сортировка: сначала ядро/вода, потом по выручке (вода без выручки — вверх по инвест-приоритету)
        picked.sort(key=lambda x: (0 if x['tier'] in ('core', 'water') else 1, -x['revenue_rub']))
        # CSV на дроп. Колонки людей здесь НЕ добавляем: формат
        # centrifugal-base.csv — контракт соседней сессии, люди живут в export_core.
        buf = _io.StringIO()
        w = _csv.writer(buf, delimiter=';')
        w.writerow(['inn', 'ogrn', 'name', 'region', 'okved_main', 'revenue_rub', 'tier', 'sector',
                    'phones', 'emails', 'site', 'priority_score', 'equipment'])
        for r0 in picked:
            w.writerow([r0['inn'], r0['ogrn'], r0['name'], r0['region'], r0['okved_main'],
                        int(r0['revenue_rub']), r0['tier'], r0['sector'], r0['phones'], r0['emails'],
                        r0['site'], r0['priority'], r0['equipment']])
        blob = buf.getvalue().encode('utf-8')
        with_email = sum(1 for r0 in picked if '@' in (r0['emails'] or ''))
        try:
            _D2 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
            _D2.open(urllib.request.Request(drop + '/centrifugal-base.csv', data=blob,
                     method='PUT', headers={'X-Drop-Token': tok}), timeout=120)
            uploaded = True
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:80]}'
        json.dump({'op': 'centrifugal_export', 'total': len(picked), 'with_email': with_email,
                   'by_tier': by_tier, 'by_sector': dict(sorted(by_sector.items(), key=lambda x: -x[1])),
                   'floor_mult': floor_mult, 'uploaded': uploaded, 'file': 'centrifugal-base.csv',
                   'top5': [{'inn': r0['inn'], 'name': r0['name'][:40],
                             'rev_млрд': round(r0['revenue_rub'] / 1e9, 1),
                             'email': (r0['emails'][:40] if r0['emails'] else '')} for r0 in picked[:5]]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_serp':
        # ТЕСТ: достаточно ли СНИППЕТОВ xmlriver для ОПО-данных (без браузера/дельфина)?
        u2, k2 = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
        out = {}
        for c in (args.get('companies') or []):
            inn = str(c.get('inn') or ''); name = c.get('name', '')
            q = f'{name} ИНН {inn} опасный производственный объект компрессорная станция реестр ОПО checko nadzor-info'
            su = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(u2)
                  + '&key=' + urllib.parse.quote(k2) + '&domain=ru&query=' + urllib.parse.quote(q))
            try:
                xml = _DIRECT.open(su, timeout=35).read().decode('utf-8', 'replace')
            except Exception as e:  # noqa: BLE001
                out[name] = {'error': str(e)[:80]}; continue
            snips = ' '.join(re.findall(r'<(?:passages|title|text|content)>(.*?)</(?:passages|title|text|content)>', xml, re.S))
            snips = re.sub(r'<[^>]+>', ' ', snips)
            obj = _OPO_OBJ.findall(snips)
            reg = re.findall(r'А\d{2}[-\s]?\d{4,6}(?:[-\s]?\d{2,4})?', snips)
            ctx = bool(re.search(r'опасн\w+\s+производствен|ОПО|Ростехнадзор|промышленн\w+\s+безопасн', snips, re.I))
            out[name] = {'inn_in_snips': inn in snips.replace(' ', ''),
                         'opo_ctx': ctx, 'opo_objects': list(set(obj))[:5],
                         'opo_regs': list(set(reg))[:5], 'snip_sample': snips[:400]}
        json.dump({'op': 'opo_serp', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'opo_probe':
        # РАЗВЕДКА авторитетного источника ОПО по ИНН: checko/list-org (раздел ОПО из
        # Ростехнадзора) + офиц. реестр через SERP. Браузер+CapMonster, дельфин если есть профиль.
        # Самодостаточно (локальные переменные) — не трогаем модульные глобали.
        import browser_probe as BP
        _dtoken = _read_secret('DOLPHIN_TOKEN')
        # порядок: args -> live-список по токену -> кэш dolphin-profiles.txt (устойчиво к 401)
        _dprofiles = _resolve_dolphin_profiles(args.get('dolphin_profiles'), _dtoken)
        inn = str(args.get('inn') or '')
        name = args.get('name', '')
        # eo.nadzor-info.ru — профильный портал по ОПО/промбезопасности (владелец 2026-07-23)
        cands = [f'https://eo.nadzor-info.ru/search?q={inn}',
                 f'https://checko.ru/company/{inn}',
                 f'https://www.rusprofile.ru/search?query={inn}',
                 f'https://www.list-org.com/search?type=inn&val={inn}']
        # найдём офиц.-реестр/агрегатор через SERP
        try:
            u2, k2 = os.environ.get('XMLRIVER_USER', ''), os.environ.get('XMLRIVER_KEY', '')
            if u2 and k2:
                q = f'{name} ИНН {inn} опасный производственный объект реестр ОПО'
                su = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(u2)
                      + '&key=' + urllib.parse.quote(k2) + '&domain=ru&query=' + urllib.parse.quote(q))
                xml = _DIRECT.open(su, timeout=35).read().decode('utf-8', 'replace')
                for uu in re.findall(r'<url>(.*?)</url>', xml, re.S)[:5]:
                    uu = uu.strip().replace('&amp;', '&')
                    if uu not in cands:
                        cands.append(uu)
        except Exception:  # noqa: BLE001
            pass
        results = {}
        for _i, url in enumerate(cands[:6]):
            try:
                pargs = {'url': url, 'solve': True, 'return_html': True,
                         'html_cap': 220000, 'wait_ms': 9000, 'screenshot': False}
                if _dprofiles and _dtoken:
                    pargs.update(dolphin_profile=str(_dprofiles[_i % len(_dprofiles)]),
                                 dolphin_token=_dtoken)
                out = BP.probe(pargs)
                html = out.get('html', '') or ''
                txt = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ',
                                                     html, flags=re.S | re.I))
                low = txt.lower()
                results[url] = {
                    'html_len': len(html), 'blocked': _looks_blocked(html),
                    'captcha': out.get('captcha_type'),
                    'has_opo_word': ('опасн' in low and 'производствен' in low),
                    'opo_regs': list(set(re.findall(r'А\d{2}[-\s]?\d{4,6}(?:[-\s]?\d{2,4})?', txt)))[:6],
                    'opo_objects': list(set(_OPO_OBJ.findall(txt)))[:5],
                    'inn_present': inn in txt.replace(' ', ''),
                }
            except Exception as e:  # noqa: BLE001
                results[url] = {'error': str(e)[:120]}
        json.dump({'op': 'opo_probe', 'inn': inn, 'dolphin_profiles_found': len(_dprofiles),
                   'results': results}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dnscheck':
        # проверка DNS доменов с РФ-IP сервера: A + HTTP-редирект + почтовые записи
        # (MX/SPF/DKIM/DMARC через nslookup — питон-сокет TXT/MX не умеет).
        import socket as _sock
        import subprocess as _sp
        import urllib.request as _u
        RESOLVER = args.get('resolver', '8.8.8.8')
        # DKIM-селекторы под провайдеров: Я360=mail, Mail.ru=mailru, VK=dkim/selector
        DKIM_SEL = args.get('dkim_selectors') or ['mail', 'mailru', 'dkim', 'default', 'selector1']

        def _nslookup(qtype, name):
            try:
                r = _sp.run(['nslookup', '-type=' + qtype, name, RESOLVER],
                            capture_output=True, text=True, timeout=20,
                            encoding='utf-8', errors='replace')
                return (r.stdout or '') + (r.stderr or '')
            except Exception as e:  # noqa: BLE001
                return f'__err__ {e}'

        out = {}
        for dom in (args.get('domains') or []):
            rec = {'a': None, 'http_code': None, 'http_redirect': None,
                   'mx': None, 'spf': None, 'dmarc': None, 'dkim_selector': None}
            try:
                rec['a'] = _sock.gethostbyname(dom)
            except Exception:  # noqa: BLE001
                rec['a'] = None
            for scheme in ('https', 'http'):
                try:
                    req = _u.Request(f'{scheme}://{dom}/', method='GET',
                                     headers={'User-Agent': 'Mozilla/5.0'})
                    class _NoRedir(_u.HTTPRedirectHandler):
                        def redirect_request(self, *a, **k):
                            return None
                    r = _u.build_opener(_NoRedir).open(req, timeout=15)
                    rec['http_code'] = r.getcode()
                    break
                except _u.HTTPError as e:
                    rec['http_code'] = e.code
                    rec['http_redirect'] = e.headers.get('Location')
                    break
                except Exception:  # noqa: BLE001
                    continue
            # MX
            mxo = _nslookup('MX', dom)
            mxs = re.findall(r'mail exchanger\s*=\s*(\S+)', mxo)
            rec['mx'] = mxs[0].rstrip('.') if mxs else None
            # SPF (TXT на корне)
            txto = _nslookup('TXT', dom)
            spf = re.search(r'"(v=spf1[^"]*)"', txto)
            rec['spf'] = spf.group(1) if spf else None
            # DMARC
            dmo = _nslookup('TXT', '_dmarc.' + dom)
            dm = re.search(r'"(v=DMARC1[^"]*)"', dmo)
            rec['dmarc'] = dm.group(1) if dm else None
            # DKIM: пробуем селекторы, фиксируем первый найденный
            for sel in DKIM_SEL:
                dko = _nslookup('TXT', f'{sel}._domainkey.{dom}')
                if re.search(r'v=DKIM1|k=rsa|p=[A-Za-z0-9+/]{20,}', dko):
                    rec['dkim_selector'] = sel
                    break
            out[dom] = rec
        json.dump({'op': 'dnscheck', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'hh_signals':
        # HH БЕЗ API (владелец 26.07: «оператора в компрессорную ищут 300 компаний,
        # этот источник нам нужен»). api.hh.ru отдаёт 403 без токена приложения,
        # заявка на модерации до 15 рабочих дней — а публичная выдача hh.ru
        # открыта обычным HTTP (проверено: 200, без капчи). Появится токен —
        # переключим на API, парсер останется фолбэком.
        # Вакансия в компрессорную = ПРЯМОЕ доказательство, что у предприятия
        # есть компрессорное хозяйство. Матчим работодателя с базой обзвона по
        # названию и пишем сигнал в enrich.db. Durable: stage_log('hh').
        import enrich_db as _EDBh
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import hh_scan as _HH
        db = _EDBh.EnrichDB()
        pages = int(args.get('pages') or 3)
        rows = _HH.scan(queries=args.get('queries'), pages=pages,
                        archived=bool(args.get('archived')))
        # индекс базы обзвона: нормализованное имя -> (инн, полное имя)
        import sqlite3 as _sq
        ix = _sq.connect(r'C:\sender\obzvon-index.db')

        def _norm(x):
            x = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ГК|НПО|НПП|ТОО)\s+', '', str(x or ''),
                       flags=re.I)
            x = re.sub(r'[«»"\'`]', '', x)
            return re.sub(r'\s+', ' ', x).strip().lower()

        base = {}
        for _inn, _ns, _nf in ix.execute(
                "SELECT inn, name_short, name_full FROM obzvon"):
            for _n in (_ns, _nf):
                k = _norm(_n)
                if len(k) >= 4:
                    base.setdefault(k, _inn)
        out = {'op': 'hh_signals', 'вакансий': len(rows), 'работодателей': 0,
               'сматчено_с_базой': 0, 'сматчено_dadata': 0, 'не_опознано': 0,
               'сигналов_записано': 0, 'примеры': [], 'без_ИНН': []}
        by_emp = {}
        for r in rows:
            by_emp.setdefault(r['employer'], []).append(r)
        out['работодателей'] = len(by_emp)

        # ДОБОР ЧЕРЕЗ DADATA. Матч по имени брал только 52 из 371: на hh компании
        # пишутся брендами («Газпром нефть», «ЭФКО»), а в базе обзвона — полные
        # юрлица. Работодатель, которого нет в нашей базе, — всё равно лид: он
        # прямо сейчас нанимает в компрессорную. Поэтому неопознанных прогоняем
        # через dadata (тот же путь, что новостные лиды) и заводим карточку.
        import news_scan as _NSh
        _dtok = _read_secret('DADATA_TOKEN')
        _resolve = bool(args.get('dadata', True)) and bool(_dtok)

        def _inn_of(emp_name):
            """Сначала наша база (бесплатно), затем dadata. (инн, способ, карточка)."""
            hit = base.get(_norm(emp_name))
            if hit:
                return hit, 'base', None
            if not _resolve:
                return None, '', None
            try:
                s = _NSh.dadata_suggest(emp_name, _dtok)
            except Exception:  # noqa: BLE001
                return None, '', None
            # score=0 внутри dadata_suggest уже отсеян: лучше лид без ИНН, чем ИНН тёзки
            _i = ((s or {}).get('inn') or '').strip()
            return (_i, 'dadata', s) if _i else (None, '', None)

        for emp, vac in by_emp.items():
            inn, how, card = _inn_of(emp)
            if not inn:
                out['не_опознано'] += 1
                if len(out['без_ИНН']) < 40:
                    out['без_ИНН'].append(emp[:60])
                continue
            if how == 'base':
                out['сматчено_с_базой'] += 1
            else:
                out['сматчено_dadata'] += 1
                # карточки у такого лида ещё нет — заводим с ОКВЭД и направлением,
                # иначе он не попадёт ни в пул, ни в разбивку kc/meyer
                try:
                    _ok = (card or {}).get('okved') or ''
                    db.upsert_company(
                        inn, name=(card or {}).get('name') or emp[:200],
                        okved=_ok or None,
                        region=(card or {}).get('region') or None,
                        division=(_NSh.division_of(_ok) if _ok else None))
                except Exception:  # noqa: BLE001
                    pass
            _по_имени = sorted({v['vacancy'] for v in vac if v['vacancy']})
            titles = '; '.join(_по_имени[:3])
            # Ссылка-первоисточник: конкретная вакансия -> страница работодателя
            # -> поисковая выдача (последний фолбэк). Раньше всегда писалась
            # выдача, и «читать источник» в панели вёл на поиск, а не на
            # вакансию (владелец 28.07). Ссылку берём у вакансии, которая стоит
            # ПЕРВОЙ в what, — чтобы текст и ссылка говорили об одном и том же.
            _срт = sorted((v for v in vac if v.get('vacancy')),
                          key=lambda v: v['vacancy'])
            _src = next((v.get('url') for v in _срт if v.get('url')), '') \
                or next((v.get('url') for v in vac if v.get('url')), '')
            if not _src:
                _eid = next((str(v.get('employer_id') or '') for v in vac
                             if v.get('employer_id')), '')
                _src = (f'https://hh.ru/employer/{_eid}' if _eid.isdigit() else '')
            if not _src:
                _src = ('https://hh.ru/search/vacancy?text=' +
                        urllib.parse.quote(vac[0].get('query') or ''))
            db.add_signal(inn, source='hh',
                          event_type='наём в компрессорную',
                          what=f'{emp}: {titles}'[:400],
                          source_url=_src,
                          hotness=3)
            # РЕТРО-ФИКС ссылок (владелец 28.07): у СТАРОЙ строки с тем же what
            # ссылка осталась на поисковую выдачу - INSERT OR IGNORE её не
            # обновляет. Если сейчас есть ссылка на КОНКРЕТНУЮ вакансию этого
            # работодателя - подменяем у его строк без /vacancy/.
            if '/vacancy/' in (_src or ''):
                try:
                    db.cx.execute(
                        "UPDATE signals SET source_url=? WHERE inn=? AND "
                        "source='hh' AND source_url NOT LIKE '%/vacancy/%' "
                        "AND what LIKE ?", (_src, str(inn), emp[:80] + ':%'))
                    db.cx.commit()
                except Exception:  # noqa: BLE001
                    pass
            # способ и уверенность матча пишем в стадию: если ИНН приклеен по dadata
            # с низким скором, продажник должен видеть это до звонка
            db.mark_stage(inn, 'hh', f'вакансий={len(vac)} матч={how}'
                          + (f"/{(card or {}).get('confidence')}" if how == 'dadata' else ''))
            out['сигналов_записано'] += 1
            if len(out['примеры']) < 15:
                out['примеры'].append({'инн': inn, 'работодатель': emp[:50],
                                       'вакансий': len(vac), 'пример': titles[:70],
                                       'матч': how})
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'hh_vacancy_scan':
        # ВАКАНСИЯ->КОМПАНИЯ (инверсия владельца): API hh закрыт целиком (forbidden), но
        # ЧЕЛОВЕЧЕСКИЙ сайт hh.ru/search/vacancy открыт -> парсим ЕГО через дельфин.
        # Ищем компрессорные вакансии по РФ -> работодатели -> кандидаты в горячие лиды.
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        pid = profs[0] if profs else None
        queries = args.get('queries') or ['машинист компрессорных установок',
                                          'оператор компрессорной станции',
                                          'машинист воздуходувных установок']
        pages = int(args.get('pages', 1))
        found = {}   # employer -> {vacancies:[...], area}
        raw_diag = {}
        for q in queries[:6]:
            for pg in range(pages):
                url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q)
                       + '&items_on_page=50&page=' + str(pg))
                try:
                    r = BP.probe({'url': url, 'return_html': True, 'html_cap': 400000,
                                  'wait_ms': 4000, 'screenshot': False, 'solve': True,
                                  'dolphin_profile': pid, 'dolphin_token': tokd})
                    html = r.get('html') or ''
                    if q not in raw_diag:
                        raw_diag[q] = {'html_len': len(html), 'captcha': r.get('captcha_type'),
                                       'has_serp': 'vacancy-serp' in html or 'vacancy-card' in html,
                                       'forbidden': 'forbidden' in html[:2000].lower()}
                    # карточки: работодатель (data-qa vacancy-serp__vacancy-employer /
                    # vacancy-card__company-name) + заголовок вакансии
                    emps = re.findall(r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>([^<]{2,80})<', html)
                    titles = re.findall(r'data-qa="[^"]*vacancy[^"]*title[^"]*"[^>]*>([^<]{3,120})<', html)
                    for i, emp in enumerate(emps):
                        emp = re.sub(r'\s+', ' ', emp).strip()
                        if not emp:
                            continue
                        rec = found.setdefault(emp, {'query': q, 'titles': []})
                        if i < len(titles):
                            rec['titles'].append(re.sub(r'\s+', ' ', titles[i]).strip()[:80])
                except Exception as e:  # noqa: BLE001
                    raw_diag[q] = {'error': f'{type(e).__name__}: {str(e)[:70]}'}
        try:
            BP.dolphin_stop(pid, token=tokd)
        except Exception:  # noqa: BLE001
            pass
        out = {'op': 'hh_vacancy_scan', 'profile': pid, 'employers_found': len(found),
               'diag': raw_diag,
               'sample': [{'employer': e, 'query': v['query'], 'titles': v['titles'][:2]}
                          for e, v in list(found.items())[:15]]}
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'vk_oauth_dolphin':
        # Добить VK через дельфин (владелец): открыть OAuth-URL ВНУТРИ дельфин-профиля ->
        # токен привяжется к IP профиля (socks5). Затем ТЕМ ЖЕ профилем дёрнуть groups.search,
        # чтобы IP совпал. Шаг 1 (probe_ip): сравнить исходящий IP профиля и сервера.
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        pid = profs[0] if profs else None
        out = {'op': 'vk_oauth_dolphin', 'profile': pid}
        if not pid:
            out['error'] = 'нет профиля'; json.dump(out, sys.stdout, ensure_ascii=False); return
        # IP сервера (прямой) и IP через дельфин-профиль
        try:
            out['server_ip'] = _DIRECT.open('https://api.ipify.org', timeout=15).read().decode()
        except Exception as e:  # noqa: BLE001
            out['server_ip'] = f'err:{str(e)[:40]}'
        try:
            r = BP.probe({'url': 'https://api.ipify.org', 'return_html': True, 'wait_ms': 2500,
                          'screenshot': False, 'dolphin_profile': pid, 'dolphin_token': tokd})
            body = re.sub(r'<[^>]+>', ' ', r.get('html') or '') + ' ' + (r.get('text') or '')
            m = re.search(r'\d+\.\d+\.\d+\.\d+', body)
            out['dolphin_ip'] = m.group(0) if m else ('пусто:' + body[:80])
        except Exception as e:  # noqa: BLE001
            out['dolphin_ip'] = f'err:{str(e)[:60]}'
        out['ip_match'] = (out.get('server_ip') == out.get('dolphin_ip'))
        # если IP разные - groups.search с сервера всё равно упрётся; если совпали ИЛИ
        # если дёргать API тем же профилем - сработает. Даём URL для ручного OAuth в профиле:
        _cid = args.get('client_id', '54687645')
        out['oauth_url'] = (f'https://oauth.vk.com/authorize?client_id={_cid}&scope=groups'
                            '&redirect_uri=https://oauth.vk.com/blank.html&response_type=token&v=5.199')
        # проба: если передан vk_token - дёрнуть groups.search ЧЕРЕЗ дельфин-профиль
        vt = args.get('vk_token') or _read_secret('VK_TOKEN_USER')
        if vt and args.get('try_search'):
            # через новую retry-функцию (перебор профилей, общий IP) + СЫРОЙ дамп
            raw = _vk_api_via_dolphin('groups.search', {'q': 'Северсталь', 'count': 3}, vt)
            out['vk_raw'] = json.dumps(raw, ensure_ascii=False)[:400]
            if 'response' in raw:
                out['search_via_dolphin'] = 'OK: ' + str(len((raw.get('response') or {}).get('items') or [])) + ' групп'
            elif raw.get('error'):
                out['search_via_dolphin'] = 'VK-ошибка: ' + str(raw['error'].get('error_msg', ''))[:80]
            else:
                out['search_via_dolphin'] = 'пусто (дельфин не отдал JSON - профили 500?)'
        try:
            BP.dolphin_stop(pid, token=tokd)
        except Exception:  # noqa: BLE001
            pass
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'coverage_probe':
        # ЧИСТЫЙ замер на выборке: обогащаем companies со ВСЕМИ источниками, считаем разбивку
        # ИЗ РЕЗУЛЬТАТА (не из БД - без легаси-мусора). write_db=false по умолчанию.
        import collections as _coll
        globals()['_ZAKUPKI_CHECK'] = bool(args.get('zakupki_check', True))
        globals()['_SMTP_CHECK'] = bool(args.get('smtp_check', True))
        globals()['_NO_VK_LOOKUP'] = bool(args.get('no_vk_lookup', True))  # VK токен без прав
        pace = (float(args.get('pace_min', 1.5)), float(args.get('pace_max', 3.5)))
        comps = args.get('companies') or []
        # ПАРАЛЛЕЛЬНО (последовательно 20 не влезали в таймаут 1800с). Инициализируем семафоры
        # (op-путь минует main-настройку). browser/xmlriver ограничены семафорами внутри.
        bw = max(1, min(int(args.get('browser_workers', 4)), 12))
        globals()['_SEM_BROWSER'] = threading.Semaphore(bw)
        _cw = max(1, min(int(args.get('workers', 8)), 16))
        def _one(c):
            try:
                return enrich_one(c, pace)
            except Exception as e:  # noqa: BLE001
                return {'inn': c.get('inn'), 'error': f'exc:{str(e)[:60]}'}
        with ThreadPoolExecutor(max_workers=_cw) as _ex:
            res = list(_ex.map(_one, comps))
        n = len(res)
        with_site = sum(1 for r in res if r.get('site'))
        with_email = sum(1 for r in res if r.get('emails'))
        with_best = sum(1 for r in res if r.get('best_for_outreach'))
        with_phone = sum(1 for r in res if r.get('phones'))
        verified = sum(1 for r in res if r.get('verified') in ('inn', 'ogrn', 'phone', 'base+serp', 'provider'))
        src = _coll.Counter(); smtp = _coll.Counter(); roles = _coll.Counter()
        for r in res:
            seen = set()
            for e in (r.get('emails') or []):
                b = (e.get('source') or 'unknown').split(':')[0]
                if b not in seen:
                    src[b] += 1; seen.add(b)
                if e.get('smtp'):
                    smtp[e['smtp']] += 1
                rl = (e.get('role') or '').split('(')[0].strip()[:20]
                if rl:
                    roles[rl] += 1
        # примеры лучших контактов
        sample = [{'name': (r.get('name') or '')[:30], 'best': r.get('best_for_outreach'),
                   'site': r.get('site'), 'n_emails': len(r.get('emails') or [])}
                  for r in res if r.get('best_for_outreach')][:8]
        json.dump({'op': 'coverage_probe', 'total': n, 'with_site': with_site,
                   'with_any_email': with_email, 'with_best_email': with_best,
                   'with_phone': with_phone, 'verified': verified,
                   'email_sources': dict(src), 'smtp_status': dict(smtp),
                   'top_roles': dict(roles.most_common(8)), 'sample': sample},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'tail_stream':
        # Хвост любого jsonl на сервере (мониторинг реальных данных прогона). args: file, n.
        _dirt = os.path.dirname(os.path.abspath(__file__))
        fn = args.get('file', 'enrich_core.jsonl')
        fp = fn if os.path.isabs(fn) else os.path.join(_dirt, fn)
        n = int(args.get('n', 10))
        rows = []; total = 0
        try:
            with open(fp, encoding='utf-8') as f:
                lines = f.readlines()
            total = len(lines)
            for ln in lines[-n:]:
                try:
                    j = json.loads(ln)
                    # компактный вид: главное для проверки «реально ли собирается»
                    rows.append({'inn': j.get('inn'), 'name': (j.get('name') or '')[:34],
                                 'site': j.get('site'), 'site_source': j.get('site_source'),
                                 'best': j.get('best_for_outreach'),
                                 'n_emails': len(j.get('emails') or []),
                                 'email_sample': [(e.get('email'), e.get('source'), e.get('smtp'))
                                                  for e in (j.get('emails') or [])[:3]],
                                 'phones': (j.get('phones') or [])[:2],
                                 'verified': j.get('verified'), 'method': j.get('method'),
                                 'opo': j.get('opo'), 'zakupki': bool(j.get('zakupki')),
                                 'error': j.get('error')})
                except Exception:  # noqa: BLE001
                    rows.append({'raw_broken': ln[:80]})
        except FileNotFoundError:
            json.dump({'op': 'tail_stream', 'error': f'нет файла {fp}'}, sys.stdout, ensure_ascii=False)
            return
        # агрегат по всему файлу
        agg = {'total': total, 'with_site': 0, 'with_email': 0, 'with_best': 0, 'src': {}}
        try:
            with open(fp, encoding='utf-8') as f:
                for ln in f:
                    try:
                        j = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if j.get('site'): agg['with_site'] += 1
                    if j.get('emails'): agg['with_email'] += 1
                    if j.get('best_for_outreach'): agg['with_best'] += 1
                    # extract-разбивка: масштаб деградации провайдера (regex-provider-fail =
                    # контакты без ролей, шли до фикса транспорта 2026-07-24). Считаем
                    # ПОСЛЕДНИЙ исход по ИНН (стрим append-only, переобработки дописываются).
                    _ex = j.get('extract')
                    if _ex:
                        _ii = str(j.get('inn'))
                        agg.setdefault('_ext_by_inn', {})[_ii] = _ex
                        if args.get('fail_inns') and j.get('site'):
                            # последняя запись с сайтом — для перепрогонки без нового xmlriver
                            agg.setdefault('_row_by_inn', {})[_ii] = {
                                'inn': _ii, 'name': j.get('name') or '',
                                'site': j.get('site') or '', 'city': j.get('city') or ''}
                    # ГРОМКИЙ VK (владелец): ok / причины отказов — видно в каждом чеке
                    vg = j.get('vk_group')
                    if isinstance(vg, dict):
                        if vg.get('error'):
                            agg['vk_err'] = agg.get('vk_err', 0) + 1
                            k = vg['error'][:40]
                            agg.setdefault('vk_err_top', {})
                            agg['vk_err_top'][k] = agg['vk_err_top'].get(k, 0) + 1
                        else:
                            agg['vk_ok'] = agg.get('vk_ok', 0) + 1
                    for e in (j.get('emails') or []):
                        b = (e.get('source') or '?').split(':')[0]
                        agg['src'][b] = agg['src'].get(b, 0) + 1
        except Exception:  # noqa: BLE001
            pass
        _ebi = agg.pop('_ext_by_inn', {})
        _rbi = agg.pop('_row_by_inn', {})
        _extra = {}
        if _ebi:
            from collections import Counter as _Cx
            agg['extract'] = dict(_Cx(_ebi.values()))
            agg['uniq_inn'] = len(_ebi)
            if args.get('fail_inns'):   # компании для перепрогонки: последний исход = provider-fail
                _fi = [i for i, e in _ebi.items() if e == 'regex-provider-fail']
                _extra['fail_inns'] = _fi
                _extra['fail_companies'] = [_rbi[i] for i in _fi if i in _rbi]
        json.dump({'op': 'tail_stream', 'file': fn, 'aggregate': agg, 'tail': rows, **_extra},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'export_core':
        # ФИНАЛЬНАЯ ВЫГРУЗКА ядра с провенансом (для продажников). Источник — jsonl-поток
        # прогона (там smtp/source/opo/zakupki, чего нет в компактной БД). Лучшая запись на ИНН,
        # мердж отрасли/выручки из core-info, ПОСТ-ФИЛЬТР ОПО (юр-справки → не сигнал), скоринг.
        import csv as _csv
        import io as _io
        import glob as _g
        _dirx = os.path.dirname(os.path.abspath(__file__))
        stream = args.get('stream_file', 'enrich_core2.jsonl')
        # инфо по ядру (sector/revenue) — из core396.json локально ИЛИ inline-args ИЛИ
        # centrifugal-core-info.csv с дропа (сервер не держит core396.json — .py-only pull).
        info = {}
        try:
            for c in json.load(open(os.path.join(_dirx, args.get('info_file', 'core396.json')), encoding='utf-8')):
                info[str(c.get('inn'))] = c
        except Exception:  # noqa: BLE001
            pass
        if args.get('info'):   # inline: {inn: {sector, revenue_rub, name}}
            for k, v in args['info'].items():
                info[str(k)] = v
        if not info:           # фолбэк: тянем core-info с дропа
            try:
                _Di = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
                raw = _Di.open(urllib.request.Request(drop + '/centrifugal-core-info.csv',
                               headers={'X-Drop-Token': tok}), timeout=60).read().decode('utf-8-sig', 'replace')
                rdr = _csv.reader(raw.splitlines(), delimiter=';')
                next(rdr, None)
                for row in rdr:
                    if len(row) >= 5:
                        info[row[0].strip()] = {'inn': row[0].strip(), 'name': row[2],
                                                'sector': row[3], 'revenue_rub': row[4]}
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f'export_core info-from-drop skip: {str(e)[:80]}\n')
        # ОПО ТОЛЬКО ИЗ ЧЕКО (владелец: «опо только из чеко пока верифицировано используем»):
        # реальные лицензии Ростехнадзора с карточек checko (rtn_opo) + флаг pressure_equip
        # («оборудование под давлением >0,07 МПа» = компрессоры). SERP-сниппеты НЕ считаем.
        checko_opo = {}
        # ФИНАЛЬНЫЙ мердж чеко-скана — centrifugal-core-opo.csv (41 rtn_opo / 24 pressure);
        # r1/r2-файлы — сырые раунды с блокировками (нули), их не используем.
        for _cf in ('centrifugal-core-opo.csv',):
            try:
                _Dc = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
                raw = _Dc.open(urllib.request.Request(drop + '/' + _cf,
                               headers={'X-Drop-Token': tok}), timeout=60).read().decode('utf-8-sig', 'replace')
                rdr = _csv.reader(raw.splitlines(), delimiter=';')
                hdr = next(rdr, None) or []
                hix = {h: i for i, h in enumerate(hdr)}
                for row in rdr:
                    try:
                        _ci = row[hix.get('inn', 1)].strip()
                        _ro = row[hix.get('rtn_opo', 4)].strip().lower() == 'true'
                        _pe = row[hix.get('pressure_equip', 5)].strip().lower() == 'true'
                        _ln = row[hix.get('lic_nums', 6)].strip() if hix.get('lic_nums', 6) < len(row) else ''
                        if _ci and (_ro or _ci not in checko_opo):   # r2 уточняет, True не затираем False-ом
                            if _ro or checko_opo.get(_ci, {}).get('rtn_opo') is not True:
                                checko_opo[_ci] = {'rtn_opo': _ro, 'pressure_equip': _pe, 'lic_nums': _ln}
                    except Exception:  # noqa: BLE001
                        continue
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f'export_core checko-opo skip {_cf}: {str(e)[:60]}\n')
        # НОВОСТНЫЕ СИГНАЛЫ (владелец: «где ссылка на саму новость?»): событие+ссылка из
        # enrich.db signals — для продажника это «зачем звонить». До 2 свежих на ИНН.
        # Заодно имена из БД (владелец: «пустые ИНН в таблице» = имя не подтянулось из потока).
        signals_by_inn = {}
        db_names = {}
        try:
            import enrich_db as _EDBs
            _cxs = _EDBs.EnrichDB().cx
            for _ni, _nn in _cxs.execute("SELECT inn, name FROM companies WHERE name!=''").fetchall():
                db_names[str(_ni)] = _nn
            try:
                _gdec = __import__('news_scan')._gnews_decode   # редирект gnews → URL издателя
            except Exception:  # noqa: BLE001
                _gdec = lambda u: u  # noqa: E731
            for _sinn, _sev, _swh, _surl, _sts, _shot in _cxs.execute(
                    'SELECT inn, event_type, what, source_url, ts, hotness FROM signals '
                    'ORDER BY hotness DESC, ts DESC').fetchall():
                _l = signals_by_inn.setdefault(str(_sinn), [])
                if len(_l) < 2:
                    _l.append({'event': _sev or '', 'what': (_swh or '')[:160],
                               'url': _gdec(_surl or ''), 'ts': _sts or ''})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'export_core signals skip: {str(e)[:80]}\n')
        # ОКВЭД-профиль (владелец: «сфера — по окведу или сайту?» → показываем ОБА):
        # okved_main из centrifugal-base.csv на дропе; activity (с сайта) — из самой записи.
        try:
            _Db = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
            raw = _Db.open(urllib.request.Request(drop + '/centrifugal-base.csv',
                           headers={'X-Drop-Token': tok}), timeout=60).read().decode('utf-8-sig', 'replace')
            rdr = _csv.reader(raw.splitlines(), delimiter=';')
            next(rdr, None)
            for row in rdr:
                if len(row) >= 5 and row[0].strip():
                    info.setdefault(row[0].strip(), {})['okved_main'] = row[4]
        except Exception:  # noqa: BLE001
            pass
        LAW_REF = ('sudact.ru/law', 'consultant.ru', 'garant.ru', 'cntd.ru', 'kodeks',
                   'pravo.gov', 'normativ', 'zakonbase', 'legalacts', '/law/', 'zakonrf')
        def _score(rec):
            s = 0
            if rec.get('best_for_outreach'): s += 3
            if rec.get('verified') in ('inn', 'ogrn', 'phone'): s += 2
            if any((e.get('person') or '').strip() for e in (rec.get('emails') or [])): s += 2
            if checko_opo.get(str(rec.get('inn')), {}).get('rtn_opo'): s += 2   # ОПО чеко-верифицирован
            if rec.get('zakupki'): s += 1
            if rec.get('phones'): s += 1
            try:
                s += min(3, int(float(info.get(str(rec.get('inn')), {}).get('revenue_rub') or 0) / 5e9))
            except Exception:  # noqa: BLE001
                pass
            return s
        best = {}
        _stream_files = _g.glob(os.path.join(_dirx, stream.rsplit('.', 1)[0] + '*.jsonl'))
        for _es in (args.get('extra_streams') or []):   # мердж доп-стримов (recheck-волны)
            _stream_files += _g.glob(os.path.join(_dirx, str(_es).rsplit('.', 1)[0] + '*.jsonl'))
        for fp in _stream_files:
            try:
                for ln in open(fp, encoding='utf-8'):
                    try:
                        j = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    inn = str(j.get('inn') or '')
                    if not inn:
                        continue
                    # ОПО пост-фильтр: юр-справка в source_url → не считаем сигналом
                    op = j.get('opo')
                    j['_opo_ok'] = bool(op and isinstance(op, dict) and op.get('opo')
                                        and not any(l in (op.get('source_url') or '').lower() for l in LAW_REF))
                    prev = best.get(inn)
                    # лучшая запись: с best_for_outreach > больше email > есть сайт
                    key = (bool(j.get('best_for_outreach')), len(j.get('emails') or []), bool(j.get('site')))
                    if prev is None or key > prev['_k']:
                        j['_k'] = key
                        best[inn] = j
            except Exception:  # noqa: BLE001
                pass
        # опционально ограничить списком ИНН (ядро)
        want = set(str(i) for i in (args.get('inns') or []))
        rows = [best[i] for i in best if not want or i in want]
        # ДОБОР из enrich.db (дедуп-истина по всем прогонам): компании ядра, которых нет в
        # jsonl этого прогона (петля не дошла / данные из прошлых стримов), берём из БД —
        # чтобы выгрузка покрывала ВСЕ 396, а не только процессенные в этом прогоне.
        if want:
            have = set(str(r.get('inn')) for r in rows)
            missing = [i for i in want if i not in have]
            if missing:
                try:
                    import enrich_db as EDB
                    _cxx = EDB.EnrichDB().cx
                    for inn in missing:
                        cr = _cxx.execute('SELECT site,verified,phones,best_email FROM companies WHERE inn=?',
                                          (inn,)).fetchone()
                        ems = _cxx.execute('SELECT email,role,person,mx_ok,source,source_url '
                                           'FROM emails WHERE inn=?', (inn,)).fetchall()
                        if not cr and not ems:
                            continue   # вообще нет данных — пропускаем (в итог попадёт как пусто)
                        site = (cr[0] if cr else '') or ''
                        ver = (cr[1] if cr else '') or ''
                        best_db = (cr[3] if cr and len(cr) > 3 else '') or ''
                        try:
                            phones = json.loads(cr[2]) if cr and cr[2] else []
                        except Exception:  # noqa: BLE001
                            phones = []
                        emails = [{'email': e[0], 'role': e[1] or '', 'person': e[2] or '',
                                   'mx_ok': e[3], 'source': e[4] or 'db', 'source_url': e[5] or ''}
                                  for e in ems]
                        rows.append({'inn': inn, 'site': site, 'site_source': 'db' if site else '',
                                     'verified': ver, 'phones': phones if isinstance(phones, list) else [],
                                     'emails': emails,
                                     'best_for_outreach': best_db or (emails[0]['email'] if emails else ''),
                                     'method': 'db-merge', '_opo_ok': False})
                except Exception as e:  # noqa: BLE001
                    sys.stderr.write(f'export_core db-merge skip: {str(e)[:80]}\n')
        # ЗАЩИТА ОТ ЛОЖНЫХ ПРИВЯЗОК (аудит: sky.pro на 195 ИНН, optimalgroup на 125 — реклама/
        # словари/агрегаторы, ошибочно опознанные как сайт разных компаний). Обобщённо: домен
        # сайта ИЛИ домен email, привязанный к >= порогу РАЗНЫХ ИНН, — заведомо не контакт
        # конкретной компании. Обнуляем сайт/email у таких, помечаем в error.
        _shthr = int(args.get('shared_threshold', 2))   # владелец: >=2 разных ИНН на домен = ложняк (verified щадим)
        import collections as _colx
        _site_inns = _colx.defaultdict(set); _dom_inns = _colx.defaultdict(set)
        _addr_inns = _colx.defaultdict(set)   # ПОЛНЫЙ адрес на >=2 ИНН = мусор ДАЖЕ на фримейле
                                              # (владелец поймал zakup_respect@mail.ru на 8 ИНН)
        for r in rows:
            inn = str(r.get('inn') or '')
            sd = _domain((r.get('site') or '') if str(r.get('site') or '').startswith('http')
                         else 'http://' + str(r.get('site') or '')) if r.get('site') else ''
            if sd:
                _site_inns[sd].add(inn)
            for e in (r.get('emails') or []):
                em = (e.get('email') or '').lower()
                # ИНН-верифицированные источники (ЕИС по ИНН, ЕГРЮЛ, справочник-по-ИНН) могут
                # ЛЕГИТИМНО повторяться между компаниями (общий уполномоченный орган закупок) —
                # в подсчёт «общих доменов» не включаем, иначе порог 2 их убьёт.
                _esrc = (e.get('source') or '').split(':')[0]
                if _esrc in ('zakupki', 'egrul', 'directory', 'vk-group'):
                    continue
                if '@' in em:
                    _dom_inns[em.split('@')[1]].add(inn)
                    _addr_inns[em].add(inn)
        bad_sites = {d for d, s in _site_inns.items() if len(s) >= _shthr}
        bad_doms = {d for d, s in _dom_inns.items() if len(s) >= _shthr
                    and d not in ('mail.ru', 'yandex.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
                                  'list.ru', 'rambler.ru', 'mail.com', 'internet.ru')}  # фримейл — ок
        bad_addrs = {a for a, s in _addr_inns.items() if len(s) >= _shthr}  # адрес (и фримейл!)
        FREEMAIL = ('mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
                    'list.ru', 'rambler.ru', 'mail.com', 'internet.ru', 'outlook.com',
                    'icloud.com', 'vk.com')
        n_scrubbed = 0
        for r in rows:
            # ПОДТВЕРЖДЁННЫЕ (ИНН/ОГРН/тел на сайте) НЕ трогаем: настоящий владелец домена
            # (напр. реальный «Автобан») верифицирован, а 8 мис-резолвов на тот же домен — нет.
            if r.get('verified') in ('inn', 'ogrn', 'phone'):
                continue
            sd = _domain((r.get('site') or '') if str(r.get('site') or '').startswith('http')
                         else 'http://' + str(r.get('site') or '')) if r.get('site') else ''
            site_root = '.'.join(sd.split('.')[-2:]) if sd else ''   # company.ru из www.company.ru
            # per-export shared (bad_sites) ИЛИ статический блок-лист (_is_own_site ловит
            # глобально-известный мусор, редкий в этом конкретном экспорте):
            if sd and (sd in bad_sites or not _is_own_site('http://' + sd)):
                r['site'] = ''; r['site_source'] = ''
                r['error'] = (r.get('error') or '') + ' [ложная привязка сайта отсеяна]'
                n_scrubbed += 1
            # судья сказал mismatch («сайт НЕ этой компании») — чужой сайт не показываем
            elif sd and r.get('verified') == 'mismatch':
                r['site'] = ''; r['site_source'] = ''
                r['error'] = (r.get('error') or '') + ' [сайт чужой (судья), скрыт]'
                n_scrubbed += 1

            def _email_ok(em, src=''):
                em = (em or '').lower()
                if '@' not in em or _is_junk_email(em):
                    return False
                # ИНН-верифицированные источники освобождены от доменных правил: контакт
                # закупщика из ЕИС (поиск ПО ИНН) легитимно живёт на чужом домене.
                if (src or '').split(':')[0] in ('zakupki', 'egrul', 'directory', 'vk-group'):
                    return True
                if em in bad_addrs:   # один адрес на >=2 ИНН (zakup_respect@mail.ru) = агентство/мусор
                    return False
                dom = em.split('@')[1]
                if dom in bad_doms:
                    return False
                # КОРЕНЬ ПРОБЛЕМЫ (ответ владельцу «как прошло без матча ИНН»): сайт был НЕ
                # верифицирован, а провайдер-судья пропустил дженерик-лендинг (sky.pro→skyeng.ru).
                # У настоящей компании домен email == домен сайта (или фримейл). Если сайт есть,
                # а email на ДРУГОМ не-фримейл домене — это чужой контакт (мис-резолв). Режем.
                if site_root and dom not in FREEMAIL:
                    edom_root = '.'.join(dom.split('.')[-2:])
                    if edom_root != site_root:
                        return False
                return True
            r['emails'] = [e for e in (r.get('emails') or [])
                           if _email_ok(e.get('email'), e.get('source'))]
            _bsrc = next((e.get('source') for e in r['emails']
                          if e.get('email') == r.get('best_for_outreach')), '')
            if not _email_ok(r.get('best_for_outreach'), _bsrc):
                r['best_for_outreach'] = (r['emails'][0].get('email') if r['emails'] else '')
            # ОБРАТНОЕ противоречие (владелец: Евдаково с сайтом b2b.efko.ru — «разные компании»):
            # почта подтверждена ПО ИНН (справочник/ЕГРЮЛ), а НЕверифицированный сайт на другом
            # домене — сайту не верим (кэш/мис-резолв), контакт оставляем.
            if site_root and r.get('best_for_outreach'):
                _bd = r['best_for_outreach'].split('@')[-1].lower()
                _bdr = '.'.join(_bd.split('.')[-2:])
                if ((_bsrc or '').split(':')[0] in ('directory', 'egrul')
                        and _bd not in FREEMAIL and _bdr != site_root):
                    r['site'] = ''; r['site_source'] = ''
                    r['error'] = (r.get('error') or '') + ' [сайт противоречит ИНН-почте, отсеян]'
                    n_scrubbed += 1
        if bad_sites or bad_doms:
            sys.stderr.write(f'export_core shared-guard: сайтов-ложняков={len(bad_sites)} '
                             f'доменов={len(bad_doms)} обнулено-строк={n_scrubbed} '
                             f'примеры={list(bad_sites)[:5]}\n')
        rows.sort(key=lambda r: -_score(r))
        # люди без почты: один запрос на всю выгрузку. Источник и дату наблюдения
        # тащим как есть — продажник должен видеть, откуда имя и когда его видели.
        lyudi_po_inn = {}
        try:
            import sqlite3 as _sq3
            _lc = _sq3.connect('file:%s?mode=ro' % os.environ.get(
                'ENRICH_DB', r'C:\sender\enrich.db').replace('\\', '/'), uri=True)
            for _r in _lc.execute(
                    "select inn, person, coalesce(post,''), coalesce(role,''), "
                    "coalesce(source,''), coalesce(observed_at,''), "
                    "coalesce(source_url,'') from people "
                    "where coalesce(person,'')<>'' order by inn"):
                lyudi_po_inn.setdefault(str(_r[0]), []).append(
                    (_r[1], _r[2], _r[3], _r[4], _r[5], _r[6]))
            _lc.close()
        except Exception as _e:  # noqa: BLE001
            print('люди в выгрузку не попали: %s' % str(_e)[:120], file=sys.stderr)

        buf = _io.StringIO()
        w = _csv.writer(buf, delimiter=';')
        # city + news_object — КОНТРАКТ ВЕРСТАЛЬЩИКА ПИСЕМ (владелец 2026-07-24): news-батч
        # обязан отдавать {news_object} и {city} заполненными, пустое поле роняет отправку.
        w.writerow(['score', 'inn', 'name', 'city', 'sector', 'okved_main', 'activity_site',
                    'revenue_rub', 'site', 'site_source',
                    'best_email', 'best_smtp', 'verified', 'all_contacts(email|роль|источник|smtp|страница)',
                    'lyudi(ФИО|должность|роль|откуда|когда видели|ссылка)',
                    'phones', 'signal_event', 'signal_what', 'news_object', 'signal_url', 'signal_ts',
                    'signal_match',
                    'opo', 'opo_object', 'opo_source', 'zakupki_contact', 'method', 'error'])
        # ОКВЭД/выручка/город ИЗ ОБЩЕЙ БАЗЫ для всех строк (владелец: «ну это же есть в общей
        # базе, почему не заполнил?») — один проход по 161k CSV только для недостающих ИНН.
        _need_ok = {str(r.get('inn')) for r in rows
                    if not info.get(str(r.get('inn')), {}).get('okved_main')
                    or not info.get(str(r.get('inn')), {}).get('city')}
        if _need_ok:
            try:
                _bi = _base_index(_need_ok)
                for _i, _b in _bi.items():
                    d = info.setdefault(_i, {})
                    if not d.get('okved_main'):
                        d['okved_main'] = _b.get('okved', '')
                    if not d.get('revenue_rub'):
                        d['revenue_rub'] = _b.get('revenue', '')
                    if not d.get('name'):
                        d['name'] = _b.get('name', '')
                    if not d.get('city'):
                        d['city'] = _b.get('city', '')
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f'export_core base-okved skip: {str(e)[:80]}\n')
        # ИМЕНА ДЛЯ ПУСТЫХ (владелец гуглит ИНН руками): dadata findById по ИНН, кап 120;
        # найденное сразу upsert-им в enrich.db, чтобы больше не резолвить.
        _dd_tok = _read_secret('DADATA_TOKEN')
        _dd_used = 0
        if _dd_tok:
            try:
                import enrich_db as _EDBn
                _dbw = _EDBn.EnrichDB()
            except Exception:  # noqa: BLE001
                _dbw = None
            for r in rows:
                inn0 = str(r.get('inn') or '')
                if (r.get('name') or info.get(inn0, {}).get('name') or db_names.get(inn0)):
                    continue
                if _dd_used >= 120:
                    break
                try:
                    body = json.dumps({'query': inn0}).encode()
                    req = urllib.request.Request(
                        'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                        data=body, method='POST', headers={'Content-Type': 'application/json',
                        'Accept': 'application/json', 'Authorization': f'Token {_dd_tok}'})
                    dd = json.loads(urllib.request.urlopen(req, timeout=15).read())
                    _dd_used += 1
                    sg = (dd.get('suggestions') or [])
                    nm = (sg[0].get('value') if sg else '') or ''
                    if nm:
                        db_names[inn0] = nm
                        if _dbw:
                            _dbw.upsert_company(inn0, name=nm)
                except Exception:  # noqa: BLE001
                    continue
        # Сверка «сигнал про ЭТУ ли компанию»: ядро имени (кавычки > не-ОПФ-слово) ищем в
        # тексте сигнала. Репост чужой новости в VK-группе компании — «НЕТ имени — проверь».
        _OPF_STOP = {'общество', 'ограниченной', 'ответственностью', 'акционерное', 'публичное',
                     'закрытое', 'открытое', 'непубличное', 'научно', 'производственное',
                     'предприятие', 'компания', 'объединение', 'корпорация', 'группа',
                     'торговый', 'торговая', 'холдинг', 'фирма', 'центр'}
        def _sig_match(name, sigs):
            if not sigs:
                return ''
            nm = (name or '').strip()
            qm = re.search(r'[«"]([^»"]{3,})[»"]', nm)
            core = (qm.group(1) if qm else '').strip()
            if not core:
                cands = [w for w in re.findall(r'[А-Яа-яЁёA-Za-z\-]{5,}', nm)
                         if w.lower() not in _OPF_STOP]
                core = max(cands, key=len, default='')
            tx = ' '.join((s.get('what', '') + ' ' + s.get('event', '')) for s in sigs).lower()
            if core and core.lower()[:max(5, len(core) - 2)] in tx:   # лёгкая склонко-устойчивость
                return 'имя в тексте'
            return 'НЕТ имени в тексте — проверь вручную'
        n_best = n_person = n_opo = 0
        # ОПО-градация для старых записей (собраны до появления opo_confidence): проверяем
        # страницу-источник fetch'ем один раз на уникальный URL (сниппет Яндекса != страница).
        _opo_page_cache = {}
        def _opo_grade(op):
            conf = op.get('opo_confidence')
            if conf in ('страница', 'рег№'):
                return 'да (' + conf + ')'
            if conf == 'сниппет':
                return 'сниппет?'
            if op.get('opo_reg'):
                return 'да (рег№)'
            u = op.get('source_url') or ''
            if not u:
                return 'сниппет?'
            if u not in _opo_page_cache:
                ok = False
                try:
                    html, _m, _me = VC._fetch(u)
                    if html:
                        ptxt = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S | re.I)
                        ptxt = re.sub(r'<[^>]+>', ' ', ptxt)
                        ok = bool(_OPO_OBJ.search(ptxt))
                except Exception:  # noqa: BLE001
                    ok = False
                _opo_page_cache[u] = ok
            return 'да (страница)' if _opo_page_cache[u] else 'сниппет?'
        for r in rows:
            inn = str(r.get('inn') or '')
            ci = info.get(inn, {})
            ems = [e for e in (r.get('emails') or []) if not _is_junk_email(e.get('email'))]
            best_email = r.get('best_for_outreach') or ''
            if _is_junk_email(best_email):   # платформенный/noreply best -> первый нормальный
                best_email = ems[0].get('email') if ems else ''
            best_smtp = next((e.get('smtp') for e in ems if e.get('email') == best_email), '')
            # 5-й сегмент — страница-источник контакта (владелец: «открыть и посмотреть сразу»)
            all_c = ' ; '.join(
                f"{e.get('email')}|{(e.get('role') or '')}|{e.get('source') or ''}|"
                f"{e.get('smtp') or ''}|{e.get('source_url') or ''}"
                for e in ems)
            # ЛЮДИ БЕЗ ПОЧТЫ — в выгрузку. Владелец: «надо чтобы они в информации
            # "откуда" в базе были видны просто». Раньше человек с должностью, но
            # без адреса существовал только в таблице people, и продажник его не
            # видел — хотя это и есть ЛПР, к которому можно обратиться через общий
            # ящик. Дату наблюдения показываем рядом: связка «человек — должность»
            # живёт недолго, и по записи трёхлетней давности имя называть опасно.
            _lyudi = ' ; '.join(
                '%s|%s|%s|%s|%s|%s' % (x[0], (x[1] or '')[:60], x[2] or '',
                                       x[3] or '', x[4] or '', x[5] or '')
                for x in (lyudi_po_inn.get(str(inn)) or [])[:6])
            op = r.get('opo') if isinstance(r.get('opo'), dict) else {}
            zk = r.get('zakupki') or {}
            zkc = ''
            if isinstance(zk, dict):
                c0 = next((c for c in (zk.get('cards') or []) if c.get('contact_person')), None) or {}
                if c0:
                    # + ссылка на карточку закупки (владелец: «нужна ссылка для проверки»)
                    zkc = (f"{c0.get('contact_person','')}|{c0.get('email','')}|"
                           f"{c0.get('phone','')}|{c0.get('url','')}")
            if best_email: n_best += 1
            if any((e.get('person') or '').strip() for e in ems): n_person += 1
            if (checko_opo.get(inn) or {}).get('rtn_opo'): n_opo += 1
            # ОПО: только чеко-верификация (владелец). SERP-сигнал в колонки не пишем.
            _ck = checko_opo.get(inn) or {}
            _og = 'да (чеко)' if _ck.get('rtn_opo') else ''
            _sigs = signals_by_inn.get(inn) or []
            # best_smtp пустой = SMTP-проба НЕ выполнялась для этого адреса (контакт из
            # БД-мерджа/старого прогона без smtp_check, или адрес не best в момент пробы) —
            # помечаем явно, чтобы продажник не путал с «проверен и жив».
            if best_email and not best_smtp:
                best_smtp = 'не проверялся'
            w.writerow([_score(r), inn,
                        (r.get('name') or ci.get('name') or db_names.get(inn) or ''),
                        ci.get('city') or r.get('city') or '',
                        ci.get('sector', ''), ci.get('okved_main', ''),
                        (r.get('activity') or '')[:120], ci.get('revenue_rub', ''),
                        r.get('site') or '', r.get('site_source') or '',
                        best_email, best_smtp, r.get('verified') or '', all_c, _lyudi,
                        # ' | ' а не пробел: телефоны теперь бывают с доб. и меткой отдела
                        ' | '.join(r.get('phones') or []),
                        ' | '.join(s['event'] for s in _sigs),
                        ' | '.join(s['what'] for s in _sigs),
                        # news_object: ОДНА конкретика (первый=сильнейший сигнал) для подстановки
                        # {news_object} в письмо; signal_what (все) — для проверки продажником
                        (_sigs[0]['what'] if _sigs else ''),
                        ' | '.join(s['url'] for s in _sigs if s['url']),
                        ' | '.join(s['ts'] for s in _sigs if s['ts']),
                        # сверка (владелец поймал: ИАЗ-новость у Лазермета — репост в VK-группе):
                        # имя компании должно встречаться в тексте сигнала, иначе «проверь»
                        _sig_match((r.get('name') or db_names.get(inn) or ''), _sigs),
                        _og,
                        ('оборудование под давлением' if _ck.get('pressure_equip')
                         else ('ОПО-лицензия' if _ck.get('rtn_opo') else '')),
                        ('checko: ' + _ck['lic_nums']) if _ck.get('rtn_opo') and _ck.get('lic_nums')
                        else ('checko' if _ck.get('rtn_opo') else ''), zkc,
                        r.get('method') or '', r.get('error') or ''])
        blob = buf.getvalue().encode('utf-8')
        out_name = args.get('out', 'centrifugal-core-enriched.csv')
        uploaded = False
        try:
            _D3 = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tok = os.environ.get('DROP_TOKEN', '')
            _D3.open(urllib.request.Request(drop + '/' + out_name, data=blob, method='PUT',
                     headers={'X-Drop-Token': tok}), timeout=120)
            uploaded = True
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:80]}'
        json.dump({'op': 'export_core', 'rows': len(rows), 'with_best': n_best,
                   'with_person_email': n_person, 'with_opo': n_opo, 'file': out_name,
                   'uploaded': uploaded}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'source_selftest':
        # ЕДИНЫЙ ТЕСТ каждого источника отдельно (владелец: каждое обогащение запускается
        # отдельно и даёт данные). На реальных компаниях -> per-source pass/данные.
        import time as _t
        test_inn_site = args.get('test_company') or {'inn': '7830000426', 'name': 'Водоканал Санкт-Петербурга',
                                                     'city': 'Санкт-Петербург'}
        priv = {'inn': '7725104641', 'name': 'ДОРОЖНО-СТРОИТЕЛЬНАЯ КОМПАНИЯ АВТОБАН', 'ogrn': '1027739058258'}
        out = {}
        def _run(name, fn):
            t0 = _t.time()
            try:
                r = fn()
                out[name] = {'ok': bool(r), 'sec': round(_t.time() - t0, 1),
                             'sample': (json.dumps(r, ensure_ascii=False)[:220] if r else None)}
            except Exception as e:  # noqa: BLE001
                out[name] = {'ok': False, 'err': f'{type(e).__name__}: {str(e)[:80]}'}

        def _run_panel(name, fn, candidates):
            # источник, доступность данных у которого зависит от компании: пробегаем небольшую
            # панель реальных компаний, источник считается рабочим если ХОТЬ ОДНА дала данные.
            t0 = _t.time(); hits = 0; sample = None; err = None
            for c in candidates:
                try:
                    r = fn(c)
                    if r:
                        hits += 1
                        if sample is None:
                            sample = json.dumps(r, ensure_ascii=False)[:220]
                except Exception as e:  # noqa: BLE001
                    err = f'{type(e).__name__}: {str(e)[:60]}'
            out[name] = {'ok': hits > 0, 'sec': round(_t.time() - t0, 1),
                         'hits': f'{hits}/{len(candidates)}', 'sample': sample}
            if err:
                out[name]['err'] = err
        # 1. xmlriver сайт+карточка
        _run('1_xmlriver_site', lambda: (lambda t: {'site': t[0], 'src': t[1],
             'card_phone': (t[2] or {}).get('phone')})(find_site_via_xmlriver(test_inn_site)))
        # 2. staff-поиск (панель: [name, domain]) — данные есть только если у компании есть
        #    страница руководства; проверяем на нескольких, source рабочий если хоть одна дала.
        staff_panel = args.get('staff_panel') or [
            {'name': 'ПАО Северсталь', 'domain': 'severstal.com'},
            {'name': 'ПАО НЛМК', 'domain': 'nlmk.ru'},
            {'name': 'ПАО ММК', 'domain': 'mmk.ru'},
            {'name': 'ЕвроХим', 'domain': 'eurochem.ru'},
        ]
        _run_panel('2_staff_search',
                   lambda c: find_staff_via_search({'name': c['name']}, c['domain']),
                   staff_panel)
        # 3. ЕГРЮЛ-email (панель ИНН) — email в ЕГРЮЛ есть далеко не у всех; пробегаем панель
        #    реальных ИНН, source рабочий если хоть один вернул зарегистрированный email.
        egrul_panel = args.get('egrul_panel') or [test_inn_site['inn'], priv['inn'],
                                                  '7830000426', '7736050003', '7728168971']
        _run_panel('3_egrul_email', lambda inn: _egrul_emails_by_inn(inn), egrul_panel)
        # 4. ЕИС-закупки
        _run('4_zakupki_eis', lambda: (lambda z: {'rss_items': (z or {}).get('rss_items'),
             'cards': len((z or {}).get('cards') or []),
             'first_contact': next((c for c in (z or {}).get('cards') or [] if c.get('contact_person')), None)}
             )(find_zakupki_contacts(test_inn_site['inn'], max_cards=2)))
        # 5. справочники
        _run('5_directory', lambda: find_directory_contacts(priv))
        # 6. SMTP-проба
        _run('6_smtp_verify', lambda: {'support@yandex.ru': smtp_verify('support@yandex.ru'),
             'nonexist999zzz@yandex.ru': smtp_verify('nonexist999zzz@yandex.ru')})
        # 7. ОПО-сигнал
        _run('7_opo_signal', lambda: find_opo_signal(priv))
        # 8. dadata резолв
        _run('8_dadata_resolve', lambda: __import__('news_scan').dadata_suggest('Северстали', _read_secret('DADATA_TOKEN')))
        json.dump({'op': 'source_selftest', 'sources': out,
                   'ok_count': sum(1 for v in out.values() if v.get('ok')),
                   'total': len(out)}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'coverage_report':
        # Замер покрытия по списку ИНН из enrich.db (без повторного обогащения): у скольких
        # сайт/email/по каким источникам/smtp-статус/verified. Читает то, что уже накоплено.
        import enrich_db as EDB
        import collections as _coll
        db = EDB.EnrichDB()
        inns = [str(i) for i in (args.get('inns') or [])]
        if not inns:
            inns = [r[0] for r in db.cx.execute('SELECT inn FROM companies').fetchall()]
        st = {'total': len(inns), 'with_site': 0, 'with_any_email': 0, 'with_best': 0,
              'verified': 0, 'by_email_source': {}, 'by_smtp': {}, 'with_phone': 0}
        src_c = _coll.Counter(); smtp_c = _coll.Counter()
        for inn in inns:
            c = db.cx.execute('SELECT site,best_email,verified,phones FROM companies WHERE inn=?',
                              (inn,)).fetchone()
            if not c:
                continue
            site, best, ver, phones = c
            if site:
                st['with_site'] += 1
            if best:
                st['with_best'] += 1
            if ver in ('inn', 'ogrn', 'phone', 'base+serp', 'provider'):
                st['verified'] += 1
            if phones:
                st['with_phone'] += 1
            ems = db.cx.execute('SELECT email,source,mx_ok FROM emails WHERE inn=?', (inn,)).fetchall()
            if ems:
                st['with_any_email'] += 1
            seen_src = set()
            for em, esrc, mxok in ems:
                base = (esrc or 'unknown').split(':')[0]
                if base not in seen_src:
                    src_c[base] += 1; seen_src.add(base)
        st['by_email_source'] = dict(src_c)
        json.dump({'op': 'coverage_report', **st}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'clean_bad_sites':
        # Вычистить из enrich.db «сайты», попавшие из контент-платформ/агрегаторов (dzen-
        # инцидент): site -> NULL, чтобы переобогащение пошло заново. dry_run=true - отчёт.
        import enrich_db as EDB
        db = EDB.EnrichDB()
        # Список НАМЕРЕННО отдельный от AGGREGATORS: там есть широкие подстроки
        # ('gis', 'tender', 'zakupki'), которые при массовой чистке снесли бы живые
        # домены (logistics.ru и т.п.). Здесь — только точные ложняки.
        bad = ('dzen.', 'zen.yandex', 'vc.ru', 'tenchat', 'pikabu', 'habr', 'rutube', 'youla',
               'journal.tinkoff', 'dprom.online', 'vbr.ru', '2gis', 'zoon', 'yandex.',
               'google.', 'youtube', 'wikipedia', 'avito', 'hh.ru', 'rusprofile', 'list-org',
               'checko', 'zachestnyibiznes', 'rbc.ru',
               # аудит общих сайтов 2026-07-26: сервисы проверки контрагентов и портал
               # раскрытия Интерфакса разъехались по 16 разным ИНН как «сайт компании».
               # Холдинги (СИБУР/Росатом/Линде) сюда НЕ попадают — общий домен у них
               # законный, чистим только заведомые справочники.
               'credinform', 'birweb', '1prime.ru', 'b2b.house', 'example.com')
        bad = bad + tuple(str(x).lower() for x in (args.get('extra') or []))
        rows = db.cx.execute("SELECT inn, site FROM companies WHERE site!='' AND site IS NOT NULL").fetchall()
        hit = [(i, st) for i, st in rows if any(b in str(st).lower() for b in bad)]
        # Почты, СНЯТЫЕ с этих справочников, опаснее самого сайта: они уходят в реальную
        # рассылку как контакт компании. Чистим их тем же списком (раньше op трогал
        # только companies.site, и адрес вида @credinform.ru оставался жить).
        # ВАЖНО: для почт список bad НЕ подходит — в нём есть 'yandex.', 'mail.ru',
        # 'google.' как домены «это не сайт компании», а адрес @yandex.ru у малой
        # компании абсолютно нормальный (сухой прогон дал 274 удаления, и почти все —
        # живые контакты). Поэтому для почт отдельный узкий список реестров.
        BAD_MAIL = ('rusprofile', 'credinform', 'list-org', 'checko.ru', 'zachestnyibiznes',
                    'birweb', '1prime.ru', 'b2b.house', 'example.com', 'sbis.ru',
                    'spark-interfax', 'kartoteka', 'seldon', 'e-ecolog', 'companium')
        BAD_MAIL = BAD_MAIL + tuple(str(x).lower() for x in (args.get('extra_mail') or []))
        emails = db.cx.execute("SELECT inn, email FROM emails WHERE email LIKE '%@%'").fetchall()
        ehit = [(i, e) for i, e in emails
                if any(b in str(e).lower().split('@')[-1] for b in BAD_MAIL)]
        out = {'op': 'clean_bad_sites', 'dry_run': bool(args.get('dry_run', True)),
               'total_with_site': len(rows), 'bad_found': len(hit), 'sample': hit[:15],
               'bad_emails': len(ehit), 'email_sample': ehit[:15]}
        if not args.get('dry_run', True):
            for i, _st in hit:
                db.cx.execute("UPDATE companies SET site='' WHERE inn=?", (i,))
            for i, e in ehit:
                db.cx.execute('DELETE FROM emails WHERE inn=? AND lower(email)=?',
                              (i, str(e).lower()))
                db.cx.execute('UPDATE companies SET best_email=\'\' WHERE inn=? '
                              'AND lower(best_email)=?', (i, str(e).lower()))
            db.cx.commit()
            out['cleaned'] = len(hit)
            out['emails_deleted'] = len(ehit)
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'clean_shared_sites':
        # ОБОБЩЁННЫЙ детектор ложных привязок (аудит: sky.pro на 195 ИНН). Домен сайта ИЛИ
        # email, привязанный к >= порогу РАЗНЫХ ИНН = не сайт/почта конкретной компании
        # (реклама/словарь/агрегатор/мис-резолв SERP). Обнуляет сайт + удаляет такие email.
        # dry_run=true — только отчёт (какие домены и сколько). Ловит НОВЫЕ ложняки без хардкода.
        import enrich_db as EDB
        import collections as _cc
        db = EDB.EnrichDB()
        thr = int(args.get('shared_threshold', 2))   # владелец: >=2 разных ИНН на домен = ложняк (verified щадим)
        FREE = {'mail.ru', 'yandex.ru', 'gmail.com', 'bk.ru', 'inbox.ru', 'list.ru',
                'rambler.ru', 'mail.com', 'internet.ru', 'ya.ru'}
        site_inns = _cc.defaultdict(set); dom_inns = _cc.defaultdict(set)
        for inn, site in db.cx.execute("SELECT inn, site FROM companies WHERE site!='' AND site IS NOT NULL").fetchall():
            d = _domain(str(site) if str(site).startswith('http') else 'http://' + str(site))
            if d:
                site_inns[d].add(str(inn))
        for inn, email, esrc in db.cx.execute("SELECT inn, email, source FROM emails").fetchall():
            # ИНН-верифицированные источники (ЕИС/ЕГРЮЛ/справочник) легитимно повторяются
            # между компаниями (общий уполномоченный орган закупок) — не считаем «общими».
            if (esrc or '').split(':')[0] in ('zakupki', 'egrul', 'directory', 'vk-group'):
                continue
            if '@' in (email or ''):
                dom_inns[email.split('@')[1].lower()].add(str(inn))
        bad_sites = {d: len(s) for d, s in site_inns.items() if len(s) >= thr}
        bad_doms = {d: len(s) for d, s in dom_inns.items() if len(s) >= thr and d not in FREE}
        out = {'op': 'clean_shared_sites', 'dry_run': bool(args.get('dry_run', True)),
               'threshold': thr,
               'bad_sites': dict(sorted(bad_sites.items(), key=lambda x: -x[1])[:25]),
               'bad_email_domains': dict(sorted(bad_doms.items(), key=lambda x: -x[1])[:25])}
        if not args.get('dry_run', True):
            ns = nd = 0
            # ПОДТВЕРЖДЁННЫЕ (verified inn/ogrn/phone) НЕ трогаем: реальный владелец домена
            # верифицирован, чистим только мис-резолвы на тот же домен.
            verified_inns = {str(r[0]) for r in db.cx.execute(
                "SELECT inn FROM companies WHERE verified IN ('inn','ogrn','phone')").fetchall()}
            for d in bad_sites:
                for inn in site_inns[d]:
                    if inn in verified_inns:
                        continue
                    db.cx.execute("UPDATE companies SET site='' WHERE inn=?", (inn,))
                    ns += 1
            for d in bad_doms:
                for inn in dom_inns[d]:
                    if inn in verified_inns:
                        continue
                    cur = db.cx.execute("DELETE FROM emails WHERE inn=? AND lower(email) LIKE ?",
                                        (inn, '%@' + d))
                    nd += cur.rowcount
                    db.cx.execute("UPDATE companies SET best_email='' WHERE inn=? AND lower(best_email) LIKE ?",
                                  (inn, '%@' + d))
            db.cx.commit()
            out['sites_nulled'] = ns; out['emails_deleted'] = nd
            # список пострадавших ИНН с именами — для ПЕРЕОТКРЫТИЯ реального сайта
            # (владелец: «перепроверить с новыми вводными, может реальный сайт найдётся»)
            _aff = set()
            for d in bad_sites:
                _aff |= {i for i in site_inns[d] if i not in verified_inns}
            relist = []
            for i in sorted(_aff):
                try:
                    row = db.cx.execute('SELECT name, region FROM companies WHERE inn=?', (i,)).fetchone()
                    relist.append({'inn': i, 'name': (row[0] if row else '') or '',
                                   'city': (row[1] if row else '') or ''})
                except Exception:  # noqa: BLE001
                    relist.append({'inn': i, 'name': '', 'city': ''})
            out['recheck_inns'] = relist
            out['spared_verified'] = len(verified_inns)
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'fetch_grep':
        # Диагностика источника: скачать страницу С СЕРВЕРА (VC._fetch: UA/ретраи/капча-детект)
        # и показать, ГДЕ на ней сидит паттерн (владелец: «откуда взята ОПО-информация?»).
        pat = re.compile(args.get('pattern', 'компрессорн'), re.I)
        out = []
        for u in (args.get('urls') or [])[:6]:
            row = {'url': u}
            try:
                html, method, meta = VC._fetch(u)
                row['method'] = method
                row['captcha'] = meta.get('captcha_type')
                if html:
                    txt = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S | re.I)
                    txt = re.sub(r'<[^>]+>', ' ', txt)
                    txt = re.sub(r'\s+', ' ', txt)
                    hits = []
                    for m in pat.finditer(txt):
                        a, b = max(0, m.start() - 120), min(len(txt), m.end() + 120)
                        hits.append('…' + txt[a:b] + '…')
                        if len(hits) >= 4:
                            break
                    row['hits'] = len(hits)
                    row['ctx'] = hits
                else:
                    row['error'] = 'пустой html'
            except Exception as e:  # noqa: BLE001
                row['error'] = str(e)[:100]
            out.append(row)
            time.sleep(1.0)
        json.dump({'op': 'fetch_grep', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'smtp_verify':
        # тест SMTP-пробы: emails -> статус (и проверка, открыт ли порт 25 с сервера)
        out = []
        for e in (args.get('emails') or [])[:12]:
            st = smtp_verify(e)
            out.append({'email': e, 'mx_ok': mx_ok(e), 'smtp': st})
            time.sleep(1.5)   # пауза между доменами (антиспам)
        json.dump({'op': 'smtp_verify', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_proxy_check':
        # READ-ONLY: у каких профилей стоит прокси (владелец проставил вручную — проверяем,
        # не перезаписывая; повторный set перетасовал бы его ручную раскладку).
        # Через REMOTE API (облако): Local API жив только при запущенном десктоп-приложении,
        # а dolphin_list вдобавок выбрасывает поле proxy. Заодно диагностирует «приложение закрыто».
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        # ДИАГНОСТИКА ИСТОЧНИКА токена (401-охота): откуда взялся и когда истекает (JWT),
        # сам токен НЕ выводим. env затеняет файл, локальный файл затеняет drop-storage.
        tok_diag = {'env': bool(os.environ.get('DOLPHIN_TOKEN'))}
        for _p in _SECRET_FILES:
            try:
                _has = os.path.exists(_p) and any(
                    ln.strip().startswith('DOLPHIN_TOKEN=') and len(ln.split('=', 1)[1].strip()) > 10
                    for ln in open(_p, encoding='utf-8-sig'))
            except Exception:  # noqa: BLE001
                _has = 'err'
            tok_diag[_p] = _has
        try:
            import base64 as _b64
            _mid = tokd.split('.')[1]
            _pl = json.loads(_b64.urlsafe_b64decode(_mid + '=' * (-len(_mid) % 4)))
            tok_diag['jwt_iat'] = _pl.get('iat')
            tok_diag['jwt_exp'] = _pl.get('exp')
            tok_diag['now'] = int(time.time())
        except Exception:  # noqa: BLE001
            tok_diag['jwt'] = 'не-JWT/пусто' if not tokd else 'не разобрать'
        out = []
        err_remote = None
        try:
            d = BP._dolphin_remote('GET', '/browser_profiles?limit=100', token=tokd)
            items = (d.get('data') if isinstance(d, dict) else None) or []
            if isinstance(items, dict):   # иногда {'data': {'items': [...]}}
                items = items.get('items') or []
            for p in items:
                px = p.get('proxy') or {}
                out.append({'id': str(p.get('id')), 'name': (p.get('name') or '')[:24],
                            'proxy': (f"{px.get('type','?')}://{px.get('host','')}:{px.get('port','')}"
                                      if px and px.get('host') else None)})
            if not items and isinstance(d, dict):
                err_remote = json.dumps(d, ensure_ascii=False)[:200]
        except Exception as e:  # noqa: BLE001
            err_remote = str(e)[:120]
        # локальный API — отдельным полем: жив = приложение запущено (нужно для VK/hh-маршрутов)
        local_alive = bool(BP.dolphin_list(token=tokd))
        json.dump({'op': 'dolphin_proxy_check', 'total': len(out),
                   'with_proxy': sum(1 for x in out if x['proxy']),
                   'without_proxy': [x for x in out if not x['proxy']],
                   'local_api_alive': local_alive, 'remote_err': err_remote,
                   'token_diag': tok_diag,
                   'profiles': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_set_proxies':
        # Раскидать прокси по профилям через Remote API (облачный - работает даже если локальное
        # приложение лежит). Список: args.proxies ИЛИ dolphin-proxies.txt с дропа. По одному
        # прокси на профиль (round-robin). Формат прокси: user:pass@host:port (схема scheme, деф socks5).
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        # список прокси
        raw_px = args.get('proxies')
        if not raw_px:
            try:
                _d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                url = os.environ.get('DROP_URL', '').rstrip('/') + '/dolphin-proxies.txt'
                req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
                raw_px = _d.open(req, timeout=30).read().decode('utf-8', 'replace')
            except Exception as e:  # noqa: BLE001
                json.dump({'op': 'dolphin_set_proxies', 'error': f'нет списка прокси: {str(e)[:60]}'},
                          sys.stdout, ensure_ascii=False); return
        scheme = args.get('scheme', 'socks5')
        proxies = []
        for line in (raw_px if isinstance(raw_px, list) else raw_px.splitlines()):
            line = str(line).strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'(?:(socks5|socks4|https?)://)?(?:([^:@]+):([^@]*)@)?([^:/]+):(\d+)', line)
            if not m:
                continue
            sc, user, pw, host, port = m.groups()
            px = {'type': sc or scheme, 'host': host, 'port': int(port)}
            if user:
                px['login'] = user; px['password'] = pw or ''
            proxies.append(px)
        if not (profs and proxies):
            json.dump({'op': 'dolphin_set_proxies', 'error': 'нет профилей или прокси',
                       'n_profiles': len(profs), 'n_proxies': len(proxies)},
                      sys.stdout, ensure_ascii=False); return
        # VK-профиль исключаем: его IP не меняем (токен VK к нему привязан, владелец 2026-07-23)
        vk_pin = str(args.get('vk_profile', _VK_PIN_PROFILE))
        skip_vk = bool(args.get('skip_vk_profile', True))
        results = []
        _pi = 0
        for pid in profs:
            if skip_vk and str(pid) == vk_pin:
                results.append({'profile': pid, 'proxy': 'SKIP (VK-профиль, IP не меняем)', 'ok': True})
                continue
            px = proxies[_pi % len(proxies)]; _pi += 1
            try:
                r = BP._dolphin_remote('PATCH', f'/browser_profiles/{pid}', {'proxy': px}, token=tokd)
                ok = bool(isinstance(r, dict) and (r.get('success') or r.get('data') or not r.get('error')))
                results.append({'profile': pid, 'proxy': f"{px['host']}:{px['port']}", 'ok': ok,
                                'resp': json.dumps(r, ensure_ascii=False)[:120]})
            except Exception as e:  # noqa: BLE001
                results.append({'profile': pid, 'proxy': f"{px['host']}:{px['port']}",
                                'ok': False, 'err': str(e)[:80]})
        json.dump({'op': 'dolphin_set_proxies', 'assigned': len(results),
                   'ok_count': sum(1 for r in results if r.get('ok')),
                   'proxies_available': len(proxies), 'results': results[:25]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'dolphin_stop_all':
        # Погасить ВСЕ профили (сироты после прерванных прогонов) - dolphin_stop идемпотентен
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        done = []
        for pid in profs:
            try:
                BP.dolphin_stop(pid, token=tokd)
                done.append(pid)
            except Exception:  # noqa: BLE001
                pass
        json.dump({'op': 'dolphin_stop_all', 'stopped': done, 'count': len(done)},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'etp_probe':
        # проверка доступности коммерческих ЭТП с сервера (РФ-IP): отдаётся ли поиск/карточка
        # без логина. Владелец: «надо проверить так ли это».
        import ssl as _ssl
        _ctx = _ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = _ssl.CERT_NONE
        _op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                          urllib.request.HTTPSHandler(context=_ctx))
        urls = args.get('urls') or ['https://www.b2b-center.ru/market/',
                                    'https://www.fabrikant.ru/trades/', 'https://etprf.ru/']
        out = []
        for u in urls:
            rec = {'url': u}
            try:
                r = _op.open(urllib.request.Request(u, headers={'User-Agent': VC.UA}), timeout=25)
                html = r.read().decode('utf-8', 'replace'); low = html.lower()
                rec['status'] = r.status; rec['len'] = len(html)
                rec['markers'] = [k for k in ('войти', 'регистрац', 'личный кабинет', 'закупк',
                                              'тендер', 'контакт', 'организатор', 'телефон')
                                  if k in low]
            except urllib.error.HTTPError as e:
                rec['status'] = e.code
            except Exception as e:  # noqa: BLE001
                rec['error'] = f'{type(e).__name__}: {str(e)[:90]}'
            out.append(rec)
        json.dump({'op': 'etp_probe', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'fsa_probe':
        # Разведка реестра аттестованных Ростехнадзора (pub.fsa.gov.ru) С СЕРВЕРА (РФ-IP +
        # Russian Trusted CA). Пробуем набор эндпоинтов/фильтров по тестовому ИНН, отчёт
        # статус+первые байты - понять форму API до написания парсера.
        test_inn = str(args.get('inn') or '4205000908')
        tries = [
            ('POST', 'https://pub.fsa.gov.ru/api/v1/rpa/common/certificates/get',
             {'size': 10, 'page': 0, 'filter': {'inn': test_inn}}),
            ('POST', 'https://pub.fsa.gov.ru/api/v1/rpa/common/experts/get',
             {'size': 10, 'page': 0, 'filter': {'inn': test_inn}}),
            ('POST', 'https://pub.fsa.gov.ru/api/v1/ral/common/experts/get',
             {'size': 10, 'page': 0, 'filter': {'inn': test_inn}}),
            ('GET', 'https://pub.fsa.gov.ru/api/v1/rpa/common/dictionary/ affiliate'.replace(' ', ''), None),
        ]
        out = []
        for method, u, body in tries:
            rec = {'method': method, 'url': u}
            try:
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(u, data=data, method=method,
                    headers={'User-Agent': VC.UA, 'Content-Type': 'application/json',
                             'Accept': 'application/json'})
                r = _eis_get.__self__ if False else None  # noqa
                import ssl as _ssl
                _ctx = _ssl.create_default_context(); _ctx.check_hostname = False
                _ctx.verify_mode = _ssl.CERT_NONE
                _op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                  urllib.request.HTTPSHandler(context=_ctx))
                resp = _op.open(req, timeout=25)
                raw = resp.read()
                rec['status'] = resp.status
                rec['len'] = len(raw)
                rec['body_head'] = raw[:500].decode('utf-8', 'replace')
            except urllib.error.HTTPError as e:
                rec['status'] = e.code
                rec['body_head'] = e.read()[:300].decode('utf-8', 'replace')
            except Exception as e:  # noqa: BLE001
                rec['error'] = f'{type(e).__name__}: {str(e)[:120]}'
            out.append(rec)
        json.dump({'op': 'fsa_probe', 'inn': test_inn, 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'mark_shared_phones':
        # Телефоны, встречающиеся у >=min_share компаний базы = «возможно общий» (бизнес-центр/
        # бухгалтерия/аутсорс). Владелец 2026-07-23: пометить, чтобы не считать прямым контактом.
        # Выход: shared_phones.txt на дроп (нормализованные 10-значные) + опц. флаг shared_phone
        # у компаний enrich.db. Email по телефонам НЕ переносим (отменено владельцем).
        import csv as _csvs
        try:
            _csvs.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        bp = _get_base()
        if not bp:
            json.dump({'op': 'mark_shared_phones', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        PH = 18
        phone_inns = {}
        with open(bp, encoding='utf-8-sig', newline='') as f:
            rd = _csvs.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                try:
                    inn = row[1].strip()
                    if not inn:
                        continue
                    for _p in (row[PH] or '').split('|'):
                        dg = re.sub(r'\D', '', _p)
                        if len(dg) >= 10:
                            phone_inns.setdefault(dg[-10:], set()).add(inn)
                except Exception:  # noqa: BLE001
                    continue
        min_share = int(args.get('min_share', 3))
        shared = {ph: len(inns) for ph, inns in phone_inns.items() if len(inns) >= min_share}
        shared_inns = set()
        for ph, inns in phone_inns.items():
            if len(inns) >= min_share:
                shared_inns |= inns
        # список общих телефонов на дроп (для скоринга/отправки: членство = низкое доверие)
        uploaded = ''
        try:
            _D = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            drop = os.environ.get('DROP_URL', '').rstrip('/'); tk = os.environ.get('DROP_TOKEN', '')
            blob = '\n'.join(sorted(shared)).encode('utf-8')
            _D.open(urllib.request.Request(drop + '/shared_phones.txt', data=blob, method='PUT',
                    headers={'X-Drop-Token': tk}), timeout=90)
            uploaded = 'shared_phones.txt'
        except Exception as e:  # noqa: BLE001
            uploaded = f'upload-err:{str(e)[:60]}'
        # флаг в enrich.db (только для уже присутствующих компаний)
        marked = 0
        if not args.get('dry_run', True):
            try:
                import enrich_db as EDB
                db = EDB.EnrichDB()
                try:
                    db.cx.execute('ALTER TABLE companies ADD COLUMN shared_phone INTEGER DEFAULT 0')
                    db.cx.commit()
                except Exception:  # noqa: BLE001
                    pass
                have = {r[0] for r in db.cx.execute('SELECT inn FROM companies').fetchall()}
                for inn in (shared_inns & have):
                    db.cx.execute('UPDATE companies SET shared_phone=1 WHERE inn=?', (inn,))
                    marked += 1
                db.cx.commit()
            except Exception as e:  # noqa: BLE001
                marked = f'db-err:{str(e)[:60]}'
        top = sorted(shared.items(), key=lambda x: -x[1])[:8]
        json.dump({'op': 'mark_shared_phones', 'dry_run': bool(args.get('dry_run', True)),
                   'min_share': min_share, 'shared_phones': len(shared),
                   'companies_on_shared_phones': len(shared_inns),
                   'uploaded': uploaded, 'marked_in_db': marked,
                   'top_shared': [{'phone': p, 'companies': n} for p, n in top]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'phone_match':
        # Перенос email внутри групп ОДИНАКОВЫХ телефонов базы 161к (владелец 2026-07-23:
        # «попробуем, посмотрим результат, с возможностью откатить»). dry_run=true (деф.) -
        # только отчёт без записи. Запись: emails с source='phone-match:<ИНН-донора>' ->
        # откат одним DELETE (op phone_match_rollback). Группы крупнее max_group (вирт.АТС/
        # колл-центры) пропускаются - там номер ничего не значит.
        import csv as _csvp
        try:
            _csvp.field_size_limit(2 ** 20)   # иначе строка с большим полем ломает ридер -> 0 строк
        except Exception:  # noqa: BLE001
            pass
        bp = _get_base()
        if not bp:
            json.dump({'op': 'phone_match', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        _diag = {'path': bp, 'size': os.path.getsize(bp)}
        with open(bp, encoding='utf-8-sig', newline='') as _f:
            _h0 = _f.readline()
            _r1 = _f.readline()
        _diag['header_first120'] = _h0[:120]
        _diag['sep_semicolon'] = _h0.count(';')
        _diag['sep_comma'] = _h0.count(',')
        _diag['sep_tab'] = _h0.count(chr(9))
        _diag['row1_first120'] = _r1[:120]
        if args.get('diag_only'):
            with open(bp, encoding='utf-8-sig', newline='') as _f2:
                _rd2 = _csvp.reader(_f2, delimiter=';')
                _hdr = next(_rd2, [])
                _diag['ncols'] = len(_hdr)
                _diag['col18_name'] = _hdr[18] if len(_hdr) > 18 else '?'
                _diag['col19_name'] = _hdr[19] if len(_hdr) > 19 else '?'
                _samp = []
                for _k in range(3):
                    _rw = next(_rd2, [])
                    _samp.append({'ncol': len(_rw), 'c18': (_rw[18] if len(_rw) > 18 else '')[:40],
                                  'c19': (_rw[19] if len(_rw) > 19 else '')[:40]})
                _diag['rows'] = _samp
            json.dump({'op': 'phone_match', 'diag': _diag}, sys.stdout, ensure_ascii=False)
            return
        INN_, NAME_, PH, EM = 1, 5, 18, 19
        groups = {}
        with open(bp, encoding='utf-8-sig', newline='') as f:
            rd = _csvp.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                try:
                    inn = row[INN_].strip()
                    if not inn:
                        continue
                    # телефоны отформатированы (+7 916 217-95-01) -> нормализуем ДО извлечения
                    phones = set()
                    for _p in (row[PH] or '').split('|'):
                        _dg = re.sub(r'\D', '', _p)
                        if len(_dg) >= 10:
                            phones.add(_dg[-10:])
                    ems = [e.lower() for e in re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', row[EM] or '')]
                    for ph in phones:
                        groups.setdefault(ph, []).append((inn, ems, (row[NAME_] or '')[:50]))
                except Exception:  # noqa: BLE001
                    continue
        _tot_rows = sum(len(m) for m in groups.values())
        _with_email = sum(1 for m in groups.values() for (i, e, n) in m if e)
        max_group = int(args.get('max_group', 6))       # крупные группы = БЦ/бухгалтерия, режем
        name_gate = bool(args.get('name_gate', True))   # общий бренд-токен обязателен (деф.)
        cand = []
        for ph, members in groups.items():
            if len(members) < 2 or len(members) > max_group:
                continue
            donors = [(i, e, n) for i, e, n in members if e]
            empty = [(i, e, n) for i, e, n in members if not e]
            if not donors or not empty:
                continue
            d_inn, d_em, d_nm = donors[0]
            _STOP = {'торг','групп','компан','сервис','строй','инвест','пром','рус','юг',
                     'снаб','плюс','центр','групп','альянс','капитал','холдинг','финанс'}
            def _toks(x):
                return {t for t in re.findall(r'[а-яёa-z]{4,}', (x or '').lower()) if t not in _STOP}
            for r_inn, _e, r_nm in empty:
                shared = _toks(d_nm) & _toks(r_nm)
                if name_gate and not shared:
                    continue   # нет общего бренд-токена -> вероятно БЦ/бухгалтерия, не холдинг
                cand.append({'inn': r_inn, 'email': d_em[0], 'donor': d_inn, 'phone': ph,
                             'to_name': r_nm, 'donor_name': d_nm,
                             'shared_token': sorted(shared)[:2]})
        import collections as _coll
        _size_hist = dict(_coll.Counter(min(len(m), 11) for m in groups.values() if len(m) >= 2))
        # примеры групп размера 6-10 (подозрительные: БЦ/бухгалтерия, не холдинг)
        _big_ex = []
        for ph, m in groups.items():
            if 6 <= len(m) <= 10 and any(e for i, e, n in m) and len(_big_ex) < 4:
                _big_ex.append({'phone': ph, 'names': [n[:32] for i, e, n in m]})
        _gsizes = sorted((len(m) for m in groups.values()), reverse=True)[:5]
        out = {'op': 'phone_match', 'dry_run': bool(args.get('dry_run', True)),
               'rows_with_phone': _tot_rows, 'unique_phones': len(groups),
               'rows_with_email_in_groups': _with_email,
               'biggest_groups': _gsizes,
               'groups_2_to_max': sum(1 for m in groups.values() if 2 <= len(m) <= max_group),
               'size_hist_2plus': _size_hist, 'big_group_examples': _big_ex,
               'candidates': len(cand), 'sample': cand[:12]}
        if not args.get('dry_run', True):
            import enrich_db as EDB
            db = EDB.EnrichDB()
            n = 0
            for c in cand:
                try:
                    db.add_email(c['inn'], c['email'], role='общий (phone-match)',
                                 source=f"phone-match:{c['donor']}", source_url='')
                    n += 1
                except Exception:  # noqa: BLE001
                    pass
            out['written'] = n
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'phone_match_rollback':
        # ОТКАТ phone-match одним DELETE (обещание владельцу)
        import enrich_db as EDB
        db = EDB.EnrichDB()
        cur = db.cx.execute("DELETE FROM emails WHERE source LIKE 'phone-match%'")
        db.cx.commit()
        json.dump({'op': 'phone_match_rollback', 'deleted': cur.rowcount}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'zakupki_mass':
        # МАССОВЫЙ ЕИС-проход (владелец: «не только 396, а ВСЕ компании, сверху вниз по
        # выручке» - параллельный слой скоринга). Контакты закупщиков (source zakupki:eis,
        # роль «закупки», ФИО из карточки) + ГОРЯЧИЙ сигнал, если предмет закупки - наше
        # оборудование. Дурабельно: .zk_done.txt по ИНН + zakupki_stream.jsonl; самочейн;
        # стоп - файл zakupki_stop.flag на дропе.
        import csv as _csvz
        try:
            _csvz.field_size_limit(2 ** 20)
        except Exception:  # noqa: BLE001
            pass
        _dirz = os.path.dirname(os.path.abspath(__file__))
        done_p = os.path.join(_dirz, '.zk_done.txt')
        done = set()
        try:
            done = set(l.strip() for l in open(done_p, encoding='utf-8') if l.strip())
        except FileNotFoundError:
            pass
        bp = _get_base()
        if not bp:
            json.dump({'op': 'zakupki_mass', 'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        rows = []
        with open(bp, encoding='utf-8-sig', newline='') as f:
            rd = _csvz.reader(f, delimiter=';')
            next(rd, None)
            for row in rd:
                try:
                    inn = row[1].strip()
                    if not inn or inn in done:
                        continue
                    rev = float(row[34] or 0)
                    rows.append((rev, inn, (row[5] or row[6] or '')[:60]))
                except Exception:  # noqa: BLE001
                    continue
        rows.sort(key=lambda x: -x[0])
        cap = int(args.get('cap', 120))
        chunk = rows[:cap]
        ZK_HOT = re.compile(r'компрессор|воздуходув|осушит|сжат\w*\s+воздух|пневмо|'
                            r'генератор\w*\s+(азот|кислород)|фотосепаратор|рентген\w*\s+инспек', re.I)
        db = None
        try:
            import enrich_db as EDB
            db = EDB.EnrichDB()
        except Exception:  # noqa: BLE001
            pass
        st = {'processed': 0, 'with_contacts': 0, 'hot': 0, 'errors': 0}
        hot_sample = []
        dfh = open(done_p, 'a', encoding='utf-8')
        jl = open(os.path.join(_dirz, 'zakupki_stream.jsonl'), 'a', encoding='utf-8')
        for rev, inn, name in chunk:
            z = find_zakupki_contacts(inn, max_cards=int(args.get('max_cards', 3)))
            st['processed'] += 1
            jl.write(json.dumps({'inn': inn, 'name': name, 'rev': rev, 'z': z},
                                ensure_ascii=False) + '\n')
            jl.flush()
            dfh.write(inn + '\n')
            dfh.flush()
            if not z or z.get('error'):
                st['errors'] += 1 if (z or {}).get('error') else 0
                continue
            got = hot = False
            for c in (z.get('cards') or []):
                if c.get('email') and db is not None:
                    got = True
                    try:
                        db.add_email(inn, c['email'], role='закупки (конт. лицо)',
                                     person=c.get('contact_person') or '',
                                     source='zakupki:eis', source_url=c.get('url') or '')
                    except Exception:  # noqa: BLE001
                        pass
                if ZK_HOT.search(c.get('title') or ''):
                    hot = True
                    if len(hot_sample) < 6:
                        hot_sample.append({'inn': inn, 'name': name, 'title': c.get('title')})
                    if db is not None:
                        try:
                            db.add_signal(inn, source='zakupki:eis', event_type='закупка-оборудование',
                                          what=(c.get('title') or '')[:140], hotness=4,
                                          source_url=c.get('url') or '', ts='')
                        except Exception:  # noqa: BLE001
                            pass
            st['with_contacts'] += 1 if got else 0
            st['hot'] += 1 if hot else 0
        dfh.close()
        jl.close()
        # самочейн со своим стоп-флагом
        chained = ''
        if args.get('chain') and len(rows) > cap:
            drop = os.environ.get('DROP_URL', '').rstrip('/')
            tokd = os.environ.get('DROP_TOKEN', '')
            sec = os.environ.get('JOB_HMAC', '')
            import hmac as _h
            import hashlib as _hl
            try:
                req = urllib.request.Request(drop + '/list', headers={'X-Drop-Token': tokd})
                names = [f.get('name') for f in json.loads(urllib.request.urlopen(req, timeout=30).read())]
                if 'zakupki_stop.flag' in names:
                    chained = 'stopped-by-flag'
                else:
                    jid = f'{int(time.time())}-zkmass{os.getpid()}'
                    job = {'id': jid, 'task': 'enrich_contacts', 'args': args, 'ts': int(time.time())}
                    canon = json.dumps({'id': job['id'], 'task': job['task'], 'args': job['args'],
                                        'ts': job['ts']}, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=False)
                    if sec:
                        job['sig'] = _h.new(sec.encode(), canon.encode(), _hl.sha256).hexdigest()
                    rq = urllib.request.Request(drop + f'/job-{jid}.json',
                                                data=json.dumps(job, ensure_ascii=False).encode('utf-8'),
                                                method='PUT', headers={'X-Drop-Token': tokd})
                    urllib.request.urlopen(rq, timeout=60)
                    chained = jid
            except Exception as e:  # noqa: BLE001
                chained = f'chain-err:{str(e)[:60]}'
        json.dump({'op': 'zakupki_mass', **st, 'left': len(rows) - len(chunk),
                   'hot_sample': hot_sample, 'chained': chained}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'promote_named_email':
        # ЛУЧШИЙ АДРЕС = ИМЕННОЙ, а не приёмная. После ЕИС-прогона у части компаний
        # появился адрес снабженца с ФИО, но best_email по-прежнему указывает на
        # info@/sales@. Письмо с горячим поводом в общую приёмную — потеря повода,
        # поэтому пере-выбираем лучший адрес по приоритету роли и наличию человека.
        # Durable: пишем companies.best_email + stage_log('best_email_v2').
        import enrich_db as _EDBp
        db = _EDBp.EnrichDB()
        GENERIC = ('info@', 'mail@', 'office@', 'sale@', 'sales@', 'zakaz@', 'order@',
                   'secretar', 'priemnaya@', 'inbox@', 'post@', 'contact@', 'reception',
                   'admin@', 'support@', 'help@', 'shop@', 'market@')
        # Технические ЛПР ВЫШЕ закупок (владелец 29.07) — тот же порядок, что и в
        # _ROLE_RANK: выбор компрессора делает служба главного инженера/энергетика.
        # Ключи проверяются по вхождению в строку роли, поэтому узкие идут первыми.
        ROLE_RANK = (('энергет', 130), ('гл.инженер', 128), ('гл. инженер', 128),
                     ('главный инженер', 128), ('механ', 124), ('техдиректор', 122),
                     ('технический директор', 122), ('нач.производ', 120),
                     ('начальник производ', 120), ('технолог', 118),
                     ('нач.цех', 116), ('начальник цех', 116),
                     ('кипиа', 114), ('асу тп', 114),
                     ('инженер', 112), ('техни', 110), ('производ', 105),
                     ('закупк', 100), ('снабж', 95), ('тендер', 90),
                     ('директор', 60), ('руковод', 55), ('менеджер', 40))
        # роли, которые НЕ покупают наше оборудование: повышать на них нельзя, даже если
        # адрес именной (ошибка первой версии: sales@ менялся на hr@ и это считалось
        # улучшением). Отрицательный вес, чтобы такой адрес не выигрывал никогда.
        ROLE_DENY = ('кадр', 'hr', 'персонал', 'подбор', 'ваканс', 'пресс', 'press',
                     'юрис', 'бухгалт', 'реклам', 'маркет', 'сми')
        # бесплатные почтовые домены: адрес на них не привязан к компании, повышать
        # на такой адрес с корпоративного — потеря адресности
        FREEMAIL = ('mail.ru', 'bk.ru', 'inbox.ru', 'list.ru', 'yandex.ru', 'ya.ru',
                    'gmail.com', 'rambler.ru', 'internet.ru', 'icloud.com', 'outlook.com')

        # те же «непокупающие» отделы, но по САМОМУ адресу: роль в базе часто пустая
        # или «общий», а local-part говорит правду (info@kdl.ru -> pressa@kdl.ru — так
        # первая версия повысила адрес пресс-службы)
        LOCAL_DENY = ('press', 'pressa', 'smi', 'hr@', 'hr.', 'kadr', 'vacan', 'job',
                      'rabota', 'rekla', 'marketing', 'legal', 'urist', 'jurist',
                      'buh', 'account', 'noreply', 'no-reply', 'abuse', 'postmaster')

        def _dom(e):
            return (e or '').split('@')[-1].strip().lower()

        def _local(e):
            return (e or '').split('@')[0].strip().lower()

        def _deny_local(e):
            lp = _local(e)
            return any(k.rstrip('@.') in lp for k in LOCAL_DENY)

        def _is_generic(e):
            return any(g in (e or '').lower() for g in GENERIC)

        def _score(row):
            # row = (email, role, person, mx_ok, source) — курсор без row_factory.
            # Чем выше, тем лучше: роль закупок > снабжение > инженер > ... ,
            # именной адрес важнее общего, живой MX важнее непроверенного
            email, role, person, mxok, source = row[0], row[1], row[2], row[3], row[4]
            role = (role or '').lower()
            s = 0
            if any(k in role for k in ROLE_DENY) or _deny_local(email):
                return -1000          # кадры/пресса/юристы — не адресат коммерческого письма
            for key, val in ROLE_RANK:
                if key in role:
                    s += val
                    break
            if (person or '').strip():
                s += 30
            if not _is_generic(email):
                s += 25
            if mxok in (1, '1', True):
                s += 10
            if (source or '').startswith('zakupki'):
                s += 15          # контакт с карточки закупки — проверенный и по делу
            return s

        inns = [str(i).strip() for i in (args.get('inns') or []) if str(i).strip()]
        if not inns:
            # по умолчанию — весь новостной пул (fit + получатели кампаний)
            for r in db.cx.execute("SELECT inn, detail FROM stage_log "
                                   "WHERE stage='okved_v2'").fetchall():
                p = dict(x.split('=', 1) for x in str(r[1] or '').split(';') if '=' in x)
                if p.get('fit') == '1':
                    inns.append(str(r[0]))
            try:
                import sqlite3 as _sq4
                _sn = _sq4.connect(r'C:\sender\sender.db')
                for r in _sn.execute("SELECT DISTINCT inn FROM recipients "
                                     "WHERE COALESCE(inn,'')<>''").fetchall():
                    if str(r[0]) not in inns:
                        inns.append(str(r[0]))
                _sn.close()
            except Exception:  # noqa: BLE001
                pass
        if args.get('revert'):
            # откат неудачного прогона: в stage_log сохранено «было=...;стало=...»
            rb = {'op': 'promote_named_email', 'откат': 0, 'не_разобрано': 0}
            for r in db.cx.execute("SELECT inn, detail FROM stage_log "
                                   "WHERE stage='best_email_v2'").fetchall():
                p = dict(x.split('=', 1) for x in str(r[1] or '').split(';') if '=' in x)
                was = (p.get('было') or '').strip()
                if not was:
                    rb['не_разобрано'] += 1
                    continue
                db.cx.execute("UPDATE companies SET best_email=? WHERE inn=?", (was, r[0]))
                rb['откат'] += 1
            db.cx.execute("DELETE FROM stage_log WHERE stage='best_email_v2'")
            db.cx.commit()
            json.dump(rb, sys.stdout, ensure_ascii=False)
            return
        res = {'op': 'promote_named_email', 'пул': len(inns), 'заменено': 0,
               'было_общих': 0, 'осталось_общих': 0, 'без_адресов': 0, 'примеры': []}
        for inn in inns:
            rows = db.cx.execute(
                "SELECT email, role, person, mx_ok, source FROM emails WHERE inn=?",
                (inn,)).fetchall()
            if not rows:
                res['без_адресов'] += 1
                continue
            cur = db.cx.execute("SELECT best_email FROM companies WHERE inn=?",
                                (inn,)).fetchone()
            cur_mail = (cur[0] if cur else '') or ''
            if _is_generic(cur_mail) or not cur_mail:
                res['было_общих'] += 1
            best = max(rows, key=_score)
            b_mail, b_role, b_person = (best[0] or ''), (best[1] or ''), (best[2] or '')
            # ДОМЕННЫЙ ГЕЙТ (урок первой версии: адрес подменялся на чужой домен —
            # zao_primorye@mail.ru -> zno@primbank.ru, то есть на другую компанию).
            # Повышаем только если новый адрес на том же домене, что текущий лучший,
            # или на домене сайта компании. Исключение — контакт с карточки закупки
            # ЕИС: он привязан к ИНН этой компании, домен там законно другой.
            site_dom = ''
            _c2 = db.cx.execute("SELECT site FROM companies WHERE inn=?", (inn,)).fetchone()
            if _c2 and _c2[0]:
                site_dom = _dom('x@' + str(_c2[0]).replace('https://', '')
                                .replace('http://', '').replace('www.', '').split('/')[0])
            b_dom = _dom(b_mail)
            same_domain = b_dom and b_dom in (_dom(cur_mail), site_dom)
            src = str(best[4] or '')
            from_eis = src.startswith('zakupki')
            # ПРАВИЛО ВЛАДЕЛЬЦА: домен совпадать НЕ обязан (холдинг, дочка на домене
            # головной, общая служба закупок). Отсекаем не по домену, а по
            # ПРИНАДЛЕЖНОСТИ: адрес с чужого домена берём, только если этот домен не
            # принадлежит ДРУГОЙ компании нашей базы (именно так проскочил
            # zao_primorye@mail.ru -> zno@primbank.ru) и это не безымянная бесплатная почта.
            alien = False
            if b_dom and not same_domain:
                _o = db.cx.execute(
                    "SELECT inn FROM companies WHERE inn<>? AND site LIKE ? LIMIT 1",
                    (inn, '%' + b_dom + '%')).fetchone()
                alien = bool(_o)
            freemail_noname = (b_dom in FREEMAIL) and not (best[2] or '').strip()
            # источник, привязанный к ИНН (карточка закупки ЕИС, ЕГРЮЛ), — доверенный
            trusted_src = from_eis or src.startswith('egrul')
            # Чужой домен берём ТОЛЬКО при доказательстве привязки к этой компании:
            # либо источник привязан к ИНН, либо есть живой человек в покупающей роли.
            # Без доказательства чужой домен — это чужая компания: так проскочили
            # info@salstek.ru -> head@sar-steklo.ru (Салаватстекло и Саратовстекло —
            # разные заводы) и info@kld39.com -> cbmdou@admin.gorny.ru (бухгалтерия
            # муниципалитета). Обе компании в нашей базе отсутствуют, поэтому проверка
            # «домен принадлежит другому ИНН» их не поймала.
            buying_role = any(k in (best[1] or '').lower()
                              for k in ('закупк', 'снабж', 'тендер', 'инженер',
                                        'технолог', 'производ', 'директор'))
            proof = trusted_src or ((best[2] or '').strip() and buying_role)
            domain_ok = same_domain or (proof and not alien and not freemail_noname)
            # не понижаем: если текущий адрес уже именной, менять его можно только на
            # контакт закупок с живым человеком (иначе теряем адресность)
            downgrade = (cur_mail and not _is_generic(cur_mail)
                         and not (from_eis and (best[2] or '').strip()))
            if b_mail and b_mail.lower() != cur_mail.lower() and domain_ok \
                    and not downgrade and _score(best) > 0 and not _is_generic(b_mail):
                db.upsert_company(inn, best_email=b_mail.lower())
                db.mark_stage(inn, 'best_email_v2',
                              f'было={cur_mail[:40]};стало={b_mail[:40]};'
                              f'роль={b_role[:30]}')
                res['заменено'] += 1
                if len(res['примеры']) < 20:
                    res['примеры'].append({
                        'inn': inn, 'было': cur_mail[:42], 'стало': b_mail[:42],
                        'роль': b_role[:34], 'человек': b_person[:30]})
            elif _is_generic(cur_mail) or not cur_mail:
                res['осталось_общих'] += 1
        json.dump(res, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'etp_fit':
        # ЭТП по fit-пулу новостных (владелец 25.07: «а тендерные площадки
        # смотрелись?» — по данным НЕТ, стадии etp в логе не было вовсе).
        # Карточка закупки ЕИС даёт ИМЕННОЙ контакт снабженца (ФИО+email+тел) —
        # именно то, чего не хватает пустым и общим адресам пула.
        # Резюм durable: stage_log stage='etp' (по ИНН), поэтому op можно гонять
        # порциями и перезапускать после рестарта — уже сделанные пропускаются.
        import enrich_db as _EDBe
        db = _EDBe.EnrichDB()
        inns = [str(i).strip() for i in (args.get('inns') or []) if str(i).strip()]
        if not inns:
            for r in db.cx.execute("SELECT inn, detail FROM stage_log "
                                   "WHERE stage='okved_v2'").fetchall():
                p = dict(x.split('=', 1) for x in str(r[1] or '').split(';') if '=' in x)
                if p.get('fit') == '1':
                    inns.append(str(r[0]))
            # владелец 25.07: «прогони все которые будут залиты в новостные И уже
            # в них» — добавляем действующих получателей кампаний панели
            try:
                import sqlite3 as _sq3
                _sn = _sq3.connect(r'C:\sender\sender.db')
                for r in _sn.execute("SELECT DISTINCT inn FROM recipients "
                                     "WHERE COALESCE(inn,'')<>''").fetchall():
                    if str(r[0]) not in inns:
                        inns.append(str(r[0]))
                _sn.close()
            except Exception:  # noqa: BLE001 — sender.db может быть недоступна
                pass
        done = set(r[0] for r in db.cx.execute(
            "SELECT inn FROM stage_log WHERE stage='etp'").fetchall())
        todo = [i for i in inns if i not in done][:int(args.get('limit') or 40)]
        res = {'op': 'etp_fit', 'пул': len(inns), 'уже_сделано': len(done),
               'взято': len(todo), 'с_контактом': 0, 'именных': 0, 'ошибок': 0,
               'найдено': []}
        for inn in todo:
            try:
                z = find_zakupki_contacts(inn, max_cards=int(args.get('max_cards', 3)))
            except Exception as e:  # noqa: BLE001
                res['ошибок'] += 1
                db.mark_stage(inn, 'etp', f'err={str(e)[:40]}')
                continue
            cards = (z or {}).get('cards') or []
            got_mail = got_person = 0
            for c in cards:
                if not c.get('email'):
                    continue
                got_mail += 1
                person = c.get('contact_person') or ''
                if person:
                    got_person += 1
                db.add_email(inn, c['email'].lower(),
                             role='закупки (конт. лицо)', person=person,
                             mx_ok=mx_ok(c['email']), source='zakupki:eis',
                             source_url=c.get('url') or '')
            if got_mail:
                res['с_контактом'] += 1
                if got_person:
                    res['именных'] += 1
                if len(res['найдено']) < 25:
                    res['найдено'].append({
                        'inn': inn, 'emails': [c.get('email') for c in cards if c.get('email')][:3],
                        'персона': next((c.get('contact_person') for c in cards
                                         if c.get('contact_person')), '')})
            db.mark_stage(inn, 'etp',
                          f"rss={(z or {}).get('rss_items', 0)};cards={len(cards)};"
                          f"mail={got_mail};fio={got_person}")
        res['осталось'] = len([i for i in inns if i not in done]) - len(todo)
        json.dump(res, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'zakupki_probe':
        # тест ЕИС-контактов: inns -> find_zakupki_contacts
        out = [find_zakupki_contacts(i, max_cards=int(args.get('max_cards', 3)))
               for i in (args.get('inns') or [])[:5]]
        json.dump({'op': 'zakupki_probe', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'vk_probe':
        out = []
        _vtok = _read_secret('VK_TOKEN_USER') or _read_secret('VK_TOKEN')
        for n in (args.get('names') or [])[:10]:
            row = dict(name=n, vk=find_vk_group_contacts({'name': n}))
            if args.get('debug'):
                try:
                    _nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|КАО|ГК)\s+', '', n).strip('"«» ')
                    _u = ('https://api.vk.com/method/groups.search?q=' + urllib.parse.quote(_nm)
                          + '&count=5&type=group&access_token=' + _vtok + '&v=5.199')
                    _r = _DIRECT.open(urllib.request.Request(_u, headers={'User-Agent': VC.UA}), timeout=20)
                    _d = json.loads(_r.read())
                    if 'error' in _d:
                        row['raw_err'] = _d['error'].get('error_msg', '')[:120]
                    else:
                        row['raw_groups'] = [{'name': g.get('name'), 'screen': g.get('screen_name')}
                                             for g in (_d.get('response', {}).get('items') or [])[:5]]
                except Exception as e:  # noqa: BLE001
                    row['raw_err'] = f'{type(e).__name__}: {str(e)[:100]}'
            out.append(row)
        json.dump({'op': 'vk_probe', 'token_present': bool(_vtok), 'results': out},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'hh_probe':
        # адресная hh-проверка (тест). debug=true -> сырые кандидаты-работодатели
        out = []
        for n in (args.get('names') or [])[:15]:
            row = dict(name=n, hh=find_hh_compressor({'name': n}))
            if args.get('debug'):
                try:
                    _q = urllib.parse.quote(re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО)\s+', '', n).strip('"«» '))
                    _url = 'https://api.hh.ru/employers?text=' + _q + '&only_with_vacancies=true&per_page=5'
                    # 1) прямой
                    try:
                        _rq = urllib.request.Request(_url, headers={'User-Agent': 'RuspromLeadEnrich/1.0 (kirillrand4@gmail.com)', 'Accept': 'application/json'})
                        _jd = json.loads(_DIRECT.open(_rq, timeout=15).read())
                        row['direct'] = 'ok'; row['raw_employers'] = [e.get('name') for e in (_jd.get('items') or [])]
                    except Exception as _de:  # noqa: BLE001
                        row['direct'] = f'{type(_de).__name__}: {str(_de)[:50]}'
                        # 2) дельфин
                        import browser_probe as BP
                        _dtok2 = _read_secret('DOLPHIN_TOKEN')
                        _dprofs2 = _resolve_dolphin_profiles(None, _dtok2)
                        _dpid = _dprofs2[0] if _dprofs2 else None
                        _out = BP.probe({'url': _url, 'return_html': True, 'html_cap': 100000,
                                         'wait_ms': 3500, 'screenshot': False, 'solve': True,
                                         'dolphin_profile': _dpid, 'dolphin_token': _dtok2})
                        _body = (_out.get('text') or '') + ' ' + re.sub(r'<[^>]+>', ' ', _out.get('html') or '')
                        row['dolphin_len'] = len(_body); row['dolphin_head'] = _body[:200]
                        row['dolphin_captcha'] = _out.get('captcha_type')
                        _m = re.search(r'\{.*\}', _body, re.S)
                        if _m:
                            try:
                                row['dolphin_employers'] = [e.get('name') for e in (json.loads(_m.group(0)).get('items') or [])]
                            except Exception as _je:  # noqa: BLE001
                                row['dolphin_parse_err'] = str(_je)[:60]
                except Exception as e:  # noqa: BLE001
                    row['raw_err'] = f'{type(e).__name__}: {str(e)[:120]}'
            out.append(row)
        json.dump({'op': 'hh_probe', 'results': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'resolve_test':
        # РУЧНОЙ резолв имён -> ИНН той же цепочкой, что ingest_noinn (диагностика/точечное
        # использование). args: {names:[...], no_serp:bool}
        import news_scan as NS
        _tok = _read_secret('DADATA_TOKEN')
        # сырой пробник dadata с сервера: код/тело ошибки (news_scan глотает исключения)
        raw_probe = {}
        try:
            _b = json.dumps({'query': 'Фармасинтез', 'count': 1}).encode()
            _rq = urllib.request.Request(
                'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
                data=_b, method='POST', headers={'Content-Type': 'application/json',
                'Accept': 'application/json', 'Authorization': f'Token {_tok}'})
            _resp = urllib.request.urlopen(_rq, timeout=25)
            raw_probe = {'http': _resp.status,
                         'n_sugg': len(json.loads(_resp.read()).get('suggestions') or [])}
        except urllib.error.HTTPError as e:
            raw_probe = {'http': e.code, 'body': e.read()[:200].decode('utf-8', 'replace')}
        except Exception as e:  # noqa: BLE001
            raw_probe = {'error': f'{type(e).__name__}: {str(e)[:150]}'}
        out = []
        for name in (args.get('names') or [])[:30]:
            row = {'name': name, 'token_seen': bool(_tok)}
            try:
                row['variants'] = NS._name_variants(name)
                dd = NS.dadata_suggest(name, _tok)
                if dd:
                    row.update(via='dadata', inn=dd.get('inn'), resolved=dd.get('name'),
                               conf=dd.get('confidence'))
                out.append(row)
            except Exception as e:  # noqa: BLE001
                row['error'] = f'{type(e).__name__}: {str(e)[:120]}'
                out.append(row)
        json.dump({'op': 'resolve_test', 'dadata_raw_probe': raw_probe, 'results': out},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'ingest_noinn':
        # ИНГЕСТЕР лидов БЕЗ ИНН из news_stream.jsonl (владелец: «самый большой источник
        # потерь», идея SERP-резолва — его). Цепочка: (1) dadata-варианты с расклонкой
        # (news_scan.dadata_suggest, дешёво) -> (2) SERP «"имя" ИНН» через xmlriver, регекс
        # ИНН из сниппетов справочников + чексумма + обратная верификация dadata findById
        # (матч имени — чужой ИНН не приклеим). Резолвнутые уходят в enrich.db (companies +
        # signals) = попадают в скоринг и лид-деск. Прогресс durable (.resolved-файл).
        import news_scan as NS
        ddtok = _read_secret('DADATA_TOKEN')
        _dirn = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(_dirn, args.get('stream', 'news_stream.jsonl'))
        done_path = path + '.resolved'

        def _inn_valid(inn):
            s = str(inn)
            if not s.isdigit() or len(s) not in (10, 12):
                return False
            def ctl(digs, w):
                return str(sum(int(d) * k for d, k in zip(digs, w)) % 11 % 10)
            if len(s) == 10:
                return s[9] == ctl(s, (2, 4, 10, 3, 5, 9, 4, 6, 8))
            return (s[10] == ctl(s, (7, 2, 4, 10, 3, 5, 9, 4, 6, 8))
                    and s[11] == ctl(s, (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)))

        def _serp_inn(name):
            """xmlriver Яндекс «"имя" ИНН» -> кандидаты ИНН из сниппетов (по порядку выдачи)."""
            user = os.environ.get('XMLRIVER_USER', ''); key = os.environ.get('XMLRIVER_KEY', '')
            if not (user and key):
                return []
            q = f'"{name}" ИНН'
            url = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
                   + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
                   + '&query=' + urllib.parse.quote(q))
            xml = None
            for att in range(3):
                try:
                    with _SEM_XMLRIVER:
                        xml = _DIRECT.open(url, timeout=35).read().decode('utf-8', 'replace')
                    if 'свободных каналов' in xml:
                        xml = None; time.sleep(_XMLRIVER_PAUZA); continue
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(_XMLRIVER_PAUZA)
            if not xml:
                return []
            _bump('xmlriver')
            out, seen = [], set()
            for m in re.finditer(r'ИНН\D{0,10}(\d{12}|\d{10})', xml):
                inn = m.group(1)
                if inn not in seen and _inn_valid(inn):
                    seen.add(inn); out.append(inn)
            return out

        def _dd_findbyid(inn):
            try:
                body = json.dumps({'query': str(inn)}).encode()
                req = urllib.request.Request(
                    'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
                    data=body, method='POST', headers={'Content-Type': 'application/json',
                    'Accept': 'application/json', 'Authorization': f'Token {ddtok}'})
                d = json.loads(urllib.request.urlopen(req, timeout=25).read())
                s = (d.get('suggestions') or [])
                if not s:
                    return None
                dd = s[0].get('data', {})
                return {'inn': dd.get('inn'), 'name': s[0].get('value'),
                        'okved': dd.get('okved') or '',
                        'region': ((dd.get('address') or {}).get('data') or {}).get('region'),
                        'status': (dd.get('state') or {}).get('status')}
            except Exception:  # noqa: BLE001
                return None

        done = {}
        try:
            for line in open(done_path, encoding='utf-8'):
                try:
                    j = json.loads(line); done[j['k']] = j
                except Exception:  # noqa: BLE001
                    continue
        except FileNotFoundError:
            pass
        recs = []
        try:
            for line in open(path, encoding='utf-8'):
                try:
                    r = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if not r.get('inn') and r.get('company'):
                    recs.append(r)
        except FileNotFoundError:
            json.dump({'op': 'ingest_noinn', 'error': f'нет {path}'}, sys.stdout, ensure_ascii=False)
            return
        byname = {}
        for r in recs:  # дедуп по нормализованному имени (последняя запись побеждает)
            k = re.sub(r'[^а-яёa-z0-9 ]', '', r['company'].lower()).strip()[:60]
            if k:
                byname[k] = r
        retry_un = bool(args.get('retry_unresolved', False))
        items = [(k, v) for k, v in byname.items()
                 if k not in done or (retry_un and not done[k].get('inn'))]
        cap = int(args.get('cap', 0))
        if cap:
            items = items[:cap]
        db = None
        if args.get('write_db', True):
            try:
                import enrich_db as EDB
                db = EDB.EnrichDB()
            except Exception:  # noqa: BLE001
                pass
        dfh = open(done_path, 'a', encoding='utf-8')
        resolved = 0; via_cnt = {}; samples = []; unresolved_sample = []
        _ing_lock = threading.Lock()

        def _ing_one(kv):
            nonlocal resolved
            k, r = kv
            name = r['company']
            dd = NS.dadata_suggest(name, ddtok)
            via = 'dadata' if dd else None
            if not dd and not args.get('no_serp'):
                for inn in _serp_inn(name)[:3]:
                    fb = _dd_findbyid(inn)
                    if fb and NS._match_score(name, fb['name']) >= 1:
                        dd = {**fb, 'confidence': 'serp'}
                        via = 'serp'; break
            with _ing_lock:  # БД + done-файл + счётчики под одним локом (sqlite одно соединение)
                if dd and dd.get('inn'):
                    resolved += 1
                    via_cnt[via] = via_cnt.get(via, 0) + 1
                    if db is not None:
                        try:
                            db.upsert_company(dd['inn'], name=dd.get('name') or name,
                                              division=NS.division_of(dd.get('okved') or ''),
                                              okved=dd.get('okved') or '',
                                              region=dd.get('region') or r.get('region') or '')
                            db.add_signal(dd['inn'],
                                          source=r.get('source_name') or r.get('collector') or 'news',
                                          event_type=r.get('event_type') or '', what=r.get('what') or '',
                                          sum=str(r.get('sum') or ''), source_url=r.get('source_url') or '',
                                          hotness=int(r.get('hotness') or 0), ts=r.get('published') or '')
                            for _em in _egrul_emails_by_inn(dd['inn']):
                                db.add_email(dd['inn'], _em, role='юрзначимый (ЕГРЮЛ)',
                                             source='egrul:dadata', source_url='')
                        except Exception:  # noqa: BLE001
                            pass
                    if len(samples) < 8:
                        samples.append({'company': name, 'resolved': dd.get('name'),
                                        'inn': dd['inn'], 'via': via,
                                        'conf': dd.get('confidence', '')})
                    dfh.write(json.dumps({'k': k, 'inn': dd['inn'], 'via': via},
                                         ensure_ascii=False) + '\n')
                else:
                    if len(unresolved_sample) < 10:
                        unresolved_sample.append(name[:60])
                    dfh.write(json.dumps({'k': k, 'inn': None}, ensure_ascii=False) + '\n')
                dfh.flush()

        # ПАРАЛЛЕЛЬНО (последовательно 150 имён не влезали в таймаут джобы 1800с):
        # dadata тред-безопасен, xmlriver под _SEM_XMLRIVER — каналы не переливаются.
        _iw = max(1, min(int(args.get('workers', 10)), 20))
        with ThreadPoolExecutor(max_workers=_iw) as _ex:
            list(_ex.map(_ing_one, items))
        dfh.close()
        # сводка по ВСЕМУ .resolved-файлу (включая прошлые прогоны — отчёт таймаутнутого
        # прогона теряется, а done-файл durable и хранит всю правду)
        d_tot = d_inn = 0; d_via = {}
        try:
            for line in open(done_path, encoding='utf-8'):
                try:
                    j = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                d_tot += 1
                if j.get('inn'):
                    d_inn += 1
                    d_via[j.get('via') or '?'] = d_via.get(j.get('via') or '?', 0) + 1
        except FileNotFoundError:
            pass
        json.dump({'op': 'ingest_noinn', 'stream_noinn_records': len(recs),
                   'unique_names': len(byname), 'already_done': len(byname) - len(items),
                   'processed': len(items), 'resolved': resolved, 'via': via_cnt,
                   'resolve_rate': round(resolved / len(items), 3) if items else None,
                   'samples': samples, 'unresolved_sample': unresolved_sample,
                   'done_total': {'names': d_tot, 'with_inn': d_inn, 'via': d_via,
                                  'rate': round(d_inn / d_tot, 3) if d_tot else None}},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'envcheck':
        # диагностика ключей: (a) видит ли раннер в окружении, (b) есть ли в файле
        # runner-secrets.env (владелец мог добавить, но не рестартнуть раннер). Значений НЕ показываем.
        import os as _os
        keys = ['CAPMONSTER_KEY', 'TWOCAPTCHA_KEY', 'RUCAPTCHA_KEY', 'DOLPHIN_TOKEN',
                'XMLRIVER_USER', 'XMLRIVER_KEY', 'PROVIDER_API_KEY', 'VK_TOKEN']
        in_env = {k: bool(_os.environ.get(k)) for k in keys}
        # проверяем ОБА runner-secrets.env (локальный + стабильный на дропе)
        def _parse(fp):
            out = {}
            try:
                if _os.path.exists(fp):
                    for line in open(fp, encoding='utf-8-sig'):
                        line = line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        kk, vv = line.split('=', 1)
                        out[kk.strip()] = vv.strip()
            except Exception:  # noqa: BLE001
                pass
            return out
        files = {}
        for fp in _SECRET_FILES:
            parsed = _parse(fp)
            files[fp] = {'exists': _os.path.exists(fp),
                         'keys': {k: bool(parsed.get(k) and not parsed.get(k, '').startswith('<'))
                                  for k in keys}}
        # эффективно доступно (env ИЛИ любой файл) — как реально увидит код
        effective = {k: bool(_read_secret(k)) for k in keys}
        json.dump({'op': 'envcheck', 'in_runner_env': in_env, 'files': files,
                   'effective_available': effective,
                   'note': 'effective_available=true -> код увидит ключ (даже если раннер env не подхватил)'},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'smtp_login_batch':
        # фактическая проверка SMTP-логина по списку ящиков (host 465 SSL).
        # args.boxes = [{env, login, host, pw}]. Ничего не пишет — только вердикты.
        import smtplib as _sm
        res = []
        for b in (args.get('boxes') or [])[:20]:
            v = {'env': b.get('env'), 'login': b.get('login'), 'host': b.get('host')}
            try:
                s = _sm.SMTP_SSL(b['host'], 465, timeout=25)
                s.login(b['login'], b['pw'])
                s.quit()
                v['ok'] = True
            except Exception as e:  # noqa: BLE001
                v['ok'] = False
                v['err'] = str(e)[:160]
            res.append(v)
        json.dump({'op': 'smtp_login_batch', 'results': res,
                   'ok_count': sum(1 for r in res if r['ok']),
                   'total': len(res)}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'panel_env_set':
        # обновить пароли ящиков: merge args.values в C:\sender\panel.env (бэкап рядом),
        # затем AppEnvironmentExtra службы из очищенного panel.env (одна строка,
        # \r\n-joined — ровно тот способ, что сработал 2026-07-24) + stop/start.
        import shutil as _sh
        import subprocess
        out = {'op': 'panel_env_set'}
        vals = args.get('values') or {}
        path = args.get('path') or r'C:\sender\panel.env'
        svc = args.get('service') or 'SenderPanel'
        try:
            old = []
            if os.path.exists(path):
                _sh.copy2(path, path + '.bak-' + str(int(time.time())))
                with open(path, encoding='utf-8-sig') as f:
                    old = f.read().splitlines()
            keep = [ln for ln in old
                    if not any(ln.strip().startswith(k + '=') for k in vals)]
            merged = keep + [f'{k}={v}' for k, v in vals.items()]
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(merged) + '\n')
            # чистые пары для env службы: без пустых/комментариев, значения без ' # хвостов'
            clean = []
            for ln in merged:
                ln = ln.strip()
                if not ln or ln.startswith('#') or '=' not in ln:
                    continue
                k, _, v = ln.partition('=')
                v = re.sub(r'\s+#.*$', '', v).strip()
                if k.strip() and v:
                    clean.append(f'{k.strip()}={v}')
            out['env_keys'] = [c.split('=', 1)[0] for c in clean]
            nssm = _sh.which('nssm')
            if not nssm:
                for cand in (r'C:\nssm\nssm.exe', r'C:\nssm\win64\nssm.exe',
                             r'C:\tools\nssm\nssm.exe',
                             r'C:\nssm-2.24\win64\nssm.exe'):
                    if os.path.exists(cand):
                        nssm = cand
                        break
            if not nssm:
                out['nssm'] = 'не найден — env службы НЕ обновлён, panel.env записан'
            else:
                def _n(*a):
                    p = subprocess.run([nssm, *a], capture_output=True, text=True,
                                       timeout=60)
                    return (p.returncode,
                            ((p.stdout or '') + (p.stderr or '')).replace('\x00', '').strip()[:300])
                rc, msg = _n('set', svc, 'AppEnvironmentExtra', '\r\n'.join(clean))
                out['nssm_set'] = {'rc': rc, 'msg': msg}
                if args.get('restart', True) and rc == 0:
                    _n('stop', svc)
                    time.sleep(3)
                    rc2, msg2 = _n('start', svc)
                    time.sleep(4)
                    rc3, st = _n('status', svc)
                    out['restart'] = {'start_rc': rc2, 'start_msg': msg2, 'status': st}
                rcg, envs = _n('get', svc, 'AppEnvironmentExtra')
                out['env_lines_in_service'] = len([x for x in envs.splitlines() if x.strip()])
        except Exception as e:  # noqa: BLE001
            out['error'] = repr(e)[:400]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'panel_file_put':
        # файлы панели через дроп: {files:[{drop,dest}]} — dest только под C:\sender;
        # {get: path} — прочитать файл (b64) БЕЗ записи (смотрим перед перезаписью).
        import base64 as _b64
        out = {'op': 'panel_file_put'}
        gp = args.get('get')
        if gp:
            p = str(gp)
            if not p.lower().startswith('c:\\sender') or '..' in p:
                json.dump({'error': 'путь вне C:\\sender'}, sys.stdout, ensure_ascii=False)
                return
            if not os.path.exists(p):
                json.dump({'get': p, 'exists': False}, sys.stdout, ensure_ascii=False)
                return
            with open(p, 'rb') as f:
                blob = f.read()
            json.dump({'get': p, 'exists': True, 'size': len(blob),
                       'b64': _b64.b64encode(blob).decode()[:400000]},
                      sys.stdout, ensure_ascii=False)
            return
        done, errs = [], []
        for it in (args.get('files') or []):
            dest = str(it.get('dest') or '')
            name = os.path.basename(str(it.get('drop') or ''))
            if not dest.lower().startswith('c:\\sender') or '..' in dest:
                errs.append(f'{dest}: вне C:\\sender')
                continue
            if it.get('b64'):
                # инлайн-содержимое в самом задании: БЕЗ HTTP к дропу (обходит
                # hairpin-NAT, из-за которого внешний GET рвётся на 384КБ)
                try:
                    blob = _b64.b64decode(str(it['b64']))
                    if os.path.exists(dest):
                        import shutil as _sh3
                        _sh3.copy2(dest, dest + '.bak-' + str(int(time.time())))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, 'wb') as f:
                        f.write(blob)
                    done.append(f'inline -> {dest} ({len(blob)}b)')
                except Exception as e:  # noqa: BLE001
                    errs.append(f'{dest}: inline {str(e)[:80]}')
                continue
            try:
                url = (os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
                       .rstrip('/') + '/' + name)
                req = urllib.request.Request(
                    url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
                with urllib.request.urlopen(req, timeout=90) as r:
                    blob = r.read()
                if len(blob) < 10:
                    errs.append(f'{name}: подозрительно мало ({len(blob)}b)')
                    continue
                if os.path.exists(dest):
                    import shutil as _sh2
                    _sh2.copy2(dest, dest + '.bak-' + str(int(time.time())))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as f:
                    f.write(blob)
                done.append(f'{name} -> {dest} ({len(blob)}b)')
            except Exception as e:  # noqa: BLE001
                errs.append(f'{name}: {str(e)[:80]}')
        json.dump({'op': 'panel_file_put', 'done': done, 'errors': errs,
                   'ok': not errs}, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'stage_report':
        # отчёт по логу стадий: покрытие каждой стадии + (опц.) стадии по списку ИНН.
        import enrich_db as _EDBs
        db = _EDBs.EnrichDB()
        out = {'op': 'stage_report'}
        try:
            out['по_стадиям'] = {r[0]: r[1] for r in db.cx.execute(
                "SELECT stage, COUNT(*) FROM stage_log GROUP BY stage ORDER BY 2 DESC")}
            out['ИНН_с_логом'] = db.cx.execute(
                "SELECT COUNT(DISTINCT inn) FROM stage_log").fetchone()[0]
        except Exception as e:  # noqa: BLE001
            out['error'] = str(e)[:120]
        inns = args.get('inns')
        if inns:
            out['по_инн'] = {str(i): db.stages_for(i) for i in inns[:50]}
        st = args.get('missing_stage')
        if st and inns:
            out['без_стадии_' + st] = db.stage_missing(inns, st)
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'stage_backfill':
        # ретро-заполнение stage_log из УЖЕ имеющихся колонок companies/emails —
        # чтобы прошлые прогоны (до появления лога) тоже были видны как «стадия была».
        import enrich_db as _EDBb
        db = _EDBb.EnrichDB()
        out = {'op': 'stage_backfill', 'marked': {}}
        try:
            rows = db.cx.execute(
                "SELECT inn, site, cand_site, phones, verified, activity, best_email "
                "FROM companies").fetchall()
            em_inns = {r[0] for r in db.cx.execute("SELECT DISTINCT inn FROM emails")}
            cnt = {}
            for inn, site, cand, phones, verified, activity, best in rows:
                def _m(stg, det=''):
                    db.mark_stage(inn, stg, det)
                    cnt[stg] = cnt.get(stg, 0) + 1
                if site:
                    _m('site', str(site))
                elif cand:
                    _m('site_cand', str(cand))
                if verified in ('inn', 'ogrn', 'phone', 'base+serp', 'provider'):
                    _m('verify', str(verified))
                if phones and phones not in ('[]', '', None):
                    _m('phone')
                if activity and activity not in ('н/д', '', None):
                    _m('activity')
                if inn in em_inns or best:
                    _m('email')
            out['marked'] = cnt
        except Exception as e:  # noqa: BLE001
            out['error'] = repr(e)[:200]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'resolve_leaked':
        # Пере-резолв «утёкших» лидов: события в news_stream.jsonl с компанией, но
        # без ИНН (dadata не осилил разговорное имя). Гейт владельца: принимаем ИНН
        # ТОЛЬКО если город компании (dadata-адрес) совпадает с городом события —
        # иначе легко поймать тёзку в другом регионе. Пишем найденное в enrich.db
        # (companies+signals) и в result. Резюмируемо: skip уже с ИНН.
        import glob as _glob
        _dir = os.path.dirname(os.path.abspath(__file__))
        token = _read_secret('DADATA_TOKEN')
        try:
            import news_scan as _NS
        except Exception as e:  # noqa: BLE001
            json.dump({'op': 'resolve_leaked', 'error': f'news_scan import: {e}'},
                      sys.stdout, ensure_ascii=False)
            return

        def _place_tokens(s):
            # значимые топонимы из строки региона/города (без ОПФ мест и служебных)
            s = re.sub(r'(?i)\b(область|обл\.?|край|респ\w*|округ|район|р-н|г\.\s*о\.|'
                       r'городской округ|пос\.|село|деревня|станица|г\.|город|мкр\.?)\b',
                       ' ', s or '')
            toks = re.findall(r'[А-ЯЁ][А-Яа-яё\-]{2,}', s)
            STOP = {'Кузбасс': 'Кемеров'}  # синонимы регионов
            out = set()
            for t in toks:
                out.add(t.lower())
                for k, v in STOP.items():
                    if t == k:
                        out.add(v.lower())
            return out

        def _resolve_with_city(name, ev_region):
            # dadata variants → кандидаты с городом; матч по имени + городу
            best = None
            for v in _NS._name_variants(name):
                try:
                    body = json.dumps({'query': v, 'count': 5}).encode()
                    req = urllib.request.Request(
                        'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party',
                        data=body, method='POST',
                        headers={'Content-Type': 'application/json',
                                 'Accept': 'application/json',
                                 'Authorization': f'Token {token}'})
                    d = None
                    for _att in range(3):
                        try:
                            d = json.loads(urllib.request.urlopen(req, timeout=25).read())
                            break
                        except urllib.error.HTTPError as he:
                            if he.code in (429, 500, 502, 503):
                                time.sleep(2.0 * (_att + 1)); continue
                            raise
                        except Exception:  # noqa: BLE001
                            time.sleep(1.0 * (_att + 1))
                    if not d:
                        continue
                    for s in (d.get('suggestions') or []):
                        data = s.get('data', {}) or {}
                        addr = (data.get('address') or {}).get('data') or {}
                        comp_place = ' '.join(str(addr.get(k) or '') for k in
                                              ('city', 'settlement', 'region', 'area'))
                        name_sc = _NS._match_score(name, s.get('value') or '')
                        ev_tok = _place_tokens(ev_region)
                        comp_tok = _place_tokens(comp_place)
                        city_ok = bool(ev_tok & comp_tok)
                        # балл: имя + бонус за город; без города события — только имя
                        score = name_sc + (2 if city_ok else 0)
                        cand = {'inn': data.get('inn'), 'okved': data.get('okved') or '',
                                'name': s.get('value'), 'city_ok': city_ok,
                                'name_sc': name_sc, 'comp_place': comp_place.strip(),
                                'status': (data.get('state') or {}).get('status'),
                                'egrul_emails': [e.get('value') for e in (data.get('emails') or [])
                                                 if isinstance(e, dict) and e.get('value')][:3]}
                        if best is None or score > best[0]:
                            best = (score, cand)
                except Exception:  # noqa: BLE001
                    continue
            return best

        files = sorted(set(_glob.glob(os.path.join(_dir, 'news_stream*.jsonl'))
                           + _glob.glob(os.path.join(_dir, '*stream_news*.jsonl'))))
        seen_company = {}
        for fp in files:
            try:
                with open(fp, encoding='utf-8', errors='replace') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            r = json.loads(line)
                        except Exception:  # noqa: BLE001
                            continue
                        if not r.get('is_capex') or r.get('inn'):
                            continue
                        comp = (r.get('company') or '').strip()
                        if not comp:
                            continue
                        # берём запись с самым информативным регионом
                        prev = seen_company.get(comp)
                        if prev is None or (not prev.get('region') and r.get('region')):
                            seen_company[comp] = r
            except Exception:  # noqa: BLE001
                continue

        targets = list(seen_company.items())
        limit = int(args.get('limit', 0)) or len(targets)
        offset = int(args.get('offset', 0))
        batch = targets[offset:offset + limit]
        try:
            import enrich_db as _EDBl
            db = _EDBl.EnrichDB()
        except Exception:  # noqa: BLE001
            db = None
        recovered, city_reject, no_match = [], [], []
        require_city = bool(args.get('require_city', True))
        for comp, r in batch:
            ev_region = r.get('region') or ''
            res = _resolve_with_city(comp, ev_region)
            if not res or not res[1].get('inn') or res[1]['name_sc'] < 1:
                no_match.append(comp)
                continue
            cand = res[1]
            # гейт города: если у события есть регион — требуем совпадение
            if require_city and ev_region.strip() and not cand['city_ok']:
                city_reject.append({'company': comp, 'ev_region': ev_region,
                                    'comp_place': cand['comp_place'], 'inn': cand['inn']})
                continue
            rec = {'company': comp, 'inn': cand['inn'], 'okved': cand['okved'],
                   'name': cand['name'], 'ev_region': ev_region,
                   'comp_place': cand['comp_place'], 'city_ok': cand['city_ok'],
                   'name_sc': cand['name_sc'], 'what': r.get('what'),
                   'source_url': r.get('source_url'), 'hotness': r.get('hotness'),
                   'egrul_emails': cand['egrul_emails']}
            recovered.append(rec)
            if db is not None and cand['inn']:
                try:
                    try:
                        div, _b = _EDBl.division_for_okveds(cand['okved'], None)
                    except Exception:  # noqa: BLE001
                        div = None
                    db.upsert_company(cand['inn'], name=cand['name'], division=div,
                                      okved=cand['okved'], region=ev_region or None)
                    _w = (r.get('what') or '')
                    db.add_signal(cand['inn'], source=r.get('source_name') or 'news:releaked',
                                  event_type=r.get('event_type') or '', what=_w,
                                  sum=str(r.get('sum') or ''),
                                  source_url=r.get('source_url') or '',
                                  hotness=int(r.get('hotness') or 0), ts=r.get('published') or '')
                    for em in cand['egrul_emails']:
                        db.add_email(cand['inn'], em, role='юрзначимый (ЕГРЮЛ)',
                                     source='egrul:dadata-releak', source_url='')
                    db.mark_stage(cand['inn'], 'releak_resolve',
                                  f"city_ok={cand['city_ok']} sc={cand['name_sc']}")
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(0.4)
        json.dump({'op': 'resolve_leaked', 'уник_компаний': len(targets),
                   'обработано': len(batch), 'offset': offset,
                   'восстановлено': len(recovered),
                   'отклонено_по_городу': len(city_reject),
                   'не_нашлось': len(no_match),
                   'recovered_sample': recovered[:20],
                   'city_reject_sample': city_reject[:10]},
                  sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'panel_zip_deploy':
        # деплой panel-update.zip с дропа: стоп SenderPanel → распаковка в
        # C:\sender (поверх) → старт → svc_probe. Бэкап sender/ и web/dist перед.
        import shutil as _sh
        import subprocess
        import zipfile as _zip
        out = {'op': 'panel_zip_deploy'}
        name = os.path.basename(str(args.get('zip') or 'panel-update.zip'))
        svc = args.get('service') or 'SenderPanel'
        nssm = _sh.which('nssm')
        if not nssm:
            for cand in (r'C:\nssm\nssm.exe', r'C:\nssm\win64\nssm.exe',
                         r'C:\tools\nssm\nssm.exe', r'C:\nssm-2.24\win64\nssm.exe'):
                if os.path.exists(cand):
                    nssm = cand
                    break
        def _n(*a):
            p = subprocess.run([nssm, *a], capture_output=True, timeout=90)
            raw = (p.stdout or b'') + (p.stderr or b'')
            try:
                t = raw.decode('utf-16-le') if b'\x00' in raw[:8] else raw.decode('utf-8', 'replace')
            except Exception:  # noqa: BLE001
                t = raw.decode('utf-8', 'replace')
            return p.returncode, t.strip()[:200]
        try:
            url = (os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
                   .rstrip('/') + '/' + name)
            req = urllib.request.Request(
                url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
            zpath = os.path.join(r'C:\sender', name)
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
            with open(zpath, 'wb') as f:
                f.write(blob)
            out['zip_bytes'] = len(blob)
            if not _zip.is_zipfile(zpath):
                out['error'] = 'скачанный файл не zip'
                json.dump(out, sys.stdout, ensure_ascii=False)
                return
            ts = str(int(time.time()))
            for sub in ('sender', os.path.join('web', 'dist')):
                src = os.path.join(r'C:\sender', sub)
                if os.path.exists(src):
                    bak = os.path.join(r'C:\sender', '_bak-' + ts,
                                       sub.replace(os.sep, '_'))
                    os.makedirs(os.path.dirname(bak), exist_ok=True)
                    _sh.copytree(src, bak)
            out['backup'] = '_bak-' + ts
            if _sh.which('nssm') or nssm:
                out['stop'] = _n('stop', svc)
            time.sleep(3)
            with _zip.ZipFile(zpath) as z:
                names = z.namelist()
                for nm in names:
                    if '..' in nm or nm.startswith(('/', '\\')):
                        out['error'] = f'подозрительный путь в zip: {nm}'
                        json.dump(out, sys.stdout, ensure_ascii=False)
                        return
                z.extractall(r'C:\sender')
            out['extracted'] = len(names)
            if nssm:
                _n('start', svc)
            time.sleep(5)
            if nssm:
                out['status'] = _n('status', svc)[1]
            try:
                req2 = urllib.request.Request('http://127.0.0.1:8091/', method='GET')
                with urllib.request.urlopen(req2, timeout=10) as r:
                    out['http'] = r.status
            except Exception as e:  # noqa: BLE001
                out['http'] = str(e)[:80]  # 403 = панель жива (нужен auth)
        except Exception as e:  # noqa: BLE001
            out['error'] = repr(e)[:400]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'panel_py':
        # запустить скрипт питоном ПАНЕЛИ (3.11) в C:\sender с env из panel.env —
        # тот же интерпретатор/пакет sender, что у службы. Для тиков/E2E-скриптов.
        import subprocess
        out = {'op': 'panel_py'}
        script = str(args.get('script') or '')
        if not script.lower().startswith('c:\\sender') or '..' in script:
            json.dump({'error': 'скрипт должен лежать под C:\\sender'},
                      sys.stdout, ensure_ascii=False)
            return
        env = dict(os.environ)
        pep = r'C:\sender\panel.env'
        if os.path.exists(pep):
            with open(pep, encoding='utf-8-sig') as f:
                for ln in f.read().splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith('#') and '=' in ln:
                        k, _, v = ln.partition('=')
                        v = re.sub(r'\s+#.*$', '', v).strip()
                        if k.strip() and v:
                            env[k.strip()] = v
        py = r'C:\Program Files\Python311\python.exe'
        if not os.path.exists(py):
            py = sys.executable
        try:
            p = subprocess.run([py, script, *[str(a) for a in (args.get('argv') or [])]],
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace', cwd=r'C:\sender', env=env,
                               timeout=int(args.get('timeout', 900)))
            out.update({'rc': p.returncode, 'stdout_tail': (p.stdout or '')[-6000:],
                        'stderr_tail': (p.stderr or '')[-3000:]})
        except Exception as e:  # noqa: BLE001
            out['error'] = repr(e)[:300]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'svc_probe':
        # диагностика службы панели: статус, ключи env (без значений), panel.env,
        # HTTP панели, хвост stderr-лога; при STOPPED — повторный старт и статус.
        import shutil as _sh
        import subprocess
        out = {'op': 'svc_probe'}
        svc = args.get('service') or 'SenderPanel'
        nssm = _sh.which('nssm')
        if not nssm:
            for cand in (r'C:\nssm\nssm.exe', r'C:\nssm\win64\nssm.exe',
                         r'C:\tools\nssm\nssm.exe', r'C:\nssm-2.24\win64\nssm.exe'):
                if os.path.exists(cand):
                    nssm = cand
                    break
        def _nb(*a):
            # nssm пишет UTF-16LE — декодируем сами из байтов
            p = subprocess.run([nssm, *a], capture_output=True, timeout=60)
            raw = (p.stdout or b'') + (p.stderr or b'')
            try:
                txt = raw.decode('utf-16-le') if b'\x00' in raw[:8] else raw.decode('utf-8', 'replace')
            except Exception:  # noqa: BLE001
                txt = raw.decode('utf-8', 'replace')
            return p.returncode, txt.strip()
        try:
            _, st = _nb('status', svc)
            out['status'] = st[:60]
            _, envs = _nb('get', svc, 'AppEnvironmentExtra')
            lines = [x for x in envs.replace('\r', '\n').split('\n') if x.strip()]
            out['env_in_service'] = {'count': len(lines),
                                     'keys': [x.split('=', 1)[0] for x in lines if '=' in x]}
            pep = args.get('panel_env_path') or r'C:\sender\panel.env'
            if os.path.exists(pep):
                with open(pep, encoding='utf-8-sig') as f:
                    kv = [ln.partition('=') for ln in f.read().splitlines()
                          if ln.strip() and not ln.strip().startswith('#') and '=' in ln]
                out['panel_env'] = {'count': len(kv),
                                    'keys': [(k.strip(), len(v.strip())) for k, _, v in kv]}
            for p in ('AppStdout', 'AppStderr', 'Application', 'AppParameters', 'AppDirectory'):
                _, v = _nb('get', svc, p)
                out.setdefault('nssm_params', {})[p] = v[:200]
            logp = out.get('nssm_params', {}).get('AppStderr', '')
            if logp and os.path.exists(logp):
                with open(logp, 'rb') as f:
                    f.seek(max(0, os.path.getsize(logp) - 6000))
                    out['stderr_tail'] = f.read().decode('utf-8', 'replace')[-3000:]
            if 'STOPPED' in out['status'] and args.get('try_start', True):
                _nb('start', svc)
                time.sleep(10)
                _, st2 = _nb('status', svc)
                out['status_after_start'] = st2[:60]
            try:
                req = urllib.request.Request('http://127.0.0.1:8091/', method='GET')
                with urllib.request.urlopen(req, timeout=10) as r:
                    out['http'] = {'code': r.status, 'len': len(r.read())}
            except Exception as e:  # noqa: BLE001
                out['http'] = {'error': str(e)[:120]}
        except Exception as e:  # noqa: BLE001
            out['error'] = repr(e)[:400]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('op') == 'smtp_selftest':
        # self-тест реальной отправки через движок панели (ящики s1/s2). Пишет письмо
        # ОДНОГО ящика ДРУГОМУ через Sender.send_reply(live=True) — тот же путь, что
        # ручная отправка в вебе. Гоняется из песочницы через runner (env сервера).
        out = {'op': 'smtp_selftest'}
        try:
            sys.path.insert(0, r'C:\sender')
            import os as _os
            _os.chdir(r'C:\sender')
            # пароли ящиков можно передать прямо в джобе (args.pw = {env_name: пароль}) —
            # подставляем в окружение процесса ДО валидации конфига. Так тест-цикл
            # закрывается без правки env службы. Тестовые ящики; джоб чистим с дропа.
            for _k, _v in (args.get('pw') or {}).items():
                if _k and _v:
                    _os.environ[str(_k)] = str(_v)
            if args.get('pw_from_panel_env'):
                # пароли из C:\sender\panel.env — тест ровно того, что записано службе
                _pep = args.get('panel_env_path') or r'C:\sender\panel.env'
                if os.path.exists(_pep):
                    with open(_pep, encoding='utf-8-sig') as _f:
                        for _ln in _f.read().splitlines():
                            _ln = _ln.strip()
                            if _ln and not _ln.startswith('#') and '=' in _ln:
                                _k, _, _v = _ln.partition('=')
                                _v = re.sub(r'\s+#.*$', '', _v).strip()
                                if _k.strip() and _v:
                                    _os.environ[_k.strip()] = _v
            from sender.config import Config as _Cfg
            from sender.store import Store as _St
            from sender.wiring import build_deps as _bd
            cfg = _Cfg.load(_os.getenv('SENDER_CONFIG', './sender.yaml'), env=_os.environ)
            st = _St(cfg.get('service.db_path', 'sender.db')); st.init_schema()
            try:
                cfg.load_mailbox_overrides(st)
            except Exception:  # noqa: BLE001
                pass
            mbs = cfg.mailboxes()
            out['mailboxes'] = [{'id': m.mailbox_id, 'smtp': f'{m.smtp_host}:{m.smtp_port}',
                                 'login': m.login, 'env': m.password_env,
                                 'pw_set': bool(_os.environ.get(m.password_env))} for m in mbs]
            frm = args.get('from') or next((m.mailbox_id for m in mbs
                                            if m.mailbox_id.startswith('s1@')), None)
            to = args.get('to') or next((m.mailbox_id for m in mbs
                                         if m.mailbox_id.startswith('s2@')), None)
            if frm and to:
                deps = _bd(cfg, st)
                res = deps.sender.send_reply(mailbox_id=frm, to_email=to,
                    subject=args.get('subject', 'selftest'),
                    body=args.get('body', 'Проверка реальной отправки. ООО «Руспром»'), live=True)
                out.update({'sent': True, 'from': frm, 'to': to,
                            'dry_run': res.dry_run, 'msgid': res.rfc_message_id})
            else:
                out['sent'] = False; out['error'] = 'нет s1/s2 среди ящиков'
        except Exception as e:  # noqa: BLE001
            out['sent'] = False; out['error'] = repr(e)[:400]
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
    if args.get('read_stream'):
        # вернуть записи из jsonl на сервере (для оффлайн модель-сравнения на крауленных текстах)
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          os.path.basename(str(args['read_stream'])))
        recs, lim = [], int(args.get('limit', 200))
        try:
            with open(fp, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        recs.append(json.loads(line))
                    except Exception:  # noqa: BLE001
                        continue
                    if len(recs) >= lim:
                        break
        except Exception as e:  # noqa: BLE001
            json.dump({'error': f'read-fail:{str(e)[:80]}', 'path': fp}, sys.stdout, ensure_ascii=False)
            return
        json.dump({'records': recs, 'count': len(recs)}, sys.stdout, ensure_ascii=False)
        return
    if args.get('base_cities'):
        # ВСЕ уникальные населённые пункты из юрадресов базы [9] (формат ЕГРЮЛ:
        # «443058, Самарская область, г. о. Самара, г. Самара, ул. Физкультурная, ...»).
        # Токенизируем по запятым; маркеры типов НП; «г. о.» (гор. округ), «с. п.» (сельское
        # поселение), «м. о.» (мун. округ) — НЕ населённые пункты, исключаем. Берём ПОСЛЕДНИЙ
        # маркер-совпадение (самый специфичный: город идёт до улицы, деревня — после района).
        import csv
        p = _get_base()
        if not p:
            json.dump({'error': 'база не найдена'}, sys.stdout, ensure_ascii=False)
            return
        ADDR, REG = 9, 10
        try:
            csv.field_size_limit(2 ** 18)
        except Exception:  # noqa: BLE001
            pass
        MARKERS = [  # (тип, regex по токену)
            ('г', re.compile(r'^(?:г\.|город)\s*(?!о\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('пгт', re.compile(r'^(?:пгт\.?|п\.\s*г\.\s*т\.?)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('рп', re.compile(r'^рп\.?\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('с', re.compile(r'^(?:с\.|село)\s*(?!п\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('п', re.compile(r'^(?:п\.|пос\.|посёлок|поселок)\s*(?!г\.)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('д', re.compile(r'^(?:д\.|дер\.|деревня)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('х', re.compile(r'^(?:х\.|хутор)\s*([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('ст-ца', re.compile(r'^(?:ст-ца|станица)\s+([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
            ('аул', re.compile(r'^аул\s+([А-ЯЁ][А-Яа-яЁё\- ]{1,40})$')),
        ]
        seen = {}
        scanned = parsed = 0
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = csv.reader(f, delimiter=';')
            next(rd, None)
            while True:
                try:
                    row = next(rd)
                except StopIteration:
                    break
                except Exception:  # noqa: BLE001
                    continue
                scanned += 1
                if len(row) <= REG:
                    continue
                addr = (row[ADDR] or '')
                reg = (row[REG] or '').strip()
                hit = None
                for tok in (t.strip() for t in addr.split(',')):
                    tok = re.sub(r'\s+', ' ', tok)
                    for typ, rx in MARKERS:
                        m = rx.match(tok)
                        if m:
                            hit = (typ, m.group(1).strip())
                for_typ_city = hit
                if for_typ_city:
                    parsed += 1
                    typ, city = for_typ_city
                    k = (city, reg)
                    if k in seen:
                        seen[k]['n'] += 1
                    else:
                        seen[k] = {'city': city, 'type': typ, 'region': reg, 'n': 1}
        out = sorted(seen.values(), key=lambda x: -x['n'])
        json.dump({'scanned': scanned, 'with_settlement': parsed, 'unique': len(out),
                   'settlements': out}, sys.stdout, ensure_ascii=False)
        return
    if args.get('base_peek'):
        json.dump(_base_peek(int(args.get('n', 3))), sys.stdout, ensure_ascii=False)
        return
    if args.get('base_pick'):
        json.dump(_base_pick(no_site=args.get('no_site', True),
                             size_col=args.get('size_col'), limit=int(args.get('limit', 500)),
                             okved_prefixes=set(args['okved_prefixes']) if args.get('okved_prefixes') else None),
                  sys.stdout, ensure_ascii=False)
        return
    companies = args.get('companies', [])
    # СПИСОК ИЗ ФАЙЛА НА СЕРВЕРЕ (12.08). Задание уходит раннеру через дроп, и
    # тысяча компаний в теле задания — это сотни килобайт по хайрпин-NAT, который
    # рвётся на 384КБ. Кладём список на сервер один раз и передаём путь: задание
    # остаётся крошечным, а список переживает перезапуск раннера.
    if not companies and args.get('companies_file'):
        try:
            with open(args['companies_file'], encoding='utf-8') as _cf:
                companies = json.load(_cf)
        except Exception as _ce:  # noqa: BLE001
            json.dump({'error': 'companies_file: %s' % str(_ce)[:120]},
                      sys.stdout, ensure_ascii=False)
            return
    # РЕЗЮМИРУЕМОСТЬ списка компаний (автономная ночь: раннер перезапускается на бэр-python,
    # длинный джоб иначе переобрабатывается с нуля). resume=true -> пропускаем ИНН, уже
    # сделанные в stream_file (по _done_inns). Так рестарт продолжает, а не дублирует.
    if companies and args.get('resume'):
        try:
            import glob as _rg
            _sf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               args.get('stream_file', 'enrich_stream.jsonl'))
            _done = set()
            _attempts = {}   # ИНН -> сколько раз уже писался в поток (для кап-исчерпания)
            _max_att = int(args.get('max_attempts', 3))   # безрезультатных попыток на ИНН
            for _fp in _rg.glob(_sf) + _rg.glob(_sf.rsplit('.', 1)[0] + '*.jsonl'):
                try:
                    for _ln in open(_fp, encoding='utf-8'):
                        try:
                            _j = json.loads(_ln)
                            _inn = str(_j.get('inn') or '')
                            if not _inn:
                                continue
                            _attempts[_inn] = _attempts.get(_inn, 0) + 1
                            # regex-provider-fail НЕ done: провайдер падал (транспорт до
                            # фикса 2026-07-24), контакты без ролей → переобработать.
                            # Более поздняя provider-запись перекроет и добавит в done.
                            if _j.get('extract') == 'regex-provider-fail':
                                _done.discard(_inn)
                                continue
                            # сделано = есть email ИЛИ verified ИЛИ явный «нет контактов» без ошибки-транзиента
                            if (_j.get('emails') or _j.get('best_for_outreach')
                                    or _j.get('verified') or _j.get('method') == 'ok'):
                                _done.add(_inn)
                        except Exception:  # noqa: BLE001
                            continue
                except Exception:  # noqa: BLE001
                    continue
            # КАП ПОПЫТОК (урок ночи: раннер падал и переисполнял job → компании-без-email
            # перекрауливались каждый проход бесконечно, жгли xmlriver). Исчерпавшие лимит —
            # в skip наравне с готовыми: цепочка сходится, а не крутится на «сайт не найден».
            _exhausted = {i for i, c in _attempts.items() if c >= _max_att and i not in _done}
            _skip = _done | _exhausted
            _before = len(companies)
            companies = [c for c in companies if str(c.get('inn') or '') not in _skip]
            sys.stderr.write(f'resume: было {_before}, к обработке {len(companies)} '
                             f'(done {len(_done)}, исчерпано {len(_exhausted)})\n')
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass
    # МАССОВЫЙ прогон по базе (финальная задача: xmlriver-поиск сайта + выгрузка контактов
    # для ВСЕЙ базы без сайта). Резюмируемо: пропускаем уже сделанные ИНН (из jsonl). Берём
    # по убыванию выручки (лучшие лиды первыми). cap>0 — ограничить пачку (валидация/бюджет).
    if args.get('mass_base'):
        _dirm = os.path.dirname(os.path.abspath(__file__))
        done = _done_inns(_dirm)
        allc = _base_pick(no_site=args.get('no_site', True), size_col=args.get('size_col'),
                          limit=10 ** 9,
                          okved_prefixes=set(args['okved_prefixes']) if args.get('okved_prefixes') else None)
        pool = allc.get('companies', []) if isinstance(allc, dict) else []
        todo = [c for c in pool if str(c.get('inn') or '') not in done]
        cap = int(args.get('cap', 0))
        if cap > 0:
            todo = todo[:cap]
        companies = todo
        # САМОЧЕЙНИНГ: если есть работа и chain=True — сразу пишем следующий job на дроп (в
        # начале, чтобы пережить таймаут раннера). Раннер серийный → преемник запустится после
        # этого чанка, его done-set уже включит наши ИНН. Пустой пул → чейна нет → стоп.
        if args.get('chain') and companies:
            ch = _chain_next(args)
            sys.stderr.write(f'chain-next: {ch}\n')
        sys.stderr.write(f'mass_base: no-site всего={len(pool)}, done={len(done)}, '
                         f'к обработке={len(companies)} (cap={cap or "нет"})\n')
        sys.stderr.flush()
    # НОВОСТНЫЕ КОМПАНИИ: контакты для компаний с новостным сигналом. Владелец: новостные лиды
    # ценные → обогащаем ПОЛНОСТЬЮ (xmlriver + все фолбэки + браузер, «всё что можно»), не
    # ограничиваясь известным сайтом [20]; базовый сайт — лишь последний фолбэк (base_site). ГЕЙТ
    # уточнён: пропускаем только тех, у кого уже есть ПОДТВЕРЖДЁННЫЙ контакт; «сходили-пусто» по
    # горячему сигналу перепробуем (кап попыток). Резюмируемо + чейнинг. По умолчанию ВЫКЛ.
    if args.get('news_enrich'):
        import glob as _glob
        _dirm = os.path.dirname(os.path.abspath(__file__))
        _NEWS_RETRY = int(args.get('news_retry', 2))   # перепробовать «пустые» не более N раз
        verified, all_inns = set(), []
        try:
            import enrich_db as EDB
            _cx = EDB.EnrichDB().cx
            all_inns = [r[0] for r in _cx.execute(
                "SELECT DISTINCT inn FROM signals WHERE inn!='' AND inn IS NOT NULL").fetchall()]
            # «обогащён» = есть ПОДТВЕРЖДЁННЫЙ контакт (verified ∈ {inn,ogrn,phone,provider} + email)
            verified = {r[0] for r in _cx.execute(
                "SELECT DISTINCT c.inn FROM companies c JOIN emails e ON e.inn=c.inn "
                "WHERE c.verified IN ('inn','ogrn','phone','provider')").fetchall()}
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'news_enrich: db err {str(e)[:80]}\n')
        # счётчик попыток по ИНН из новостного потока — «пустые» перепроверяем, но с капом
        # (иначе цепочка зациклится на компаниях без email). Поток тот же, что пишет main().
        _pref = args.get('stream_file', 'enrich_stream.jsonl').rsplit('.', 1)[0]
        attempts = {}
        for fp in _glob.glob(os.path.join(_dirm, _pref + '*.jsonl')):
            try:
                with open(fp, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            _inn = str(json.loads(line).get('inn') or '')
                        except Exception:  # noqa: BLE001
                            continue
                        if _inn:
                            attempts[_inn] = attempts.get(_inn, 0) + 1
            except Exception:  # noqa: BLE001
                pass
        exhausted = {i for i, c in attempts.items() if c >= _NEWS_RETRY}
        skip = verified | exhausted
        todo_inns = [i for i in all_inns if str(i) not in skip]
        idx = _base_index(set(str(i) for i in todo_inns))
        # обогащаем полностью через xmlriver: сайт из базы [20] НЕ ставим в site (иначе краул
        # пойдёт по нему без xmlriver), а кладём в base_site как последний фолбэк. city/phones —
        # для xmlriver-запроса и верификации сайта.
        # имя/регион из enrich.db — фолбэк для новостных компаний ВНЕ базы обзвона
        # (например, спасённые ингестером): без имени xmlriver-запрос сломан
        db_names = {}
        try:
            for r_ in _cx.execute('SELECT inn,name,region FROM companies').fetchall():
                db_names[str(r_[0])] = (r_[1] or '', r_[2] or '')
        except Exception:  # noqa: BLE001
            pass
        companies = []
        for i in todo_inns:
            bi = idx.get(str(i), {})
            nm = bi.get('name', '') or db_names.get(str(i), ('', ''))[0]
            ct = bi.get('city', '') or db_names.get(str(i), ('', ''))[1]
            companies.append(dict(inn=str(i), name=nm, city=ct,
                                  phones=bi.get('phones', []), base_site=bi.get('site', '')))
        companies = [c for c in companies if c['name']]   # без имени обогащать нечем
        cap = int(args.get('cap', 0))
        if cap > 0:
            companies = companies[:cap]
        if args.get('chain') and companies:
            sys.stderr.write(f'chain-next: {_chain_next(args)}\n')
        sys.stderr.write(f'news_enrich: сигналов-ИНН={len(all_inns)}, verified-skip={len(verified)}, '
                         f'retry-исчерпано={len(exhausted)}, к обработке={len(companies)}\n')
        sys.stderr.flush()
    # диагностика карточки Яндекса: сырой блок knowledge_graph для проверки полей (есть ли
    # email/сайт/телефон). Не тратит provider/браузер — только xmlriver по компании.
    if args.get('kg_probe'):
        out = []
        for c in companies[:8]:
            site, src, card = find_site_via_xmlriver(c)
            row = {'name': c.get('name'), 'site': site, 'src': src, 'card': card}
            try:
                user = os.environ.get('XMLRIVER_USER', ''); key = os.environ.get('XMLRIVER_KEY', '')
                nm = re.sub(r'^(ООО|АО|ЗАО|ПАО|ОАО|ИП|ПО)\s+', '', c.get('name', '')).strip().strip('"«»')
                q = f'{nm} {c.get("city", "")} официальный сайт'.strip()
                u = ('http://xmlriver.com/search_yandex/xml?user=' + urllib.parse.quote(user)
                     + '&key=' + urllib.parse.quote(key) + '&domain=ru&device=desktop'
                     + '&additional=knowledge_graph_y&query=' + urllib.parse.quote(q))
                xml = _DIRECT.open(u, timeout=35).read().decode('utf-8', 'replace')
                mm = re.search(r'<knowledge_graph\b.*?</knowledge_graph>', xml, re.S)
                row['raw_kg'] = mm.group(0)[:2000] if mm else None
            except Exception as e:  # noqa: BLE001
                row['raw_err'] = str(e)[:60]
            out.append(row)
        json.dump({'kg_probe': out, 'cost': dict(_COST)}, sys.stdout, ensure_ascii=False)
        return
    pace = (float(args.get('pace_min', 6.0)), float(args.get('pace_max', 14.0)))
    workers = max(1, min(int(args.get('workers', 6)), 80))  # прямой HTTP лёгкий → потолок выше
    # управление параллелизмом (сервер мощный → можно поднять)
    global _NO_BROWSER, _SEM_BROWSER, _USE_FALLBACK, _RETURN_TEXT, _SKIP_PROVIDER
    global _DOLPHIN_TOKEN, _DOLPHIN_PROFILES, _SEM_XMLRIVER
    # число каналов xmlriver управляемо из args (env XMLRIVER_CHANNELS не долетает до сервера)
    if args.get('channels'):
        _SEM_XMLRIVER = threading.Semaphore(max(1, int(args['channels'])))
    # МОДЕЛЬ extract_roles: массовый вал → haiku (9× дешевле, ~90%, проверено); иначе fable.
    VC._PROVIDER_MODEL = args.get('extract_model') or (
        'claude-haiku-4-5' if (args.get('mass_base') or args.get('news_enrich')) else 'claude-fable-5')
    # таймаут краул-fetch: мёртвые сайты не держат воркер по 45-90с (массовый прогон)
    if args.get('fetch_timeout'):
        VC._FETCH_TIMEOUT = int(args['fetch_timeout'])
    # КАНАЛ ПРОКСИ на весь прогон: 'mobile' — первым идёт мобильный адрес
    # (переобход того, что датацентр не пробил), 'massa' — обычные 78.
    # Ставим через окружение процесса: kanal() читает его как умолчание, значит
    # канал достаётся ВСЕМ рабочим потокам, а не только главному.
    if args.get('proxy_kanal'):
        os.environ['PROXY_KANAL'] = str(args['proxy_kanal'])
    _NO_BROWSER = bool(args.get('no_browser', False))
    _USE_FALLBACK = not bool(args.get('no_fallback', False))
    _RETURN_TEXT = bool(args.get('return_text', False))
    _SKIP_PROVIDER = bool(args.get('skip_provider', False))
    globals()['_NO_STAFF_SEARCH'] = bool(args.get('no_staff_search', False))
    globals()['_NO_DIR_LOOKUP'] = bool(args.get('no_dir_lookup', False))
    globals()['_OPO_CHECK'] = bool(args.get('opo_check', False))
    globals()['_DISCOVERY_ONLY'] = bool(args.get('discovery_only', False))
    globals()['_HH_CHECK'] = bool(args.get('hh_check', False))
    globals()['_NO_SITE_CACHE'] = bool(args.get('no_site_cache', False))
    globals()['_NO_SITE_CONFIRM'] = bool(args.get('no_site_confirm', False))
    globals()['_NO_REKV_SEARCH'] = bool(args.get('no_rekv_search', False))
    globals()['_NO_VK_LOOKUP'] = bool(args.get('no_vk_lookup', False))
    globals()['_ZAKUPKI_CHECK'] = bool(args.get('zakupki_check', False))
    globals()['_SMTP_CHECK'] = bool(args.get('smtp_check', False))
    if args.get('site_cache_days'):
        globals()['_SITE_CACHE_DAYS'] = int(args['site_cache_days'])
    # токен — из args ИЛИ env ИЛИ любого runner-secrets.env (устойчиво к удалению локального
    # файла: есть стабильная копия на дропе). Профили пока только из args.
    _DOLPHIN_TOKEN = args.get('dolphin_token', '') or _read_secret('DOLPHIN_TOKEN')
    _DOLPHIN_PROFILES = _resolve_dolphin_profiles(args.get('dolphin_profiles'), _DOLPHIN_TOKEN)
    bw = max(1, min(int(args.get('browser_workers', 2)), 30))
    _SEM_BROWSER = threading.Semaphore(bw)

    # ИНКРЕМЕНТАЛЬНАЯ запись в ДВА места разными способами (переживает таймаут/рестарт;
    # если один файл побьётся — второй цел): (1) enrich.db SQLite/WAL, (2) enrich_stream.jsonl
    # append-only (битая строка не рушит остальные; из него восстановима БД). Пишем СРАЗУ
    # по готовности компании, а не в конце.
    _wr = bool(args.get('write_db', True))
    _db = None
    _jsonl = None
    _wlock = threading.Lock()
    _dir = os.path.dirname(os.path.abspath(__file__))
    if _wr:
        try:
            import enrich_db as EDB
            _db = EDB.EnrichDB()
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'enrich_db init skip: {str(e)[:100]}\n')
        try:
            _jsonl = open(os.path.join(_dir, args.get('stream_file', 'enrich_stream.jsonl')),
                          'a', encoding='utf-8')
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'jsonl init skip: {str(e)[:100]}\n')
    cin = {str(c.get('inn')): c for c in companies if c.get('inn')}

    def _persist(r):
        inn = str(r.get('inn') or '')
        if not inn or not _wr:
            return
        src = cin.get(inn, {})
        with _wlock:
            # (1) JSONL — максимально устойчивый: append + flush + fsync
            if _jsonl is not None:
                try:
                    rec = dict(r)
                    rec['_okved'] = src.get('okved')
                    rec['_src'] = args.get('source') or 'enrich'
                    _jsonl.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    _jsonl.flush()
                    try:
                        os.fsync(_jsonl.fileno())
                    except Exception:  # noqa: BLE001
                        pass
                except Exception:  # noqa: BLE001
                    pass
            # (2) SQLite — структурированное, идемпотентно по ИНН
            if _db is not None:
                try:
                    # направление по ТОЧНОМУ маппингу владельца (основной [16] + ВСЕ доп [17])
                    div = src.get('division') or args.get('division')
                    if not div:
                        try:
                            import enrich_db as _E
                            div, _bud = _E.division_for_okveds(src.get('okved'), src.get('okved_all'))
                        except Exception:  # noqa: BLE001
                            div = None
                    # сайт: подтверждённый → site; неподтверждённый → cand_site (в базе для
                    # ручной сверки, но не как настоящий); mismatch → не пишем. И НЕ ТРОГАЕМ, если
                    # у компании уже есть положительный verified (не затираем подтверждённое).
                    _ver = r.get('verified'); _sv = r.get('site')
                    _conf = _ver in ('inn', 'ogrn', 'phone', 'base+serp', 'provider')
                    _ex = _db.cx.execute('SELECT verified FROM companies WHERE inn=?', (inn,)).fetchone()
                    _already = bool(_ex and _ex[0] in ('inn', 'ogrn', 'phone', 'base+serp', 'provider'))
                    if _already:
                        ver_w = site_w = cand_w = None          # уже подтверждён — не трогаем
                    elif _conf:
                        ver_w, site_w, cand_w = _ver, _sv, None
                    elif _ver == 'mismatch':
                        ver_w, site_w, cand_w = _ver, None, None  # метку пишем, чужой сайт — нет
                    else:
                        ver_w, site_w, cand_w = _ver, None, _sv   # кандидат на ручную сверку
                    _db.upsert_company(
                        inn, name=r.get('name') or src.get('name'),
                        division=div or None,
                        okved=src.get('okved'), region=src.get('city') or src.get('region'),
                        pxr=src.get('pxr'), site=site_w, cand_site=cand_w, activity=r.get('activity'),
                        is_competitor=r.get('is_competitor'), verified=ver_w,
                        best_email=r.get('best_for_outreach'), phones=r.get('phones'),
                        # заголовок/описание главной — пишем ТОЛЬКО когда сайт подтверждён
                        # ЭТИМ прогоном (_conf): у чужого/неподтверждённого сайта описание
                        # относится к чужой компании, и в базе это была бы ложь со ссылкой
                        site_title=(r.get('site_title') if _conf else None),
                        site_description=(r.get('site_description') if _conf else None),
                        site_meta_url=(r.get('site_meta_url') if _conf else None),
                        # страница-доказательство пишется всегда, когда она есть:
                        # метка без ссылки непроверяема
                        verified_url=r.get('verified_url') or None,
                        # сверка географии — сигнал для разбора; 'не видно' тоже
                        # пишем, иначе пустое поле не отличить от «не считали»
                        region_sverka=r.get('region_sverka') or None)
                    for e in (r.get('emails') or []):
                        _db.add_email(inn, e.get('email', ''), role=e.get('role', ''),
                                      person=e.get('person', ''), mx_ok=e.get('mx_ok'),
                                      source=args.get('source') or 'enrich',
                                      source_url=e.get('source_url') or '',
                                      razdel=e.get('razdel') or '',
                                      pometka=e.get('pometka') or '',
                                      imya_ok=imya_nadezhno(
                                          e.get('source') or args.get('source') or 'enrich',
                                          e.get('person') or '',
                                          e.get('source_url') or ''))
                        # все страницы-источники — отдельной таблицей
                        if e.get('source_urls'):
                            _db.add_email_sources(inn, e.get('email', ''),
                                                  e['source_urls'])
                    # ПЕРЕНОС ХОЗЯИНУ ДОМЕНА: краулили под одной компанией, а домен по базе
                    # закреплён за другой — контакты пишем ЕЙ, а не выбрасываем. Источник
                    # подписан явно, чтобы потом было видно, откуда они взялись.
                    _pn = r.get('perenos') or {}
                    if _pn.get('inn') and (_pn.get('emails') or _pn.get('phones')):
                        try:
                            _db.upsert_company(_pn['inn'], name=_pn.get('name') or None)
                            _ist = 'краул-соседа:%s' % _pn.get('domain', '')
                            for e in (_pn.get('emails') or []):
                                if e.get('email'):
                                    _db.add_email(_pn['inn'], e['email'],
                                                  role=e.get('role', ''),
                                                  person=e.get('person', ''),
                                                  mx_ok=e.get('mx_ok'),
                                                  source=_ist,
                                                  source_url=e.get('source_url') or '')
                            if hasattr(_db, 'mark_stage'):
                                _db.mark_stage(_pn['inn'], 'email_ot_soseda',
                                               '%d шт с %s (краулили под %s)'
                                               % (len(_pn.get('emails') or []),
                                                  _pn.get('domain', ''), inn))
                        except Exception:  # noqa: BLE001
                            pass
                    # НАЙДЕНА ВНЕ БАЗЫ: чужой сайт, хозяин опознан ИНН'ом со
                    # страницы, но в базе обзвона его нет. Не выбрасываем.
                    _vb = r.get('vne_bazy') or {}
                    if _vb.get('inn'):
                        try:
                            _db.add_vne_bazy(
                                _vb['inn'], domain=_vb.get('domain', ''),
                                site_title=_vb.get('site_title', ''),
                                found_via=_vb.get('found_via', ''),
                                found_crawling=str(inn),
                                source_url=(r.get('site') or ''),
                                emails=_vb.get('emails') or [])
                        except Exception:  # noqa: BLE001
                            pass
                    # лог стадий: пишем ТОЛЬКО успешно завершённые по этой строке
                    # (канон владельца 2026-07-24) — чтобы стадии гонять в любом
                    # порядке с резюме и видеть «были/не были» запросом, не догадкой.
                    if hasattr(_db, 'mark_stage'):
                        _ms = _db.mark_stage
                        if r.get('site'):
                            _ms(inn, 'site', f"{r.get('site')} ({r.get('site_source') or ''})")
                        elif r.get('cand_site'):
                            _ms(inn, 'site_cand', str(r.get('cand_site')))
                        if r.get('crawled_text') or (r.get('timings') or {}).get('crawl'):
                            _ms(inn, 'crawl', str((r.get('timings') or {}).get('crawl') or 'ok'))
                        if r.get('emails'):
                            _ms(inn, 'email', f"{len(r['emails'])} шт; how={r.get('method') or ''}")
                        if r.get('verified') in ('inn', 'ogrn', 'phone', 'base+serp', 'provider'):
                            _ms(inn, 'verify', str(r.get('verified')))
                        if r.get('phones'):
                            _ms(inn, 'phone', f"{len(r.get('phones') or [])} шт")
                        if r.get('opo'):
                            _ms(inn, 'opo', 'signal')
                        if r.get('hh'):
                            _ms(inn, 'hh', 'vacancy')
                        if r.get('zakupki'):
                            _ms(inn, 'zakupki', str(len((r.get('zakupki') or {}).get('cards') or [])))
                except Exception:  # noqa: BLE001
                    pass

    def _one(c):
        try:
            r = enrich_one(c, pace)
        except Exception as e:  # noqa: BLE001
            r = {'inn': c.get('inn'), 'name': c.get('name'), 'error': f'exc:{str(e)[:80]}'}
        _persist(r)   # пишем СРАЗУ, не дожидаясь конца прогона
        return r

    # Параллельно МЕЖДУ компаниями (у каждой свой сайт). Discovery по общим хостам
    # (list-org/поисковик) сериализован семафором внутри enrich_one — один сайт не грузим.
    if workers > 1 and len(companies) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_one, companies))
    else:
        results = [_one(c) for c in companies]
    if _jsonl is not None:
        try:
            _jsonl.close()
        except Exception:  # noqa: BLE001
            pass
    from collections import Counter
    with_email = sum(1 for r in results if r.get('emails'))
    with_lpr = sum(1 for r in results if r.get('best_for_outreach'))
    site_src = Counter(r.get('site_source') for r in results if r.get('site_source'))
    json.dump({'results': results, 'count': len(results),
               'summary': {'with_email': with_email, 'with_lpr_email': with_lpr,
                           'site_sources': dict(site_src)},
               'cost': dict(_COST)},
              sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
