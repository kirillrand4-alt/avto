# -*- coding: utf-8 -*-
"""Общий заслон: номер, сидящий на нескольких предприятиях, личным не бывает.

ПОЧЕМУ ОТДЕЛЬНЫМ МОДУЛЕМ, А НЕ СТРОЧКОЙ В КАЖДОМ СКРИПТЕ. Правило простое, а ловит больше
всех остальных вместе взятых — и ровно поэтому его нельзя считать по своему файлу. Мера
2-й сессии: **номер, сидящий на десяти предприятиях, в каждом отдельном файле выглядит
чистым**. Из-за этого мы со 2-й сессией спорили о доле общих номеров (64 % против 56 %) —
считали разное: она по всей панели, я по своей выгрузке. Спор был бессмысленным, потому что
сравнивали несравнимое.

Отсюда два требования, оба обязательные:
  * группировать по ВСЕЙ базе, а не по проверяемому куску. Проверяемых строк может быть 72,
    а знать надо, сколько ИНН у этого номера во всех 21 208;
  * гонять при КАЖДОЙ сборке, а не разово. Дефект возвращается с каждым новым источником:
    приёмная завода приезжает снова и снова, под разными людьми.

ЧТО ИМЕННО СЧИТАЕТСЯ. Из номера снимается всё, кроме цифр, берутся последние десять — так
«+7 (8555) 37-51-37», «8 8555 375137» и «8555375137» становятся одним ключом. Дальше по
ключу собираются ИНН и люди. Больше одного ИНН — номер общий, и это не мнение, а факт базы.

ЧТО НЕ ДЕЛАЕТСЯ: ничего не удаляется. Владелец сказал прямо — разделять, а не отсеивать.
Общий номер это путь к человеку через коммутатор, и выбросить его значит потерять вход на
предприятие. Модуль проставляет `vid_nomera` и `predpriyatiy_na_nomere`, а решение по строке
принимает тот, кто её читает.

Использование как модуля:
    import nomer_obshchiy as N
    karta = N.postroit([(inn, telefon), ...])      # ключ -> {'inn': {...}, 'lyudi': {...}}
    N.razmetit(rows, karta, pole_tel='telefon', pole_inn='inn')

Использование как программы:
    python3 nomer_obshchiy.py BAZA.csv --tel telefon --inn inn [--fio fio] \
                              [--proverit 72.csv] [--out размеченный.csv]
`BAZA.csv` — ВСЯ база, по которой строится карта; `--proverit` — тот кусок, который надо
разметить. Если `--proverit` не задан, размечается сама база.
"""
import collections
import csv
import re
import sys

csv.field_size_limit(10 ** 7)

# Мобильные коды России. Нужны не для отбраковки, а чтобы назвать вид номера: городской
# номер приёмной и личный мобильный — разные вещи, и путать их дороже, чем не знать.
MOBILNYE = tuple('9')


POCHTA = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')


def klyuch(tel):
    """Последние десять цифр. Пусто — номер негодный, о чём и говорим отдельно."""
    c = re.sub(r'\D', '', tel or '')
    if len(c) < 10:
        return ''
    return c[-10:]


def eto_pochta(v):
    """Почта в колонке контакта — не «нечитаемый номер».

    Замер на своде: из 21 208 строк 18 662 не дали десяти цифр, и первый вывод «проверить
    источник» был бы неверным на порядок — колонка `kontakt` хранит и телефоны, и почты, а
    вид лежит в соседней `tip_kontakta`. Считать почту испорченным номером значит выдумать
    18 тысяч дефектов на ровном месте.
    """
    return bool(POCHTA.match((v or '').strip()))


def vid(k):
    if not k:
        return 'номер нечитаемый'
    return 'мобильный' if k.startswith(MOBILNYE) else 'городской'


def familiya(fio):
    """Первое слово имени. Сравнивать строки целиком нельзя — поправка 1-й сессии.

    Их замер по моему же файлу: из 153 номеров с пометкой «номер на разных людях одного
    предприятия» у 29 «разные люди» оказались ОДНИМ человеком в разных написаниях —
    «Пестовских Юрий» против «Пестовских Юрий Александрович», «Чикуров В.В.» против
    «Чикуров Владимир Васильевич». Это 18 % ложных тревог, и рождало их сравнение строк.
    """
    ch = re.split(r'[\s.,]+', (fio or '').strip())
    return ch[0].lower().replace('ё', 'е') if ch and ch[0] else ''


def postroit(pary):
    """Карта «ключ номера -> ИНН и люди на нём» по ВСЕЙ базе.

    `pary` — последовательность (inn, telefon) или (inn, telefon, fio).
    """
    karta = collections.defaultdict(lambda: {'inn': set(), 'lyudi': set(), 'familii': set(),
                                             'vstrechalsya': 0})
    for p in pary:
        inn, tel = p[0], p[1]
        fio = p[2] if len(p) > 2 else ''
        k = klyuch(tel)
        if not k:
            continue
        z = karta[k]
        z['vstrechalsya'] += 1
        if inn:
            z['inn'].add(str(inn).strip())
        if fio:
            z['lyudi'].add(str(fio).strip())
            f = familiya(fio)
            if f:
                z.setdefault('familii', set()).add(f)
    return karta


def sudba(k, karta, ishodnoe=''):
    """Что известно про номер: вид, сколько предприятий и людей, и вывод одной строкой."""
    if not k and eto_pochta(ishodnoe):
        return {'vid_nomera': 'это почта, не телефон', 'predpriyatiy_na_nomere': 0,
                'lyudey_na_nomere': 0, 'vyvod': 'не номер: в колонке контакта адрес почты'}
    z = karta.get(k)
    n_inn = len(z['inn']) if z else 0
    n_lyud = len(z['lyudi']) if z else 0
    n_fam = len(z.get('familii') or ()) if z else 0
    if not k:
        # ПУСТО И ИСПОРЧЕНО — РАЗНЫЕ ВЕЩИ, и путать их значит выдумать себе 17 тысяч дефектов.
        # Первый прогон по своду отнёс 16 990 строк в «проверить источник»; при разборе
        # 16 985 из них оказались просто без контакта (`tip_kontakta` = «без контакта»), и
        # чинить там нечего — это и есть наше узкое место: человек найден, номера нет.
        if not (ishodnoe or '').strip():
            return {'vid_nomera': 'контакта нет', 'predpriyatiy_na_nomere': 0,
                    'lyudey_na_nomere': 0,
                    'vyvod': 'контакта нет вовсе — человек найден, номер не добыт'}
        return {'vid_nomera': 'номер нечитаемый', 'predpriyatiy_na_nomere': 0,
                'lyudey_na_nomere': 0,
                'vyvod': 'из номера не набирается десяти цифр — проверить источник'}
    # РЕШАЕТ ФАМИЛИЯ, А НЕ ЧИСЛО ИНН — вторая поправка 1-й сессии, и она в мою же пользу.
    # Моё правило «номер у двух ИНН не личный» снимало НАСТОЯЩИЕ личные: Сидиченко Александр
    # Александрович числится у двух предприятий сразу, и это обычное дело — один человек у
    # двух работодателей. Номер у него личный. Не личный он тогда, когда на нём РАЗНЫЕ ЛЮДИ.
    if n_fam > 1:
        v = (f'ОБЩИЙ: на номере {n_fam} разных фамилий ({n_inn} предприятий) — это приёмная, '
             f'коммутатор или линия площадки, личным быть не может')
    elif n_inn > 1:
        v = (f'личным быть может: одна фамилия, но человек числится ещё у '
             f'{n_inn - 1} предприятия — проверить, не сменил ли место')
    elif n_lyud > 2 and n_fam > 1:
        v = (f'ПОДОЗРИТЕЛЬНЫЙ: одно предприятие, но {n_fam} разных фамилий — похоже на '
             f'общий заводской номер с добавочными')
    else:
        v = 'личным быть может: одно предприятие, один-два человека'
    return {'vid_nomera': vid(k), 'predpriyatiy_na_nomere': n_inn, 'lyudey_na_nomere': n_lyud,
            'vyvod': v}


def razmetit(rows, karta, pole_tel='telefon', pole_inn='inn'):
    """Проставить разметку в строки. Ничего не удаляет и не переставляет."""
    for r in rows:
        v = r.get(pole_tel)
        r.update(sudba(klyuch(v), karta, v))
    return rows


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    baza_put = sys.argv[1]

    def arg(imya, po_umolchaniyu=None):
        return sys.argv[sys.argv.index(imya) + 1] if imya in sys.argv else po_umolchaniyu

    p_tel, p_inn, p_fio = arg('--tel', 'telefon'), arg('--inn', 'inn'), arg('--fio', 'fio')
    baza = list(csv.DictReader(open(baza_put, encoding='utf-8-sig'), delimiter=';'))
    # В карту идут только телефоны: почта в той же колонке ключа не даёт и счёт бы не портила,
    # но явный отбор делает числа проверяемыми.
    karta = postroit([(r.get(p_inn), r.get(p_tel), r.get(p_fio) or '') for r in baza
                      if not eto_pochta(r.get(p_tel))])
    print(f'база {baza_put}: строк {len(baza)}, разных номеров {len(karta)}', file=sys.stderr)

    obshchih = {k: z for k, z in karta.items() if len(z['inn']) > 1}
    print(f'номеров у 2+ предприятий: {len(obshchih)}; строк, которые они закрывают: '
          f'{sum(z["vstrechalsya"] for z in obshchih.values())}', file=sys.stderr)
    for k, z in sorted(obshchih.items(), key=lambda x: -len(x[1]['inn']))[:8]:
        print(f'  {k}  предприятий {len(z["inn"]):>3}, людей {len(z["lyudi"]):>3}',
              file=sys.stderr)

    celi_put = arg('--proverit')
    rows = (list(csv.DictReader(open(celi_put, encoding='utf-8-sig'), delimiter=';'))
            if celi_put else baza)
    razmetit(rows, karta, p_tel, p_inn)
    schet = collections.Counter(r['vyvod'].split(':')[0] for r in rows)
    print(f'\nразмечено строк {len(rows)}' + (f' из {celi_put}' if celi_put else ''),
          file=sys.stderr)
    for v, n in schet.most_common():
        print(f'  {n:>6}  {v}', file=sys.stderr)
    out = arg('--out')
    if out:
        kol = list(rows[0].keys())
        with open(out, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=kol, delimiter=';', extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)
        print(f'→ {out}', file=sys.stderr)


if __name__ == '__main__':
    main()
