# -*- coding: utf-8 -*-
r"""Обход живых сайтов из таблицы BAZA-KONTAKTY-CC (Common Crawl, 1 333 сайта) — владелец 07.10:
сделать такую же базу, как третий файл Meyer (номер точно на живой странице), плюс пометить
номер ФИО и должностью, если они стоят рядом.

На каждый сайт: главная + ссылки «контакты/о компании/реквизиты» с неё (до 8 страниц, только
свой домен) + страница с ИНН и страницы людей из таблицы. На страницах: все телефоны (в любом
написании, tel:-ссылки, слитно с 8), ИНН рядом со словом «ИНН» с контрольной суммой. Номер
считается подтверждённым, если стоит на живой странице сайта компании (страница своя по
построению). ФИО/должность — только если в тексте рядом с номером есть подпись: тогда модель
(провайдерский API) по фрагменту говорит, чей номер; без подписи модель не вызывается.
Если ИНН нет ни в таблице, ни на сайте — ищем домен в нашей базе (companies.site, obzvon.sites).
По найденным ИНН — название, ОКВЭД, регион, выручка из нашей базы.

Вход: C:\seostat\drop\drop-storage\cc-vhod.json. Выход (fsync, резюм по домену):
C:\sender\server\cc-obhod.jsonl. Запуск детачем — _pusk_cc.py.
"""
import io
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402  (в_текст, найти)
import meyer_nalichie as MN  # noqa: E402  (быстрый скачать, домен)
import verify_company as VC  # noqa: E402

ВХОД = r'C:\seostat\drop\drop-storage\cc-vhod.json'
ВЫХОД = os.path.join(DIR, 'cc-obhod.jsonl')
ПОТОКОВ = 24
_лок = threading.Lock()

ССЫЛКА_НУЖНАЯ = re.compile(r'kontakt|contact|svyaz|о-компании|o-kompanii|about|rekvizit|реквизит|контакт|'
                           r'company|o-nas|about-us|о-нас|kompaniya|struktur|rukovod|руковод|team|komanda',
                           re.I)
ТЕЛ = re.compile(r'(?:\+7|(?<!\d)8)[\s\u00a0\-\(\)]*\d{3,5}[\s\u00a0\-\)]*\d{1,3}[\s\u00a0\-]*\d{2}'
                 r'[\s\u00a0\-]*\d{2}(?!\d)')
ДОБ = re.compile(r'^\s*[,(]?\s*(?:доб|вн|ext)\.?\s*[:№]?\s*(\d{1,6})', re.I)
ИНН_RX = re.compile(r'ИНН[\s:№/]*(?:КПП[\s:№]*)?(\d{10}|\d{12})(?!\d)', re.I)
ПОДПИСЬ = re.compile(r'директор|инженер|технолог|снабж|закуп|агроном|руковод|начальник|менеджер|бухгалт|'
                     r'приёмн|приемн|отдел|секретар|заведующ|механик|энергетик|качеств|лаборат|продаж|'
                     r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна|ична|чна)\b|[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.',
                     re.I)
КЛАССЫ = ('директор', 'главный инженер', 'технический директор', 'производство', 'главный технолог',
          'технолог', 'качество', 'закупки', 'агроном', 'семеноводство', 'элеватор',
          'коммерческий директор', 'продажи', 'бухгалтерия', 'кадры', 'инженер', 'приёмная', 'общий',
          'другое')
ПРОМПТ = (
    'Сайт компании {домен} ({название}). Страница: {url}\n'
    'Текст страницы вокруг телефонов:\n«««{текст}»»»\n\nНомера:\n{номера}\n\n'
    'Для КАЖДОГО номера по тексту рядом с ним: кому он принадлежит. Подпись (ФИО, должность, отдел) '
    'обычно стоит ПЕРЕД номером; номер соседа не приписывай; если подписи нет — пусто.\n'
    'Класс — строго одно из: ' + '|'.join(КЛАССЫ) + '. «директор» — только первое лицо или его '
    'заместитель; региональный/финансовый/коммерческий/по продажам директор — не «директор». '
    '«общий» — номер без подписи, общий, справочная, диспетчер, приём заказов.\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер_в_списке,"фио":"…или пусто","должность":"как в тексте '
    'или пусто","класс":"…"}}]')


def инн_ок(s):
    ц = [int(c) for c in s]
    if len(ц) == 10:
        к = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(a * b for a, b in zip(к, ц)) % 11 % 10 == ц[9]
    if len(ц) == 12:
        к1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        к2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return (sum(a * b for a, b in zip(к1, ц)) % 11 % 10 == ц[10]
                and sum(a * b for a, b in zip(к2, ц)) % 11 % 10 == ц[11])
    return False


def норм(сырое):
    ц = re.sub(r'\D', '', сырое)
    if len(ц) == 11 and ц[0] in '78':
        ц = '7' + ц[1:]
    elif len(ц) == 10:
        ц = '7' + ц
    if len(ц) != 11 or ц[1] in '012':
        return ''
    return '+7 %s %s-%s-%s' % (ц[1:4], ц[4:7], ц[7:9], ц[9:11])


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def ссылки(база, html):
    out = []
    свой = MN.домен(база)
    for м in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href, текст = м.group(1).strip(), re.sub(r'<[^>]+>', ' ', м.group(2))
        if href.startswith(('mailto:', 'tel:', 'javascript:')):
            continue
        u = urllib.parse.urljoin(база, href)
        if MN.домен(u) != свой:
            continue
        if ССЫЛКА_НУЖНАЯ.search(urllib.parse.unquote(u)) or ССЫЛКА_НУЖНАЯ.search(текст):
            if u not in out:
                out.append(u)
    return out


def спросить(о, url, текст, номера):
    промпт = ПРОМПТ.format(домен=о['домен'], название=о['название'] or о['заголовок'][:80], url=url,
                           текст=текст[:6500], номера='\n'.join('%d. %s' % (i + 1, н) for i, н in enumerate(номера)))
    for попытка in range(3):
        try:
            out = VC._provider_call_stdlib(промпт)
            return {int(x.get('n', 0)): x for x in json.loads(re.search(r'\[.*\]', out, re.S).group(0))
                    if isinstance(x, dict)}
        except Exception:  # noqa: BLE001
            time.sleep(5 * (попытка + 1))
    return {}


def сайт(о, домены_базы):
    старт = о['сайт'] or ('https://' + о['домен'])
    очередь = [старт]
    for u in [о.get('страница_инн')] + [л['страница'] for л in о['люди']]:
        if u and u.startswith('http') and u not in очередь:
            очередь.append(u)
    страницы, тексты = [], {}
    i = 0
    while i < len(очередь) and len(тексты) < 10:
        u = очередь[i]
        i += 1
        статус, html, загол = MN.скачать(u)
        страницы.append([u, статус])
        if статус != 'ok':
            continue
        тексты[u] = MP.в_текст(html)
        if i == 1:
            for л in ссылки(u, html)[:8]:
                if л not in очередь:
                    очередь.append(л)
    # номера на живых страницах
    номера = {}
    for u, т in тексты.items():
        for м in ТЕЛ.finditer(т):
            н = норм(м.group(0))
            if not н:
                continue
            доб = ДОБ.match(т[м.end():м.end() + 20])
            ключ = н + ((' доб. ' + доб.group(1)) if доб else '')
            з = номера.setdefault(ключ, {'номер': н, 'доб': доб.group(1) if доб else '', 'страницы': [],
                                         'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]),
                                         '_поз': (u, м.start())})
            if u not in з['страницы']:
                з['страницы'].append(u)
        # tel:-ссылки, которых нет в видимом тексте
        for м in re.finditer(r'\[tel:([^\]]+)\]', т):
            н = норм(м.group(1))
            if н and н not in номера:
                номера[н] = {'номер': н, 'доб': '', 'страницы': [u], 'контекст': re.sub(r'\s+', ' ', т[max(0, м.start() - 200):м.end() + 60]),
                             '_поз': (u, м.start())}
    из_таблицы = {норм(x) for x in о['телефоны']}
    for з in номера.values():
        з['из_таблицы'] = з['номер'] in из_таблицы
        з['тип'] = 'мобильный' if з['номер'][3] == '9' and not з['доб'] else ('городской + доб.' if з['доб'] else 'городской')
    # подписи рядом: модель по странице, только где в тексте перед номером есть подпись
    по_стр = {}
    for ключ, з in номера.items():
        u, п = з['_поз']
        до = тексты[u][max(0, п - 160):п]
        if ПОДПИСЬ.search(до):
            по_стр.setdefault(u, []).append(ключ)
    for u, ключи in по_стр.items():
        for k in range(0, len(ключи), 14):
            кусок = ключи[k:k + 14]
            т = тексты[u]
            окна = sorted((max(0, номера[кл]['_поз'][1] - 400), номера[кл]['_поз'][1] + 150) for кл in кусок)
            слито = []
            for a, b in окна:
                if слито and a <= слито[-1][1]:
                    слито[-1] = (слито[-1][0], max(b, слито[-1][1]))
                else:
                    слито.append((a, b))
            ответ = спросить(о, u, '\n…\n'.join(т[a:b] for a, b in слито), кусок)
            for j, кл in enumerate(кусок):
                x = ответ.get(j + 1) or {}
                номера[кл].update({'фио': (x.get('фио') or '')[:80], 'должность': (x.get('должность') or '')[:120],
                                   'класс': x.get('класс') if x.get('класс') in КЛАССЫ else ''})
    for з in номера.values():
        з.pop('_поз', None)
    # ИНН на живых страницах (с контрольной суммой)
    инн_живой = []
    for т in тексты.values():
        for м in ИНН_RX.finditer(т):
            if инн_ок(м.group(1)) and м.group(1) not in инн_живой:
                инн_живой.append(м.group(1))
    # люди из таблицы: стоит ли ФИО на живой странице
    люди = []
    for л in о['люди']:
        фам = (л['фио'] or '').split()[0] if л['фио'] else ''
        т = тексты.get(л['страница'], '')
        люди.append(dict(л, фио_на_живой=bool(фам and фам in т), страница_живая=bool(т)))
    записать({'домен': о['домен'], 'страницы': страницы, 'номера': list(номера.values()),
              'инн_живой': инн_живой, 'инн_база': sorted(домены_базы.get(MN.домен(старт), []))[:5],
              'люди': люди})


def домены_базы():
    c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=120)
    c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")
    out = {}
    for inn, s in c.execute("select inn, coalesce(site,'') from companies where coalesce(site,'')<>'' "
                            "union all select inn, coalesce(sites,'') from obz.obzvon where coalesce(sites,'')<>''"):
        for x in re.split(r'[\s,;|]+', s):
            if '.' in x:
                out.setdefault(MN.домен(x), set()).add(str(inn))
    c.close()
    return out


def main():
    вход = json.load(io.open(ВХОД, encoding='utf-8'))
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['домен'])
            except ValueError:
                pass
    очередь = [о for о in вход if о['домен'] not in сделано]
    дб = домены_базы()
    print('сайтов', len(вход), 'в очереди', len(очередь), 'доменов в базе', len(дб), flush=True)
    t0 = time.time()
    счёт = [0]

    def один(о):
        try:
            сайт(о, дб)
        except Exception as e:  # noqa: BLE001
            print('сбой', о['домен'], repr(e)[:120], flush=True)
        счёт[0] += 1
        if счёт[0] % 100 == 0:
            print('готово сайтов %d за %d мин' % (счёт[0], (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(один, очередь))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
