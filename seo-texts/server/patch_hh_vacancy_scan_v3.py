# -*- coding: utf-8 -*-
"""Патч v3: доводит одну дельфин-сессию до рабочего вида и чистит имена работодателей.

Что показал прогон v2 (29.07.2026):
  - ГЛАВНОЕ: html_len = 2 314 318 при capped=False, how=data_qa, 85 работодателей.
    То есть прежние селекторы data-qa НИКОГДА не были сломаны — их ломало усечение
    HTML по html_cap=400000. Первоначальный диагноз «устаревшая разметка» был неверен.
  - Страница 2 падала HTTP 500 по всем запросам. Причина — в самом dolphin_start:
    он ПЕРЕД стартом всегда делает stop, поэтому второй probe гасил только что
    сохранённый профиль и падал на гонке «остановка/запуск».
  - Имена рваные: рядом с «АО Саратовский Завод РМК» лезли «ООО», «2201», «845» —
    регулярка `>([^<]{2,80})<` цепляла фрагменты вложенных тегов и числа рейтингов.

Что делает v3:
  browser_probe.py
    1. dolphin_start(..., reuse=False): при reuse=True и уже поднятом профиле
       возвращает его текущий CDP-порт вместо stop+start;
    2. probe() передаёт reuse=dolphin_keep.
  enrich_contacts.py (блок op hh_vacancy_scan)
    3. извлечение работодателя берёт всё содержимое элемента (включая вложенные теги),
       снимает разметку и схлопывает пробелы;
    4. фильтр мусора: отбрасываются чисто числовые, короче 3 символов и голые
       организационные формы без названия.

Безопасность: бэкапы обоих файлов, проверка компиляцией с откатом, идемпотентность.

Запуск:
    C:\\Program Files\\Python311\\python.exe C:\\sender\\server\\patch_hh_vacancy_scan_v3.py
"""
import os
import py_compile
import shutil
import sys
import time

SRC = os.environ.get('ENRICH_PATH', r'C:\sender\server\enrich_contacts.py')
PROBE = os.environ.get('PROBE_PATH', r'C:\sender\server\browser_probe.py')

# ---------- browser_probe: переиспользование поднятого профиля ----------
START_OLD = """def dolphin_start(profile_id, headless=False, token=None, skip_if_running=False):"""
START_NEW = """def dolphin_start(profile_id, headless=False, token=None, skip_if_running=False,
                  reuse=False):"""

REUSE_ANCHOR = """    if skip_if_running and dolphin_is_running(profile_id, token=token) is True:
        raise RuntimeError(f'profile {profile_id} busy (уже запущен)')"""
REUSE_NEW = """    if skip_if_running and dolphin_is_running(profile_id, token=token) is True:
        raise RuntimeError(f'profile {profile_id} busy (уже запущен)')
    if reuse:
        # одна сессия на прогон: если профиль уже поднят — отдаём его текущий CDP-порт.
        # Без этого dolphin_start ниже сделает stop+start и уронит удерживаемую сессию.
        try:
            _d = _dolphin_req('GET', f'browser_profiles/{profile_id}', timeout=10, token=token)
            _au = (_d or {}).get('automation') or {}
            if _au.get('port'):
                _p, _ws = _au['port'], _au.get('wsEndpoint')
                return (f'ws://127.0.0.1:{_p}{_ws}' if _ws else f'http://127.0.0.1:{_p}'), _p
        except Exception:  # noqa: BLE001
            pass"""

CALL_OLD = """            cdp_ep, dport = dolphin_start(dolphin_pid, headless=bool(args.get('headless_dolphin', False)),
                                          token=args.get('dolphin_token'))"""
CALL_NEW = """            cdp_ep, dport = dolphin_start(dolphin_pid, headless=bool(args.get('headless_dolphin', False)),
                                          token=args.get('dolphin_token'),
                                          reuse=bool(args.get('dolphin_keep')))"""

# ---------- enrich_contacts: чистое извлечение ----------
EXTRACT_OLD = """            emps = re.findall(
                r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>([^<]{2,80})<', html)
            if emps:
                titles = re.findall(
                    r'data-qa="[^"]*vacancy[^"]*(?:title|name)[^"]*"[^>]*>([^<]{3,120})<', html)
                return ([(e, titles[i] if i < len(titles) else '')
                         for i, e in enumerate(emps)], 'data_qa')"""
EXTRACT_NEW = """            def _clean(s):
                s = re.sub(r'<[^>]+>', ' ', s)
                s = s.replace('&nbsp;', ' ').replace('\\xa0', ' ')
                s = re.sub(r'&[a-z]+;', ' ', s)
                return re.sub(r'\\s+', ' ', s).strip()

            BARE = {'ООО', 'АО', 'ПАО', 'ОАО', 'ЗАО', 'НАО', 'ТОО', 'ОДО', 'ИП', 'ГБУ',
                    'МУП', 'ГУП', 'ФГУП', 'АНО', 'ФКУ'}
            raw = re.findall(
                r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
                html, flags=re.S)
            emps = []
            for x in raw:
                x = _clean(x)
                if len(x) < 3 or x.isdigit() or x in BARE:
                    continue          # числа рейтингов и голые орг-формы без названия
                emps.append(x[:90])
            if emps:
                traw = re.findall(
                    r'data-qa="[^"]*vacancy[^"]*(?:title|name)[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
                    html, flags=re.S)
                titles = [t for t in (_clean(t) for t in traw) if len(t) > 2]
                return ([(e, titles[i] if i < len(titles) else '')
                         for i, e in enumerate(emps)], 'data_qa')"""


def _patch(path, pairs, marker, label):
    """pairs: [(old, new), ...]. Все old должны встретиться ровно один раз."""
    if not os.path.exists(path):
        print(f'ПРОПУСК {label}: не найден {path}')
        return False
    t = open(path, encoding='utf-8').read()
    if marker in t:
        print(f'{label}: v3 уже применён')
        return False
    for old, _ in pairs:
        n = t.count(old)
        if n != 1:
            print(f'{label}: фрагмент найден {n} раз (нужно 1), НЕ ПАТЧУ:\n    {old[:70]}...')
            return False
    bak = f'{path}.bak-{int(time.time())}'
    shutil.copy2(path, bak)
    for old, new in pairs:
        t = t.replace(old, new, 1)
    open(path, 'w', encoding='utf-8').write(t)
    try:
        py_compile.compile(path, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, path)
        sys.exit(f'{label}: ОШИБКА КОМПИЛЯЦИИ, откачен из {bak}: {e}')
    print(f'{label}: пропатчен (бэкап {bak})')
    return True


def main():
    _patch(PROBE,
           [(START_OLD, START_NEW), (REUSE_ANCHOR, REUSE_NEW), (CALL_OLD, CALL_NEW)],
           marker='reuse=False):', label='browser_probe')
    _patch(SRC, [(EXTRACT_OLD, EXTRACT_NEW)],
           marker="BARE = {'ООО'", label='enrich_contacts')
    print('готово.')


if __name__ == '__main__':
    main()
