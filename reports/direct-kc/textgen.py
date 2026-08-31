# -*- coding: utf-8 -*-
"""Генерация текстовых выводов по сделкам (русская морфология)."""

def plural(n, one, few, many):
    n = abs(int(n)); n100, n10 = n % 100, n % 10
    if 11 <= n100 <= 14: return many
    if n10 == 1: return one
    if 2 <= n10 <= 4: return few
    return many

def deals_word(n):  return plural(n, 'сделка', 'сделки', 'сделок')

EQUIP_FORMS = {
    'винтовой компрессор':  ('винтовой компрессор', 'винтовых компрессора', 'винтовых компрессоров'),
    'дизельный компрессор': ('дизельный компрессор', 'дизельных компрессора', 'дизельных компрессоров'),
    'МКС':                  ('МКС', 'МКС', 'МКС'),
    'осушитель':            ('осушитель', 'осушителя', 'осушителей'),
    'воздуходувка':         ('воздуходувка', 'воздуходувки', 'воздуходувок'),
    'генератор азота':      ('генератор азота', 'генератора азота', 'генераторов азота'),
    'фотосепаратор':        ('фотосепаратор', 'фотосепаратора', 'фотосепараторов'),
    'тип оборудования не указан': ('сделка без указания типа оборудования',
                                   'сделки без указания типа оборудования',
                                   'сделок без указания типа оборудования'),
}
def equip_phrase(kind, n):
    return f"{n} {plural(n, *EQUIP_FORMS.get(kind, (kind, kind, kind)))}"

def money(v):
    """Денежная сумма прописью, без завершающей точки."""
    if not v: return None
    if v >= 1_000_000: return f"{v/1_000_000:.1f}".replace('.', ',') + " млн руб"
    if v >= 1_000:     return f"{v/1_000:.0f}" + " тыс. руб"
    return f"{v:,.0f}".replace(',', ' ') + " руб"

def join_ru(items):
    items = [i for i in items if i]
    if not items: return ''
    if len(items) == 1: return items[0]
    return ', '.join(items[:-1]) + ' и ' + items[-1]

def _power_key(p):
    try: return (0, float(str(p).replace(',', '.')))
    except (TypeError, ValueError): return (1, 0.0)

def summary_text(deals):
    """deals — список качественных сделок (Лид 3) одного аккаунта."""
    n = len(deals)
    if n == 0:
        return "Сделок за неделю не создано."

    # 1) распределение всех созданных сделок по мощности
    by_pow, no_pow = {}, 0
    for d in deals:
        if d['power']: by_pow[d['power']] = by_pow.get(d['power'], 0) + 1
        else: no_pow += 1
    parts = [f"{c} {deals_word(c)} на {p} кВт" for p, c in sorted(by_pow.items(), key=lambda kv: _power_key(kv[0]))]
    if no_pow:
        parts.append(f"в {no_pow} {plural(no_pow,'сделке','сделках','сделках')} мощность не заполнена")
    verb = 'создана' if n % 10 == 1 and n % 100 != 11 else 'создано'
    if len(parts) == 1 and not no_pow:
        head = f"За неделю {verb} {parts[0]}."
    else:
        head = f"За неделю {verb} {n} {deals_word(n)}: {join_ru(parts)}."

    # 2) статусы
    work = [d for d in deals if d['category'] == 'в работе']
    win  = [d for d in deals if d['category'] == 'успешная']
    lose = [d for d in deals if d['category'] == 'провалена']
    w, y, z = len(work), len(win), len(lose)
    seg = [f"В работе {w} {deals_word(w)}" if w else "В работе сделок нет"]
    seg.append((f"успешно {'завершена' if y % 10 == 1 and y % 100 != 11 else 'завершены'} {y}")
               if y else "успешно завершённых нет")
    seg.append((f"{'провалена' if z % 10 == 1 and z % 100 != 11 else 'провалены'} {z}")
               if z else "проваленных нет")
    status = ', '.join(seg) + '.'

    # 3) оборудование и мощности только по сделкам в работе
    if work:
        grp = {}
        for d in work:
            k = (d['equipment'], d['power'])
            grp[k] = grp.get(k, 0) + 1
        items = []
        for (eq, p), c in sorted(grp.items(), key=lambda kv: (kv[0][0], _power_key(kv[0][1]))):
            items.append(equip_phrase(eq, c) + (f" на {p} кВт" if p else " без указания мощности"))
        equip = "В сделках в работе: " + join_ru(items) + "."
    else:
        equip = "Сделок в работе нет."

    # 4) ориентировочная сумма активных сделок
    s = sum(d['summa'] for d in work)
    if s > 0:
        filled = sum(1 for d in work if d['summa'] > 0)
        tail = f"Ориентировочная сумма активных сделок — {money(s)}"
        if filled < w:
            tail += f" (сумма заполнена у {filled} из {w} сделок)"
        tail += '.'
    else:
        tail = "Ориентировочная сумма активных сделок не рассчитана: суммы сделок не заполнены."
    return ' '.join([head, status, equip, tail])
