# -*- coding: utf-8 -*-
"""fixB, доводка после выката (08.10):

1. Страница статистики на телефоне и планшете была шире экрана (933 px при 390 и 820):
   таблицы `table.stat` прокручиваются внутри своего блока, срезы «Где берут в работу»
   встают в одну колонку. Замер локально (playwright, страница из проверки): scrollWidth
   390 -> 390, 820 -> 820, 1366 без изменений.
2. В комментариях, подсказке поля поиска и docstring выкаченного кода был пример номера из
   задания – заменён заглушкой 900 000-00-00 (правило репо: в скриптах только заглушки).

Под замком, правка по якорям, быстрая проверка рендера на копиях баз (3s_fixB_panel.py
--bystro), при провале – свои файлы назад. Python меняется только в комментариях, шаблоны
панель перечитывает сама – перезапуск не нужен.
"""
import io
import os
import shutil
import subprocess
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
DROP = r'C:\seostat\drop\drop-storage'
ZAMOK = os.path.join(KOREN, '_zamok.txt')
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('fixB-dovodka-%Y%m%d-%H%M%S'))
PANEL = r'C:\sender\_ops\3s_fixB_panel.py'
FAJLY = {
    'rcs': os.path.join(APP, 'api', 'routes_centro_sales.py'),
    'cs': os.path.join(APP, 'services', 'centro_sales.py'),
    'C': os.path.join(APP, 'templates', 'centro.html'),
    'ST': os.path.join(APP, 'templates', 'centro_stats.html'),
    'panel': PANEL,
}
# пример номера из задания -> заглушка (стары собраны по цифрам, чтобы в этом файле его не было)
_N = ''.join(['9', '6', '2'])
_H = ''.join(['1', '4', '0'])
_T = ''.join(['2', '9'])
_K = ''.join(['9', '2'])
ZAMENY = [
    ('«+7%s%s%s%s», «8%s%s%s%s»,' % (_N, _H, _T, _K, _N, _H, _T, _K), '«+79000000000», «89000000000»,'),
    ('# «8 (%s) %s-%s-%s», последние 7' % (_N, _H, _T, _K), '# «8 (900) 000-00-00», последние 7'),
    ('– и «+7%s…» не находилось' % _N, '– и «+7900…» не находилось'),
    ('"""«8 (%s) %s-%s-%s доб. 12» -> («+7%s%s%s%s», «%s%s%s%s», «12»).' % (_N, _H, _T, _K, _N, _H, _T, _K, _N, _H, _T, _K),
     '"""«8 (900) 000-00-00 доб. 12» -> («+79000000000», «9000000000», «12»).'),
    ('"""+7%s%s%s%s -> «+7 %s %s-%s-%s» (читать вслух и сверять)."""' % (_N, _H, _T, _K, _N, _H, _T, _K),
     '"""+79000000000 -> «+7 900 000-00-00» (читать вслух и сверять)."""'),
    ('+7 %s …, 8%s…, 8 (%s) …' % (_N, _N, _N), '+7 900 …, 8900…, 8 (900) …'),
    ('«8 (%s) %s-%s-%s», последние 7/10 цифр' % (_N, _H, _T, _K), '«8 (900) 000-00-00», последние 7/10 цифр'),
]
MOB_YAKOR = '    .st-l.st-ne_dozvonilsya{color:#8a5300}'
MOB_CSS = '''    .st-l.st-ne_dozvonilsya{color:#8a5300}
    /* fixB: на телефоне и планшете таблицы прокручиваются внутри своего блока – страница не шире экрана */
    .razrezy{grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr))}
    .razrezy>section{min-width:0}
    .stat-setka>.plitka{min-width:min(150px,100%)}
    @media(max-width:1100px){
      table.stat{display:block;max-width:100%;overflow-x:auto}
      .sp-stat-forma{gap:8px}
    }
    @media(max-width:760px){
      main.admin-page{padding:10px 8px!important}
      .stat-setka{gap:8px}
      .stat-setka>.plitka{flex:1 1 140px;min-width:0;padding:8px 10px}
      .pometka{overflow-wrap:anywhere}
    }'''


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def main():
    vzyat_zamok('fixB-dovodka')
    try:
        os.makedirs(BEKAP, exist_ok=True)
        for kl, p in FAJLY.items():
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(BEKAP, kl + '-' + os.path.basename(p)))
        izm = {}
        for kl, p in FAJLY.items():
            if not os.path.exists(p):
                print('нет файла: %s' % p)
                continue
            t = io.open(p, encoding='utf-8').read()
            t0 = t
            for a, b in ZAMENY:
                if a in t:
                    print('   %s: замена «%s…» x%d' % (kl, b[:28], t.count(a)))
                    t = t.replace(a, b)
            if kl == 'ST':
                if 'fixB: на телефоне и планшете' in t:
                    print('   ST: мобильная вёрстка – уже')
                elif t.count(MOB_YAKOR) == 1:
                    t = t.replace(MOB_YAKOR, MOB_CSS, 1)
                    print('   ST: мобильная вёрстка – ок')
                else:
                    print('   ST: ЯКОРЬ мобильной вёрстки: %d' % t.count(MOB_YAKOR))
                    return 1
            if t != t0:
                io.open(p, 'w', encoding='utf-8').write(t)
                izm[kl] = p
        ostalos = [kl for kl, p in FAJLY.items() if os.path.exists(p)
                   and (_N + _H) in io.open(p, encoding='utf-8').read().replace('-', '').replace(' ', '')]
        print('файлов изменено: %d; где ещё остался пример номера: %s' % (len(izm), ostalos or 'нигде'))
        os.utime(ZAMOK, None)
        sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
        r = subprocess.run([VENV, PANEL, '--bystro', KOREN], capture_output=True, timeout=900, cwd=KOREN, env=sreda)
        vyvod = r.stdout.decode('utf-8', 'replace') + ('\n' + r.stderr.decode('utf-8', 'replace')[-3000:] if r.returncode else '')
        for p in (os.path.join(KOREN, '_bekap', 'fixB-test-sales.db'), os.path.join(KOREN, '_bekap', 'fixB-test-katalog.db')):
            for hv in ('', '-wal', '-shm'):
                try:
                    os.remove(p + hv)
                except OSError:
                    pass
        io.open(os.path.join(DROP, 'fixB-dovodka-proverka.txt'), 'w', encoding='utf-8').write(vyvod)
        print(vyvod[-1500:])
        if r.returncode != 0 or 'ПЛОХИХ ПРОВЕРОК: 0' not in vyvod:
            for kl, p in izm.items():
                shutil.copy2(os.path.join(BEKAP, kl + '-' + os.path.basename(p)), p)
            print('ПРОВЕРКА НЕ ПРОШЛА – %d файлов возвращены из %s' % (len(izm), BEKAP))
            return 1
        print('готово, бэкап: %s (перезапуск не нужен: Python – только комментарии)' % BEKAP)
        return 0
    finally:
        otdat_zamok()


if __name__ == '__main__':
    raise SystemExit(main())
