# -*- coding: utf-8 -*-
"""Патч боевой копии enrich_contacts.py: чинит op `hh_vacancy_scan`.

Что было сломано (диагностика 29.07.2026, см. engineers-lens/VERIFY-hh-vakansii.md):
  1. Устаревшие селекторы. HTML приходил целиком (400 000 символов, капчи нет,
     forbidden нет), но регулярки искали `data-qa="...employer..."` и
     `data-qa="...vacancy...title..."` — в текущей разметке hh таких атрибутов нет.
     Итог: employers_found = 0.
  2. Профили не ротировались: op принимает список `dolphin_profiles`, но брал только
     profs[0] и держал его на все запросы. Два запроса из четырёх падали с HTTP 500
     (конфликт повторного запуска того же профиля).

Что делает патч:
  - извлечение в три стратегии по убыванию надёжности: JSON-состояние SPA -> data-qa ->
    разбор текста по префиксам организационных форм. Какая сработала, видно в diag['how'];
  - ротация профилей: каждый запрос идёт своим профилем из переданного списка;
  - останавливаются все использованные профили, а не один.

Безопасность:
  - заменяется ТОЛЬКО блок этого op (границы — строка самого op и следующий op);
  - перед записью делается бэкап enrich_contacts.py.bak-<timestamp>;
  - результат проверяется компиляцией, при ошибке файл откатывается из бэкапа.

Запуск на сервере владельца:
    C:\\Program Files\\Python311\\python.exe C:\\sender\\server\\patch_hh_vacancy_scan.py
Откат: вернуть файл из .bak-<timestamp>.
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
        # ВАКАНСИЯ->КОМПАНИЯ: api.hh.ru отдаёт 403 без токена приложения, поэтому парсим
        # человеческую выдачу hh.ru/search/vacancy через дельфин-профиль с мобильным IP.
        # Вакансия по целевой роли = роль на предприятии сейчас освободилась или растёт.
        import browser_probe as BP
        tokd = _read_secret('DOLPHIN_TOKEN')
        profs = _resolve_dolphin_profiles(args.get('dolphin_profiles'), tokd)
        queries = args.get('queries') or ['главный инженер', 'главный энергетик',
                                          'главный механик', 'начальник компрессорной станции']
        pages = int(args.get('pages', 1))
        found = {}   # employer -> {query, titles:[...]}
        raw_diag = {}
        used = []

        def _extract(html):
            """(pairs, how). Три стратегии по убыванию устойчивости к редизайну hh."""
            # 1) JSON-состояние SPA: устойчиво к смене вёрстки
            emps = re.findall(
                r'"employer"\\s*:\\s*\\{(?:[^{}]|\\{[^{}]*\\})*?"name"\\s*:\\s*"([^"]{2,90})"', html)
            if emps:
                return [(e, '') for e in emps], 'json_employer'
            # 2) прежние data-qa (вдруг вернут)
            emps = re.findall(
                r'data-qa="[^"]*(?:employer|company-name)[^"]*"[^>]*>([^<]{2,80})<', html)
            if emps:
                titles = re.findall(
                    r'data-qa="[^"]*vacancy[^"]*(?:title|name)[^"]*"[^>]*>([^<]{3,120})<', html)
                return ([(e, titles[i] if i < len(titles) else '')
                         for i, e in enumerate(emps)], 'data_qa')
            # 3) текст: строки, начинающиеся с организационной формы
            txt = re.sub(r'<(script|style)[^>]*>.*?</\\1>', ' ', html, flags=re.S | re.I)
            txt = re.sub(r'<[^>]+>', '\\n', txt)
            out = []
            for line in txt.split('\\n'):
                line = re.sub(r'\\s+', ' ', line).strip()
                if re.match(r'^(ООО|АО|ПАО|ОАО|ЗАО|НАО|ГБУ|ГАУ|МУП|ГУП|ФГУП|АНО|Филиал)\\b',
                            line) and len(line) < 120:
                    out.append((line, ''))
            return out, 'text'

        for qi, q in enumerate(queries[:6]):
            pid = profs[qi % len(profs)] if profs else None   # ротация профилей
            if pid and pid not in used:
                used.append(pid)
            for pg in range(pages):
                url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q)
                       + '&items_on_page=50&page=' + str(pg))
                try:
                    r = BP.probe({'url': url, 'return_html': True, 'html_cap': 400000,
                                  'wait_ms': 5000, 'screenshot': False, 'solve': True,
                                  'dolphin_profile': pid, 'dolphin_token': tokd})
                    html = r.get('html') or ''
                    pairs, how = _extract(html)
                    if q not in raw_diag:
                        raw_diag[q] = {'html_len': len(html), 'captcha': r.get('captcha_type'),
                                       'how': how, 'pairs': len(pairs), 'profile': pid,
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
        for p in used:
            try:
                BP.dolphin_stop(p, token=tokd)
            except Exception:  # noqa: BLE001
                pass
        out = {'op': 'hh_vacancy_scan', 'profiles': used, 'employers_found': len(found),
               'diag': raw_diag,
               'sample': [{'employer': e, 'query': v['query'], 'titles': v['titles'][:2]}
                          for e, v in list(found.items())[:25]]}
        json.dump(out, sys.stdout, ensure_ascii=False)
        return
'''


def main():
    if not os.path.exists(SRC):
        sys.exit(f'не найден {SRC} (переопредели путь через ENRICH_PATH)')
    text = open(SRC, encoding='utf-8').read()

    if START not in text:
        sys.exit('не найден блок hh_vacancy_scan — файл уже другой, патч не применён')
    i = text.index(START)
    j = text.find(END, i)
    if j < 0:
        sys.exit('не найден следующий op (vk_oauth_dolphin) — границы блока неясны, отказ')

    old = text[i:j]
    if 'json_employer' in old:
        print('патч уже применён, ничего не делаю')
        return

    bak = f'{SRC}.bak-{int(time.time())}'
    shutil.copy2(SRC, bak)
    print(f'бэкап: {bak}')
    print(f'заменяю блок: {len(old)} -> {len(NEW_BLOCK)} символов')

    open(SRC, 'w', encoding='utf-8').write(text[:i] + NEW_BLOCK + '\n' + text[j:])
    try:
        py_compile.compile(SRC, doraise=True)
    except Exception as e:  # noqa: BLE001
        shutil.copy2(bak, SRC)
        sys.exit(f'ОШИБКА КОМПИЛЯЦИИ, файл откачен из бэкапа: {e}')
    print('готово, файл компилируется. Перезапуск службы не нужен: раннер запускает '
          'скрипт заново на каждое задание.')


if __name__ == '__main__':
    main()
