# -*- coding: utf-8 -*-
"""Выкатка фронта панели рассылки в C:\\sender\\web\\dist.

Путь взят не из документации, а из параметров живой службы:
  nssm get SenderPanel AppParameters -> "... --static-dir C:\\sender\\web\\dist"
В репозитории есть и C:\\sender\\sender\\web\\dist — это НЕ то, что раздаётся.

Порядок: бэкап -> распаковка -> ПРОВЕРКА, что index.html ссылается на реально
лежащие файлы -> при провале автоматический откат. Проверка не формальность:
26.07.2026 панель легла ровно на рассинхроне index.html и assets.

Старые бандлы НЕ удаляем: у оператора может быть открыта вкладка на прежней
версии, и удаление файла даёт ей белый экран до перезагрузки.

Запуск: python _ops_deploy_web.py <путь_к_zip> [apply]
"""
import json
import os
import re
import shutil
import sys
import time
import zipfile

DIST = r'C:\sender\web\dist'


def refs_ok(dist):
    """Все /assets/... из index.html обязаны существовать на диске."""
    ih = os.path.join(dist, 'index.html')
    if not os.path.exists(ih):
        return False, ['нет index.html']
    html = open(ih, encoding='utf-8', errors='replace').read()
    bad = []
    refs = sorted(set(re.findall(r'/assets/[A-Za-z0-9._-]+', html)))
    for ref in refs:
        if not os.path.exists(os.path.join(dist, ref.lstrip('/').replace('/', os.sep))):
            bad.append(ref)
    return (not bad), (bad or refs)


def main():
    zip_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\sender\_ops\web-dist-update.zip'
    apply = len(sys.argv) > 2 and sys.argv[2] == 'apply'
    out = {'режим': 'ПРИМЕНЕНИЕ' if apply else 'сухой прогон', 'dist': DIST}

    if not os.path.exists(zip_path):
        out['итог'] = f'нет пакета {zip_path}'
        print(json.dumps(out, ensure_ascii=False))
        return

    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    out['в_пакете'] = names

    ok_before, refs_before = refs_ok(DIST)
    out['до'] = {'ссылки_целы': ok_before, 'ссылки': refs_before}

    if not apply:
        out['итог'] = 'сухой прогон, ничего не менял'
        print(json.dumps(out, ensure_ascii=False))
        return

    bak = f'{DIST}.bak-{int(time.time())}'
    shutil.copytree(DIST, bak)
    out['бэкап'] = bak

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(DIST)
    out['распакован'] = True

    ok_after, refs_after = refs_ok(DIST)
    out['после'] = {'ссылки_целы': ok_after, 'ссылки': refs_after}
    if not ok_after:
        # откат: возвращаем index.html из бэкапа, ассеты не трогаем (они только добавились)
        shutil.copy(os.path.join(bak, 'index.html'), os.path.join(DIST, 'index.html'))
        out['итог'] = 'ПРОВЕРКА НЕ ПРОШЛА -> index.html откачен из бэкапа'
        print(json.dumps(out, ensure_ascii=False))
        return

    # живая проверка через саму панель
    try:
        import urllib.request
        with urllib.request.urlopen('http://127.0.0.1:8091/', timeout=10) as r:
            html = r.read().decode('utf-8', 'replace')
        live = sorted(set(re.findall(r'/assets/[A-Za-z0-9._-]+', html)))
        out['панель_отдаёт'] = live
        checks = {}
        for ref in live:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:8091{ref}', timeout=10) as rr:
                    checks[ref] = f'{rr.status}, {len(rr.read())} б'
            except Exception as e:  # noqa: BLE001
                checks[ref] = f'ОШИБКА {str(e)[:60]}'
        out['проверка_отдачи'] = checks
        out['итог'] = ('ГОТОВО' if all('ОШИБКА' not in v for v in checks.values())
                       else 'панель не отдаёт часть файлов — смотреть выше')
    except Exception as e:  # noqa: BLE001
        out['итог'] = f'файлы на месте, но панель не ответила: {str(e)[:120]}'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
