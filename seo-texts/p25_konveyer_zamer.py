# -*- coding: utf-8 -*-
"""Замер конвейера «новость → лучший ролевой контакт → письмо» на ЖИВЫХ базах.

ЗАЧЕМ. Владелец говорит: много ошибок на стадии «новость = лучший ролевой контакт».
Прежде чем что-то предлагать, надо померить, ГДЕ именно и СКОЛЬКО, — иначе выйдет
починка по рассуждению. Прибор ничего не меняет.

ЧТО ЧИТАЛ В КОДЕ И ПОЧЕМУ ЭТО ПОДОЗРИТЕЛЬНО.

1. РОЛЬ ВЫБИРАЮТ ДВА РАЗНЫХ ПРАВИЛА В ОДНОМ ФАЙЛЕ.
   * `_best_by_role` (строка ~405) — словарь `_ROLE_RANK` с ТОЧНЫМ совпадением
     строки роли: {'снабжение/закупки':0, 'гл.инженер':1, 'директор':2,
     'продажи':3, 'приёмная':4, 'бухгалтерия':5, 'общий':6}, всё прочее → 9.
   * `best_email_v2` (строка ~5257) — ПОДСТРОКИ ('закупк', 'снабж', 'тендер',
     'главный инженер'…) плюс запреты ROLE_DENY/LOCAL_DENY (кадры, пресса,
     бухгалтерия, юристы) с весом -1000 и учёт именного адреса, MX, источника.

   Два места на одно правило расходятся молча. И расходятся ПО СУЩЕСТВУ:
   у v1 «бухгалтерия» это ранг 5, то есть ЛУЧШЕ чем «общий» (6); у v2
   бухгалтерия запрещена совсем. Кто победит — зависит от порядка прогонов.

2. ТОЧНОЕ СОВПАДЕНИЕ СТРОКИ — заслон, который молча отменяет разрешение.
   Роль «снабжение» (без «/закупки»), «гл. инженер» (с пробелом), «Главный
   инженер», «закупки» получают ранг 9 — ХУЖЕ «общего». То есть найденный
   снабженец проигрывает адресу info@.

3. ПРОВАЛ ПРОВАЙДЕРА ДАЁТ ВСЕМ РОЛЬ «общий».
   В regex-фолбэке каждому адресу ставится role='общий'. Тогда у всех ранг 6,
   и `_best_by_role` берёт ПЕРВЫЙ по порядку — то есть случайный. А
   `_is_junk_email` ловит только платформенные домены и noreply: hr@, buh@,
   press@ через него проходят и могут стать получателем.

ЧТО СЧИТАЕТ ПРИБОР (числа, не мнения):
  * сколько ролей в базе НЕ попадают в семь точных ключей v1;
  * на скольких компаниях v1 и v2 выбрали бы РАЗНЫЕ адреса;
  * сколько best_email — «непокупающие» отделы (кадры/пресса/бухгалтерия);
  * сколько получателей стоят на слабом провенансе (verified_by='name');
  * качество новостного повода: длина what, доля вакансий, доля suspect.

Имена колонок НЕ угадываются: сперва печатается pragma table_info.
"""
import collections
import json
import os
import re
import sqlite3

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'

# --- правила ОДИН В ОДИН из кода конвейера (чтобы мерить его, а не свою версию)
V1_RANK = {'снабжение/закупки': 0, 'гл.инженер': 1, 'директор': 2,
           'продажи': 3, 'приёмная': 4, 'бухгалтерия': 5, 'общий': 6}
V2_RANK = (('закупк', 100), ('снабж', 95), ('тендер', 90), ('главный инженер', 85),
           ('гл. инженер', 85), ('технолог', 80), ('производ', 70),
           ('директор', 60), ('руковод', 55), ('менеджер', 40))
V2_DENY = ('кадр', 'hr', 'персонал', 'подбор', 'ваканс', 'пресс', 'press',
           'юрис', 'бухгалт', 'реклам', 'маркет', 'сми')
LOCAL_DENY = ('press', 'pressa', 'smi', 'hr@', 'hr.', 'kadr', 'vacan', 'job',
              'rabota', 'rekla', 'marketing', 'legal', 'urist', 'jurist',
              'buh', 'account', 'noreply', 'no-reply', 'abuse', 'postmaster')
GENERIC = ('info@', 'mail@', 'office@', 'sale@', 'sales@', 'zakaz@', 'order@',
           'secretar', 'priemnaya@', 'inbox@', 'post@', 'contact@', 'reception',
           'admin@', 'support@', 'help@', 'shop@', 'market@')


def v1_rank(role):
    return V1_RANK.get((role or '').strip().lower(), 9)


def deny_local(e):
    lp = (e or '').split('@')[0].lower()
    return any(k.rstrip('@.') in lp for k in LOCAL_DENY)


def v2_score(email, role, person, mxok=0, source=''):
    role = (role or '').lower()
    if any(k in role for k in V2_DENY) or deny_local(email):
        return -1000
    s = 0
    for key, val in V2_RANK:
        if key in role:
            s += val
            break
    if (person or '').strip():
        s += 30
    if not any(g in (email or '').lower() for g in GENERIC):
        s += 25
    if mxok in (1, '1', True):
        s += 10
    if str(source or '').startswith('zakupki'):
        s += 15
    return s


def kolonki(cx, tabl):
    try:
        return [r[1] for r in cx.execute('pragma table_info(%s)' % tabl)]
    except Exception:  # noqa: BLE001
        return []


def main():
    if not os.path.exists(ENRICH):
        print('ИТОГ ' + json.dumps({'enrich.db нет': ENRICH}, ensure_ascii=False))
        return
    cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    print('=== таблицы enrich.db: %s' % ', '.join(sorted(tabl)))
    for t in ('companies', 'emails', 'signals'):
        if t in tabl:
            print('  %-10s колонки: %s' % (t, ', '.join(kolonki(cx, t))))

    sch = collections.Counter()
    primery = collections.defaultdict(list)

    # ---------- 1. РОЛИ: сколько НЕ попадает в точные ключи v1
    e_kol = kolonki(cx, 'emails')
    if 'emails' in tabl and e_kol:
        p_role = 'role' if 'role' in e_kol else ''
        p_mail = 'email' if 'email' in e_kol else ''
        p_inn = 'inn' if 'inn' in e_kol else ''
        p_pers = 'person' if 'person' in e_kol else ''
        p_src = 'source' if 'source' in e_kol else ''
        p_mx = 'mx_ok' if 'mx_ok' in e_kol else ''
        if p_role and p_mail:
            roli = collections.Counter()
            for r in cx.execute('select coalesce(%s,"") from %s' % (p_role, 'emails')):
                roli[(r[0] or '').strip().lower()] += 1
            vsego_r = sum(roli.values())
            ne_v_kluche = sum(n for rl, n in roli.items() if rl not in V1_RANK)
            sch['адресов всего'] = vsego_r
            sch['роль НЕ в семи ключах v1 (ранг 9, хуже «общего»)'] = ne_v_kluche
            print('\n=== роли в базе (первые 18), * = не попадает в ключи v1')
            for rl, n in roli.most_common(18):
                print('  %-34s %6d %s' % (rl[:34] or '(пусто)', n,
                                          '' if rl in V1_RANK else '*'))

            # ---------- 2. РАСХОЖДЕНИЕ v1 и v2 на одной компании
            if p_inn:
                po_inn = collections.defaultdict(list)
                polya = ','.join(x for x in (p_inn, p_mail, p_role, p_pers, p_mx, p_src)
                                 if x)
                for r in cx.execute('select %s from emails' % polya):
                    z = dict(zip([x for x in (p_inn, p_mail, p_role, p_pers, p_mx, p_src)
                                  if x], r))
                    if z.get(p_mail):
                        po_inn[str(z[p_inn])].append(z)
                razoshlis = 0
                for inn, rows in po_inn.items():
                    if len(rows) < 2:
                        continue
                    v1 = sorted(rows, key=lambda z: v1_rank(z.get(p_role)))[0][p_mail]
                    v2 = sorted(rows, key=lambda z: -v2_score(
                        z.get(p_mail), z.get(p_role), z.get(p_pers) if p_pers else '',
                        z.get(p_mx) if p_mx else 0,
                        z.get(p_src) if p_src else ''))[0][p_mail]
                    if (v1 or '').lower() != (v2 or '').lower():
                        razoshlis += 1
                        if len(primery['расхождение']) < 10:
                            r1 = next((x for x in rows if x[p_mail] == v1), {})
                            r2 = next((x for x in rows if x[p_mail] == v2), {})
                            primery['расхождение'].append(
                                (inn, v1, (r1.get(p_role) or '')[:22],
                                 v2, (r2.get(p_role) or '')[:22]))
                sch['компаний с 2+ адресами'] = sum(1 for v in po_inn.values()
                                                    if len(v) >= 2)
                sch['НА НИХ v1 и v2 выбрали РАЗНОЕ'] = razoshlis

    # ---------- 3. best_email: непокупающие отделы и общий адрес
    c_kol = kolonki(cx, 'companies')
    if 'companies' in tabl and 'best_email' in c_kol:
        vsego = zapret = generic = pusto = 0
        for r in cx.execute('select inn, coalesce(best_email,"") from companies'):
            be = (r[1] or '').strip().lower()
            if not be:
                pusto += 1
                continue
            vsego += 1
            if deny_local(be):
                zapret += 1
                if len(primery['best_email запрещённый v2']) < 12:
                    primery['best_email запрещённый v2'].append((r[0], be))
            elif any(g in be for g in GENERIC):
                generic += 1
        sch['компаний с best_email'] = vsego
        sch['  из них адрес ЗАПРЕЩЁН правилом v2 (кадры/пресса/бухгалтерия)'] = zapret
        sch['  из них общий адрес (info@/mail@/office@…)'] = generic
        sch['компаний без best_email'] = pusto

    # ---------- 4. Провенанс адресов
    if 'emails' in tabl and 'verified_by' in e_kol:
        for r in cx.execute('select coalesce(verified_by,""), count(*) from emails '
                            'group by 1 order by 2 desc'):
            sch['провенанс: %s' % (r[0] or '(пусто)')] = r[1]

    # ---------- 5. Новостной повод
    s_kol = kolonki(cx, 'signals')
    if 'signals' in tabl and s_kol:
        p_what = 'what' if 'what' in s_kol else ''
        p_type = 'event_type' if 'event_type' in s_kol else ''
        if p_what:
            dl = [len((r[0] or '')) for r in cx.execute(
                'select coalesce(%s,"") from signals' % p_what)]
            dl_s = sorted(dl)
            sch['сигналов всего'] = len(dl)
            sch['  what короче 60 знаков (огрызок заголовка)'] = sum(
                1 for x in dl if x < 60)
            if dl_s:
                sch['  медиана длины what'] = dl_s[len(dl_s) // 2]
        if p_type:
            for r in cx.execute('select coalesce(%s,""), count(*) from signals '
                                'group by 1 order by 2 desc limit 8' % p_type):
                sch['тип события: %s' % (r[0] or '(пусто)')] = r[1]
        if 'suspect' in s_kol:
            sch['сигналов в карантине suspect=1'] = cx.execute(
                'select count(*) from signals where coalesce(suspect,0)=1').fetchone()[0]

    cx.close()

    for imya, sp in primery.items():
        print('\n=== %s (примеры)' % imya)
        for x in sp:
            print('   ' + ' | '.join(str(y)[:38] for y in x))

    print()
    for k, v in sch.items():
        print('REC %s\t%s' % (k, v))
    print('ИТОГ ' + json.dumps({
        'адресов': sch.get('адресов всего', 0),
        'роль вне ключей v1': sch.get('роль НЕ в семи ключах v1 (ранг 9, хуже «общего»)', 0),
        'v1 и v2 разошлись на компаниях': sch.get('НА НИХ v1 и v2 выбрали РАЗНОЕ', 0),
        'best_email запрещённых v2': sch.get(
            '  из них адрес ЗАПРЕЩЁН правилом v2 (кадры/пресса/бухгалтерия)', 0)},
        ensure_ascii=False))


if __name__ == '__main__':
    main()
