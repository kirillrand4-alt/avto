# -*- coding: utf-8 -*-
"""Третий продавец в обзвоне «Центробежные»: создать user3 и отдать ему треть ВИДИМОЙ базы.

Что измерено до работы (не предположено):

    назначено всего ............ 1 615
    скрыто целиком ..............  931   <- в панели их не видно
    видно оператору .............  666   (user1 333, user2 333)
    из них уже в работе .........   41   (есть состояние, комментарий или запись в журнале)
    свободно в очереди ..........  625   (user1 311, user2 314)

Владелец: «которые уже в работе, не надо брать; только те, которые в очереди стоят»
и «нужны именно отображаемые». Поэтому трогаем ТОЛЬКО очередь видимых компаний.

Делёж справедливый по нескольким признакам сразу, а не по числу строк: у трёх продавцов
должны сойтись количество компаний, число с техническим контактом, с телефоном, с
закупщиком и сумма приоритета. Способ — жадный: идём от самой ценной компании к самой
простой и каждую отдаём тому, у кого сейчас наибольшее отставание по этим признакам.
Уже взятое в работу считается стартовой нагрузкой владельца — иначе новичок получит
меньше живой работы, чем кажется по числу строк.

Запуск: panel_py, argv = ["proba"] — только расчёт, ничего не пишем;
                    argv = ["primenit", "<пароль>"] — создать user3 и записать распределение.
"""
import json, os, sqlite3, shutil, sys, time

sys.path.insert(0, r'C:\seostat')

SALES = r'C:\seostat\data\centro_sales.db'
CENTRO = r'C:\seostat\data\centrifugal.db'
PRIZNAKI = ('has_tech', 'has_phone', 'has_purchaser', 'has_signal')


def sobrat():
    s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
    c = sqlite3.connect('file:%s?mode=ro' % CENTRO, uri=True)
    naz = {r[0]: {'username': r[1], 'score': r[2] or 0.0, 'has_phone': r[3] or 0,
                  'has_purchaser': r[4] or 0, 'has_tech': r[5] or 0, 'has_signal': r[6] or 0}
           for r in s.execute('select inn, username, assignment_score, has_phone, '
                              'has_purchaser, has_tech, has_signal from company_assignment')}
    skryt = {r[0] for r in s.execute("select inn from hidden_item where kind='company'")}
    est = {r[0] for r in c.execute('select inn from company')}
    tronuto = {r[0] for r in s.execute('select inn from company_state')}
    tronuto |= {r[0] for r in s.execute('select distinct inn from company_comment')}
    tronuto |= {r[0] for r in s.execute('select distinct inn from activity_log')}
    s.close(); c.close()
    vidno = {i: v for i, v in naz.items() if i not in skryt and i in est}
    ochered = {i: v for i, v in vidno.items() if i not in tronuto}
    v_rabote = {i: v for i, v in vidno.items() if i in tronuto}
    return vidno, ochered, v_rabote


def nagruzka(spisok):
    d = {'shtuk': len(spisok), 'ball': sum(x['score'] for x in spisok)}
    for p in PRIZNAKI:
        d[p] = sum(x[p] for x in spisok)
    return d


def podelit(ochered, v_rabote, polzovateli):
    """Отбор равномерный по рангу, с добором до РАВНОГО ИТОГА.

    Две версии до этой были хуже, и обе поправлены замером:
      1) жадная («отдай тому, кто сильнее отстаёт») дала перекос 219/202/245
         и переназначила 441 строку из 625 — перетасовку почти всей базы ради трети;
      2) «каждая третья» дала 230/229/207: у старожилов есть компании В РАБОТЕ,
         а у новичка их нет, поэтому равная доля ОЧЕРЕДИ даёт неравный ИТОГ.

    Здесь цель — равный итог по видимой базе: 666 / 3 = 222 у каждого. Сколько отдать,
    считается от того, сколько у владельца уже в работе. Отдаём равномерно по рангу
    (шаг по отсортированному списку), чтобы новичку достался такой же срез сверху донизу.
    """
    korzina = {u: [] for u in polzovateli}
    novichok = polzovateli[-1]
    starye = polzovateli[:-1]
    vsego_vidno = len(ochered) + len(v_rabote)
    cel = vsego_vidno // len(polzovateli)
    for u in starye:
        moi = sorted([dict(v, inn=i) for i, v in ochered.items() if v['username'] == u],
                     key=lambda x: (-x['score'], -x['has_tech'], -x['has_phone']))
        v_rab = sum(1 for v in v_rabote.values() if v['username'] == u)
        ostavit = max(0, cel - v_rab)          # столько очереди оставляем владельцу
        otdat = max(0, len(moi) - ostavit)     # остальное новичку
        shag = len(moi) / otdat if otdat else 0
        beru = {int(k * shag + shag / 2) for k in range(otdat)} if otdat else set()
        for nomer, x in enumerate(moi):
            (korzina[novichok] if nomer in beru else korzina[u]).append(x)
    return korzina, {'cel_na_prodavca': cel}


def otchet(korzina, start_rabota, polzovateli):
    out = {}
    for u in polzovateli:
        v_rab = [v for i, v in start_rabota.items() if v['username'] == u]
        itog = nagruzka(v_rab + korzina[u])
        out[u] = {'в работе (не трогаем)': len(v_rab), 'из очереди': len(korzina[u]),
                  'ИТОГО компаний': itog['shtuk'],
                  'с техконтактом': itog['has_tech'], 'с телефоном': itog['has_phone'],
                  'с закупщиком': itog['has_purchaser'],
                  'сумма приоритета': round(itog['ball'])}
    return out


def main():
    rezhim = sys.argv[1] if len(sys.argv) > 1 else 'proba'
    parol = sys.argv[2] if len(sys.argv) > 2 else ''
    polzovateli = ['user1', 'user2', 'user3']
    vidno, ochered, v_rabote = sobrat()
    korzina, cel = podelit(ochered, v_rabote, polzovateli)
    itog = {'rezhim': rezhim,
            'vidno_operatoru': len(vidno), 'v_rabote': len(v_rabote), 'v_ocheredi': len(ochered),
            'bylo': {}, 'stanet': otchet(korzina, v_rabote, polzovateli)}
    for u in ('user1', 'user2'):
        est = [v for v in vidno.values() if v['username'] == u]
        itog['bylo'][u] = {'ИТОГО компаний': len(est),
                           'с техконтактом': sum(x['has_tech'] for x in est),
                           'с телефоном': sum(x['has_phone'] for x in est),
                           'с закупщиком': sum(x['has_purchaser'] for x in est),
                           'сумма приоритета': round(sum(x['score'] for x in est))}
    # сколько компаний реально сменит владельца
    smena = sum(1 for u in polzovateli for x in korzina[u]
                if ochered[x['inn']]['username'] != u)
    itog['smenyat_vladelca'] = smena

    if rezhim == 'primenit':
        if not parol:
            itog['ОШИБКА'] = 'нужен пароль для user3'
            print(json.dumps(itog, ensure_ascii=False)); return
        kopiya = SALES + '.bak-user3-%d' % int(time.time())
        shutil.copyfile(SALES, kopiya)
        itog['kopiya_bazy'] = kopiya
        # bcrypt стоит только в окружении службы (C:\seostat\.venv), а panel_py идёт
        # системным питоном. Поэтому пользователя заводим ШТАТНОЙ функцией, но её
        # питоном — иначе пришлось бы самому считать хеш пароля, а это ровно тот случай,
        # когда самодельное хуже готового.
        import subprocess
        venv = r'C:\seostat\.venv\Scripts\python.exe'
        r = subprocess.run(
            [venv, '-c',
             'from app.services import centro_sales as CS; '
             'CS.upsert_user("user3", %r, role="sales"); print("ok")' % parol],
            cwd=r'C:\seostat', capture_output=True, text=True, timeout=120)
        itog['sozdanie_user3'] = (r.stdout or '').strip() + (r.stderr or '')[:200]
        if 'ok' not in (r.stdout or ''):
            itog['ОШИБКА'] = 'user3 не создан, распределение НЕ применяю'
            print(json.dumps(itog, ensure_ascii=False, indent=1)); return
        conn = sqlite3.connect(SALES)
        n = 0
        for u in polzovateli:
            for x in korzina[u]:
                if ochered[x['inn']]['username'] != u:
                    conn.execute("update company_assignment set username=?, assigned_at=?, "
                                 "assigned_by=? where inn=?",
                                 (u, time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime()),
                                  'balans-3-prodavca', x['inn']))
                    n += conn.total_changes and 1 or 0
        conn.commit()
        itog['perenazncheno_strok'] = conn.total_changes
        # контрольный пересчёт ИЗ БАЗЫ, а не из расчёта
        pr = {}
        for r in conn.execute("""select a.username, count(*), sum(a.has_tech), sum(a.has_phone),
                 sum(a.has_purchaser), sum(a.assignment_score) from company_assignment a
                 where a.inn not in (select inn from hidden_item where kind='company')
                 group by a.username"""):
            pr[r[0]] = {'компаний': r[1], 'с техконтактом': r[2], 'с телефоном': r[3],
                        'с закупщиком': r[4], 'сумма приоритета': round(r[5] or 0)}
        itog['PROVERKA_IZ_BAZY'] = pr
        conn.close()
    print(json.dumps(itog, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
