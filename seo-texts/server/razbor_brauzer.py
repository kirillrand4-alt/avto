# -*- coding: utf-8 -*-
r"""Разбор выдачи, браузерная очередь каталогов (09.10, проба meyer7t; владелец: «не скачивать домены, которые стабильно
отказывают, если отказы даже через браузер» — значит, домены, что отдают страницы браузеру, оставить).

checko.ru скрипту отвечает 429 на каждую страницу, b2b.house показывает ИНН только после JS; обычному браузеру оба
отдают страницу. poisk_razbor.py при POISK_KAT_STOP=1 записывает их страницы как «не скачивалась: только браузер», а
этот шаг открывает их обычным Chromium: headless, без прокси, без антидетекта, капчи НЕ решаются. По одной вкладке на
домен, пауза RAZBOR_BRAUZER_PAUZA с между страницами; капча или RAZBOR_BRAUZER_PREDOHR отказов подряд — домен до конца
запуска останавливается. Не дольше RAZBOR_BRAUZER_MINUT минут за запуск (волна не ждёт браузер часами; остаток — в
следующей волне).

Пишет в <набор>-razbor.jsonl записи {'тип': 'каталог', 'через': 'браузер', ...} (их читают отбор и анализ как обычные).
Запускать, только когда poisk_razbor.py не идёт (один файл): шаг проверяет это сам и выходит.
Резюм: страницы с записью «через браузер» не повторяются.
"""
import collections
import io
import json
import os
import re
import subprocess
import sys
import threading
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
import cc_obhod as CO  # noqa: E402  (ИНН_RX, инн_ок)

НАБОР = os.environ.get('POISK_NABOR', 'poisk')
ВЫХОД = os.path.join(DIR, НАБОР + '-razbor.jsonl')
МИНУТ = float(os.environ.get('RAZBOR_BRAUZER_MINUT', '30'))
ПАУЗА = float(os.environ.get('RAZBOR_BRAUZER_PAUZA', '4'))
ПРЕДОХР = int(os.environ.get('RAZBOR_BRAUZER_PREDOHR', '10'))
МЕТКА = 'не скачивалась: только браузер'
УНП_RX = re.compile(r'УНП\D{0,6}(\d{9})(?!\d)')
ОГРН_RX = re.compile(r'ОГРН\D{0,12}([15]\d{12})(?!\d)')
КАПЧА = re.compile(r'captcha|smartcaptcha|cf-challenge|challenge-platform|Подтвердите, что вы не робот|'
                   r'Проверка браузера|Access denied|Доступ ограничен|Too Many Requests', re.I)
CHROME = [r'C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe',
          r'C:\Program Files\Google\Chrome\Application\chrome.exe']
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def разбор_идёт():
    # 09.10: «(...).Count» из Python возвращал пусто при живом процессе — перечисляем PID (только python: командная
    # строка самого powershell тоже содержит шаблон)
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                        "$_.CommandLine -like '*server\\poisk_razbor.py*' } | ForEach-Object { $_.ProcessId }"],
                       capture_output=True, text=True, timeout=120)
    return bool(r.stdout.split())


def очередь():
    """{домен: [(url, запросы)]} — страницы с меткой «только браузер», ещё не открытые браузером."""
    ждут, сделано = collections.OrderedDict(), set()
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('тип') != 'каталог':
            continue
        if з.get('через') == 'браузер':
            сделано.add(з['url'])
        elif str(з.get('страница') or '').startswith(МЕТКА):
            ждут[з['url']] = (з.get('домен', ''), з.get('запросы') or [])
    по_дом = collections.defaultdict(list)
    for u, (д, qq) in ждут.items():
        if u not in сделано:
            по_дом[д].append((u, qq))
    return по_дом


def домен(д, страницы, до):
    from playwright.sync_api import sync_playwright
    exe = next((p for p in CHROME if os.path.exists(p)), None)
    сч = collections.Counter()
    подряд = 0
    with sync_playwright() as pw:
        б = pw.chromium.launch(headless=True, executable_path=exe)
        стр = б.new_context(locale='ru-RU', viewport={'width': 1366, 'height': 900}).new_page()
        for u, qq in страницы:
            if time.time() > до:
                сч['не успели (лимит времени)'] += 1
                continue
            з = {'тип': 'каталог', 'url': u, 'домен': д, 'через': 'браузер', 'запросы': qq}
            try:
                отв = стр.goto(u, timeout=30000, wait_until='domcontentloaded')
                стр.wait_for_timeout(2500)
                т = стр.inner_text('body')[:300000]
                код = отв.status if отв else 0
                if КАПЧА.search(т[:5000]) or код in (401, 403, 429):
                    з['страница'] = 'отказ браузеру: %s%s' % (код, ' капча' if КАПЧА.search(т[:5000]) else '')
                else:
                    з['страница'] = 'ok'
                    з['инн'] = [м.group(1) for м in CO.ИНН_RX.finditer(т) if CO.инн_ок(м.group(1))][:300]
                    з['огрн'] = list(dict.fromkeys(ОГРН_RX.findall(т)))[:300]
                    з['унп'] = list(dict.fromkeys(УНП_RX.findall(т)))[:300]
            except Exception as e:  # noqa: BLE001
                з['страница'] = 'ошибка браузера: ' + repr(e)[:80]
            if з['страница'] == 'ok':
                подряд = 0
                записать(з)
            else:
                подряд += 1  # отказ не пишем: следующий запуск попробует снова
            сч[з['страница'][:30]] += 1
            if подряд >= ПРЕДОХР or 'капча' in з['страница']:
                сч['домен остановлен: ' + з['страница'][:40]] += 1
                break
            time.sleep(ПАУЗА)
        б.close()
    return д, dict(сч)


def main():
    if разбор_идёт():
        print('готово: poisk_razbor.py идёт — браузерная очередь в этот раз пропущена', flush=True)
        return
    по_дом = очередь()
    print('страниц для браузера', {д: len(v) for д, v in по_дом.items()}, flush=True)
    до = time.time() + МИНУТ * 60
    итог = {}
    потоки = []
    for д, стр in по_дом.items():
        т = threading.Thread(target=lambda д=д, стр=стр: итог.__setitem__(д, домен(д, стр, до)[1]))
        т.start()
        потоки.append(т)
    for т in потоки:
        т.join()
    print('готово', json.dumps(итог, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
