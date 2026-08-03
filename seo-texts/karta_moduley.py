# -*- coding: utf-8 -*-
"""Карточка на каждый модуль: что делает, входы, выходы, как запустить, можно ли по одному ИНН.

Задача владельца: «вычленить все скрипты, вызовы провайдера и остальное, что используется для
нашей задачи, чтобы можно было использовать для задачи любой. Вбиваю компанию либо ИНН, и по ней
ищется вся информация: тендеры, контактные лица, новости. Чтобы каждый модуль можно было
запустить ОТДЕЛЬНО друг от друга по списку компаний.»

ПОЧЕМУ ЧАСТЬ РАБОТЫ ЗДЕСЬ, А ЧАСТЬ У АГЕНТОВ. Владелец предложил отдать модули провайдеру, если
так не будет хуже. Разделение вышло такое:

- **провайдеру** — описание по тексту: что делает, входы, выходы, команда запуска, роль в системе.
  Это он умеет и стоит копейки;
- **агенту** — то, что требует ЗАМЕРА: сколько строк в выходном файле, каков выход канала в людях
  с личными мобильными, жив ли источник, что именно мешает запуску по одному ИНН. Провайдер
  видит только вставленный текст: он не прочитает CSV и не дёрнет адрес.

Поэтому здесь код сначала СЧИТАЕТ (строки выходных файлов, вызовы провайдера и раннера, признаки
работы по ИНН находятся регулярками по коду), и только потом отдаёт провайдеру собранные факты,
чтобы тот сложил из них карточку. Провайдер ничего не выясняет, он оформляет.

Заслон против выдумки: в промпте запрещено добавлять числа и имена файлов, которых нет во
входных данных. Модель, дописавшая своё, ловится сверкой имён файлов с теми, что нашёл код.

Использование:
    python3 karta_moduley.py                 # все модули корня
    python3 karta_moduley.py --tolko a,b,c   # только названные
    python3 karta_moduley.py --threads 4
"""
import ast
import csv
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
VYHOD = os.path.join(BAZA, 'engineers-lens', 'MODULI')
MODEL = os.environ.get('MODEL_KARTA', 'gemini-3.6-flash')

# Пути к файлам, встречающиеся в коде: 'engineers-lens/xxx.csv', os.path.join(L, 'yyy.csv')
PUT = re.compile(r"['\"]([\w\-/]+\.(?:csv|json|jsonl|md|txt|sqlite))['\"]")
PROVAJDER = re.compile(r'gen_provider|call_model|make_client|G\.call')
RANNER = re.compile(r"run_on_server|RUNNER_CLIENT|KLIENT|'task':\s*'(\w+)'")
ZADACHA = re.compile(r"'task':\s*'(\w+)'")
# Признаки того, что модуль умеет работать по списку: аргумент со списком, фильтр по ИНН
PO_SPISKU = re.compile(r'--spisok|--inn|sys\.argv\[1\]|argparse|--limit|--predel')


def dokstroka(put):
    try:
        d = ast.get_docstring(ast.parse(open(put, encoding='utf-8').read()))
        return (d or '').strip()
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return ''


def strok(put):
    if not os.path.exists(put):
        return None
    try:
        return sum(1 for _ in open(put, encoding='utf-8-sig', errors='replace')) - 1
    except OSError:
        return None


def razobrat_modul(imya):
    """Собрать ФАКТЫ о модуле из кода и с диска. Никаких суждений, только измеримое."""
    put = os.path.join(BAZA, imya)
    kod = open(put, encoding='utf-8', errors='replace').read()
    puti = sorted(set(PUT.findall(kod)))
    fajly = []
    for p in puti:
        for baza in (BAZA, os.path.join(BAZA, 'engineers-lens'),
                     os.path.join(BAZA, 'engineers-lens', 'centro')):
            polnyy = os.path.join(baza, p)
            if os.path.exists(polnyy):
                fajly.append({'put': p, 'strok': strok(polnyy),
                              'bajt': os.path.getsize(polnyy)})
                break
        else:
            fajly.append({'put': p, 'strok': None, 'bajt': None})
    return {
        'imya': imya,
        'bajt': os.path.getsize(put),
        'strok_koda': kod.count('\n') + 1,
        'dokstroka': dokstroka(put)[:6000],
        'provajder': bool(PROVAJDER.search(kod)),
        'modeli': sorted(set(re.findall(r"MODEL\w*\s*=\s*os\.environ\.get\([^,]+,\s*'([^']+)'", kod))),
        'zadachi_rannera': sorted(set(ZADACHA.findall(kod))),
        'fajly': fajly[:24],
        'est_argumenty': sorted(set(re.findall(r"'(--[a-z\-]+)'", kod)))[:14],
        'priznak_po_spisku': bool(PO_SPISKU.search(kod)),
        'funkcii': sorted(set(re.findall(r'^def (\w+)', kod, re.M)))[:20],
    }


PROMPT = """Ты пишешь КАРТОЧКУ МОДУЛЯ для системы сбора данных о промышленных предприятиях.

ЗАЧЕМ. Владелец строит систему: вбивает название компании или ИНН, и по ней собирается вся
информация — закупки и тендеры, контактные лица, новости о назначениях и проектах. Каждый модуль
должен запускаться ОТДЕЛЬНО от других, по одной компании или по списку компаний.

ЧТО ТЕБЕ ДАНО. Факты, снятые с кода и с диска программой: имя файла, его докстрока (авторское
описание), найденные в коде пути к файлам с реальным числом строк, признаки вызова провайдера и
раннера, аргументы командной строки, имена функций.

ЖЁСТКИЕ ПРАВИЛА, нарушение делает карточку вредной:
1. НЕ ВЫДУМЫВАЙ ни одного числа, имени файла, ключа командной строки или функции, которых нет во
   входных данных. Если чего-то не знаешь — напиши «в коде не видно».
2. Не пересказывай докстроку целиком, извлекай из неё смысл.
3. Пиши по-русски, деловым языком, без длинных тире.
4. Про запуск по одному ИНН отвечай честно: если во входных данных нет признака работы по списку,
   так и скажи, и предположи, что минимально надо добавить.

ФОРМАТ ОТВЕТА, строго маркдаун, ровно эти разделы:

## <имя файла>
**Назначение.** Одна-две фразы: что делает и зачем в системе.
**Роль в системе.** Одно из: сбор из внешнего источника, обогащение, классификация, сборка
витрины, проверка, инфраструктура.
**Входы.** Список файлов с числом строк. Если строк нет — пометь «файла нет на диске».
**Выходы.** То же.
**Провайдер.** Модель и что спрашивает, либо «не вызывает».
**Раннер.** Задачи, либо «не вызывает».
**Запуск.** Команда с ключами.
**По одному ИНН или списку.** Да или нет, и что мешает.
**Зависимости.** От кого зависит и кто зависит от него, если видно по путям файлов.

ВХОДНЫЕ ДАННЫЕ (JSON):
"""


def main():
    tolko = None
    if '--tolko' in sys.argv:
        tolko = {x.strip() for x in sys.argv[sys.argv.index('--tolko') + 1].split(',')}
    threads = 4
    if '--threads' in sys.argv:
        threads = int(sys.argv[sys.argv.index('--threads') + 1])
    os.makedirs(VYHOD, exist_ok=True)

    moduli = sorted(f for f in os.listdir(BAZA) if f.endswith('.py'))
    if tolko:
        moduli = [m for m in moduli if m in tolko or m[:-3] in tolko]
    # Уже разобранные агентами с замерами — их карточки богаче, не переписываем.
    gotovo = {f[:-3] + '.py' for f in os.listdir(VYHOD)} if os.path.exists(VYHOD) else set()
    moduli = [m for m in moduli if m not in gotovo]
    print(f'модулей к описанию: {len(moduli)}', file=sys.stderr)

    import gen_provider as G
    G.env = lambda: {'PROVIDER_API_KEY': os.environ['PROVIDER_API_KEY'],
                     'PROVIDER_BASE_URL': os.environ.get('PROVIDER_BASE_URL',
                                                         'https://router.cheap')}
    lock = threading.Lock()
    sch = {'ок': 0, 'сбой': 0, 'выдумка': 0}

    def odin(imya):
        try:
            f = razobrat_modul(imya)
        except Exception as e:  # noqa: BLE001
            return imya, None, f'разбор кода: {type(e).__name__}: {e}'
        try:
            o = G.call_model(MODEL, [{'role': 'user',
                                      'content': PROMPT + json.dumps(f, ensure_ascii=False,
                                                                     indent=1)}], attempts=3)
            txt = ''.join(b.text for b in o.content if b.type == 'text').strip()
        except Exception as e:  # noqa: BLE001
            return imya, None, f'провайдер: {type(e).__name__}: {str(e)[:80]}'
        # заслон: имена файлов в ответе должны быть из входных данных
        nashi = {x['put'] for x in f['fajly']} | {imya}
        chuzhie = [p for p in set(PUT.findall(txt)) if p not in nashi]
        return imya, txt, ('выдуманы пути: ' + ', '.join(chuzhie[:3]) if chuzhie else '')

    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, (imya, txt, err) in enumerate(pool.map(odin, moduli), 1):
            with lock:
                if txt:
                    open(os.path.join(VYHOD, imya[:-3] + '.md'), 'w',
                         encoding='utf-8').write(txt + '\n')
                    sch['выдумка' if err else 'ок'] += 1
                    if err:
                        print(f'  {imya}: {err}', file=sys.stderr)
                else:
                    sch['сбой'] += 1
                    print(f'  СБОЙ {imya}: {err}', file=sys.stderr)
                if i % 10 == 0:
                    print(f'  {i}/{len(moduli)}: {sch}', file=sys.stderr, flush=True)
    print(f'готово: {sch} → {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
