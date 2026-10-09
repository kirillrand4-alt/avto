# -*- coding: utf-8 -*-
r"""База КЦ, шаг 3: контакты, описание и ОКВЭД по каждой компании списка (kc-spisok.json).

Те же шаги, что для файлов Meyer, с правилом владельца 07.10 «только сайт или тендерные
площадки, номера с checko бесполезны»:
  1. checko-карточка (через прокси владельца) — только доп. ОКВЭД, если их нет (как в файле 4).
     Номера и сайт с checko не берём.
  2. Обход живого сайта (как cc_obhod): главная + «контакты/о компании/руководство» + страницы-
     источники наших контактов на том же домене; все номера на живых страницах; ИНН на странице
     (с контрольной суммой) — подтверждение, что сайт этой компании. Где перед номером есть подпись —
     модель по фрагменту говорит, чей номер (классы под КЦ: главный механик/энергетик отдельно).
  3. Описание по тексту сайта (модель): чем занимается, продукция.
  4. Закупки ЕИС (enrich_contacts.find_zakupki_contacts): контактные лица карточек, где ИНН
     компании на странице (компания — заказчик). Плюс карточки-источники из нашей базы.
Выход (fsync, резюм по ИНН): C:\sender\server\kc-kontakty.jsonl -> копия на дроп.
"""
import html as _html
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
НАБОР = os.environ.get('KC_NABOR', 'kc')  # kc — база КЦ из наших баз; poisk — сбор с нуля поиском
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import cc_obhod as CO  # noqa: E402  (ТЕЛ, ДОБ, ИНН_RX, ПОДПИСЬ, инн_ок, норм, ссылки)
import cc_checko_proxy as CP  # noqa: E402
import verify_company as VC  # noqa: E402
import enrich_contacts as EC  # noqa: E402
import kc_pochty as KP  # noqa: E402  (почты — план Meyer п. 3.2)

ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
# Беларусь (пилот 08.10: CO.ТЕЛ ловит только +7/8 — белорусские номера терялись): +375 XX XXX-XX-XX и 8 0XX …
ТЕЛ_BY = re.compile(r'(?:\+\s?375|(?<!\d)375|(?<!\d)8[\s\u00a0\-\(]*0)[\s\u00a0\-\(\)]*\d{2,4}[\s\u00a0\-\)]*\d{1,3}'
                    r'[\s\u00a0\-]*\d{2}[\s\u00a0\-]*\d{2}(?!\d)')


def норм_by(сырое):
    ц = re.sub(r'\D', '', сырое)
    if len(ц) == 11 and ц.startswith('80'):
        ц = '375' + ц[2:]
    if len(ц) != 12 or not ц.startswith('375'):
        return ''
    return '+375 %s %s-%s-%s' % (ц[3:5], ц[5:8], ц[8:10], ц[10:12])


_лок = threading.Lock()
КЛАССЫ = ('директор', 'технический директор', 'главный инженер', 'главный механик', 'главный энергетик',
          'инженер', 'производство', 'закупки', 'главный технолог', 'технолог', 'качество',
          'коммерческий директор', 'продажи', 'бухгалтерия', 'кадры', 'приёмная', 'общий', 'другое')
# справочник «Роль» плана Meyer п. 2.3 (единый для всех сегментов; менять только с согласия владельца)
РОЛИ = ('Руководитель', 'Техдиректор / главный инженер', 'Механик / энергетик / ремонт', 'Производство', 'Технолог',
        'Качество / лаборатория', 'Закупки / снабжение', 'Агрономия / семеноводство', 'Хранение / элеватор / склад',
        'Обогащение / горное', 'Коммерция / ВЭД', 'Продажи', 'Финансы / бухгалтерия', 'Кадры', 'Прочее',
        'Общий номер / приёмная')
ПРОМПТ_НОМЕРА = (
    'Сайт компании {домен} ({название}). Страница: {url}\n'
    'Текст страницы вокруг телефонов и почт:\n«««{текст}»»»\n\nКонтакты (номера и e-mail):\n{номера}\n\n'
    'Для КАЖДОГО контакта по тексту рядом с ним: кому он принадлежит. Почту с локальной частью-фамилией '
    '(ivanov@) сверяй с ФИО рядом. Подпись (ФИО, должность, отдел) '
    'обычно стоит ПЕРЕД номером; номер соседа не приписывай; если подписи нет — пусто.\n'
    'Класс — строго одно из: ' + '|'.join(КЛАССЫ) + '. «директор» — только первое лицо или его '
    'заместитель; региональный/финансовый/коммерческий/по продажам/по развитию директор — не «директор». '
    '«инженер» — инженеры, механики, энергетики, КИПиА, ремонтные службы (не главные). '
    '«производство» — директор по производству, начальник производства/цеха. «закупки» — снабжение, '
    'закупки, МТО. «общий» — номер без подписи, общий, справочная, диспетчер, приём заказов.\n'
    'Сайт может быть сайтом группы компаний: «чей» — "эта", если номер относится к компании «{название}» '
    '(или это общий номер сайта без привязки к другому предприятию), "другая" — если по тексту номер другого '
    'завода/филиала/юрлица группы (другой город, другое название).\n'
    'Роль — строго одно из: ' + '|'.join(РОЛИ) + '. «лпр» — да/возможно/нет: отвечает ли человек за покупку '
    'оборудования или влияет на неё (выбирает, согласует, эксплуатирует, задаёт требования к качеству продукции): '
    'руководитель, техдиректор/главный инженер, механик/энергетик, производство, технолог, качество, закупки — да; '
    'агроном/семеновод и заведующий элеватором/складом — да у семеноводов, элеваторов, ягод, орехов, иначе возможно; '
    'обогатитель/горные — да у руд, угля, нерудных; коммерция/ВЭД — возможно; продажи, финансы, кадры, общий — нет. '
    '«почему» — до 10 слов.\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер_в_списке,"фио":"…или пусто","должность":"как в тексте '
    'или пусто","класс":"…","роль":"…","лпр":"да|возможно|нет","почему":"…","чей":"эта|другая"}}]')
ПРОМПТ_ОПИС = (
    'Компания: {название} (ИНН {инн}), сайт {домен}. ОКВЭД основной: {оквэд}.\n'
    'Текст с сайта (главная, «о компании», продукция):\n«««{текст}»»»\n\n'
    'Ответ — ТОЛЬКО JSON без markdown: {{"описание":"1–2 предложения: чем занимается и что производит, '
    'по фактам с сайта, без рекламы","продукция":"через запятую, до 8 позиций","мощности":"объёмы/'
    'заводы/цеха, если названы на сайте, иначе пусто"}}')


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def модель(промпт, json_массив):
    for попытка in range(3):
        try:
            out = VC._provider_call_stdlib(промпт)
            if json_массив:
                return {int(x.get('n', 0)): x for x in json.loads(re.search(r'\[.*\]', out, re.S).group(0))
                        if isinstance(x, dict)}
            return json.loads(re.search(r'\{.*\}', out, re.S).group(0))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (попытка + 1))
    return {}


ПРОКСИ = []
_пк = [0]


def checko(к):
    if not ПРОКСИ:
        return {}
    with _лок:
        п = ПРОКСИ[_пк[0] % len(ПРОКСИ)]
        _пк[0] += 1
    код, html = п.get('https://checko.ru/search?query=%s' % к['inn'])
    if код != 200:
        return {'checko': str(код)}
    т = CP.текст(html)
    сайт = re.search(r'Сайт\s+((?:https?://)?(?:www\.)?[a-zа-я0-9\-]+(?:\.[a-zа-я0-9\-]+)+)', т, re.I)
    return {'checko': 'ok', 'оквэд_все': CP.окведы(т)[:60], 'сайт': сайт.group(1) if сайт else ''}


# какие внутренние страницы обходить (владелец 09.10: «собираем ли контакты со страницы руководства?»):
# к ссылкам cc_obhod (контакты, о компании, реквизиты, руководство, структура, команда) добавлены дирекция,
# администрация, менеджмент, сотрудники, отделы, закупки/снабжение/тендеры; ссылки берутся с главной И со второго
# уровня («О компании», «Контакты» — там часто подменю «Руководство», «Отделы»).
ССЫЛКА_KC = re.compile(r'kontakt|contact|svyaz|о-компании|o-kompanii|about|rekvizit|реквизит|контакт|company|o-nas|'
                       r'about-us|о-нас|kompaniya|struktur|rukovod|руковод|team|komanda|команд|management|leadership|'
                       r'direkc|дирекц|administr|администрац|menedzhment|менеджмент|sotrudnik|сотрудник|personal|персонал|'
                       r'otdel|отдел|podrazdel|подразделен|zakup|закуп|snab|снабж|tender|тендер|purchas|procure|'
                       r'kontaktnaya|spravochn|справочн|telefon|телефон|'
                       # 09.10, проба: снабжение часто на «Партнёрам/Поставщикам» (bekovocandy.ru/partners: snab@)
                       r'partner|партнер|партнёр|postavshik|поставщик|supplier|vendor', re.I)
ВТОРОЙ_УРОВЕНЬ = re.compile(r'kontakt|contact|о-компании|o-kompanii|about|company|o-nas|kompaniya|struktur|контакт|'
                            r'о-нас', re.I)


# страницы людей (владелец 09.10: «ещё есть команда, внутри пагинация и карточки сотрудников»): на странице
# команды/руководства/сотрудников/отделов берём её пагинацию и дочерние страницы (карточки людей)
ЛЮДИ = re.compile(r'team|komand|команд|rukovod|руковод|sotrudnik|сотрудник|personal|персонал|management|leadership|staff|'
                  r'struktur|структур|otdel|отдел|direkc|дирекц|administr|администрац|specialist|специалист|people|'
                  r'kontakt|contact|контакт', re.I)
ПАГИНАЦИЯ = re.compile(r'[?&](page|PAGEN_\d+|p|pg|start)=\d+|/page/\d+|/stranica-\d+', re.I)


def люди_ссылки(база, html):
    """Пагинация и карточки сотрудников со страницы людей: свой домен, тот же раздел (путь начинается с пути
    страницы или её родителя) или ссылка пагинации."""
    путь = urllib.parse.urlsplit(база).path.rstrip('/')
    родитель = путь.rsplit('/', 1)[0] if путь.count('/') > 1 else путь
    свой = MN.домен(база)
    стр, карточки = [], []
    for м in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\']', html, re.I):
        href = м.group(1).strip()
        if href.startswith(('mailto:', 'tel:', 'javascript:')) or re.search(r'\.(pdf|jpe?g|png|docx?|xlsx?|zip)$', href, re.I):
            continue
        u = urllib.parse.urljoin(база, href)
        if MN.домен(u) != свой or u.rstrip('/') == база.rstrip('/'):
            continue
        п = urllib.parse.urlsplit(u).path.rstrip('/')
        if ПАГИНАЦИЯ.search(u) and (п == путь or п.startswith(путь + '/') or п.startswith(родитель + '/')):
            if u not in стр:
                стр.append(u)
        elif путь and п.startswith(путь + '/') and п != путь and u not in карточки:
            карточки.append(u)
    return стр[:10], карточки[:30]


def ссылки_kc(база, html):
    out = []
    свой = MN.домен(база)
    for м in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href, текст = м.group(1).strip(), re.sub(r'<[^>]+>', ' ', м.group(2))
        if href.startswith(('mailto:', 'tel:', 'javascript:')) or re.search(r'\.(pdf|jpe?g|png|docx?|xlsx?|zip)$', href, re.I):
            continue
        u = urllib.parse.urljoin(база, href)
        if MN.домен(u) != свой:
            continue
        if (ССЫЛКА_KC.search(urllib.parse.unquote(u)) or ССЫЛКА_KC.search(текст)) and u not in out:
            out.append(u)
    return out


# паспорт сайта (site_facts.py) читает страницы из кэша <ИНН>.json.gz — обход кладёт туда скачанное (09.10: без этого
# у компаний нового сбора паспорт не собирался вовсе)
КЭШ_СТРАНИЦ = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')


def в_кэш(ключ, сырые):
    import gzip
    if not сырые:
        return
    try:
        os.makedirs(КЭШ_СТРАНИЦ, exist_ok=True)
        п = os.path.join(КЭШ_СТРАНИЦ, '%s.json.gz' % re.sub(r'[^\w.-]', '_', ключ))
        было = {}
        if os.path.exists(п):
            with gzip.open(п, 'rb') as f:
                было = {x.get('url'): x for x in (json.loads(f.read().decode('utf-8', 'replace')).get('pages') or [])}
        for u, h in сырые.items():
            было[u] = {'url': u, 'html': (h or '')[:400000], 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
        with gzip.open(п + '.tmp', 'wb') as f:
            f.write(json.dumps({'inn': ключ, 'pages': list(было.values())}, ensure_ascii=False).encode('utf-8'))
        os.replace(п + '.tmp', п)
    except Exception:  # noqa: BLE001
        pass  # кэш — не главное: обход не должен падать из-за него


# 09.10, проба meyer7t (владелец: «почему не всё найдено из контактов? confectum.org/contacts/»): на сайтах-компонентах
# (Битрикс + Vue/React) контакты отделов лежат JSON-ом в <script> или атрибуте (заголовки \\u-кодом, «phone»,
# «extensionPhone», «mail») — в_текст вырезает <script>, и номера с почтами отделов терялись. Здесь такие поля
# превращаются в строки «Коммерческий отдел +7 4722 20-53-15 доб. 125 e-mail: commerce@…» и дописываются к тексту
# страницы: дальше их разбирает тот же поиск номеров, добавочных, почт и подписей.
_JSON_ПОЛЯ = re.compile(r'"(title|name|fio|fullName|position|post|job|department|description|phone|phones|tel|telephone|'
                        r'extensionPhone|ext|extension|additional|mail|email|e_mail)"\s*:\s*"((?:[^"\\]|\\.){1,300})"', re.I)


def json_текст(сырое):
    if not сырое or not re.search(r'"(phone|tel|telephone|mail|email)"\s*:', сырое, re.I):
        if not сырое or '&quot;phone&quot;' not in сырое and '&quot;mail&quot;' not in сырое:
            return ''
    h = _html.unescape(сырое) if '&quot;' in сырое else сырое
    строки, тек = [], []
    for м in _JSON_ПОЛЯ.finditer(h):
        ключ, знач = м.group(1).lower(), м.group(2)
        try:
            знач = json.loads('"%s"' % знач)
        except ValueError:
            continue
        знач = re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', знач))).strip()
        if not знач or знач.lower() in ('null', 'none'):
            continue
        if ключ in ('title', 'name', 'fio', 'fullname') and тек:
            строки.append(' '.join(тек))
            тек = []
        if ключ in ('extensionphone', 'ext', 'extension', 'additional'):
            знач = 'доб. ' + знач
        elif ключ in ('mail', 'email', 'e_mail'):
            знач = 'e-mail: ' + знач
        тек.append(знач)
    if тек:
        строки.append(' '.join(тек))
    строки = list(dict.fromkeys(с for с in строки if re.search(r'\d{5}|@', с)))
    return ('\n[данные страницы]\n' + '\n'.join(строки)) if строки else ''


def _окно(т, поз, до=200, после=60):
    return re.sub(r'\s+', ' ', т[max(0, поз - до):поз + после])


def _доп_из_ec(тексты, сырые, номера):
    """09.10 (владелец: «наш обход должен брать не меньше, чем скрипты на сервере: контакты, ФИО, почта, телефон»):
    вторым проходом по тем же страницам — извлекатели enrich_contacts. Сравнение на пробе (108 компаний, те же
    страницы): у обхода больше номеров и ФИО, но EC находил 57 почт и 76 номеров, которых у обхода нет.
      * mailto / JSON-LD / раскодированные почты и ссылки tel: (EC._harvest_from_html) — чего нет, добавляется;
      * карточки «раздел -> почта» (EC.karty_kontaktov) — раздел страницы дописывается к фрагменту почты как
        подсказка роли («Отдел снабжения»);
      * люди по блокам страницы (EC.people_from_html: ФИО + должность + телефон/почта одного блока) — их контакты,
        которых нет, добавляются с подписью блока; ФИО/должность для уже найденных — после разметки моделью,
        если модель их не нашла.
    -> {ключ контакта: (ФИО, должность)} для дозаполнения после разметки."""
    def ц(x):
        return re.sub(r'\D', '', x or '')[-10:]
    есть_п = {з.get('почта') for з in номера.values() if з.get('почта')}
    есть_т = {ц(з.get('номер')) for з in номера.values() if з.get('номер')}
    люди_для = {}
    for u, h in сырые.items():
        т = тексты.get(u, '')
        тн = т.lower()
        try:
            карты = EC.karty_kontaktov(h, u) or []
        except Exception:  # noqa: BLE001
            карты = []
        раздел = {}
        for кр in карты:
            e = (кр.get('email') or '').lower()
            подп = ' '.join(x for x in (кр.get('razdel') or '', кр.get('kartochka') or '') if x).strip()
            if e and подп:
                раздел.setdefault(e, подп[:300])
        for з in номера.values():
            e = з.get('почта')
            if e and раздел.get(e) and раздел[e][:30] not in з['контекст']:
                з['контекст'] = ('Раздел страницы: ' + раздел[e] + ' | ' + з['контекст'])[-520:]
        try:
            ec_п, ec_т = EC._harvest_from_html(h)
        except Exception:  # noqa: BLE001
            ec_п, ec_т = set(), set()
        for e in sorted(x.lower() for x in ec_п):
            if e in есть_п:
                continue
            поз = тн.find(e)
            контекст = _окно(т, поз) if поз >= 0 else (раздел.get(e) or '') + ' ' + e
            номера['mail:' + e] = {'номер': '', 'почта': e, 'доб': '', 'страницы': [u], 'контекст': контекст.strip(),
                                   '_поз': (u, поз), 'откуда': 'enrich_contacts'}
            есть_п.add(e)
        for d in sorted(ec_т):
            н = CO.норм('+' + d if not d.startswith('8') else d) or норм_by(d)
            if not н or ц(н) in есть_т:
                continue
            поз = (MP.найти(т, ц(н)) or [-1])[0]
            контекст = _окно(т, поз) if поз >= 0 else 'tel: ' + н
            номера[н] = {'номер': н, 'доб': '', 'страницы': [u], 'контекст': контекст, '_поз': (u, поз),
                         'откуда': 'enrich_contacts'}
            есть_т.add(ц(н))
        try:
            люди = EC.people_from_html(h, u) or []
        except Exception:  # noqa: BLE001
            люди = []
        for ч in люди:
            подпись = ' '.join(x for x in (ч.get('post') or '', ч.get('person') or '') if x)
            тел = CO.норм(ч.get('phone') or '') or норм_by(ч.get('phone') or '')
            e = (ч.get('email') or '').lower()
            for ключ, есть in ((тел, ц(тел) in есть_т if тел else True), ('mail:' + e if e else '', e in есть_п if e else True)):
                if not ключ:
                    continue
                if есть:
                    люди_для.setdefault(ключ if ключ.startswith('mail:') else ц(ключ), (ч.get('person') or '', ч.get('post') or ''))
                    continue
                if ключ.startswith('mail:'):
                    номера[ключ] = {'номер': '', 'почта': e, 'доб': '', 'страницы': [u], 'откуда': 'enrich_contacts',
                                    'контекст': (подпись + ' e-mail: ' + e).strip(), '_поз': (u, -1)}
                    есть_п.add(e)
                else:
                    номера[тел] = {'номер': тел, 'доб': '', 'страницы': [u], 'откуда': 'enrich_contacts',
                                   'контекст': (подпись + ' тел. ' + (ч.get('phone') or тел)).strip(), '_поз': (u, -1)}
                    есть_т.add(ц(тел))
    return люди_для


def _из_кэша(ключ, сайт, уже, предел=30):
    """09.10: старые страницы сайта из кэша (Зенка обходила сайты целиком, прежний обогатитель — тоже) — без
    скачивания. Проба: у 39 из 110 компаний 474 такие страницы, на них 47 новых почт и 76 номеров у 11 компаний."""
    import gzip
    п = os.path.join(КЭШ_СТРАНИЦ, '%s.json.gz' % re.sub(r'[^\w.-]', '_', ключ or ''))
    if not ключ or not os.path.exists(п):
        return []
    try:
        with gzip.open(п, 'rb') as f:
            стр = json.loads(f.read().decode('utf-8', 'replace')).get('pages') or []
    except Exception:  # noqa: BLE001
        return []
    дом = MN.домен(сайт)
    out = [(x['url'], x['html']) for x in стр if x.get('url') and x.get('html') and x['url'] not in уже
           and MN.домен(x['url']) == дом]
    return out[:предел]


def обход(к, сайт):
    старт = сайт if сайт.startswith('http') else 'https://' + сайт
    очередь = [старт] + [u for u in к.get('страницы_базы', []) if u.startswith('http')][:6]
    тексты, страницы, сырые = {}, [], {}
    i = 0
    люди_доп = 0  # сверх 15 страниц: пагинация и карточки сотрудников, до 40
    while i < len(очередь) and len(тексты) < 15 + люди_доп:
        u = очередь[i]
        i += 1
        ст, html, _ = MN.скачать(u)
        страницы.append([u, ст])
        if ст != 'ok':
            continue
        тексты[u] = MP.в_текст(html) + json_текст(html)
        сырые[u] = html
        if i == 1 or (len(очередь) < 30 and ВТОРОЙ_УРОВЕНЬ.search(urllib.parse.unquote(u))):
            for л in ссылки_kc(u, html)[:12 if i == 1 else 6]:
                if л not in очередь:
                    очередь.append(л)
        if i > 1 and ЛЮДИ.search(urllib.parse.unquote(urllib.parse.urlsplit(u).path)):
            стр, карточки = люди_ссылки(u, html)
            for л in стр + карточки:
                if л not in очередь and люди_доп < 40:
                    очередь.append(л)
                    люди_доп += 1
    свежие = dict(сырые)  # в кэш — только скачанное сейчас (старым страницам не ставим новую дату)
    if os.environ.get('KC_BEZ_KESHA') != '1':
        # статус «кэш», не «ok»: «сайт открылся» и перепроверки (audit2, проверка сайта, опровергатели) — по живым
        for u, h in _из_кэша(к.get('inn'), старт, set(тексты)):
            тексты[u] = MP.в_текст(h) + json_текст(h)
            сырые[u] = h
            страницы.append([u, 'кэш'])
    номера = {}
    for u, т in тексты.items():
        for м in CO.ТЕЛ.finditer(т):
            н = CO.норм(м.group(0))
            if not н:
                continue
            доб = CO.ДОБ.match(т[м.end():м.end() + 20])
            ключ = н + ((' доб. ' + доб.group(1)) if доб else '')
            з = номера.setdefault(ключ, {'номер': н, 'доб': доб.group(1) if доб else '', 'страницы': [],
                                         'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]),
                                         '_поз': (u, м.start())})
            if u not in з['страницы']:
                з['страницы'].append(u)
        for м in ТЕЛ_BY.finditer(т):
            н = норм_by(м.group(0))
            if not н:
                continue
            доб = CO.ДОБ.match(т[м.end():м.end() + 20])
            ключ = н + ((' доб. ' + доб.group(1)) if доб else '')
            з = номера.setdefault(ключ, {'номер': н, 'доб': доб.group(1) if доб else '', 'страницы': [],
                                         'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]),
                                         '_поз': (u, м.start())})
            if u not in з['страницы']:
                з['страницы'].append(u)
        for м in re.finditer(r'\[tel:([^\]]+)\]', т):
            н = CO.норм(м.group(1)) or норм_by(м.group(1))
            if н and not any(з['номер'] == н for з in номера.values()):
                номера[н] = {'номер': н, 'доб': '', 'страницы': [u],
                             'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]), '_поз': (u, м.start())}
    for u, т in тексты.items():
        for п in KP.почты(сырые.get(u), т):
            ключ = 'mail:' + п['почта']
            з = номера.setdefault(ключ, {'номер': '', 'почта': п['почта'], 'доб': '', 'страницы': [],
                                         'контекст': п['контекст'], '_поз': (u, п['поз'])})
            if u not in з['страницы']:
                з['страницы'].append(u)
    try:
        люди_ec = _доп_из_ec(тексты, сырые, номера)
    except Exception:  # noqa: BLE001  (второй проход — добавка: обход не должен падать из-за него)
        люди_ec = {}
    по_стр = {}
    for ключ, з in номера.items():
        u, п = з['_поз']
        if п >= 0 and CO.ПОДПИСЬ.search(тексты[u][max(0, п - 160):п]):
            по_стр.setdefault(u, []).append(ключ)
        elif п < 0 and CO.ПОДПИСЬ.search(з['контекст'][-260:]):  # почта только в mailto: подпись по фрагменту HTML
            по_стр.setdefault(u, []).append(ключ)
    for u, ключи in по_стр.items():
        for k in range(0, len(ключи), 14):
            кусок = ключи[k:k + 14]
            т = тексты[u]
            окна = sorted((max(0, номера[кл]['_поз'][1] - 400), номера[кл]['_поз'][1] + 150) for кл in кусок
                          if номера[кл]['_поз'][1] >= 0)
            слито = []
            for a, b in окна:
                if слито and a <= слито[-1][1]:
                    слито[-1] = (слито[-1][0], max(b, слито[-1][1]))
                else:
                    слито.append((a, b))
            ответ = модель(ПРОМПТ_НОМЕРА.format(домен=MN.домен(старт), название=к['имя'], url=u,
                                                текст=('\n…\n'.join(т[a:b] for a, b in слито) + ''.join(
                                                    '\n…\n' + номера[кл]['контекст'] for кл in кусок
                                                    if номера[кл]['_поз'][1] < 0))[:6500],
                                                номера='\n'.join('%d. %s' % (j + 1, н[5:] if н.startswith('mail:') else н)
                                                                  for j, н in enumerate(кусок))), True)
            for j, кл in enumerate(кусок):
                x = ответ.get(j + 1) or {}
                номера[кл].update({'фио': (x.get('фио') or '')[:80], 'должность': (x.get('должность') or '')[:120],
                                   'класс': x.get('класс') if x.get('класс') in КЛАССЫ else '',
                                   'роль': x.get('роль') if x.get('роль') in РОЛИ else '',
                                   'лпр': x.get('лпр') if x.get('лпр') in ('да', 'возможно', 'нет') else '',
                                   'почему': (x.get('почему') or '')[:100],
                                   'чей': x.get('чей') if x.get('чей') in ('эта', 'другая') else ''})
    for ключ, з in номера.items():
        чел = люди_ec.get(ключ if ключ.startswith('mail:') else re.sub(r'\D', '', з.get('номер') or '')[-10:])
        if чел and not з.get('фио') and чел[0]:
            з['фио'], з['фио_откуда'] = чел[0][:80], 'блок страницы (enrich_contacts)'
            if not з.get('должность') and чел[1]:
                з['должность'] = чел[1][:120]
    for з in номера.values():
        з.pop('_поз', None)
    инн_живой = []
    for т in тексты.values():
        for м in CO.ИНН_RX.finditer(т):
            if CO.инн_ок(м.group(1)) and м.group(1) not in инн_живой:
                инн_живой.append(м.group(1))
    # описание: главная и «о компании»/«продукция»
    кусочки = []
    for u, т in list(тексты.items())[:5]:
        т = re.sub(r'\[tel:[^\]]*\]', ' ', т)
        т = re.sub(r'\n\s*\S{1,25}\s*(?=\n)', '\n', т)
        кусочки.append(re.sub(r'\s+', ' ', т)[:2200])
    опис = модель(ПРОМПТ_ОПИС.format(название=к['имя'], инн=к['inn'], домен=MN.домен(старт), оквэд=к['осн'],
                                     текст='\n---\n'.join(кусочки)[:8000]), False) if кусочки else {}
    в_кэш(к['inn'], свежие)
    return {'сайт': старт, 'страницы': страницы, 'номера': list(номера.values()), 'инн_живой': инн_живой,
            'описание': опис.get('описание', ''), 'продукция': опис.get('продукция', ''), 'мощности': опис.get('мощности', '')}


def закупки(к):
    out = []
    r = EC.find_zakupki_contacts(к['inn'], max_cards=10) or {}
    if r.get('error'):
        out.append({'ошибка': r['error']})
    for card in r.get('cards', []):
        out.append({'url': card.get('url'), 'предмет': card.get('subject') or card.get('title'),
                    'инн_на_странице': card.get('inn_на_странице'), 'люди': card.get('people') or [],
                    'ошибка': card.get('error', '')})
    # карточки-источники из нашей базы: живая страница, ИНН и люди
    for url in (к.get('закупки_базы') or [])[:6]:
        if any(x.get('url') == url for x in out):
            continue
        try:
            h = EC._eis_get(url)
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
            out.append({'url': url, 'предмет': '', 'инн_на_странице': к['inn'] in txt, 'люди': EC._eis_people(txt),
                        'из_базы': True})
        except Exception as e:  # noqa: BLE001
            out.append({'url': url, 'ошибка': repr(e)[:80], 'из_базы': True})
        time.sleep(1.5)
    return out


# 09.10: перепрогон обхода (новые извлекатели) — KC_VERSIYA=<метка>: записи без этой метки считаются необойдёнными;
# закупки ЕИС (медленные, от сайта не зависят) берутся из прежней записи компании, если там они были
ВЕРСИЯ = os.environ.get('KC_VERSIYA', '')
ПРОШЛЫЕ_ЗАКУПКИ = {}


def одна(к):
    з = {'inn': к['inn']}
    if ВЕРСИЯ:
        з['версия'] = ВЕРСИЯ
    try:
        сайт = к['сайт']  # только сайт из нашей базы/таблицы CC, как в файлах 1–4 (без сайта из checko)
        by = not к['inn'].isdigit()  # Беларусь «BY<УНП>» и «САЙТ:<домен>» (ИНН не определён): ни checko, ни ЕИС
        if len(к.get('все') or []) <= 1 and not by and not os.environ.get('KC_BEZ_CHECKO'):
            з['checko'] = checko(к)  # доп. ОКВЭД, как в файле 4 (пилот Meyer: не нужен — ОКВЭД уже в отборе)
        if сайт:
            з.update(обход(к, сайт))
        # ЕИС медленный (до минуты на компанию): KC_ZAKUPKI_OT — только от этой выручки (пилот 08.10: 1 млрд)
        if к['inn'] in ПРОШЛЫЕ_ЗАКУПКИ:
            з['закупки'] = ПРОШЛЫЕ_ЗАКУПКИ[к['inn']]
        else:
            з['закупки'] = [] if by or (к.get('выручка') or 0) < float(os.environ.get('KC_ZAKUPKI_OT', '0')) else закупки(к)
        з['итог'] = 'ok'
    except Exception as e:  # noqa: BLE001
        з['итог'] = 'сбой: ' + repr(e)[:120]
    записать(з)


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') == 'ok' and (not ВЕРСИЯ or з.get('версия') == ВЕРСИЯ):
                    сделано.add((з['inn'], MN.домен(з.get('сайт') or '')))
                if ВЕРСИЯ and з.get('итог') == 'ok' and any(x.get('url') for x in з.get('закупки') or []):
                    ПРОШЛЫЕ_ЗАКУПКИ[з['inn']] = з['закупки']
            except ValueError:
                pass
    очередь = sorted((к for i, к in сп.items() if (i, MN.домен(к['сайт'] or '')) not in сделано),
                     key=lambda к: -к['выручка'])  # сменился сайт (08.10: сайты групп) — обойти заново
    ПРОКСИ.extend(п for п in (CP.Прокси(x) for x in json.load(open(os.path.join(DIR, 'checko-proxies.json'))))
                  if п.get('https://checko.ru/')[0] == 200)
    print('компаний', len(сп), 'в очереди', len(очередь), 'прокси', len(ПРОКСИ), flush=True)
    t0 = time.time()
    n = [0]

    def один(к):
        одна(к)
        n[0] += 1
        if n[0] % 20 == 0:
            print('готово %d/%d за %d мин' % (n[0], len(очередь), (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(int(os.environ.get('KC_POTOKOV', '24' if НАБОР == 'pilot' else '6'))) as ex:
        list(ex.map(один, очередь))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', НАБОР + '-kontakty.jsonl'))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
