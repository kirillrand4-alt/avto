# -*- coding: utf-8 -*-
r"""Сверка ВСЕХ номеров со страниц по базе Meyer с живыми страницами-источниками.

Владелец 06.10: «сделай то же самое [что meyer-lpr-tel], но для компаний, где есть
номер со страницы любой + расположи по ЛПР-приоритетам, также проверь полностью
источники, чтобы совпадали».

Вход: C:\seostat\drop\drop-storage\meyer-vse-vhod.json — список страниц
{url, inn, имя, сайт, номера:[{id, номер, доб, тип, ...}]} (одна страница — один
скачок, один вызов модели на все её номера, кусками).
Для каждой страницы: скачать (напрямую, без проверки серта, через прокси; повтор
при 429/503), найти каждый номер в любом написании; если на живой странице нет —
искать в кэше обхода pagecache/<ИНН>.json.gz. Вокруг найденных номеров склеить
фрагменты и спросить модель (провайдерский API): чей номер — ФИО, должность,
КЛАСС из закрытого списка, та ли компания.

Выход (durable, fsync, резюм по id): C:\sender\server\meyer-proverka-vse.jsonl.
Запуск: python meyer_proverka_vse.py [--povtor]  (--povtor: заново те, где страница
не открылась). Детачем — через _pusk_proverki_vse.py.
"""
import io
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import meyer_proverka as MP  # noqa: E402  (ascii_url, в_текст, найти, из_кэша_обхода, UA)
import verify_company as VC  # noqa: E402

ВХОД = r'C:\seostat\drop\drop-storage\meyer-vse-vhod.json'
ВЫХОД = os.path.join(DIR, 'meyer-proverka-vse.jsonl')
ПОТОКОВ = 12
КУСОК_НОМЕРОВ = 14
КУСОК_ТЕКСТА = 6500
_лок = threading.Lock()
_хосты, _хосты_лок = {}, threading.Lock()
_прямой = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_без_серт = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))

КЛАССЫ = ('директор', 'главный инженер', 'технический директор', 'производство', 'главный технолог',
          'технолог', 'качество', 'закупки', 'агроном', 'семеноводство', 'элеватор',
          'коммерческий директор', 'продажи', 'бухгалтерия', 'кадры', 'инженер', 'приёмная', 'общий',
          'другое')

ПРОМПТ = (
    'Проверяешь телефоны компании «{имя}» (ИНН {инн}, сайт {сайт}).\n'
    'Страница-источник: {url}\nЗаголовок: {заголовок}\n'
    'Текст страницы вокруг этих номеров:\n«««{текст}»»»\n\n'
    'Номера (могут быть написаны в тексте в другом формате):\n{номера}\n\n'
    'Для КАЖДОГО номера определи по тексту рядом с ним, кому он принадлежит. Подпись (ФИО, '
    'должность, отдел) обычно стоит ПЕРЕД номером; номер соседнего человека не приписывай.\n'
    'Класс — строго одно из: ' + '|'.join(КЛАССЫ) + '.\n'
    '«директор» — только первое лицо или его заместитель (генеральный, исполнительный директор, '
    'директор, управляющий, собственник, заместитель директора). Региональный, финансовый, '
    'коммерческий, по маркетингу/развитию/персоналу/продажам директор — НЕ «директор». '
    '«производство» — директор/начальник производства, цех, производственный отдел. '
    '«элеватор» — заведующий элеватором/зерноскладом/ХПП/током. «закупки» — снабжение, закупки, '
    'МТС, «поставщикам». «инженер» — механик, энергетик, прочие инженеры. «приёмная» — приёмная, '
    'секретарь. «общий» — номер без подписи, общий номер компании/офиса, справочная, диспетчер, '
    'приём заявок/заказов.\n'
    '«компания_та»: «да» — страница этой компании или карточка ИМЕННО этой компании; «нет» — '
    'другая организация (сосед в справочнике, дилер, партнёр); «неясно».\n'
    'Ответ — ТОЛЬКО JSON-массив без markdown: [{{"n":номер_в_списке,"есть":true/false,'
    '"фио":"ФИО или пусто","должность":"должность/отдел как в тексте или пусто",'
    '"класс":"…","компания_та":"да|нет|неясно"}}]')


def записать(записи):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            for з in записи:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def скачать(url):
    """(статус, html, заголовок). Один хост — по одному запросу (чтобы не ловить 429)."""
    хост = urllib.parse.urlsplit(url).hostname or ''
    with _хосты_лок:
        лок = _хосты.setdefault(хост, threading.Lock())
    req = urllib.request.Request(MP.ascii_url(url), headers={
        'User-Agent': MP.UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'})
    ошибка = ''
    with лок:
        for попытка, opener in enumerate((_прямой, _без_серт, None, _прямой)):
            try:
                r = urllib.request.urlopen(req, timeout=25) if opener is None else opener.open(req, timeout=25)
                with r:
                    тип = r.headers.get('Content-Type', '')
                    сырое = r.read(6_000_000)
                if 'pdf' in тип.lower():
                    return 'pdf', '', ''
                м = re.search(r'charset=([\w\-]+)', тип) or re.search(rb'charset=["\']?([\w\-]+)', сырое[:3000])
                кодир = (м.group(1) if isinstance(м.group(1), str) else м.group(1).decode('ascii', 'ignore')) if м else 'utf-8'
                try:
                    текст = сырое.decode(кодир, errors='replace')
                except LookupError:
                    текст = сырое.decode('utf-8', errors='replace')
                з = re.search(r'<title[^>]*>(.*?)</title>', текст, re.S | re.I)
                return 'ok', текст, (MP.html.unescape(з.group(1)).strip()[:150] if з else '')
            except urllib.error.HTTPError as e:
                ошибка = 'HTTP %s' % e.code
                if e.code in (404, 410):
                    break
                if e.code in (429, 503):
                    time.sleep(20 * (попытка + 1))
            except Exception as e:  # noqa: BLE001
                ошибка = type(e).__name__ + ': ' + str(e)[:60]
                if 'getaddrinfo' in str(e) or 'Name or service' in str(e):
                    break  # домена нет — дальше не мучаем
    return 'ошибка: ' + ошибка, '', ''


def окна(текст, позиции, до=420, после=220):
    """Склеить перекрывающиеся окна вокруг позиций номеров в один текст."""
    отрезки = sorted((max(0, п - до), min(len(текст), п + после)) for п in позиции)
    слито = []
    for a, b in отрезки:
        if слито and a <= слито[-1][1] + 40:
            слито[-1] = (слито[-1][0], max(слито[-1][1], b))
        else:
            слито.append((a, b))
    return '\n…\n'.join(текст[a:b] for a, b in слито)


def спросить(стр, заголовок, текст, номера):
    промпт = ПРОМПТ.format(имя=стр['имя'], инн=стр['inn'], сайт=стр['сайт'] or '—', url=стр['url'],
                           заголовок=заголовок or '—', текст=текст[:КУСОК_ТЕКСТА],
                           номера='\n'.join('%d. %s%s' % (i + 1, н['номер'], (' доб. ' + н['доб']) if н['доб'] else '')
                                            for i, н in enumerate(номера)))
    for попытка in range(3):
        try:
            out = VC._provider_call_stdlib(промпт)
            м = re.search(r'\[.*\]', out or '', re.S)
            ответ = json.loads(м.group(0))
            return {int(о.get('n', 0)): о for о in ответ if isinstance(о, dict)}
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:80]
            time.sleep(6 * (попытка + 1))
    return {'ошибка': err}


def страница(стр):
    статус, сырое, заголовок = скачать(стр['url'])
    текст = MP.в_текст(сырое) if статус == 'ok' else ''
    найдено, нет = [], []
    for н in стр['номера']:
        цифры = re.sub(r'\D', '', н['номер'])[-10:]
        поз = MP.найти(текст, цифры) if текст else []
        (найдено if поз else нет).append((н, поз))
    # чего нет на живой странице — ищем в сохранённой копии обхода
    из_кэша = {}
    for н, _ in нет:
        к = MP.из_кэша_обхода(стр['inn'], re.sub(r'\D', '', н['номер'])[-10:])
        if к:
            из_кэша.setdefault((к[0], к[2]), [к[1], []])[1].append(н)
    записи = []
    for н, _ in нет:
        if not any(н in v[1] for v in из_кэша.values()):
            записи.append({'id': н['id'], 'inn': стр['inn'], 'url': стр['url'], 'страница': статус,
                           'найден': False, 'итог': 'не найден' if статус == 'ok' else 'страница недоступна'})
    группы = []
    if найдено:
        группы.append(('живая страница', заголовок, текст, найдено))
    for (url_к, ts), (текст_к, номера_к) in из_кэша.items():
        группы.append(('кэш обхода %s: %s' % (ts[:10], url_к[:100]), '', текст_к,
                       [(н, MP.найти(текст_к, re.sub(r'\D', '', н['номер'])[-10:])) for н in номера_к]))
    for откуда, загол, текст_г, пары in группы:
        for i in range(0, len(пары), КУСОК_НОМЕРОВ):
            кусок = пары[i:i + КУСОК_НОМЕРОВ]
            фрагмент = окна(текст_г, [п for _, позиции in кусок for п in позиции[:2]])
            ответы = спросить(стр, загол, фрагмент, [н for н, _ in кусок])
            for j, (н, позиции) in enumerate(кусок):
                о = ответы.get(j + 1) if 'ошибка' not in ответы else None
                з = {'id': н['id'], 'inn': стр['inn'], 'url': стр['url'], 'страница': статус,
                     'найден': True, 'проверено_по': откуда}
                if о is None:
                    з.update({'итог': 'ошибка модели', 'ошибка': ответы.get('ошибка', 'нет ответа')})
                else:
                    з.update({'есть': о.get('есть'), 'фио': (о.get('фио') or '')[:80],
                              'должность': (о.get('должность') or '')[:120],
                              'класс': о.get('класс') if о.get('класс') in КЛАССЫ else 'другое',
                              'компания_та': о.get('компания_та', ''), 'итог': 'сверен'})
                    п0 = позиции[0] if позиции else 0
                    з['контекст'] = re.sub(r'\s+', ' ', текст_г[max(0, п0 - 160):п0 + 60])
                записи.append(з)
    записать(записи)


def main():
    повтор = '--povtor' in sys.argv
    вход = json.load(io.open(ВХОД, encoding='utf-8'))
    сделано = {}
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                сделано[з['id']] = з.get('итог')
            except ValueError:
                pass
    очередь = []
    for стр in вход:
        ост = [н for н in стр['номера'] if н['id'] not in сделано
               or сделано[н['id']] == 'ошибка модели'
               or (повтор and сделано[н['id']] == 'страница недоступна')]
        if ост:
            очередь.append(dict(стр, номера=ост))
    print('страниц', len(вход), 'в очереди', len(очередь), flush=True)
    t0 = time.time()
    счёт = [0]

    def один(стр):
        try:
            страница(стр)
        except Exception as e:  # noqa: BLE001
            print('сбой', стр['url'][:80], repr(e)[:100], flush=True)
        счёт[0] += 1
        if счёт[0] % 200 == 0:
            print('готово страниц %d за %d мин' % (счёт[0], (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(один, очередь))
    print('готово', flush=True)


if __name__ == '__main__':
    main()
