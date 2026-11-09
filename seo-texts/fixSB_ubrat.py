# -*- coding: utf-8 -*-
r"""fixSB (09.11): панель Meyer – убрать правый блок «нынешний статус» / «за всё время» из таблицы «По менеджерам по продажам».

Владелец 09.11: блок почти дублирует левый (при «всё время» совпадает, остаток очереди есть в «Темп и прогноз») –
«давай его уберём». Меняются только шаблоны: templates/_statblok.html (вторая группа шапки, вторые ячейки строк,
colspan пустой строки 13->7, сноска про «за всё время») и заголовок в templates/centro_stats.html. Python не
трогается, перезапуск не нужен (шаблоны перечитываются). Заодно – сверка «в очереди» по живой базе.

    python3 zapusk_na_servere.py fixSB_ubrat.py            # сверка и план, без записи
    python3 zapusk_na_servere.py fixSB_ubrat.py --primenit
Откат: вернуть файлы из C:\centro2\_bekap\fixSB-<время>\.
"""
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
T = os.path.join(KOREN, 'app', 'templates')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
ZAMOK = os.path.join(KOREN, '_zamok.txt')

TH2 = ('<th class="razd">взял в работу</th><th>не понравилась</th><th>дубль</th><th title="переведено в привлечение">'
       'привлечение</th><th>в очереди</th><th title="попыток «не дозвонился» (компания осталась в очереди)">не дозвонился</th>')
PRAVKI = [
    ('_statblok.html', '\n            <th class="gr razd" colspan="6">{% if statblok.vse %}нынешний статус{% else %}за всё время'
                       '{% endif %}</th></tr>', '</tr>'),
    ('_statblok.html', '\n            ' + TH2 + '</tr>', '</tr>'),
    ('_statblok.html', '{{ chetyre(statblok.itog.den, statblok.itog_ss_den) }}{{ chetyre(statblok.itog.vse, statblok.itog_ss_vse) }}',
                       '{{ chetyre(statblok.itog.den, statblok.itog_ss_den) }}'),
    ('_statblok.html', '{{ chetyre(z.den, z.ss_den) }}{{ chetyre(z.vse, z.ss_vse) }}', '{{ chetyre(z.den, z.ss_den) }}'),
    ('_statblok.html', '<td colspan="13" class="tiho">', '<td colspan="7" class="tiho">'),
    ('_statblok.html', 'За всё время – нынешний статус; в очереди только то, что менеджер по продажам видит (без скрытых).',
                       'В очереди – только то, что менеджер по продажам видит (без скрытых).'),
    ('_statblok.html', '{% if statblok.itog.vse.prochee %}\n        Ещё {{ statblok.itog.vse.prochee }} – со старым статусом вне '
                       'этих трёх.{% endif %}', ''),
    ('centro_stats.html', '<h2>По менеджерам по продажам: за период и за всё время</h2>', '<h2>По менеджерам по продажам: за период</h2>'),
]


def sverka():
    s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
    vybor = ('v_rabote', 'ne_ponravilas', 'dubl', 'privlechenie')
    print('сверка очереди (живая база): закреплено − со статусом − скрыто = в очереди')
    for u, fio in s.execute("SELECT username, fio FROM users WHERE role='sales' AND is_active=1 ORDER BY fio"):
        n = s.execute('SELECT COUNT(*) FROM company_assignment WHERE username=?', (u,)).fetchone()[0]
        st = s.execute('SELECT COUNT(*) FROM company_assignment a JOIN company_state c ON c.inn=a.inn AND c.username=a.username '
                       'WHERE a.username=? AND c.call_result IN (%s)' % ','.join('?' * len(vybor)), (u, *vybor)).fetchone()[0]
        sk = s.execute("SELECT COUNT(DISTINCT a.inn) FROM company_assignment a JOIN hidden_item h ON h.inn=a.inn AND h.kind='company' "
                       'WHERE a.username=?', (u,)).fetchone()[0]
        print('  %-20s %4d − %3d − %2d = %4d' % (fio, n, st, sk, n - st - sk))
    print('компании Волкова (fixVR 02.11) у получателей: получил / ещё в очереди / уже отметил сам')
    for u, fio in s.execute("SELECT username, fio FROM users WHERE role='sales' AND is_active=1 ORDER BY fio"):
        pol = s.execute('SELECT COUNT(*) FROM company_assignment WHERE username=? AND vladelec_do_fixVR IS NOT NULL', (u,)).fetchone()[0]
        otm = s.execute('SELECT COUNT(*) FROM company_assignment a JOIN company_state c ON c.inn=a.inn AND c.username=a.username '
                        "WHERE a.username=? AND a.vladelec_do_fixVR IS NOT NULL AND COALESCE(c.call_result,'new')<>'new'", (u,)).fetchone()[0]
        print('  %-20s %3d / %3d / %3d' % (fio, pol, pol - otm, otm))


def main():
    sverka()
    teksty = {}
    for f, staroe, _n in PRAVKI:
        teksty.setdefault(f, io.open(os.path.join(T, f), encoding='utf-8').read())
    for i, (f, staroe, novoe) in enumerate(PRAVKI, 1):
        n = teksty[f].count(staroe)
        print('%d. %-18s вхождений %d' % (i, f, n))
        if n != 1:
            raise SystemExit('правка %d: ожидалось 1 – остановка' % i)
    if '--primenit' not in sys.argv:
        print('ПЛАН: ничего не записано')
        return
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
    os.write(fd, ('fixSB %s' % time.strftime('%H:%M:%S')).encode('utf-8'))
    os.close(fd)
    try:
        papka = os.path.join(KOREN, '_bekap', 'fixSB-' + time.strftime('%Y%m%d-%H%M%S'))
        os.makedirs(papka, exist_ok=True)
        for f in teksty:
            shutil.copy2(os.path.join(T, f), os.path.join(papka, f))
        for f, staroe, novoe in PRAVKI:
            teksty[f] = teksty[f].replace(staroe, novoe, 1)
        for f, t in teksty.items():
            io.open(os.path.join(T, f), 'w', encoding='utf-8', newline='').write(t)
        # синтаксис шаблонов (parse, без фильтров панели вроде fio) – иначе вернуть копии
        p = subprocess.run([VENV, '-c', 'import io,jinja2,os,sys; e=jinja2.Environment(); '
                            '[e.parse(io.open(os.path.join(sys.argv[1], x), encoding="utf-8").read()) for x in sys.argv[2:]]; '
                            'print("OK")', T] + list(teksty),
                           capture_output=True, text=True)
        if 'OK' not in p.stdout:
            for f in teksty:
                shutil.copy2(os.path.join(papka, f), os.path.join(T, f))
            raise SystemExit('шаблон не разбирается – возвращены копии:\n' + p.stderr[-800:])
        print('ЗАПИСАНО; шаблоны разбираются (%s); копия %s' % (p.stdout.strip(), papka))
    finally:
        try:
            os.remove(ZAMOK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
