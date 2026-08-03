# -*- coding: utf-8 -*-
"""Обратный ход `lpr_serp back` заданиями подряд: по человеку ищем ЕГО контакт.

Берёт человека, уже записанного поиском ЛПР, но без телефона и почты, и спрашивает выдачу
запросом «"Фамилия Имя Отчество" "<компания>"» — профиль на отраслевом портале, программа
конференции с почтой, карточка спикера.

Замер первого задания: 51 человек, 100 страниц, **14 телефонов и 12 почт записано** — то
есть контакт нашёлся у половины. Это самый прямой путь к личному номеру из всех открытых:
человек уже известен по должности, ищем именно его.

Гоню заданиями, потому что очередь тяжёлых задач раннера однопоточная и рубит на 1 800 с.
Возобновление у модуля своё: он каждый раз берёт следующих БЕЗ контакта, поэтому повтор
не переспрашивает закрытых.
"""
import json, subprocess, sys, time

ZADANIY = int(sys.argv[1]) if len(sys.argv) > 1 else 12
LIM = sys.argv[2] if len(sys.argv) > 2 else '120'
itogo = {'людей': 0, 'с_выдачей': 0, 'страниц': 0, 'записано_тел': 0, 'записано_почт': 0}
for i in range(1, ZADANIY + 1):
    t = time.time()
    p = subprocess.run([sys.executable, 'zapusk_na_servere.py', 'lpr_serp.py', 'back',
                        '--lim', LIM, '--budget', '1500', '--workers', '5',
                        '--apply', '--tag', 'back3s'],
                       capture_output=True, text=True, timeout=2100)
    posl = None
    for ln in (p.stdout or '').splitlines():
        if '"записано_тел"' in ln:
            try:
                posl = json.loads(ln[ln.find('{'):ln.rfind('}') + 1])
            except Exception:  # noqa: BLE001
                pass
    if posl is None:
        print(f'задание {i}: счётчика в ответе нет — {(p.stdout or p.stderr)[-250:]}',
              file=sys.stderr, flush=True)
        continue
    sch = posl.get('счётчики') or posl
    for k in itogo:
        itogo[k] += int(sch.get(k) or 0)
    print(f'задание {i}/{ZADANIY}: людей {sch.get("людей")}, страниц {sch.get("страниц")}, '
          f'ТЕЛЕФОНОВ {sch.get("записано_тел")}, почт {sch.get("записано_почт")}, '
          f'{int(time.time() - t)} с', file=sys.stderr, flush=True)
    if not int(sch.get('людей') or 0):
        print('людей без контакта не осталось — останавливаюсь', file=sys.stderr)
        break
print(f'ИТОГО обратный ход: {itogo}', file=sys.stderr)
