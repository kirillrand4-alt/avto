# -*- coding: utf-8 -*-
"""Опись всех боевых модулей через провайдера: карточка на каждый файл.

Владелец строит систему, где вбивается название компании или ИНН — и по ней
собирается всё: тендеры, контактные лица, новости. При этом каждый модуль
должен запускаться и отдельно, по списку компаний. Чтобы это собрать, нужна
опись: что модуль даёт, куда пишет, зовёт ли модель и МОЖНО ЛИ его натравить
на произвольный список ИНН.

ПОЧЕМУ ПРОВАЙДЕР, А НЕ Я. Правило владельца: всю тяжёлую работу — через
провайдерский API. 161 файл прочитать и описать — это ровно она. Своими
токенами делаются только сборка и проверка выборки, где нужно понимание
архитектуры целиком.

МОДЕЛИ по замеру владельца от 02.08: свободный текст разбирает
`gemini-3.6-flash`. Четыре самых больших модуля (enrich_contacts 9048 строк,
news_scan 1876, browser_probe 1150, enrich_db 901) идут к `claude-fable-5`:
там надо не пересказать докстринг, а понять устройство диспетчера операций.

БОЛЬШИЕ ФАЙЛЫ НЕ РЕЖЕМ ПОПОЛАМ. Обрезка по первым N килобайтам даёт карточку
по началу файла, а самое важное — ветки операций и запись в базу — лежит в
середине. Поэтому у больших модулей извлекается СКЕЛЕТ: докстринг, константы,
сигнатуры функций и все ветки `args.get('op') == '...'` с первой строкой
каждой. Так модель видит устройство целиком, а не первую двадцатую часть.

Прогон резюмируемый: готовые карточки лежат в jsonl и повторно не оплачиваются.

Запуск: python opis_moduley.py [--potok N] [--lim N] [--zanovo]
"""
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

КОРЕНЬ = os.path.dirname(os.path.abspath(__file__))
ВЫХОД = os.path.join(КОРЕНЬ, 'MODULI')
ЖУРНАЛ = os.path.join(ВЫХОД, 'karty.jsonl')
КЛЮЧ = os.environ.get('PROVIDER_API_KEY', '')
БАЗА_API = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
БЫСТРАЯ = 'gemini-3.6-flash'
УМНАЯ = 'claude-fable-5'
ПОРОГ_СКЕЛЕТА = 60_000        # символов исходника, после которых берём скелет
_ПЕЧАТЬ = threading.Lock()


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


ПОТОК = арг('--potok', 8)
ЛИМ = арг('--lim', 400)
ЗАНОВО = '--zanovo' in sys.argv


def файлы():
    """Боевые модули. Одноразовые замеры (_probe_, _ops_, _zamer_) пропускаем.

    Исключение оговорено отдельно: если замер — единственная реализация канала
    (так вышло с 2ГИС: пять скриптов-замеров и ни одного боевого), он всё
    равно попадает в опись, потому что иначе канал выглядит несуществующим.
    """
    сп = []
    for папка in ('.', 'ops', 'panel_centro'):
        d = os.path.join(КОРЕНЬ, папка)
        if not os.path.isdir(d):
            continue
        for имя in sorted(os.listdir(d)):
            if not имя.endswith('.py'):
                continue
            if имя.startswith('_') and 'map_2gis3' not in имя:
                continue
            сп.append(os.path.relpath(os.path.join(d, имя), КОРЕНЬ))
    для_справки = os.path.join(КОРЕНЬ, '..', 'gen_provider.py')
    if os.path.exists(для_справки):
        сп.append(os.path.relpath(для_справки, КОРЕНЬ))
    return сп


def скелет(текст):
    """Устройство файла: докстринг, константы, сигнатуры, ветки операций."""
    строки = текст.splitlines()
    взято, в_докстринге = [], False
    for i, с in enumerate(строки):
        if i < 60:
            взято.append(с)
            if с.strip().startswith('"""') and i:
                в_докстринге = not в_докстринге
            continue
        if re.match(r'^(def |class |[А-ЯA-Z_]{3,}\s*=|@)', с):
            взято.append(f'{i + 1}: {с.rstrip()}')
        elif re.search(r"args\.get\('op'\)\s*==|elif\s+op\s*==|if\s+op\s*==", с):
            взято.append(f'{i + 1}: {с.strip()}')
            for j in range(i + 1, min(i + 4, len(строки))):
                if строки[j].strip().startswith('#') or строки[j].strip():
                    взято.append(f'      {строки[j].strip()[:110]}')
                    break
    return '\n'.join(взято)[:70_000]


ВОПРОС = (
    'Ты составляешь техническую опись модуля. Отвечай СТРОГО одним JSON-объектом '
    'без пояснений вокруг.\n\n'
    'Поля:\n'
    '"naznachenie" — что делает модуль, 1-2 предложения по существу;\n'
    '"vhod" — что подаётся: аргументы командной строки, файлы, таблицы;\n'
    '"vyhod" — куда пишет результат: таблицы enrich.db, CSV, дроп, база панели;\n'
    '"provayder" — если зовёт LLM, назови МОДЕЛЬ и ЭНДПОИНТ '
    '(/v1/messages с x-api-key либо /v1/chat/completions с Bearer); иначе "нет";\n'
    '"po_spisku" — можно ли натравить на ПРОИЗВОЛЬНЫЙ список ИНН: как именно '
    '(параметр, файл целей) либо что мешает (путь зашит константой — назови её);\n'
    '"po_odnoy_kompanii" — можно ли запустить по ОДНОМУ ИНН и что для этого нужно;\n'
    '"sostoyanie" — одно из: боевой, частично, замер, брошен;\n'
    '"zavisimosti" — какие свои модули импортирует и что нужно в окружении;\n'
    '"ogranicheniya" — известные ограничения, чего модуль НЕ делает.\n\n'
    'ГЛАВНОЕ: "po_spisku" и "po_odnoy_kompanii" — ради них опись и делается. '
    'Смотри код, а не докстринг: докстринг может отставать. Если в файле дан '
    'СКЕЛЕТ (номера строк и сигнатуры), так и скажи в ogranicheniya, что вывод '
    'сделан по скелету.\n\nФАЙЛ: '
)


def спросить(модель, промпт):
    if модель.startswith('claude'):
        тело = json.dumps({'model': модель, 'max_tokens': 1500, 'stream': True,
                           'messages': [{'role': 'user', 'content': промпт}]},
                          ensure_ascii=False).encode('utf-8')
        зпр = urllib.request.Request(
            БАЗА_API + '/v1/messages', data=тело, method='POST',
            headers={'x-api-key': КЛЮЧ, 'anthropic-version': '2023-06-01',
                     'content-type': 'application/json',
                     'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
        куски = []
        with urllib.request.urlopen(зпр, timeout=300) as о:
            for сыр in о:
                с = сыр.decode('utf-8', 'replace').strip()
                if not с.startswith('data:'):
                    continue
                try:
                    ев = json.loads(с[5:].strip())
                except Exception:  # noqa: BLE001
                    continue
                if ев.get('type') == 'content_block_delta':
                    куски.append((ев.get('delta') or {}).get('text', ''))
        return ''.join(куски)
    тело = json.dumps({'model': модель, 'max_tokens': 1500,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    зпр = urllib.request.Request(
        БАЗА_API + '/v1/chat/completions', data=тело, method='POST',
        headers={'Authorization': 'Bearer ' + КЛЮЧ,
                 'Content-Type': 'application/json',
                 'User-Agent': 'curl/8.5.0'})
    with urllib.request.urlopen(зпр, timeout=300) as о:
        д = json.loads(о.read().decode('utf-8', 'replace'))
    return д['choices'][0]['message']['content'] or ''


def джейсон(текст):
    м = re.search(r'\{.*\}', текст or '', re.S)
    if not м:
        return {}
    try:
        return json.loads(м.group(0))
    except Exception:  # noqa: BLE001
        try:
            return json.loads(re.sub(r',\s*([}\]])', r'\1', м.group(0)))
        except Exception:  # noqa: BLE001
            return {}


def описать(путь):
    полный = os.path.join(КОРЕНЬ, путь)
    сыр = open(полный, encoding='utf-8', errors='replace').read()
    большой = len(сыр) > ПОРОГ_СКЕЛЕТА
    тело = скелет(сыр) if большой else сыр[:70_000]
    модель = УМНАЯ if большой else БЫСТРАЯ
    карта = {'fayl': путь, 'strok': сыр.count('\n') + 1,
             'baytov': len(сыр), 'model_opisi': модель,
             'po_skeletu': большой}
    try:
        ответ = спросить(модель, ВОПРОС + путь +
                         ('\n(дан СКЕЛЕТ файла)\n\n' if большой else '\n\n') + тело)
        карта.update(джейсон(ответ) or {'oshibka': 'модель не вернула JSON'})
    except Exception as e:  # noqa: BLE001
        карта['oshibka'] = f'{type(e).__name__}: {str(e)[:150]}'
    return карта


def main():
    if not КЛЮЧ:
        raise SystemExit('нет PROVIDER_API_KEY')
    os.makedirs(ВЫХОД, exist_ok=True)
    готово = {}
    if os.path.exists(ЖУРНАЛ) and not ЗАНОВО:
        for стр in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                к = json.loads(стр)
            except Exception:  # noqa: BLE001
                continue
            if к.get('fayl') and not к.get('oshibka'):
                готово[к['fayl']] = к
    очередь = [п for п in файлы() if п not in готово][:ЛИМ]
    print(f'боевых модулей: {len(файлы())}, уже описано: {len(готово)}, '
          f'в этот прогон: {len(очередь)}')
    sys.stdout.flush()
    if not очередь:
        print('описывать нечего')
        return

    начало = time.time()
    сделано, ошибок = 0, 0
    with ThreadPoolExecutor(max_workers=ПОТОК) as пул:
        for карта in пул.map(описать, очередь):
            сделано += 1
            # ПИШЕМ СРАЗУ: прогон могут оборвать, и всё, что не легло на диск,
            # придётся оплачивать заново
            with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
                ж.write(json.dumps(карта, ensure_ascii=False) + '\n')
                ж.flush()
                os.fsync(ж.fileno())
            if карта.get('oshibka'):
                ошибок += 1
                if ошибок <= 5:
                    print(f'  {карта["fayl"]}: {карта["oshibka"]}')
            if сделано % 20 == 0:
                with _ПЕЧАТЬ:
                    print(f'  … {сделано}/{len(очередь)}, ошибок {ошибок}, '
                          f'{round(time.time() - начало)} с')
                    sys.stdout.flush()
    print(f'описано {сделано}, ошибок {ошибок}, секунд {round(time.time() - начало)}')


if __name__ == '__main__':
    main()
