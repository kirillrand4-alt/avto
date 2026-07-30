# -*- coding: utf-8 -*-
"""Поиск техЛПР по ВСЕМУ списку целей — цикл ВНУТРИ серверного процесса.

Зачем отдельный оп, если `lpr_serp` уже умеет `--targets` и `--off/--lim`:
круги гонял локальный клиент-опрашиватель, и он умирал вместе с шеллом
песочницы или рестартом контейнера. За день так погибли четыре прогона, и ни
один не оставил ни строчки причины — просто пропадал процесс.

Лечится переносом ЦИКЛА на сервер: одно задание раннера, внутри него
последовательные пачки, между пачками — запись в базу и в журнал. Локально
ничего ждать не нужно, результат забирается с дропа отдельной командой.

Каждая пачка вызывается подпроцессом, а не импортом: `lpr_serp` — скрипт с
разбором `sys.argv` на уровне модуля, импортировать его дважды нельзя.
Падение одной пачки не роняет прогон: код возврата пишется в отчёт, цикл
идёт дальше.

Запуск: python lpr_vse_celi.py [--lim 8] [--budget 1500] [--mode b]
"""
import json
import os
import subprocess
import sys
import time

ЦЕЛИ = r'C:\seostat\drop\celi_bez_tehlpr.jsonl'
СКРИПТ = r'C:\sender\server\ops\lpr_serp.py'
ЖУРНАЛ = r'C:\sender\server\lpr_vse_celi.jsonl'


def арг(имя, по_умолчанию):
    return (sys.argv[sys.argv.index(имя) + 1]
            if имя in sys.argv else по_умолчанию)


# СТАРТ СО СМЕЩЕНИЯ. Без него повторный заход переделывает уже пройденное:
# бюджет одного задания раннера покрывает около сорока целей из ста
# пятидесяти трёх, значит заходов нужно четыре, и каждый должен продолжать, а
# не начинать. По умолчанию берём смещение из журнала — он durable и переживёт
# смерть процесса.
def _из_журнала():
    если = 0
    if os.path.exists(ЖУРНАЛ):
        for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            # пачку с падением НЕ считаем пройденной — её надо повторить
            if not з.get('rc'):
                если = max(если, int(з.get('off', 0)) + 1)
    return если


СТАРТ = int(арг('--start', '-1'))
ПАЧКА = int(арг('--lim', '8'))
БЮДЖЕТ = float(арг('--budget', '1500'))
РЕЖИМ = арг('--mode', 'b')


def main():
    if not os.path.exists(ЦЕЛИ):
        raise SystemExit(f'нет файла целей {ЦЕЛИ}')
    всего = sum(1 for _ in open(ЦЕЛИ, encoding='utf-8', errors='replace'))
    print(f'целей в файле: {всего}, пачка по {ПАЧКА}, бюджет {БЮДЖЕТ} с')
    sys.stdout.flush()

    начало = time.time()
    кругов, упало, пусто = 0, 0, 0
    старт = СТАРТ if СТАРТ >= 0 else _из_журнала()
    print(f'старт со смещения {старт}'
          f'{" (из журнала)" if СТАРТ < 0 else ""}')
    sys.stdout.flush()
    for off in range(старт, всего, ПАЧКА):
        осталось = БЮДЖЕТ - (time.time() - начало)
        if осталось < 120:
            print(f'бюджет вышел на смещении {off} из {всего}')
            break
        т0 = time.time()
        аргв = [sys.executable, СКРИПТ, 'serp', '--targets', ЦЕЛИ, '--vse',
                '--mode', РЕЖИМ, '--off', str(off), '--lim', str(ПАЧКА),
                '--tag', f's{off}', '--budget', str(int(min(осталось - 60, 300)))]
        try:
            п = subprocess.run(аргв, capture_output=True, text=True,
                               timeout=min(осталось, 420), encoding='utf-8',
                               errors='replace')
            rc, out, err = п.returncode, p_out(п.stdout), p_out(п.stderr)
        except subprocess.TimeoutExpired:
            rc, out, err = -9, '', 'таймаут пачки'
        except Exception as e:  # noqa: BLE001
            rc, out, err = -1, '', f'{type(e).__name__}: {str(e)[:200]}'
        кругов += 1
        if rc:
            упало += 1
        elif not out.strip():
            пусто += 1
        запись = {'off': off, 'rc': rc, 'сек': round(time.time() - т0, 1),
                  'вывод': out[-1500:], 'ошибка': err[-800:]}
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
            ж.write(json.dumps(запись, ensure_ascii=False) + '\n')
            ж.flush()
            os.fsync(ж.fileno())
        # печатаем СРАЗУ, чтобы хвост stdout показывал ход, а не только итог
        метка = 'ok' if not rc else f'ПАДЕНИЕ rc={rc}'
        print(f'  off={off:>4} {метка} {round(time.time() - т0, 1)} с  '
              f'{(out.strip().splitlines() or [""])[-1][:110]}')
        if rc and err:
            print(f'      {err.strip().splitlines()[-1][:150]}')
        sys.stdout.flush()

    print()
    print(f'кругов {кругов}, упало {упало}, пустых {пусто}, '
          f'журнал {ЖУРНАЛ}')


def p_out(x):
    return x or ''


if __name__ == '__main__':
    main()
