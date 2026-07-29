# -*- coding: utf-8 -*-
"""Генератор кандидатов корпоративного адреса по ФИО и домену.

Наблюдение (проверено на 5 доменах, см. engineers-lens/HARVEST-rukovodstvo.md): схемы
адресов у разных компаний РАЗНЫЕ, но пространство схем мало и перечислимо. Поэтому дешевле
сгенерировать все варианты и отдать их SMTP-проверке (email_probe.py), чем искать образец
на каждом домене.

Пространство схемы: порядок (фамилия вперёд / инициалы вперёд) x разделитель (. _ нет)
x число инициалов (0 / 1 / 2). Регистр НЕ вариант: локальная часть у подавляющего
большинства серверов регистронезависима.

Реальная комбинаторика идёт не от схемы, а от ТРАНСЛИТЕРАЦИИ: я/ю/ы/ь/ё/х/ц/щ пишут
по-разному. Поэтому генерируются альтернативы, а список ранжируется — сперва частые схемы
и основная транслитерация, чтобы SMTP-проб было меньше (много проб с одного IP = блокировка).

Использование:
    python3 email_guess.py "Курюмов Ярослав Георгиевич" ch-energo.ru
    python3 email_guess.py --selftest
"""
import argparse
import sys

# основной вариант + альтернативы (то, где реально расходятся системы транслитерации)
TRANSLIT = {
    'а': ['a'], 'б': ['b'], 'в': ['v'], 'г': ['g'], 'д': ['d'], 'е': ['e'],
    'ё': ['e', 'yo'], 'ж': ['zh'], 'з': ['z'], 'и': ['i'], 'й': ['y', 'i'],
    'к': ['k'], 'л': ['l'], 'м': ['m'], 'н': ['n'], 'о': ['o'], 'п': ['p'],
    'р': ['r'], 'с': ['s'], 'т': ['t'], 'у': ['u'], 'ф': ['f'],
    'х': ['kh', 'h'], 'ц': ['ts', 'c'], 'ч': ['ch'], 'ш': ['sh'],
    'щ': ['sch', 'shch'], 'ъ': [''], 'ы': ['y', 'i'], 'ь': [''],
    'э': ['e'], 'ю': ['yu', 'iu'], 'я': ['ya', 'ia'],
}

# схемы в порядке убывания наблюдаемой частоты (по 5 подтверждённым образцам)
SCHEMES = [
    ('surname_initials', '_', 2),   # zaytsev_mm, Ulyanychev_IV
    ('surname_initials', '.', 2),   # Artyushina.TO
    ('initials_surname', '.', 2),   # in.krylova
    ('surname_only',     '',  0),   # tolbin
    ('surname_initials', '.', 1),
    ('surname_initials', '_', 1),
    ('initials_surname', '.', 1),
    ('initials_surname', '_', 2),
    ('initials_surname', '_', 1),
    ('surname_initials', '',  2),
    ('initials_surname', '',  2),
    ('surname_initials', '-', 2),
]


def translit_variants(word, cap=6):
    """Все правдоподобные латинские написания слова, основной вариант первым."""
    out = ['']
    for ch in word.lower():
        opts = TRANSLIT.get(ch, [ch] if ch.isalpha() else [''])
        out = [pref + o for pref in out for o in opts]
        if len(out) > 400:                     # защита от взрыва на длинных фамилиях
            out = out[:400]
    seen, res = set(), []
    for w in out:
        if w and w not in seen:
            seen.add(w)
            res.append(w)
    return res[:cap]


def parse_fio(fio):
    """'Курюмов Ярослав Георгиевич' или 'Митюхин А.Ю.' -> (фамилия, [инициалы])."""
    parts = [p for p in fio.replace('.', ' ').split() if p]
    if not parts:
        raise ValueError('пустое ФИО')
    surname = parts[0]
    inits = []
    for p in parts[1:]:
        inits.append(p[0])
    return surname, inits[:2]


def candidates(fio, domain, limit=24):
    surname, inits = parse_fio(fio)
    s_vars = translit_variants(surname)
    i_vars = []
    for ini in inits:
        i_vars.append(translit_variants(ini, cap=2))

    out, seen = [], set()
    for order, sep, n in SCHEMES:
        if n > len(i_vars):
            continue
        # набор написаний инициалов: декартово по первым n инициалам
        ini_combos = ['']
        for k in range(n):
            ini_combos = [a + b for a in ini_combos for b in i_vars[k]]
        ini_combos = ini_combos or ['']
        for sv in s_vars:
            for iv in (ini_combos if n else ['']):
                if order == 'surname_only' or not n:
                    local = sv
                elif order == 'surname_initials':
                    local = f'{sv}{sep}{iv}'
                else:
                    local = f'{iv}{sep}{sv}'
                addr = f'{local}@{domain}'
                if addr not in seen:
                    seen.add(addr)
                    out.append(addr)
                if len(out) >= limit:
                    return out
    return out


SELFTEST = [
    # (ФИО, домен, реально существующий адрес — из engineers-lens/HARVEST-rukovodstvo.md)
    ('Крылова Ирина Николаевна', 'ch-energo.ru', 'in.krylova@ch-energo.ru'),
    ('Зайцев Михаил Михайлович', 'orene.ru', 'zaytsev_mm@orene.ru'),
    ('Ульянычев Игорь Владимирович', 'mrsk-cp.ru', 'ulyanychev_iv@mrsk-cp.ru'),
    ('Артюшина Татьяна Олеговна', 'kl.mrsk-cp.ru', 'artyushina.to@kl.mrsk-cp.ru'),
    ('Толбин Иван Иванович', 'penzacom.ru', 'tolbin@penzacom.ru'),
]


def selftest():
    ok = 0
    for fio, dom, real in SELFTEST:
        cands = [c.lower() for c in candidates(fio, dom, limit=60)]
        hit = real.lower() in cands
        pos = cands.index(real.lower()) + 1 if hit else '-'
        print(f'{"OK " if hit else "MISS"} {real:34s} позиция {pos:>3} из {len(cands)}')
        ok += hit
    print(f'\nнакрыто {ok}/{len(SELFTEST)} реальных адресов')
    return ok == len(SELFTEST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fio', nargs='?')
    ap.add_argument('domain', nargs='?')
    ap.add_argument('--limit', type=int, default=24)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not (a.fio and a.domain):
        sys.exit('нужно: "Фамилия Имя Отчество" домен  либо --selftest')
    for c in candidates(a.fio, a.domain, a.limit):
        print(c)


if __name__ == '__main__':
    main()
