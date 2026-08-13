# -*- coding: utf-8 -*-
"""Пульт к ZennoPoster: кладём команду в файл, кубик-диспетчер её выполняет.

Зачем: у ZennoPoster нет внешнего API (порты 1000/1001/5001/6001/6002 закрыты,
TasksRunner.exe ключей не принимает). Зато ИЗНУТРИ проекта доступен весь класс
ZennoLab.CommandCenter.ZennoPoster — StartTask/StopTask/SetMaxThreads/TasksList.
Поэтому в ZennoPoster один раз ставится вечная задача-диспетчер (zenno/dispetcher.cs),
она читает komanda.txt и отвечает в dispetcher.json. Этот файл — вторая половина
пары: пишет команды и читает ответ.

Использование (на сервере):
    python zenno_pult.py sostoyanie                  что вообще есть и что крутится
    python zenno_pult.py pusk Obogahenie 10          запустить на 10 потоков
    python zenno_pult.py potoki Obogahenie 6         сменить потоки на ходу
    python zenno_pult.py stop Obogahenie             остановить мягко
    python zenno_pult.py sbros Obogahenie            прервать немедленно
    python zenno_pult.py zhurnal                     последние выполненные команды

Ответ диспетчера не мгновенный: он спит между кругами (по умолчанию 10 с), поэтому
команды с ожиданием ждут появления свежего dispetcher.json до 60 секунд.
"""
import json
import os
import sys
import time

OBMEN = os.environ.get('ZENNO_OBMEN', r'C:\seostat\drop\zenno')
KOMANDA = os.path.join(OBMEN, 'komanda.txt')
SOSTOYANIE = os.path.join(OBMEN, 'dispetcher.json')
ZHURNAL = os.path.join(OBMEN, 'vypolneno.txt')

KOMANDY = ('pusk', 'stop', 'sbros', 'potoki', 'spisok')


def sostoyanie(zhdat_svezhee=0):
    """Прочитать ответ диспетчера. zhdat_svezhee — ждать файл не старше N секунд."""
    krayniy = time.time() + 60
    while True:
        try:
            vozrast = time.time() - os.path.getmtime(SOSTOYANIE)
            d = json.load(open(SOSTOYANIE, encoding='utf-8-sig'))
            d['возраст_ответа_сек'] = round(vozrast)
            if not zhdat_svezhee or vozrast <= zhdat_svezhee or time.time() > krayniy:
                if zhdat_svezhee and vozrast > zhdat_svezhee:
                    d['предупреждение'] = ('ответ старше %d с — диспетчер не крутится'
                                           % zhdat_svezhee)
                return d
        except FileNotFoundError:
            if time.time() > krayniy:
                return {'ошибка': 'диспетчер ни разу не отвечал: нет %s' % SOSTOYANIE}
        except Exception as e:  # noqa: BLE001
            if time.time() > krayniy:
                return {'ошибка': '%s: %s' % (type(e).__name__, e)}
        time.sleep(3)


def polozhit(stroka):
    os.makedirs(OBMEN, exist_ok=True)
    # дописываем, а не перезаписываем: диспетчер читает файл целиком и очищает его,
    # так что две команды подряд не затрут друг друга
    with open(KOMANDA, 'a', encoding='utf-8') as f:
        f.write(stroka.rstrip() + '\n')
        f.flush()
        os.fsync(f.fileno())


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1].lower()

    if cmd in ('sostoyanie', 'состояние', 'stat'):
        print(json.dumps(sostoyanie(), ensure_ascii=False, indent=1))
        return 0

    if cmd in ('zhurnal', 'журнал', 'log'):
        if not os.path.exists(ZHURNAL):
            print('журнал пуст: %s' % ZHURNAL)
            return 0
        stroki = open(ZHURNAL, encoding='utf-8-sig', errors='replace').read().splitlines()
        print('\n'.join(stroki[-30:]))
        return 0

    if cmd not in KOMANDY:
        print('неизвестная команда %r; знаю: %s, sostoyanie, zhurnal'
              % (cmd, ', '.join(KOMANDY)))
        return 2

    stroka = ' '.join(sys.argv[1:])
    polozhit(stroka)
    # ждём круга диспетчера и показываем, что он ответил
    otvet = sostoyanie(zhdat_svezhee=30)
    print(json.dumps({'отправлено': stroka, 'ответ_диспетчера': otvet},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
