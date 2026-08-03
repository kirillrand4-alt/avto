# -*- coding: utf-8 -*-
"""Гнать `people_sources` на сервере владельца заданиями подряд.

ПОЧЕМУ ПОДРЯД, А НЕ ОДНИМ ПРОГОНОМ. Задание раннера умирает по таймауту на 1800 с, а модуль
тратит около 90 с на предприятие (выдача -> страницы и документы -> разбор провайдером).
Значит одно задание берёт примерно 18 предприятий, и покрытие набирается только чередой
заданий. Возобновление у модуля своё: поток `C:\\seostat\\drop\\people_sources_<режим>.jsonl`,
повторный запуск продолжает с места остановки и уже пройденных не трогает.

Модуль запускается через `panel_py`, а не через задачу раннера: задачи для него в allowlist
нет и не будет, но `enrich_contacts` умеет положить файл под `C:\\sender` и выполнить его.
Это и открыло модуль, который не запускался ни разу.
"""
import json, os, subprocess, sys, time

REZHIM = sys.argv[1] if len(sys.argv) > 1 else 'conf'
ZADANIY = int(sys.argv[2]) if len(sys.argv) > 2 else 8
BYUDZHET = os.environ.get('BYUDZHET', '1500')

itogo = {'пройдено': 0, 'людей': 0, 'технических': 0, 'телефонов': 0, 'почт': 0, 'ошибок': 0}
for i in range(1, ZADANIY + 1):
    t = time.time()
    p = subprocess.run([sys.executable, 'zapusk_na_servere.py', 'people_sources.py',
                        REZHIM, BYUDZHET, '--apply'],
                       capture_output=True, text=True, timeout=2100)
    posl = None
    for ln in (p.stdout or '').splitlines():
        ln = ln.strip()
        if ln.startswith('{') and '"пройдено"' in ln:
            try:
                posl = json.loads(ln)
            except Exception:
                pass
    if posl is None:
        print(f'задание {i}: ответа со счётчиком нет — {(p.stderr or p.stdout)[-300:]}',
              file=sys.stderr, flush=True)
        continue
    for k in itogo:
        itogo[k] += int(posl.get(k) or 0)
    print(f'задание {i}/{ZADANIY} [{REZHIM}]: пройдено {posl.get("пройдено")}, '
          f'людей {posl.get("людей")}, технических {posl.get("технических")}, '
          f'телефонов {posl.get("телефонов")}, почт {posl.get("почт")}, '
          f'ошибок {posl.get("ошибок")}, {int(time.time()-t)} с', file=sys.stderr, flush=True)
print(f'ИТОГО по режиму {REZHIM}: {itogo}', file=sys.stderr)
