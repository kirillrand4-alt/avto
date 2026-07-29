# -*- coding: utf-8 -*-
"""Патч v4: одна дельфин-сессия на весь прогон, фильтр по России, чистка мусора.

Почему не через browser_probe. В v3 пробовали удержать сессию флагом dolphin_keep, но
probe() в конце делает browser.close(), это рвёт CDP-сессию, у профиля пропадает
automation.port — и добавленный reuse уходит на stop+start, то есть на ту же гонку,
из-за которой страницы 2+ падали с HTTP 500. Правильное решение — не дробить обход на
вызовы probe(), а держать Playwright открытым и обойти все URL внутри одного запуска.
Поэтому v4 меняет ТОЛЬКО блок op: он сам поднимает профиль, сам ходит по страницам,
сам гасит. browser_probe.py не трогается совсем (его роль здесь — dolphin_start/stop).

Также в v4:
  - area=113 в URL: hh покрывает СНГ, без фильтра в выдачу лезли ТОО из Казахстана
    и Узбекистана. Фильтруем на уровне запроса, а не постфактум;
  - стоп-лист элементов интерфейса: под тот же data-qa попадали «Компании»,
    «Компании для вас», «Посмотреть»;
  - в ответ отдаётся полный список работодателей (не первые 30) с числом попаданий
    и списком запросов, по которым компания нашлась.

Безопасность: бэкап, замена только блока между строкой op и следующим op, проверка
компиляцией с откатом, идемпотентность (маркер hhscan_v4).

Запуск:
    C:\\Program Files\\Python311\\python.exe C:\\sender\\server\\patch_hh_vacancy_scan_v4.py
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
        # hhscan_v4. ВАКАНСИЯ->КОМПАНИЯ. api.hh.ru отдаёт 403 без токена приложения,
        # поэтому берём человеческую выдачу hh.ru/search/vacancy через дельфин-профиль
        # с мобильным IP. Вакансия по целевой роли = роль на предприятии сейчас
        # освободилась или расширяется, то есть датированный горячий сигнал.
        #
        # ОДНА СЕССИЯ: Playwright держится открытым на весь обход. Через BP.probe так не
        # выходило — probe() в конце делает browser.close(), CDP рвётся, профиль теряет
        # automation.port, и следующий вызов уходил на stop+start (страницы 2+ падали 500).
        import browser_probe as BP
        from playwright.sync_api import sync_playwright
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        pid = profs[0] if profs else None
        queries = args.get('queries') or ['главный инженер', 'главный энергетик',
                                          'главный механик', 'начальник компрессорной станции']
        pages = int(args.get('pages', 1))
        area = str(args.get('area', 113))       # 113 = Россия; hh покрывает и СНГ
        wait_ms = int(args.get('wait_ms', 5000))
        found = {}
        raw_diag = {}

        UI = {'компании', 'компании для вас', 'посмотреть', 'вакансии', 'резюме', 'поиск',
              'все вакансии', 'смотреть все', 'показать ещё', 'ещё', 'работа', 'вход',
              'создать резюме', 'сохранить поиск', 'вакансии на карте'}
        BARE = {'ООО', 'АО', 'ПАО', 'ОАО', 'ЗАО', 'НАО', 'ТОО', 'ОДО', 'ИП', 'ГБУ',
                'МУП', 'ГУП', 'ФГУП', 'АНО', 'ФКУ'}

        def _clean(s):
            s = re.sub(r'<[^>]+>', ' ', s)
            s = s.replace('&nbsp;', ' ').replace('\\xa0', ' ')
            s = re.sub(r'&[a-z]+;', ' ', s)
            return re.sub(r'\\s+', ' ', s).strip()

        def _extract(html):
            raw = re.findall(
                r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>(.*?)</(?:a|span|div)>',
                html, flags=re.S)
            how = 'data_qa'
            if not raw:
                raw = re.findall(
                    r'"employer"\\s*:\\s*\\{(?:[^{}]|\\{[^{}]*\\})*?"name"\\s*:\\s*"([^"]{2,90})"',
                    html)
                how = 'json_employer' if raw else 'none'
            out = []
            for x in raw:
                x = _clean(x)
                if len(x) < 3 or x.isdigit() or x in BARE or x.lower() in UI:
                    continue
                if not re.search(r'[А-Яа-яA-Za-z]', x):
                    continue
                out.append(x[:90])
            return out, how

        cdp_ep, dport = BP.dolphin_start(pid, headless=False, token=tokd)
        try:
            with sync_playwright() as _p:
                browser = _p.chromium.connect_over_cdp(cdp_ep)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                for q in queries[:8]:
                    for pg in range(pages):
                        url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q)
                               + '&area=' + area + '&items_on_page=50&page=' + str(pg))
                        key = f'{q}|{pg}'
                        try:
                            page.goto(url, timeout=45000, wait_until='domcontentloaded')
                            page.wait_for_timeout(wait_ms)
                            html = page.content()
                            emps, how = _extract(html)
                            raw_diag[key] = {'html_len': len(html), 'how': how,
                                             'employers': len(emps)}
                            for e in emps:
                                rec = found.setdefault(e, {'hits': 0, 'queries': []})
                                rec['hits'] += 1
                                if q not in rec['queries']:
                                    rec['queries'].append(q)
                        except Exception as ex:  # noqa: BLE001
                            raw_diag[key] = {'error': f'{type(ex).__name__}: {str(ex)[:80]}'}
                try:
                    page.close()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    BP.dolphin_close_tabs(browser)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
        finally:
            try:
                BP.dolphin_stop(pid, token=tokd)
            except Exception:  # noqa: BLE001
                pass

        out = {'op': 'hh_vacancy_scan', 'profile': pid, 'area': area,
               'employers_found': len(found), 'diag': raw_diag,
               'employers': [{'employer': e, 'hits': v['hits'], 'queries': v['queries']}
                             for e, v in sorted(found.items(),
                                                key=lambda kv: -kv[1]['hits'])]}
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
'''


def main():
    if not os.path.exists(SRC):
        sys.exit(f'не найден {SRC} (переопредели путь через ENRICH_PATH)')
    text = open(SRC, encoding='utf-8').read()
    if START not in text:
        sys.exit('не найден блок hh_vacancy_scan — файл другой, патч не применён')
    i = text.index(START)
    j = text.find(END, i)
    if j < 0:
        sys.exit('не найден следующий op (vk_oauth_dolphin) — границы блока неясны, отказ')
    if 'hhscan_v4' in text[i:j]:
        print('v4 уже применён, ничего не делаю')
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
    print('готово, файл компилируется. browser_probe.py не изменялся.')


if __name__ == '__main__':
    main()
