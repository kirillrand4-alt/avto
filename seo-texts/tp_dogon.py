# -*- coding: utf-8 -*-
"""Догон: пересчитать телефоны в уже скачанных карточках Tender.pro починенной регуляркой.

Зачем. Прежняя регулярка сборщика пропускала пятизначный код города: она требовала после кода
минимум две цифры, а в живой записи `+7 (34350) 4-00-88` после кода идёт `4-00-88`. И номер в
скобках без кода страны — `тел. (8482) 56-10-44` — тоже терялся: восьмёрка съедалась как код
страны, оставалось девять цифр.

Замер: из 3 761 карточки, отсечённой от разбора по признакам «нет телефона и нет технического
слова», телефон есть у **264**, и у **241** из них рядом стоит ФИО. То есть цифра «телефон в
комментарии у 4 504 из 9 021» была занижена, и занижена именно из-за формата записи.

Скрипт не качает ничего заново: карточки уже лежат в `tp-kartochki.csv` вместе с текстом
комментария. Он пересчитывает колонку `telefony_tekst` и **сохраняет прежнее значение в
`telefony_tekst_staryy`**, чтобы правку можно было проверить, а не принимать на слово.

После него `tenderpro_lica.py` подхватит новые строки сам: он отбирает карточки с телефоном или
техническим словом и пропускает уже разобранные по `tender_id`.

Использование:
    python3 tp_dogon.py [--suho] [--kart ИМЯ.csv]   # --suho: только замер, файл не менять
"""
import csv
import os
import re
import shutil
import sys

import tenderpro_harvest as T

BAZA = os.path.dirname(os.path.abspath(__file__))
TP = os.path.join(BAZA, 'engineers-lens', 'centro', 'tenderpro')
# Файл берётся аргументом: пересчитывать приходится и перевыкаченный корпус, а не только
# исходный. Набор колонок при записи берётся ИЗ ЗАГОЛОВКА файла, а не из жёсткого списка —
# именно жёсткий список сдвинул колонки у соседней сессии.
KART = os.path.join(TP, sys.argv[sys.argv.index('--kart') + 1]) if '--kart' in sys.argv \
    else os.path.join(TP, 'tp-kartochki.csv')
FIO = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                 r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}(?:вич|вна|не|ну|ой|ым)\b'
                 r'|[А-ЯЁ]\.\s?[А-ЯЁ]\.\s?[А-ЯЁ][а-яё\-]{2,}')


def main():
    suho = '--suho' in sys.argv
    rows = list(csv.DictReader(open(KART, encoding='utf-8-sig'), delimiter=';'))
    cols = list(rows[0].keys())
    if 'telefony_tekst_staryy' not in cols:
        cols.insert(cols.index('telefony_tekst') + 1, 'telefony_tekst_staryy')

    bylo_s_tel = sum(1 for r in rows
                     if (r.get('telefony_razmetka') or r.get('telefony_tekst')))
    novyh, novyh_s_fio, otsech_bylo = 0, 0, 0
    for r in rows:
        staroe = r.get('telefony_tekst') or ''
        r['telefony_tekst_staryy'] = staroe
        com = r.get('comment') or ''
        tel_r = r.get('telefony_razmetka') or ''
        nashli = [t for t in T.telefony_iz_teksta(com) if t not in tel_r]
        # **Дополняем, а не переписываем.** Сохранённый комментарий обрезан до 2 000 знаков
        # (`tenderpro_harvest.kartochki`), а прежняя колонка заполнялась по полному тексту
        # карточки. Поэтому пересчёт по обрезанному полю сам по себе теряет номера, жившие за
        # обрезом: сухой прогон показал −39 карточек при расхождении регулярок всего в 7
        # номерах. Разница целиком объяснялась обрезом, а не регуляркой.
        bylo = [t.strip() for t in staroe.split('|') if t.strip()]
        r['telefony_tekst'] = ' | '.join(dict.fromkeys(bylo + nashli))
        otsechena = not (tel_r or staroe or r.get('est_teh'))
        if otsechena:
            otsech_bylo += 1
            if nashli:
                novyh += 1
                if FIO.search(com):
                    novyh_s_fio += 1

    stalo_s_tel = sum(1 for r in rows
                      if (r.get('telefony_razmetka') or r.get('telefony_tekst')))
    print(f'карточек: {len(rows)}')
    print(f'  с телефоном было: {bylo_s_tel}, стало: {stalo_s_tel} '
          f'(прирост {stalo_s_tel - bylo_s_tel})')
    print(f'  из {otsech_bylo} отсечённых прежде: телефон нашёлся у {novyh}, '
          f'из них с ФИО рядом {novyh_s_fio}')

    if suho:
        print('сухой прогон, файл не изменён')
        return
    shutil.copy(KART, KART + '.do-dogona')
    with open(KART, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    # Отчитываемся цифрой ИЗ ЗАПИСАННОГО ФАЙЛА, а не из счётчика в памяти: счётчик уже трижды
    # за сутки расходился с файлом на этой же задаче.
    proverka = list(csv.DictReader(open(KART, encoding='utf-8-sig'), delimiter=';'))
    po_fajlu = sum(1 for r in proverka
                   if (r.get('telefony_razmetka') or r.get('telefony_tekst')))
    print(f'записано; по перечитанному файлу с телефоном: {po_fajlu} из {len(proverka)}')
    print(f'прежняя версия сохранена: {KART}.do-dogona')


if __name__ == '__main__':
    main()
