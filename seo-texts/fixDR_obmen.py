# -*- coding: utf-8 -*-
r"""fixDR (16.11): панель Meyer – вернуть «домашние регионы» обменом 1:1.

Правило владельца 13.10: Алтайский край – только барнаульским, Краснодарский край – только краснодарским, Воронежская
область – только воронежским. Раздача компаний Волкова (fixVR 02.11, «поровну всем») это правило нарушила: 9 алтайских
ушли краснодарским и воронежским. Владелец 16.11: «перекинь их в свои регионы для всех».

Как: каждая компания «не дома» (только без работы менеджера: без статуса, комментариев и недозвонов) уходит менеджеру
своего города, а он взамен отдаёт одну компанию из доли Волкова (vladelec_do_fixVR) нейтрального региона (не из трёх
домашних), тоже без работы и не из холдинга, с ближайшим баллом; у одного менеджера – не больше ceil(N/команда) обменов.
Итог: число компаний и доля Волкова у каждого прежние. Если пары нет – простой перенос тому из команды, у кого меньше
компаний. Меняется только company_assignment (username, assigned_at, assigned_by, прежний владелец – vladelec_do_fixDR).
Повторный запуск без нарушений ничего не делает. Копия базы – C:\centro2\_bekap\fixDR-<время>\, журнал – на дроп.

    python3 zapusk_na_servere.py fixDR_obmen.py            # план без записи
    python3 zapusk_na_servere.py fixDR_obmen.py --primenit
Откат: UPDATE company_assignment SET username=vladelec_do_fixDR WHERE vladelec_do_fixDR IS NOT NULL
"""
import collections
import io
import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

KOREN = r'C:\centro2'
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
ZAMOK = os.path.join(KOREN, '_zamok.txt')
DROP = r'C:\seostat\drop\drop-storage'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
DOM = {'Алтайский край': 'Барнаул', 'Краснодарский край': 'Краснодар', 'Воронежская область': 'Воронеж'}
PRICHINA = 'fixDR 16.11: домашний регион (правило 13.10)'


def main():
    primenit = '--primenit' in sys.argv
    s = sqlite3.connect(SALES, timeout=30)
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    lyudi = {u: (f, g) for u, f, g in s.execute("SELECT username, fio, COALESCE(gorod,'') FROM users "
                                                "WHERE role='sales' AND is_active=1")}
    akol = {r[1] for r in s.execute('PRAGMA table_info(company_assignment)')}
    vr = 'vladelec_do_fixVR' if 'vladelec_do_fixVR' in akol else 'NULL'
    rows = {i: (u, float(b or 0), v) for i, u, b, v in s.execute(
        'SELECT inn, username, assignment_score, %s FROM company_assignment' % vr)}
    region = dict(k.execute('SELECT inn, region FROM company').fetchall())
    nazv = dict(k.execute('SELECT inn, predpriyatie FROM company').fetchall())
    hold = {str(i) for i, g in k.execute('SELECT inn, gruppa FROM holding_chlen') if g}
    rabota = {(i, u) for i, u, r in s.execute("SELECT inn, username, COALESCE(call_result,'new') FROM company_state") if r != 'new'}
    rabota |= {(i, u) for i, u in s.execute('SELECT inn, username FROM company_comment')}
    try:
        rabota |= {(i, u) for i, u in s.execute('SELECT inn, state_user FROM zvonok_sobytie')}
    except sqlite3.OperationalError:
        pass

    def gorod(u):
        return lyudi.get(u, ('', ''))[1]

    nar = sorted((i for i, (u, b, v) in rows.items() if region.get(i) in DOM and gorod(u) != DOM[region[i]]),
                 key=lambda i: -rows[i][1])
    s_rabotoy = [i for i in nar if (i, rows[i][0]) in rabota]
    nar = [i for i in nar if i not in s_rabotoy]
    print('нарушений: %d (из них с работой менеджера – не трогаю: %d)' % (len(nar) + len(s_rabotoy), len(s_rabotoy)))
    for i in s_rabotoy:
        print('  С РАБОТОЙ, оставлено: %s %s %s у %s' % (i, nazv.get(i), region.get(i), lyudi[rows[i][0]][0]))
    if not nar:
        print('нечего переносить')
        return
    sch = collections.Counter(u for u, b, v in rows.values())
    plan, zanyato, otdal = [], set(), collections.Counter()
    for i in nar:
        u_ot = rows[i][0]
        g = DOM[region[i]]
        komanda = [u for u in lyudi if gorod(u) == g]
        predel = math.ceil(len(nar) / max(1, len(komanda)))
        kand = [j for j, (u, b, v) in rows.items() if u in komanda and v and j not in zanyato and j not in hold
                and region.get(j) not in DOM and (j, u) not in rabota and otdal[u] < predel]
        if kand:
            j = min(kand, key=lambda j: (abs(rows[j][1] - rows[i][1]), otdal[rows[j][0]], j))
            u_k = rows[j][0]
            zanyato |= {i, j}
            otdal[u_k] += 1
            plan.append({'inn': i, 'ot': u_ot, 'komu': u_k, 'obmen_na': j})
            plan.append({'inn': j, 'ot': u_k, 'komu': u_ot, 'obmen_na': i})
        else:
            u_k = min(komanda, key=lambda u: (sch[u], u))
            sch[u_k] += 1
            sch[u_ot] -= 1
            plan.append({'inn': i, 'ot': u_ot, 'komu': u_k, 'obmen_na': None})
    print('\nПЛАН (%d перемещений):' % len(plan))
    for p in plan:
        print('  %s %-34s %-22s балл %7.1f  %s → %s%s' % (
            p['inn'], (nazv.get(p['inn']) or '')[:34], (region.get(p['inn']) or '')[:22], rows[p['inn']][1],
            lyudi[p['ot']][0], lyudi[p['komu']][0], '  (обмен на %s)' % p['obmen_na'] if p['obmen_na'] else '  (без пары)'))
    if not primenit:
        print('\nПЛАН: ничего не записано')
        return

    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    os.write(fd, ('fixDR %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
    os.close(fd)
    try:
        papka = os.path.join(KOREN, '_bekap', 'fixDR-' + VREMYA)
        os.makedirs(papka, exist_ok=True)
        b = sqlite3.connect(os.path.join(papka, 'centro_sales_meyer1.db'))
        s.backup(b)
        b.close()
        if 'vladelec_do_fixDR' not in akol:
            s.execute('ALTER TABLE company_assignment ADD COLUMN vladelec_do_fixDR TEXT')
        teper = datetime.now(timezone.utc).isoformat(timespec='seconds')
        s.execute('BEGIN IMMEDIATE')
        try:
            for p in plan:
                n = s.execute('UPDATE company_assignment SET vladelec_do_fixDR=username, username=?, assigned_at=?, assigned_by=? '
                              'WHERE inn=? AND username=?', (p['komu'], teper, PRICHINA, p['inn'], p['ot'])).rowcount
                if n != 1:
                    raise RuntimeError('строка %s изменилась – откат' % p['inn'])
            s.execute('COMMIT')
        except BaseException:
            s.execute('ROLLBACK')
            raise
        zh = os.path.join(DROP, 'fixDR-obmen-zhurnal-%s.json' % VREMYA)
        io.open(zh, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=0))
        ost = [i for i, u in s.execute('SELECT inn, username FROM company_assignment')
               if region.get(i) in DOM and gorod(u) != DOM[region[i]]]
        print('\nЗАПИСАНО: %d; нарушений осталось %d; копия базы %s; журнал %s' % (len(plan), len(ost), papka, os.path.basename(zh)))
        print('закреплено:', {lyudi[u][0]: n for u, n in s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1')
                              if u in lyudi})
    finally:
        try:
            os.remove(ZAMOK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
