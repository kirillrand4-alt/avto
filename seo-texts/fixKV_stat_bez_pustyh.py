# -*- coding: utf-8 -*-
r"""fixKV (21.10): в статистике панели КЦ не показывать продавцов без назначенных компаний.

Владелец: «убери юзера 3 из статистики». У user3 после раздела (fixKR) 0 компаний. Правка — одна строка маршрута
статистики в C:\seostat\app\api\routes_centro_sales.py: список продавцов дополнительно фильтруется по наличию
назначений. Вход, аккаунт, данные НЕ трогаются. Замок C:\seostat\_zamok.txt, бэкап файла, перезапуск obzvon.

Откат: файл из C:\seostat\_bekap\fixKV-<время>\ и `nssm restart obzvon`.

    python3 zapusk_na_servere.py fixKV_stat_bez_pustyh.py            # показать, что заменится
    python3 zapusk_na_servere.py fixKV_stat_bez_pustyh.py --primenit # запись и перезапуск
"""
import io
import os
import shutil
import subprocess
import sys
import time

FAYL = r'C:\seostat\app\api\routes_centro_sales.py'
ZAMOK = r'C:\seostat\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')

STAROE = '    prodavcy = sorted(u for u, x in lyudi.items() if x["role"] == "sales" and x["aktiven"])\n'
NOVOE = (
    '    # В статистику попадают только продавцы с назначенными компаниями: у кого очередь опустела (0 назначений),\n'
    '    # в таблице не показываем (владелец 21.10: «убери юзера 3 из статистики»). Вход и аккаунт при этом целы.\n'
    '    _s_naznach = {str(x.get("username") or "") for x in naznach.values()}\n'
    '    prodavcy = sorted(u for u, x in lyudi.items() if x["role"] == "sales" and x["aktiven"] and u in _s_naznach)\n'
)


def main():
    primenit = '--primenit' in sys.argv
    t = io.open(FAYL, encoding='utf-8').read()
    if NOVOE in t:
        print('уже применено: фильтр по назначениям на месте')
        return
    n = t.count(STAROE)
    print('вхождений заменяемой строки: %d' % n)
    if n != 1:
        raise SystemExit('ожидалась ровно одна строка; правка не выполнена')
    if not primenit:
        print('СУХОЙ ПРОГОН: заменю строку\n  %s\nна блок с фильтром `u in _s_naznach`' % STAROE.strip())
        return
    if os.path.exists(ZAMOK):
        raise SystemExit('панель занята (замок %s)' % ZAMOK)
    io.open(ZAMOK, 'w', encoding='utf-8').write('fixKV %s' % VREMYA)
    try:
        papka = os.path.join(r'C:\seostat\_bekap', 'fixKV-' + VREMYA)
        os.makedirs(papka, exist_ok=True)
        shutil.copy2(FAYL, os.path.join(papka, 'routes_centro_sales.py'))
        io.open(FAYL, 'w', encoding='utf-8').write(t.replace(STAROE, NOVOE))
        import py_compile
        py_compile.compile(FAYL, doraise=True)
        r = subprocess.run(['nssm', 'restart', 'obzvon'], capture_output=True, text=True)
        print('nssm restart obzvon: rc=%s %s' % (r.returncode, (r.stdout + r.stderr).strip()[:200]))
        print('ЗАПИСАНО; копия файла %s' % papka)
        print('p25obzvon (8014) подхватит после своего перезапуска')
    finally:
        try:
            os.remove(ZAMOK)
        except OSError:
            pass


if __name__ == '__main__':
    main()
