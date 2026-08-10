# -*- coding: utf-8 -*-
"""574 факта держатся на ПЕРЕЧНЕ заключений предприятия, а не на конкретном заключении.

Владелец в пункте 5 просил проверить глазами, куда ведут ссылки. Проверка показала:
ссылка вида `monitor-pb.ru/conclusions?exploiter=ИНН` открывает СПИСОК всех заключений
предприятия. Список рисуется скриптом, текста на странице нет — то есть отдельный факт
(«Центробежный компрессор 32ВЦ-100-9М3, зав. № 95005») такая ссылка поштучно не
доказывает. У остальных 4 570 фактов этого корпуса конкретная ссылка есть, у этих 574 —
нет.

Что делаем: открываем перечень браузером (он и рисуется скриптом), дожидаемся таблицы,
снимаем из неё строки — номер заключения, объект экспертизы, заводской номер и адрес
конкретного заключения. Дальше сопоставление по заводскому номеру делает уже
применялка на стороне базы, здесь только честно снимаем, что показано.

Долговечность: пишем в C:\\sender\\park_perechen.jsonl построчно с fsync.
Резюмируемость: ИНН, по которым уже снято, пропускаем.

Запуск: panel_py, argv = [<сколько ИНН за вызов>]
"""
import json, os, re, sys, time

BAZA = r'C:\sender'
ZAD = os.path.join(BAZA, "park_perechen_inn.json")
OUT = os.path.join(BAZA, 'park_perechen.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
_ZAKL = re.compile(r'/conclusion/(\d+)')


def _hrom():
    for k in (r'C:\sender\pw-browsers', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')):
        if not k or not os.path.isdir(k):
            continue
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _sdelano():
    v = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            for ln in f:
                try:
                    v.add(json.loads(ln)['inn'])
                except Exception:
                    pass
    return v


def _zapisat(s):
    with open(OUT, 'a', encoding='utf-8') as f:
        f.write(json.dumps(s, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def main():
    skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    zad = json.load(open(ZAD, encoding='utf-8'))
    gotovo = _sdelano()
    ochered = [i for i in zad if i not in gotovo][:skolko]
    itog = {'inn_v_zadanii': len(zad), 'k_snyatiyu': len(ochered),
            'snyato': 0, 'strok_vsego': 0, 'pusto': 0, 'oshibki': []}
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox',
                                         '--disable-blink-features=AutomationControlled']}
        if exe:
            kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        ctx = br.new_context(user_agent=UA, locale='ru-RU',
                             viewport={'width': 1500, 'height': 1000},
                             ignore_https_errors=True)
        page = ctx.new_page()
        for inn in ochered:
            u = 'https://monitor-pb.ru/conclusions?exploiter=%s' % inn
            zapis = {'inn': inn, 'perechen': u, 'stroki': [],
                     'ts': time.strftime('%Y-%m-%d %H:%M:%S')}
            try:
                page.goto(u, timeout=90000, wait_until='domcontentloaded')
                # таблица рисуется скриптом: ждём появления ссылок на заключения
                try:
                    page.wait_for_selector('a[href*="/conclusion/"]', timeout=25000)
                except Exception:
                    page.wait_for_timeout(6000)
                # листаем до конца: часть перечней подгружает строки по прокрутке
                for _ in range(6):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(900)
                html = page.content()
                for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S):
                    m = _ZAKL.search(tr)
                    if not m:
                        continue
                    yach = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c)).strip()
                            for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)]
                    zapis['stroki'].append({
                        'zaklyuchenie_id': m.group(1),
                        'ssylka': 'https://monitor-pb.ru/conclusion/' + m.group(1),
                        'yacheyki': [y for y in yach if y][:9]})
                if not zapis['stroki']:
                    itog['pusto'] += 1
                    zapis['pochemu_pusto'] = re.sub(
                        r'\s+', ' ', page.inner_text('body'))[:300]
            except Exception as e:
                zapis['oshibka'] = str(e)[:160]
                itog['oshibki'].append('%s: %s' % (inn, str(e)[:90]))
            _zapisat(zapis)
            itog['snyato'] += 1
            itog['strok_vsego'] += len(zapis['stroki'])
        br.close()
    itog['oshibki'] = itog['oshibki'][:8]
    print(json.dumps(itog, ensure_ascii=False))


if __name__ == '__main__':
    main()
