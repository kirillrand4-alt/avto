# -*- coding: utf-8 -*-
# 19.10, владелец: «проверь номера по факту присутствия на странице» — база холодного прозвона (сервис). Механика
# meyer_nalichie (живая страница-источник, номер в любом написании, контекст, чья страница), вход/выход свои.
# Особые источники: карточка checko — через прокси владельца (cc_checko_proxy); декларация ФСА — страница pub.fsa.gov.ru
# рисуется скриптом, поэтому «страница» = карточка декларации из API ФСА (те же данные, что видит браузер).
# Вход: дроп hz-nalichie-vhod.json ({url, inn, номера:[{id, номер}]}). Выход: hz\hz-nalichie.jsonl (fsync, резюм) + дроп.
import json, os, re, shutil, sys, time
DIR = r'C:\sender\server'
if __name__ == '__main__' and '--vnutri' not in sys.argv:
    import subprocess
    лог = os.path.join(DIR, 'hz', 'hz_nalichie_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, 'hz', 'hz_nalichie.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                             close_fds=False, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    time.sleep(60)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-600:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import cc_checko_proxy as CP  # noqa: E402
import fsa_pilot_orehi as F  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

MN.ВХОД = r'C:\seostat\drop\drop-storage\hz-nalichie-vhod.json'
MN.ВЫХОД = os.path.join(DIR, 'hz', 'hz-nalichie.jsonl')
MN.ПОТОКОВ = 16
_обычное = MN.скачать
_прокси = []
_фса = {}


def скачать(url):
    if 'checko.ru/' in url:
        if not _прокси:
            _прокси.extend(CP.Прокси(x) for x in json.load(open(os.path.join(DIR, 'checko-proxies.json'))))
            for x in _прокси:
                x.пауза, x.пауза_429 = 8.0, 60
        px = _прокси[hash(url) % len(_прокси)]
        код, html = px.get(url)
        return ('ok' if код == 200 and html else 'ошибка %s' % код), html or '', 'checko'
    м = re.search(r'pub\.fsa\.gov\.ru/rds/declaration/view/(\d+)', url)
    if м:
        if 'H2' not in _фса or time.time() - _фса['t'] > 1200:
            _фса['H2'], _фса['t'] = F.вход(), time.time()
        d = F.запрос(_фса['H2'], '/api/v1/rds/common/declarations/%s' % м.group(1))
        if not d:
            return 'ошибка API ФСА', '', 'декларация ФСА'
        return 'ok', json.dumps({k: d.get(k) for k in ('applicant', 'manufacturer')}, ensure_ascii=False), 'декларация ФСА (API)'
    return _обычное(url)


MN.скачать = скачать
MN.main()
shutil.copyfile(MN.ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', 'hz-nalichie.jsonl'))
print('===ИТОГ=== готово', flush=True)
