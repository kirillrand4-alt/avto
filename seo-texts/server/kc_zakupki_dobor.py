# -*- coding: utf-8 -*-
r"""Контакты закупок ЕИС отдельным шагом (владелец 09.10: «ЕИС-контакты закупок брать от выручки 120 млн, а не от
1 млрд — согласен»). Контактные лица карточек закупок, где компания — заказчик, — это снабжение (ЛПР «да»).

В обходе (kc_kontakty) закупки смотрятся только от KC_ZAKUPKI_OT (1 млрд — ради скорости обхода). Этот шаг добирает
их у компаний от KC_ZAKUPKI_DOBOR_OT (по умолчанию 120 млн), у которых в записи обхода закупок ещё нет: тот же
kc_kontakty.закупки (EC.find_zakupki_contacts: RSS-поиск извещений по ИНН -> карточки -> контактный блок; карточки
из нашей базы). Результат — новая строка в <набор>-kontakty.jsonl: копия последней записи компании с полем «закупки»
и отметкой «закупки_добор» (Excel и проверки берут последнюю запись компании). Резюм: компании с отметкой
пропускаются. Запускать, когда обход этого набора не идёт (один файл).

    KC_NABOR=<набор> python kc_zakupki_dobor.py
"""
import io
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
ОТ = float(os.environ.get('KC_ZAKUPKI_DOBOR_OT', '120e6'))
ПОТОКОВ = int(os.environ.get('KC_ZAKUPKI_POTOKOV', '6'))
_лок = threading.Lock()


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    задачи = []
    for i, к in сп.items():
        з = последняя.get(i)
        if not з or not i.isdigit() or (к.get('выручка') or 0) < ОТ:
            continue
        if з.get('закупки_добор') or any(x.get('люди') or x.get('url') for x in з.get('закупки') or []):
            continue
        задачи.append((к, з))
    задачи.sort(key=lambda x: -(x[0].get('выручка') or 0))
    print('компаний для закупок ЕИС', len(задачи), 'от выручки', ОТ, flush=True)
    t0 = time.time()
    сч = {'карточек': 0, 'людей': 0, 'с людьми': 0, 'ошибок': 0}
    n = [0]

    def одна(x):
        к, з = x
        try:
            зак = KK.закупки(к)
        except Exception as e:  # noqa: BLE001
            зак = [{'ошибка': repr(e)[:100]}]
        нов = dict(з, закупки=зак, закупки_добор=time.strftime('%Y-%m-%d %H:%M'))
        записать(нов)
        люди = sum(len(c.get('люди') or []) for c in зак)
        with _лок:
            сч['карточек'] += sum(1 for c in зак if c.get('url'))
            сч['людей'] += люди
            сч['с людьми'] += bool(люди)
            сч['ошибок'] += sum(1 for c in зак if c.get('ошибка'))
            n[0] += 1
            if n[0] % 10 == 0:
                print('готово %d/%d за %d мин' % (n[0], len(задачи), (time.time() - t0) / 60), flush=True)

    with ThreadPoolExecutor(ПОТОКОВ) as ex:
        list(ex.map(одна, задачи))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    сч['компаний'] = len(задачи)
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
