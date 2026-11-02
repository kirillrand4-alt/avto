# -*- coding: utf-8 -*-
r"""fixVR (02.11): панель Meyer – компании уволившегося Волкова (meyer4) поровну остальным менеджерам в «Вся очередь».

Владелец 02.11: «волков, те что были у него, раскидай равномерно во "вся очередь" остальным» / «он уволился»;
на вопрос про 8 «Дубль» и 8 «Не понравилась» – «Раздать все 270»; вход Волкову – «Оставить вход».

Как: все назначения meyer4 делятся между активными продавцами (кроме него) поровну по числу, порядок – по баллу
очереди «змейкой» (качество поровну), группа холдинга (holding_chlen каталога) – целиком одному. Меняется только
company_assignment: username, assigned_at (сейчас), assigned_by («fixVR 02.11: …»), прежний владелец – в колонке
vladelec_do_fixVR. Состояние Волкова (company_state) новому владельцу НЕ копируется – у получателя компания без
статуса, то есть в «Вся очередь»; записи Волкова (статус, комментарии, журнал) остаются как история. Балл и ступень
не меняются (от владельца не зависят). Копия базы – C:\centro2\_bekap\fixVR-<время>\, журнал – на дроп.

    python3 zapusk_na_servere.py fixVR_razdel.py            # план без записи
    python3 zapusk_na_servere.py fixVR_razdel.py --primenit
Откат: UPDATE company_assignment SET username=vladelec_do_fixVR WHERE vladelec_do_fixVR IS NOT NULL
       (assigned_at/assigned_by прежние – в журнале на дропе).
"""
import collections
import io
import json
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
OT = 'meyer4'
PRICHINA = 'fixVR 02.11: Волков уволился, раздача поровну'


def main():
    primenit = '--primenit' in sys.argv
    s = sqlite3.connect(SALES, timeout=30)
    s.row_factory = sqlite3.Row
    fio = dict(s.execute('SELECT username, fio FROM users').fetchall())
    komu = [r[0] for r in s.execute("SELECT username FROM users WHERE role='sales' AND is_active=1 AND username<>? "
                                    "ORDER BY username", (OT,))]
    print('от: %s (%s); кому: %s' % (OT, fio.get(OT), ', '.join('%s %s' % (u, fio.get(u)) for u in komu)))
    rows = [dict(r) for r in s.execute('SELECT * FROM company_assignment WHERE username=?', (OT,))]
    st = {r['inn']: r['call_result'] for r in s.execute('SELECT inn, call_result FROM company_state WHERE username=?', (OT,))}
    u_drugih = s.execute('SELECT COUNT(*) FROM company_state WHERE username<>? AND inn IN (SELECT inn FROM company_assignment '
                         'WHERE username=?)', (OT, OT)).fetchone()[0]
    print('у Волкова: %d; статусы: %s; состояний этих ИНН у других: %d' % (
        len(rows), dict(collections.Counter(st.get(r['inn']) or 'new' for r in rows)), u_drugih))

    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True, timeout=30)
    hold = {str(i): str(g) for i, g in k.execute('SELECT inn, gruppa FROM holding_chlen') if g}
    nazv = dict(k.execute('SELECT inn, predpriyatie FROM company').fetchall())

    # группы холдинга (у Волкова), порядок – по лучшему баллу группы
    gruppy = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: -float(r.get('assignment_score') or 0)):
        gruppy.setdefault(hold.get(r['inn']) or ('#' + r['inn']), []).append(r)
    cel = {u: len(rows) // len(komu) + (1 if i < len(rows) % len(komu) else 0) for i, u in enumerate(komu)}
    sch, ball, plan = collections.Counter(), collections.Counter(), {}
    for g, chleny in gruppy.items():
        # кому: у кого больше всего свободного места до цели; при равенстве – меньше набранный балл
        kto = max(komu, key=lambda u: (cel[u] - sch[u], -ball[u]))
        for r in chleny:
            plan[r['inn']] = kto
            sch[kto] += 1
            ball[kto] += float(r.get('assignment_score') or 0)
    grupp_bolshe1 = sum(1 for ch in gruppy.values() if len(ch) > 1)
    print('групп холдинга среди его компаний (>1 компании): %d' % grupp_bolshe1)
    print('\nПЛАН (получит / сумма балла / из них со статусом Волкова «взял»/«не понр.»/«дубль»):')
    for u in komu:
        mine = [i for i, x in plan.items() if x == u]
        c = collections.Counter(st.get(i) or 'new' for i in mine)
        print('  %-7s %-20s +%3d  балл %8.1f  v_rabote %d, ne_ponravilas %d, dubl %d' % (
            u, fio.get(u), sch[u], ball[u], c['v_rabote'], c['ne_ponravilas'], c['dubl']))
    seychas = dict(s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall())
    print('сейчас назначено:', seychas)
    print('станет:', {u: seychas.get(u, 0) + sch[u] for u in komu}, '| у', OT, 0)
    if not primenit:
        print('\nПЛАН: ничего не записано')
        return

    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    os.write(fd, ('fixVR %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
    os.close(fd)
    try:
        papka = os.path.join(KOREN, '_bekap', 'fixVR-' + VREMYA)
        os.makedirs(papka, exist_ok=True)
        b = sqlite3.connect(os.path.join(papka, 'centro_sales_meyer1.db'))
        s.backup(b)
        b.close()
        if 'vladelec_do_fixVR' not in {r[1] for r in s.execute('PRAGMA table_info(company_assignment)')}:
            s.execute('ALTER TABLE company_assignment ADD COLUMN vladelec_do_fixVR TEXT')
        teper = datetime.now(timezone.utc).isoformat(timespec='seconds')
        zhurnal = []
        s.execute('BEGIN IMMEDIATE')
        try:
            for r in rows:
                kto = plan[r['inn']]
                n = s.execute('UPDATE company_assignment SET vladelec_do_fixVR=username, username=?, assigned_at=?, assigned_by=? '
                              'WHERE inn=? AND username=?', (kto, teper, PRICHINA, r['inn'], OT)).rowcount
                if n != 1:
                    raise RuntimeError('строка %s изменилась – откат' % r['inn'])
                zhurnal.append({'inn': r['inn'], 'nazvanie': nazv.get(r['inn']), 'ot': OT, 'komu': kto,
                                'status_u_volkova': st.get(r['inn']) or 'new',
                                'assigned_at_bylo': r.get('assigned_at'), 'assigned_by_bylo': r.get('assigned_by')})
            s.execute('COMMIT')
        except BaseException:
            s.execute('ROLLBACK')
            raise
        zh = os.path.join(DROP, 'fixVR-razdel-zhurnal-%s.json' % VREMYA)
        io.open(zh, 'w', encoding='utf-8').write(json.dumps(zhurnal, ensure_ascii=False, indent=0))
        print('\nЗАПИСАНО: %d; теперь %s; копия базы %s; журнал %s' % (
            len(zhurnal), dict(s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall()),
            papka, os.path.basename(zh)))
        print('откат: UPDATE company_assignment SET username=vladelec_do_fixVR WHERE vladelec_do_fixVR IS NOT NULL')
    finally:
        try:
            os.remove(ZAMOK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
