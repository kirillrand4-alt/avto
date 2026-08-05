# -*- coding: utf-8 -*-
"""Уточняющий замер конвейера: где ошибаются ОБА правила ролей. Ничего не меняет.

Первый замер дал большие числа, и по своему же правилу я проверяю прибор, а не объявляю
открытие. В списке «best_email запрещён правилом v2» стоит `spbsearchru@mail.ru`: запрет
сработал на подстроку `hr` внутри слова «sear-CHR-u». Это ровно тот класс, на котором я
сегодня уже обожглась («к/с» совпадало с окончанием слова «фаКС»). Значит у v2 своя
болезнь — слишком короткая подстрока, — и её надо померить, а не чинить наугад.

СЧИТАЕТ ТРИ ВЕЩИ:

1. У V1 (точное совпадение роли) — сколько ТЕХНИЧЕСКИХ и ЗАКУПОЧНЫХ ролей получают
   ранг 9, то есть проигрывают адресу «общий». Пустая роль и кадры считаются отдельно:
   у них ранг 9 не вреден. Вредно, когда проигрывает гл.механик.

2. У V2 (подстроки) — сколько запретов ложные: подстрока найдена ВНУТРИ слова, а не
   как отдельная часть адреса. Различаю по границе: `hr@`, `hr.`, `-hr`, `_hr`, `hr-`
   это роль; `searchru` — не роль.

3. Правило «адрес у нескольких предприятий» (сегодня оно поймало больше всех в моём
   канале): сколько best_email обслуживают 2+ разных ИНН. Такой адрес принадлежит не
   предприятию, а посреднику, управляющей компании или холдингу.
"""
import collections
import json
import os
import re
import sqlite3

ENRICH = r'C:\sender\enrich.db'

V1_RANK = {'снабжение/закупки': 0, 'гл.инженер': 1, 'директор': 2,
           'продажи': 3, 'приёмная': 4, 'бухгалтерия': 5, 'общий': 6}
# Роли, ради которых всё затевалось: круг 1-2, они ПОКУПАЮТ и решают.
TEHNICHESKIE = re.compile(
    r'закупк|снабж|тендер|инженер|механик|энергетик|технолог|производ|цех|'
    r'асу|кипиа|кип\b|техдир|техконтакт|главн|нач\.', re.I)
NE_ADRESAT = re.compile(r'кадр|hr|персонал|подбор|ваканс|пресс|press|юрис|бухгалт|'
                        r'реклам|маркет|сми', re.I)
LOCAL_DENY = ('press', 'pressa', 'smi', 'hr@', 'hr.', 'kadr', 'vacan', 'job',
              'rabota', 'rekla', 'marketing', 'legal', 'urist', 'jurist',
              'buh', 'account', 'noreply', 'no-reply', 'abuse', 'postmaster')


def deny_kak_v_kode(e):
    """Запрет ТОЧНО как в коде v2: голая подстрока в local-part."""
    lp = (e or '').split('@')[0].lower()
    for k in LOCAL_DENY:
        if k.rstrip('@.') in lp:
            return k
    return ''


def deny_po_granice(e):
    """Тот же запрет, но подстрока обязана быть ОТДЕЛЬНОЙ частью адреса.

    Части адреса разделяют точка, дефис, подчёркивание, цифры и край строки.
    «hr@», «hr.pc», «zavod-hr» — роль. «searchru» — слово, в котором hr случайно.
    """
    lp = (e or '').split('@')[0].lower()
    chasti = [c for c in re.split(r'[^a-zа-я]+', lp) if c]
    for k in LOCAL_DENY:
        kk = k.rstrip('@.')
        for c in chasti:
            # отдельная часть целиком ИЛИ часть начинается/кончается ключом
            if c == kk or c.startswith(kk) or c.endswith(kk):
                if len(c) <= len(kk) + 4:      # «buhgalteriya» да, «buhta» нет
                    return k
    return ''


def main():
    if not os.path.exists(ENRICH):
        print('ИТОГ ' + json.dumps({'нет базы': ENRICH}, ensure_ascii=False))
        return
    cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    sch = collections.Counter()
    pr = collections.defaultdict(list)

    # ---------- 1. V1: технические роли, проигрывающие «общему»
    roli = collections.Counter()
    for r in cx.execute('select coalesce(role,"") from emails'):
        roli[(r[0] or '').strip().lower()] += 1
    poteryano = 0
    print('=== V1: роли с рангом 9 (ХУЖЕ «общего»), разложенные по смыслу')
    for rl, n in sorted(roli.items(), key=lambda x: -x[1]):
        if rl in V1_RANK:
            continue
        if not rl:
            sch['ранг 9: роль пустая (не вредно)'] += n
        elif NE_ADRESAT.search(rl):
            sch['ранг 9: не наш адресат (кадры/пресса) — правильно'] += n
        elif TEHNICHESKIE.search(rl):
            sch['ранг 9: ТЕХНИЧЕСКАЯ или ЗАКУПОЧНАЯ роль — ПРОИГРЫВАЕТ info@'] += n
            poteryano += n
            if len(pr['проигрывают info@']) < 16:
                pr['проигрывают info@'].append((rl, n))
        else:
            sch['ранг 9: прочее'] += n

    # ---------- 2. V2: ложные запреты
    lozh = tochno = 0
    for r in cx.execute('select coalesce(best_email,"") from companies '
                        'where coalesce(best_email,"")<>""'):
        e = (r[0] or '').lower()
        vkode = deny_kak_v_kode(e)
        pogranice = deny_po_granice(e)
        if vkode and not pogranice:
            lozh += 1
            if len(pr['ЛОЖНЫЙ запрет v2']) < 12:
                pr['ЛОЖНЫЙ запрет v2'].append((e, 'сработало на «%s»' % vkode))
        elif vkode:
            tochno += 1
    sch['best_email: запрет v2 сработал ВЕРНО'] = tochno
    sch['best_email: запрет v2 ЛОЖНЫЙ (подстрока внутри слова)'] = lozh

    # ---------- 3. Адрес у нескольких предприятий
    po_adresu = collections.defaultdict(set)
    for r in cx.execute('select inn, coalesce(best_email,"") from companies '
                        'where coalesce(best_email,"")<>""'):
        po_adresu[(r[1] or '').lower()].add(str(r[0]))
    obshchie = {e: i for e, i in po_adresu.items() if len(i) > 1}
    sch['best_email всего разных адресов'] = len(po_adresu)
    sch['АДРЕС У НЕСКОЛЬКИХ ПРЕДПРИЯТИЙ (не свой, а посредника)'] = len(obshchie)
    sch['  предприятий, сидящих на таком адресе'] = sum(len(i) for i in obshchie.values())
    for e, inns in sorted(obshchie.items(), key=lambda x: -len(x[1]))[:12]:
        pr['адрес у нескольких'].append((e, '%d предприятий' % len(inns)))

    # ---------- 4. Сколько компаний имеют ТЕХНИЧЕСКИЙ адрес, но best_email общий
    e_po_inn = collections.defaultdict(list)
    for r in cx.execute('select inn, coalesce(email,""), coalesce(role,"") from emails'):
        if r[1]:
            e_po_inn[str(r[0])].append((r[1].lower(), (r[2] or '').lower()))
    upushcheno = 0
    for r in cx.execute('select inn, coalesce(best_email,"") from companies '
                        'where coalesce(best_email,"")<>""'):
        inn, be = str(r[0]), (r[1] or '').lower()
        rows = e_po_inn.get(inn) or []
        rol_be = next((rl for em, rl in rows if em == be), '')
        # у компании ЕСТЬ технический адрес, а выбран общий или пустой по роли
        est_teh = any(TEHNICHESKIE.search(rl) and not NE_ADRESAT.search(rl)
                      for _, rl in rows)
        if est_teh and (rol_be in ('общий', 'приёмная', '') or
                        not TEHNICHESKIE.search(rol_be)):
            upushcheno += 1
            if len(pr['упущен технический адрес']) < 12:
                teh = next(em for em, rl in rows
                           if TEHNICHESKIE.search(rl) and not NE_ADRESAT.search(rl))
                pr['упущен технический адрес'].append(
                    (inn, 'выбран %s (%s)' % (be[:26], rol_be[:14] or 'без роли'),
                     'а есть %s' % teh[:26]))
    sch['КОМПАНИЙ: есть технический адрес, а письмо пойдёт на общий'] = upushcheno

    cx.close()
    for imya, sp in pr.items():
        print('\n=== %s' % imya)
        for x in sp:
            print('   ' + ' | '.join(str(y)[:44] for y in x))
    print()
    for k, v in sch.most_common():
        print('REC %s\t%s' % (k, v))
    print('ИТОГ ' + json.dumps({
        'технических ролей проигрывают info@': poteryano,
        'ложных запретов v2': lozh,
        'адресов у нескольких предприятий': len(obshchie),
        'компаний с упущенным техническим адресом': upushcheno},
        ensure_ascii=False))


if __name__ == '__main__':
    main()
