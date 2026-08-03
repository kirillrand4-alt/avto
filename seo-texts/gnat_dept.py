# -*- coding: utf-8 -*-
"""Справочники подразделений заданиями подряд.

Первый прогон: 1 245 предприятий, 454 телефона, 307 почт, 172 человека в панель. В панели
предприятий 1 573, а модуль берёт цели своим потоком и продолжает с места остановки, поэтому
покрытие набирается чередой заданий — одно задание это около 1 200 предприятий за 1 500 с.

Выдачу НЕ трогает: работает обходом сайтов, поэтому идёт параллельно с обратным ходом и с
ним не конкурирует. Это и есть причина, по которой выбран именно он.

Останавливаюсь, когда задание перестало давать записи: пустой прогон дешевле повторять, чем
объяснять потом, почему счётчик стоял.
"""
import json, re, subprocess, sys, time

ZADANIY = int(sys.argv[1]) if len(sys.argv) > 1 else 6
itogo = {'obrabotano': 0, 'zapisano_tel': 0, 'zapisano_pocht': 0, 'zapisano_lyudey': 0}
pusto_podryad = 0
for i in range(1, ZADANIY + 1):
    t = time.time()
    p = subprocess.run([sys.executable, 'zapusk_na_servere.py', 'dept_directory.py',
                        '1500', '4', '--apply', '--stream', 'dept3s'],
                       capture_output=True, text=True, timeout=2100)
    posl = None
    for ln in (p.stdout or '').splitlines():
        if '"записано_тел"' in ln:
            try:
                posl = json.loads(ln[ln.find('{'):ln.rfind('}') + 1])
            except Exception:  # noqa: BLE001
                pass
    if posl is None:
        print(f'задание {i}: счётчика нет — {(p.stdout or p.stderr)[-250:]}',
              file=sys.stderr, flush=True)
        continue
    tel = int(posl.get('записано_тел') or 0)
    poch = int(posl.get('записано_почт') or 0)
    lyud = int(posl.get('записано_людей') or 0)
    itogo['obrabotano'] += int(posl.get('обработано') or 0)
    itogo['zapisano_tel'] += tel
    itogo['zapisano_pocht'] += poch
    itogo['zapisano_lyudey'] += lyud
    print(f'задание {i}/{ZADANIY}: обработано {posl.get("обработано")}, '
          f'ТЕЛЕФОНОВ {tel}, почт {poch}, людей {lyud}, техЛПР '
          f'{int(posl.get("A_техЛПР") or 0) + int(posl.get("B_техЛПР") or 0)}, '
          f'{int(time.time() - t)} с', file=sys.stderr, flush=True)
    pusto_podryad = pusto_podryad + 1 if (tel + poch + lyud) == 0 else 0
    if pusto_podryad >= 2:
        print('два задания подряд без единой записи — выборка выдохлась, останавливаюсь',
              file=sys.stderr)
        break
print(f'ИТОГО справочники: {itogo}', file=sys.stderr)
