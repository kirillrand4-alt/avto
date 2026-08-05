# -*- coding: utf-8 -*-
"""Сухой прогон единого правила выбора адресата по ЖИВОЙ базе. НИЧЕГО не пишет.

Предлагать «давайте починим» мало: надо показать, что именно поменяется на 4 565
компаниях с адресом. Прибор берёт правило из `p25_rol_adresata.py`, прогоняет по
enrich.db и раскладывает изменения ПО ПРИЧИНАМ, а не одним числом. Каждое изменение
подписано: почему новый адрес лучше старого.

Направления считаются отдельно, потому что это разные по цене вещи:
  * общий -> технический: письмо дойдёт до того, кто решает (главная выгода);
  * непокупающий отдел -> любой годный: письмо перестанет уходить в кадры;
  * адрес посредника -> адрес предприятия: письмо перестанет уходить в холдинг;
  * стало ПУСТО: слать было некому, и честнее это увидеть, чем слать в кадры.
"""
import collections
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r'C:\sender\_ops')

# Раннер кладёт мои файлы с приставкой «3s_», поэтому модуль на сервере называется
# иначе, чем в репозитории. Импорт по одному имени тихо падает — ищу оба, и если
# не найден ни один, это будет ВИДНО, а не сойдёт за пустой прогон.
R = None
for _imya in ('p25_rol_adresata', '3s_p25_rol_adresata'):
    try:
        import importlib
        R = importlib.import_module(_imya)
        break
    except Exception:  # noqa: BLE001
        for _put in (r'C:\sender\_ops\3s_p25_rol_adresata.py',
                     os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'p25_rol_adresata.py')):
            if os.path.exists(_put):
                import importlib.util
                _sp = importlib.util.spec_from_file_location('rol_adresata', _put)
                R = importlib.util.module_from_spec(_sp)
                _sp.loader.exec_module(R)
                break
        if R:
            break
if R is None:
    print('ИТОГ ' + json.dumps({'модуль правила не найден': True}, ensure_ascii=False))
    raise SystemExit

ENRICH = r'C:\sender\enrich.db'


def main():
    if not os.path.exists(ENRICH):
        print('ИТОГ ' + json.dumps({'нет базы': ENRICH}, ensure_ascii=False))
        return
    cx = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    e_kol = [r[1] for r in cx.execute('pragma table_info(emails)')]
    c_kol = [r[1] for r in cx.execute('pragma table_info(companies)')]
    print('emails: %s' % ', '.join(e_kol))
    print('companies: %s' % ', '.join(c_kol))

    # Адреса, стоящие у нескольких ИНН — считаем по ВСЕЙ таблице адресов, а не по
    # best_email: посредник может быть ещё не выбран лучшим, но уже виден.
    po_adresu = collections.defaultdict(set)
    for r in cx.execute('select inn, lower(coalesce(email,"")) from emails '
                        'where coalesce(email,"")<>""'):
        po_adresu[r[1]].add(str(r[0]))
    u_neskolkih = {e for e, i in po_adresu.items() if len(i) > 1}
    print('адресов у нескольких предприятий: %d' % len(u_neskolkih))

    polya = [x for x in ('inn', 'email', 'role', 'person', 'mx_ok', 'source') if x in e_kol]
    po_inn = collections.defaultdict(list)
    for r in cx.execute('select %s from emails' % ','.join(polya)):
        z = dict(zip(polya, r))
        if z.get('email'):
            po_inn[str(z['inn'])].append(z)

    sayt_po_inn = {}
    if 'site' in c_kol:
        for r in cx.execute('select inn, coalesce(site,"") from companies'):
            sayt_po_inn[str(r[0])] = r[1]

    sch = collections.Counter()
    primery = collections.defaultdict(list)
    for r in cx.execute('select inn, coalesce(best_email,"") from companies'):
        inn, staryy = str(r[0]), (r[1] or '').strip().lower()
        kont = po_inn.get(inn) or []
        if not kont:
            continue
        novyy, pochemu, razbor = R.vybrat_adresata(
            kont, sayt_po_inn.get(inn, ''), u_neskolkih)
        sch['компаний рассмотрено'] += 1
        if novyy == staryy:
            sch['адресат не меняется'] += 1
            continue
        if not staryy:
            sch['был пуст -> назначен адресат'] += 1
            if len(primery['был пуст']) < 6:
                primery['был пуст'].append((inn, novyy, pochemu))
            continue
        if not novyy:
            prich = R.ne_adresat(staryy, next(
                (k.get('role') for k in kont if (k.get('email') or '').lower() == staryy),
                ''))
            sch['СТАЛО ПУСТО: слать было некому (%s)' % (prich or 'непригоден')] += 1
            if len(primery['стало пусто']) < 8:
                primery['стало пусто'].append((inn, staryy, prich or 'непригоден'))
            continue
        # Направление изменения
        st_rol = next((k.get('role') or '' for k in kont
                       if (k.get('email') or '').lower() == staryy), '')
        nv_rol = next((k.get('role') or '' for k in kont
                       if (k.get('email') or '').lower() == novyy), '')
        prichina_st = R.ne_adresat(staryy, st_rol)
        if prichina_st:
            vid = 'непокупающий отдел -> годный адрес'
        elif staryy in u_neskolkih:
            vid = 'адрес посредника -> адрес предприятия'
        elif R.ves_roli(nv_rol)[0] > R.ves_roli(st_rol)[0]:
            vid = 'общий/слабый -> ТЕХНИЧЕСКИЙ или закупки'
        elif R.domen(novyy) == R.domen(sayt_po_inn.get(inn, '')) and \
                R.domen(staryy) != R.domen(sayt_po_inn.get(inn, '')):
            vid = 'чужой домен -> домен предприятия'
        else:
            vid = 'прочее изменение'
        sch['ИЗМЕНЕНИЕ: ' + vid] += 1
        if len(primery[vid]) < 7:
            primery[vid].append((inn, '%s (%s)' % (staryy[:30], st_rol[:16] or 'без роли'),
                                 '-> %s (%s)' % (novyy[:30], nv_rol[:16] or 'без роли'),
                                 pochemu[:52]))
    cx.close()

    for vid, sp in primery.items():
        print('\n=== %s' % vid)
        for x in sp:
            print('   ' + ' | '.join(str(y)[:46] for y in x))
    print()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    menyaetsya = sum(v for k, v in sch.items() if k.startswith('ИЗМЕНЕНИЕ')) \
        + sch.get('был пуст -> назначен адресат', 0) \
        + sum(v for k, v in sch.items() if k.startswith('СТАЛО ПУСТО'))
    print('ИТОГ ' + json.dumps({
        'рассмотрено компаний': sch.get('компаний рассмотрено', 0),
        'адресат поменяется': menyaetsya,
        'из них на технический/закупки': sch.get(
            'ИЗМЕНЕНИЕ: общий/слабый -> ТЕХНИЧЕСКИЙ или закупки', 0),
        'из них уйдёт из кадров/бухгалтерии': sch.get(
            'ИЗМЕНЕНИЕ: непокупающий отдел -> годный адрес', 0),
        'из них уйдёт от посредника': sch.get(
            'ИЗМЕНЕНИЕ: адрес посредника -> адрес предприятия', 0)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
