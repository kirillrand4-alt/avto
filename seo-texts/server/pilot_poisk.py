# -*- coding: utf-8 -*-
r"""Пилот плана Meyer, шаг 1 — поиск по каталогу запросов: Яндекс И Google, с листанием страниц.

Проверено 08.10: xmlriver отдаёт 10 результатов на страницу, groupby=100 игнорируется — глубже только
листанием (`page=`). Правила глубины:
  * насыщение: если на странице >= НАСЫЩЕНИЕ сайтов-не-агрегаторов — берём следующую страницу (до СТРАНИЦ);
  * тест глубины: часть шаблонов — всегда страницы 1..3 (замер, сколько нового дают страницы 2–3).
Журнал (fsync, резюм по (движок, страница, запрос)): C:\sender\server\pilot-serp.jsonl -> копия на дроп.
Задачи: C:\seostat\drop\drop-storage\pilot-zadachi.json (pilot_zadachi.py: группы K1..X1, у задачи — движки и
«страниц»: 0 — правило насыщения, 1 — только первая, 3 — принудительно 3). Стоп при балансе ниже резерва.
"""
import io
import json
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
ВЫХОД = os.path.join(DIR, 'pilot-serp.jsonl')
ПОТОКОВ = int(os.environ.get('PILOT_POTOKOV', '8'))
СТРАНИЦ = 3
НАСЫЩЕНИЕ = 6
U = os.environ.get('XMLRIVER_USER', '')
K = os.environ.get('XMLRIVER_KEY', '')
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_лок = threading.Lock()
СТОП = {'стоп': ''}
АГРЕГАТ = re.compile(r'(yandex\.|ya\.ru|google\.|youtube\.|vk\.(com|ru)|ok\.ru|t\.me|dzen\.ru|wikipedia|avito|ozon\.|'
                     r'wildberries|2gis|zoon\.|flamp|otzovik|hh\.ru|superjob|rabota|rusprofile|checko|list-org|'
                     r'zachestnyibiznes|sbis|audit-it|rbc\.ru|kontur|orgpage|spravker|all\.biz|pulscen|tiu\.ru|b2b|'
                     r'tender|zakupki|agroserver|regtorg|productcenter|selhozproizvoditeli|miltor|xn--|'
                     r'news|novosti|ria\.ru|tass|kommersant|interfax|vedomosti)', re.I)


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def чист(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()


def запрос(движок, q, стр):
    """-> (доки, ошибка). стр — номер страницы с 1; страница 1 запрашивается без page (как раньше)."""
    url = 'http://xmlriver.com/search_%s/xml?user=%s&key=%s&query=%s' % (
        движок, urllib.parse.quote(U), urllib.parse.quote(K), urllib.parse.quote(q))
    if стр > 1:  # проверено 08.10: Яндекс page с 0 (page=1 — 2-я стр.), Google с 1 (page=2 — 2-я стр.)
        url += '&page=%d' % (стр - 1 if движок == 'yandex' else стр)
    with _лок:
        СЧЁТ['запросов'] += 1
    xml, ошибка = '', ''
    for попытка in range(4):
        try:
            with НП.open(url, timeout=120) as r:
                xml = r.read(3000000).decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            ошибка = repr(e)[:80]
            time.sleep(5)
            continue
        ош = re.search(r'<error[^>]*>(.*?)</error>', xml, re.S)
        ошибка = чист(ош.group(1)) if ош else ''
        if 'закончились средства' in ошибка or 'недостаточно средств' in ошибка.lower():
            СТОП['стоп'] = ошибка
            return [], ошибка
        if 'перезапрос' in ошибка or 'свободных каналов' in ошибка:
            time.sleep(4)
            continue
        break
    доки = []
    for блок in re.findall(r'<doc>(.*?)</doc>', xml, re.S):
        u = чист((re.search(r'<url>(.*?)</url>', блок, re.S) or [None, ''])[1])
        т = чист((re.search(r'<title>(.*?)</title>', блок, re.S) or [None, ''])[1])
        п = чист((re.search(r'<passage>(.*?)</passage>', блок, re.S) or [None, ''])[1])
        if u:
            доки.append({'url': u, 'title': т[:160], 'текст': п[:300]})
    return доки, ошибка


СЧЁТ = {'запросов': 0}
РЕЗЕРВ = float(os.environ.get('PILOT_REZERV', '26'))  # ₽ на балансе — не тратить (сайты, агенты, news-scan)


def баланс():
    try:
        return float(НП.open('http://xmlriver.com/api/get_balance/?user=%s&key=%s' % (U, K), timeout=30).read(100))
    except Exception:  # noqa: BLE001
        return None


def сайтов(доки):
    return sum(1 for д in доки if not АГРЕГАТ.search(urllib.parse.urlsplit(д['url']).hostname or ''))


def одна(з, сделано):
    q, вид, рег = з['q'], з['вид'], з['рег']
    тест_глубины = з['страниц'] == 3
    for движок in з['движки']:
        for стр in range(1, (з['страниц'] or СТРАНИЦ) + 1):
            if СТОП['стоп']:
                return
            if (движок, стр, q) in сделано:
                доки = сделано[(движок, стр, q)]
            else:
                доки, ош = запрос(движок, q, стр)
                if СТОП['стоп']:
                    return
                записать({'запрос': q, 'вид': вид, 'регион': рег, 'агентов': з['агентов'], 'группа': з['группа'],
                          'движок': движок, 'стр': стр,
                          'доки': доки, 'итог': 'ok' if доки or not ош else 'ошибка', 'ошибка': ош,
                          'тест_глубины': тест_глубины})
            if з['страниц'] == 0 and сайтов(доки) < НАСЫЩЕНИЕ:
                break
            if not доки:
                break


def main():
    задачи = json.load(io.open(os.path.join(ДРОП, 'pilot-zadachi.json'), encoding='utf-8'))
    сделано = {}
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
                if з.get('итог') == 'ok':
                    сделано[(з['движок'], з['стр'], з['запрос'])] = з['доки']
            except ValueError:
                pass
    print('задач', len(задачи), 'в журнале', len(сделано), 'баланс', баланс(), flush=True)
    t0 = time.time()
    n = [0]

    def шаг(з):
        одна(з, сделано)
        n[0] += 1
        if n[0] % 150 == 0:
            б = баланс()
            if б is not None and б < РЕЗЕРВ:
                СТОП['стоп'] = 'баланс %.1f < резерва %.0f' % (б, РЕЗЕРВ)
            print('баланс', б, 'запросов', СЧЁТ['запросов'], flush=True)
        if n[0] % 100 == 0:
            print('%d/%d за %d мин' % (n[0], len(задачи), (time.time() - t0) / 60), flush=True)
            shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'pilot-serp.jsonl'))

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(шаг, задачи))
    shutil.copyfile(ВЫХОД, os.path.join(ДРОП, 'pilot-serp.jsonl'))
    print('готово', json.dumps({'стоп': СТОП['стоп'], 'запросов': СЧЁТ['запросов'], 'баланс': баланс()},
                               ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
