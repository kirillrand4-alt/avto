# -*- coding: utf-8 -*-
"""Заменить серверный enrich_db.py репозиторной версией — с откатом при беде.

ЗАЧЕМ. На сервере одна копия модуля, 27 385 б, и она отстала от репозитория
(64 110 б). Прямой опрос сервера:

    канон('ГЛАВНЫЙ ЭНЕРГЕТИК')              сервер → гл.инженер   репо → гл.энергетик
    канон('начальник компрессорного цеха')  сервер → общий        репо → нач.цеха
    TECH_ROLES                              сервер → НЕТ          репо → есть

Цена в живых базах: 20 человек записаны не той ролью. «Общий» вместо «нач.цеха»
хуже всего — он уводит начальника компрессорного цеха из технических вообще.

ПОЧЕМУ ЭТО ОСТОРОЖНАЯ ОПЕРАЦИЯ. Модуль общий на три сессии, и мой прошлый деплой
уже затирал чужую правку. Поэтому:
  1) БЭКАП с отметкой времени рядом, в `C:\\sender\\server\\_backup`;
  2) замена;
  3) ПРОБА В ОТДЕЛЬНОМ ПРОЦЕССЕ — модуль уже загружен в текущий, и проверка
     «на себе» показала бы старое поведение;
  4) проба не прошла — ОТКАТ ВЫПОЛНЯЕТСЯ САМ, без моего участия.

Пункт 4 — это правило, купленное дорого: проверка перед необратимым шагом
обязана БЛОКИРОВАТЬ, а не печатать. В прошлый раз мой оп напечатал «порт занят»
и всё равно поставил службу на занятый порт.

ЧЕГО ОП НЕ ДЕЛАЕТ. Не перезаписывает роли в базах. Замена модуля исправляет
БУДУЩИЕ записи; уже записанные 20 человек — отдельный проход, и он должен
показать цитату, а не молча переписать.

Запуск: python vylozhit_enrich_db.py <файл-на-дропе.py> [--apply]
"""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import time

ЦЕЛЬ = r'C:\sender\server\enrich_db.py'
БЭКАПЫ = r'C:\sender\server\_backup'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИМЯ = next((а for а in sys.argv[1:] if а.lower().endswith('.py')), '')

ПРОБА = r'''# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"C:\sender\server")
import enrich_db as E
ok = True
проверки = [("Главный инженер", "гл.инженер"),
            ("ГЛАВНЫЙ ЭНЕРГЕТИК", "гл.энергетик"),
            ("Главный механик", "гл.механик"),
            ("начальник компрессорного цеха", "нач.цеха"),
            ("Технический директор", "техдиректор")]
for что, ждём in проверки:
    было = E.EnrichDB._canon_role(что)
    if было != ждём:
        ok = False
        print("НЕ СХОДИТСЯ:", что, "->", было, "ждали", ждём)
if not hasattr(E.EnrichDB, "TECH_ROLES"):
    ok = False
    print("НЕТ TECH_ROLES")
# модуль обязан ОТКРЫВАТЬ базу, а не только импортироваться
try:
    db = E.EnrichDB()
    n = db.cx.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    print("companies:", n)
except Exception as ex:
    ok = False
    print("БАЗА НЕ ОТКРЫЛАСЬ:", type(ex).__name__, str(ex)[:120])
print("ПРОБА:", "ПРОШЛА" if ok else "ПРОВАЛЕНА")
sys.exit(0 if ok else 1)
'''


def хэш(путь):
    return hashlib.sha1(io.open(путь, 'rb').read()).hexdigest()[:12]


def main():
    if not ИМЯ:
        print('нужно: vylozhit_enrich_db.py <файл.py> [--apply]')
        return
    новый = os.path.join(ОБМЕН, ИМЯ)
    if not os.path.exists(новый):
        print('НЕТ ФАЙЛА НА ДРОПЕ:', новый)
        return
    было_р, было_х = os.path.getsize(ЦЕЛЬ), хэш(ЦЕЛЬ)
    стало_р, стало_х = os.path.getsize(новый), хэш(новый)
    print(f'сейчас на сервере: {было_р} б  sha1 {было_х}')
    print(f'кандидат:          {стало_р} б  sha1 {стало_х}')
    if было_х == стало_х:
        print('ОДИН И ТОТ ЖЕ ФАЙЛ — менять нечего')
        return
    if not ПРИМЕНИТЬ:
        print('СУХОЙ ПРОГОН, замены не было')
        return

    os.makedirs(БЭКАПЫ, exist_ok=True)
    метка = time.strftime('%Y%m%d-%H%M%S')
    бэкап = os.path.join(БЭКАПЫ, f'enrich_db-{метка}.py')
    shutil.copy2(ЦЕЛЬ, бэкап)
    print('бэкап:', бэкап)

    shutil.copy2(новый, ЦЕЛЬ)
    проба_путь = os.path.join(os.environ.get('TEMP', r'C:\Windows\Temp'),
                              f'_proba_edb_{метка}.py')
    with io.open(проба_путь, 'w', encoding='utf-8') as ф:
        ф.write(ПРОБА)
    от = subprocess.run([sys.executable, проба_путь], capture_output=True,
                        text=True, timeout=120)
    print('--- проба в отдельном процессе ---')
    print((от.stdout or '').strip()[-1200:])
    if от.stderr:
        print('stderr:', от.stderr.strip()[-600:])

    if от.returncode != 0:
        shutil.copy2(бэкап, ЦЕЛЬ)
        print('ОТКАТ ВЫПОЛНЕН, на сервере снова', хэш(ЦЕЛЬ))
        print('ЗАМЕНА НЕ СОСТОЯЛАСЬ')
        return

    print(f'ЗАМЕНЕНО: {было_р} → {os.path.getsize(ЦЕЛЬ)} б, sha1 {хэш(ЦЕЛЬ)}')
    print(f'откат одной строкой: copy "{бэкап}" "{ЦЕЛЬ}"')


if __name__ == '__main__':
    main()
