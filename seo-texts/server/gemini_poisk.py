# -*- coding: utf-8 -*-
# 22.10, владелец: «давай попробуем ИНН, контакты и ФИО, выручку за 1 запрос попросить и короткий ответ в JSON» — Gemini
# через провайдера с поиском Google (родной формат generateContent + tools google_search). Проба «Пром Пакинг»: без поиска
# модель выдумала ИНН и ссылки, с поиском — верно за 11 с, 0,011 $. Поэтому ответ без groundingMetadata — выбрасываем.
# Модуль: найти(компания) -> dict; запуск файлом — проба на входном JSON (список компаний) с выходом jsonl (fsync, резюм).
import json, os, re, sys, threading, time, urllib.error, urllib.request

МОДЕЛЬ = os.environ.get('GEMINI_MODEL', 'gemini-3.8-flash')
БАЗА = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')

ПР = '''Найди через поиск Google сведения о российской компании и ответь ТОЛЬКО JSON без пояснений вокруг.
Компания: {имя}. Регион: {рег}.{инн}{сайт}

Нужно:
- "инн": ИНН этой компании (10 или 12 цифр) — только если нашёл в источнике, где совпадают название и регион/адрес;
- "сайт": официальный сайт именно этой компании (не справочник, не маркетплейс, не каталог); если есть только сайт холдинга — укажи его в "сайт_группы";
- "телефоны", "почты": контакты компании с её сайта или из справочников (не больше 5 каждого);
- "руководитель": ФИО и должность руководителя (из ЕГРЮЛ/справочников);
- "лпр": до 5 сотрудников с ФИО и должностью (главный инженер, главный энергетик/механик, начальник производства, снабжение, технолог), только найденные в источниках;
- "выручка": {{"руб": число, "год": год}} — по данным отчётности;
- "источники": до 5 URL, на которых основан ответ.
Ничего не выдумывай: чего не нашёл — null или []. Формат:
{{"инн": null, "сайт": null, "сайт_группы": null, "телефоны": [], "почты": [], "руководитель": {{"фио": null, "должность": null}}, "лпр": [{{"фио": "", "должность": "", "телефон": null, "почта": null}}], "выручка": {{"руб": null, "год": null}}, "источники": []}}'''


def найти(к, ключ=None):
    """к: {'имя', 'регион', 'инн'?, 'сайт'?} -> {'ответ': dict|None, 'запросы', 'источников', 'токены', 'сек', 'ошибка'}"""
    ключ = ключ or os.environ['PROVIDER_API_KEY']
    текст = ПР.format(имя=к['имя'], рег=к.get('регион') or '—', инн=('\nИНН: %s.' % к['инн']) if к.get('инн') else '',
                      сайт=('\nВероятный сайт: %s.' % к['сайт']) if к.get('сайт') else '')
    тело = {'contents': [{'role': 'user', 'parts': [{'text': текст}]}], 'tools': [{'google_search': {}}]}
    з = urllib.request.Request('%s/v1beta/models/%s:generateContent' % (БАЗА, МОДЕЛЬ), data=json.dumps(тело).encode(),
                               headers={'x-goog-api-key': ключ, 'Authorization': 'Bearer ' + ключ,
                                        'Content-Type': 'application/json', 'User-Agent': 'curl/8.5.0'})
    t0 = time.time()
    # 22.10, проба 80: часть ответов приходит без groundingMetadata (85–110 с, много «размышлений») — похоже, шлюз раздаёт
    # запросы на разные апстримы, и не все выполняют поиск. Такой ответ повторяем (до 3 раз); последний без поиска —
    # сохраняем с пометкой «поиск: false» для сравнения, в работу не берём
    for заход in range(3):
        рез = _один(з)
        # без groundingMetadata, но с источниками и верными ИНН (проба: 7 из 8) — шлюз, видимо, сам подмешивает выдачу в
        # запрос (promptTokenCount 600–3200 при промпте ~550): берём, помечаем «поиск: по источникам»
        if рез.get('поиск') or (рез['ответ'] and (рез['ответ'].get('источники') or [])):
            if not рез.get('поиск'):
                рез['поиск'] = 'по источникам'
            break
        if рез['ошибка'].startswith('HTTP 4') and not рез['ошибка'].startswith('HTTP 429'):
            break
    рез['заходов'] = заход + 1
    рез['сек'] = round(time.time() - t0, 1)
    return рез


def _один(з):
    рез = {'ответ': None, 'поиск': False, 'запросы': [], 'источников': 0, 'токены': None, 'ошибка': ''}
    for попытка in range(3):
        try:
            d = json.loads(urllib.request.urlopen(з, timeout=300).read().decode('utf-8', 'replace'))
            break
        except urllib.error.HTTPError as e:
            рез['ошибка'] = 'HTTP %s %s' % (e.code, e.read()[:200])
        except Exception as e:  # noqa: BLE001
            рез['ошибка'] = repr(e)[:200]
        time.sleep(20 * (попытка + 1))  # 524 Cloudflare шлюза при 24 потоках — ждём
    else:
        return рез
    рез['ошибка'] = ''
    c = (d.get('candidates') or [{}])[0]
    г = c.get('groundingMetadata') or {}
    рез.update(поиск=bool(г), запросы=г.get('webSearchQueries') or [], источников=len(г.get('groundingChunks') or []),
               токены=d.get('usageMetadata'))
    ответ = ''.join(p.get('text', '') for p in (c.get('content') or {}).get('parts') or [])
    m = re.search(r'\{.*\}', ответ, re.S)
    try:
        рез['ответ'] = json.loads(m.group(0)) if m else None
    except ValueError:
        рез['ошибка'] = 'ответ не JSON'
        рез['сырой'] = ответ[:300]
    if not г:
        рез['ошибка'] = (рез['ошибка'] + '; ' if рез['ошибка'] else '') + 'нет groundingMetadata (поиск не подтверждён)'
    return рез

if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    вход, выход = sys.argv[1], sys.argv[2]
    кк = json.load(open(вход, encoding='utf-8'))
    уже = set()
    if os.path.exists(выход):
        уже = {json.loads(s)['ключ'] for s in open(выход, encoding='utf-8') if s.strip()}
    лок = threading.Lock()

    def одна(к):
        р = найти(к)
        with лок, open(выход, 'a', encoding='utf-8') as f:
            f.write(json.dumps(dict(р, ключ=к['ключ']), ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        print(к['ключ'], р['сек'], 'с', 'поиск' if р.get('поиск') else 'БЕЗ поиска', 'заходов', р.get('заходов'), (р['ответ'] or {}).get('инн'), р['ошибка'][:60], flush=True)
    with ThreadPoolExecutor(int(os.environ.get('GEMINI_POTOKOV', '10'))) as ex:
        list(ex.map(одна, [к for к in кк if к['ключ'] not in уже]))
