#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Отставить статьи, которые доводкой не чинятся, - под перегенерацию.

    python3 otstavit_brak.py [--do 2]

ЗАЧЕМ. Претензия на шаге «готово» означает, что доводка уже отработала
и не помогла. Держать такую статью на диске вредно: цепочка при повторе
находит готовый файл, ПРОПУСКАЕТ генерацию и упирается в тот же дефект.
Страница становится потерянной навсегда, а выглядит как «в очереди».

Ночью это всплыло трижды подряд на перелинковке: задания получили
адреса в 19:11, а статьи, написанные до этого, адресов не видели
и падали на включившемся гейте. Каждую пришлось отставлять руками,
и каждый раз я замечал это с опозданием.

Не удаляем, а переименовываем в .brakN.html: если дефект окажется
в проверке, а не в статье, работа не потеряна. Больше двух попыток
на страницу не делаем - если и вторая негодна, дело не в везении.
"""
import argparse
import glob
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
ZHURNAL = os.path.join(DIR, 'konveyer.jsonl')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--do', type=int, default=2, help='попыток на страницу')
    a = ap.parse_args()

    godnye, brak = set(), {}
    with open(ZHURNAL, encoding='utf-8') as f:
        for l in f:
            try:
                z = json.loads(l)
            except Exception:
                continue
            if z.get('itog') in ('чисто', 'нужен разбор'):
                godnye.add(z['slug'])
            elif z.get('itog', '').startswith('претензии'):
                brak[z['slug']] = z

    otstavleno = ischerpano = 0
    for slug, z in sorted(brak.items()):
        if slug in godnye:
            continue                      # уже вернулась в строй
        put = os.path.join(DIR, 'statyi', f'{slug}.html')
        if not os.path.exists(put):
            continue                      # уже отставлена
        # ОБРЫВ ШЛЮЗА НЕ ТРАТИТ ПОПЫТКУ. Ограничение в две попытки стоит
        # против страниц, которые падают ПО СВОЕЙ вине - раз за разом
        # выдумывают числа или теряют блок. Оборванный стрим к качеству
        # страницы отношения не имеет: шлюз уронил соединение, документ
        # пришёл обрезанным на полуслове. Считать это виной страницы -
        # значит выбрасывать её из-за чужой поломки.
        #
        # Так и вышло с enger-air--generatory-kisloroda: первая попытка
        # упала без блока FAQ (вина страницы), вторая на обрыве (вина
        # шлюза), и страница выбыла навсегда, хотя своей неудачи у неё
        # была одна.
        pret = '; '.join(z.get('pretenzii') or []) + str(z.get('hvost', ''))
        obryv = 'оборван' in pret or 'вероятен обрыв' in pret
        vid = 'obryv' if obryv else 'brak'
        bylo = len(glob.glob(os.path.join(DIR, 'statyi', f'{slug}.brak*.html')))
        if not obryv and bylo >= a.do:
            ischerpano += 1
            print(f'ИСЧЕРПАНО {slug}: {bylo} своих попыток, дело не в везении')
            continue
        # НОМЕР ПО МАКСИМУМУ, А НЕ ПО СЧЁТУ. Считать файлы нельзя: в ряду
        # бывают дыры (brak1 забран на разбор, brak2 остался), и тогда
        # счёт+1 указывает на ЗАНЯТОЕ имя. os.rename на posix затирает
        # молча, без единой ошибки.
        #
        # Так и случилось с ekomak--azotnaya-stanciya-modulnaya: при одном
        # существующем brak2 счёт дал nomer=2, и прошлая попытка исчезла.
        est = []
        for p_ in glob.glob(os.path.join(DIR, 'statyi', f'{slug}.{vid}*.html')):
            m_ = re.search(rf'\.{vid}(\d+)\.html$', p_)
            if m_:
                est.append(int(m_.group(1)))
        nomer = (max(est) + 1) if est else 1
        novoe = os.path.join(DIR, 'statyi', f'{slug}.{vid}{nomer}.html')
        if os.path.exists(novoe):
            print(f'ПРОПУЩЕНА {slug}: имя {os.path.basename(novoe)} занято')
            continue
        os.rename(put, novoe)
        prichina = '; '.join(z.get('pretenzii') or [])[:90] or z.get('shag', '?')
        otstavleno += 1
        print(f'отставлена {slug}\n    {prichina}')
    print(f'\nотставлено {otstavleno}, исчерпало попытки {ischerpano}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
