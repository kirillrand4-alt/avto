# -*- coding: utf-8 -*-
"""Патч v2 боевой копии enrich_contacts.py: op `hh_vacancy_scan`.

Что показал прогон v1 (29.07.2026): employers_found=0 при `how="text"`, `pairs=0`
и **html_len ровно 400000** — то есть HTML упирался в html_cap и обрезался. Карточки
вакансий в разметке hh лежат дальше лимита, поэтому не находила ни одна из трёх стратегий.
Чинилось не то: разбор был не главной причиной, главная — усечение.

Что меняет v2:
  1. html_cap поднят до 4 000 000 — обрезания больше нет.
  2. ОДНА дельфин-сессия на весь прогон вместо старта/стопа на каждый запрос
     (замечание владельца). Профиль поднимается один раз, все запросы и страницы идут
     внутри него, стоп один раз в конце. Это же убирает конфликт повторного запуска,
     ради которого в v1 вводилась ротация.
  3. Диагностика по маркерам: сколько в HTML вхождений '"employer"', 'data-qa=',
     'ООО', 'vacancy' и каков реальный html_len. Если разбор снова не сработает,
     из diag будет видно, что в странице есть, а чего нет — без ещё одного круга гаданий.

Безопасность: заменяется только блок этого op, перед записью бэкап, после записи
проверка компиляцией с откатом при ошибке. Идемпотентен (маркер hhscan_v2).

Запуск на сервере владельца:
    C:\\Program Files\\Python311\\python.exe C:\\sender\\server\\patch_hh_vacancy_scan_v2.py
"""
import os
import py_compile
import shutil
import sys
import time

SRC = os.environ.get('ENRICH_PATH', r'C:\sender\server\enrich_contacts.py')
START = "    if args.get('op') == 'hh_vacancy_scan':"
END = "    if args.get('op') == 'vk_oauth_dolphin':"

NEW_BLOCK = '''    if args.get('op') == 'hh_vacancy_scan':
        # hhscan_v2. ВАКАНСИЯ->КОМПАНИЯ: api.hh.ru отдаёт 403 без токена приложения,
        # поэтому парсим человеческую выдачу hh.ru/search/vacancy через дельфин-профиль
        # с мобильным IP. Вакансия по целевой роли = роль на предприятии сейчас
        # освободилась или расширяется, то есть датированный горячий сигнал.
        # ОДНА сессия профиля на весь прогон: старт/стоп на каждый запрос стоил ~40 с.
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        pid = profs[0] if profs else None
        queries = args.get('queries') or ['главный инженер', 'главный энергетик',
                                          'главный механик', 'начальник компрессорной станции']
        pages = int(args.get('pages', 1))
        cap = int(args.get('html_cap', 4000000))
        found = {}
        raw_diag = {}

        def _extract(html):
            """(pairs, how). Стратегии по убыванию устойчивости к редизайну hh."""
            emps = re.findall(
                r'"employer"\\s*:\\s*\\{(?:[^{}]|\\{[^{}]*\\})*?"name"\\s*:\\s*"([^"]{2,90})"', html)
            if emps:
                return [(e, '') for e in emps], 'json_employer'
            emps = re.findall(r'"companyName"\\s*:\\s*"([^"]{2,90})"', html)
            if emps:
                return [(e, '') for e in emps], 'json_companyName'
            emps = re.findall(
                r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>([^<]{2,80})<', html)
            if emps:
                titles = re.findall(
                    r'data-qa="[^"]*vacancy[^"]*(?:title|name)[^"]*"[^>]*>([^<]{3,120})<', html)
                return ([(e, titles[i] if i < len(titles) else '')
                         for i, e in enumerate(emps)], 'data_qa')
            txt = re.sub(r'<(script|style)[^>]*>.*?</\\1>', ' ', html, flags=re.S | re.I)
            txt = re.sub(r'<[^>]+>', '\\n', txt)
            out = []
            for line in txt.split('\\n'):
                line = re.sub(r'\\s+', ' ', line).strip()
                if re.match(r'^(ООО|АО|ПАО|ОАО|ЗАО|НАО|ГБУ|ГАУ|МУП|ГУП|ФГУП|АНО|Филиал)\\b',
                            line) and len(line) < 120:
                    out.append((line, ''))
            return out, 'text'

        for q in queries[:8]:
            for pg in range(pages):
                url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q)
                       + '&items_on_page=50&page=' + str(pg))
                try:
                    r = BP.probe({'url': url, 'return_html': True, 'html_cap': cap,
                                  'wait_ms': 6000, 'screenshot': False, 'solve': True,
                                  'dolphin_profile': pid, 'dolphin_token': tokd,
                                  'dolphin_keep': True})
                    html = r.get('html') or ''
                    pairs, how = _extract(html)
                    if q not in raw_diag:
                        raw_diag[q] = {'html_len': len(html), 'capped': len(html) >= cap,
                                       'captcha': r.get('captcha_type'), 'how': how,
                                       'pairs': len(pairs),
                                       'm_employer': html.count('"employer"'),
                                       'm_company': html.count('"companyName"'),
                                       'm_dataqa': html.count('data-qa='),
                                       'm_ooo': html.count('ООО'),
                                       'forbidden': 'forbidden' in html[:2000].lower()}
                    for emp, ttl in pairs:
                        emp = re.sub(r'\\s+', ' ', emp).strip()
                        if not emp:
                            continue
                        rec = found.setdefault(emp, {'query': q, 'titles': []})
                        if ttl:
                            rec['titles'].append(re.sub(r'\\s+', ' ', ttl).strip()[:80])
                except Exception as e:  # noqa: BLE001
                    raw_diag.setdefault(q, {})['error'] = f'{type(e).__name__}: {str(e)[:70]}'
        try:
            BP.dolphin_stop(pid, token=tokd)
        except Exception:  # noqa: BLE001
            pass
        out = {'op': 'hh_vacancy_scan', 'profile': pid, 'employers_found': len(found),
               'diag': raw_diag,
               'sample': [{'employer': e, 'query': v['query'], 'titles': v['titles'][:2]}
                          for e, v in list(found.items())[:30]]}
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
'''


PROBE = os.environ.get('PROBE_PATH', r'C:\sender\server\browser_probe.py')
PROBE_OLD = """        if dolphin_pid:
            dolphin_stop(dolphin_pid, token=args.get('dolphin_token'))  # освободить слот профиля"""
PROBE_NEW = """        if dolphin_pid and not args.get('dolphin_keep'):
            # dolphin_keep=True: не гасим профиль, чтобы следующий probe() переиспользовал
            # уже поднятую сессию. Старт/стоп профиля стоит ~40 с на запрос.
            dolphin_stop(dolphin_pid, token=args.get('dolphin_token'))  # освободить слот профиля"""


def patch_probe():
    """browser_probe.probe() гасит профиль в конце всегда. Делаем это условным."""
    if not os.path.exists(PROBE):
        print(f'ПРОПУСК: не найден {PROBE}')
        return
    t = open(PROBE, encoding='utf-8').read()
    if 'dolphin_keep' in t:
        print('browser_probe: уже поддерживает dolphin_keep, пропускаю')
        return
    if t.count(PROBE_OLD) != 1:
        print(f'browser_probe: блок гашения не найден однозначно '
              f'(вхождений {t.count(PROBE_OLD)}), НЕ ПАТЧУ — сессия останется '
              f'старт/стоп на запрос')
        return
    bak = f'{PROBE}.bak-{int(time.time())}'
    shutil.copy2(PROBE, bak)
    open(PROBE, 'w', encoding='utf-8').write(t.replace(PROBE_OLD, PROBE_NEW))
    try:
        py_compile.compile(PROBE, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, PROBE)
        sys.exit(f'browser_probe: ОШИБКА КОМПИЛЯЦИИ, откачен из {bak}: {e}')
    print(f'browser_probe: dolphin_keep добавлен (бэкап {bak})')


def main():
    patch_probe()
    if not os.path.exists(SRC):
        sys.exit(f'не найден {SRC} (переопредели путь через ENRICH_PATH)')
    text = open(SRC, encoding='utf-8').read()
    if START not in text:
        sys.exit('не найден блок hh_vacancy_scan — файл другой, патч не применён')
    i = text.index(START)
    j = text.find(END, i)
    if j < 0:
        sys.exit('не найден следующий op (vk_oauth_dolphin) — границы блока неясны, отказ')
    if 'hhscan_v2' in text[i:j]:
        print('v2 уже применён, ничего не делаю')
        return

    bak = f'{SRC}.bak-{int(time.time())}'
    shutil.copy2(SRC, bak)
    print(f'бэкап: {bak}')
    print(f'заменяю блок: {j - i} -> {len(NEW_BLOCK)} символов')
    open(SRC, 'w', encoding='utf-8').write(text[:i] + NEW_BLOCK + '\n' + text[j:])
    try:
        py_compile.compile(SRC, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, SRC)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из бэкапа: {e}')
    print('готово, файл компилируется.')


if __name__ == '__main__':
    main()
