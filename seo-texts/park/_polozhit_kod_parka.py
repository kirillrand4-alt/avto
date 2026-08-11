# -*- coding: utf-8 -*-
"""Ставит код панели парка и перезапускает ВСЕ службы, которые его держат.

Владелец сказал «фильтр так и не работает», хотя код был положен и проверен. Оказалось:
панель поднята ДВУМЯ службами из одного каталога `C:\\seostat` —

    obzvon     порт 8012   (её я перезапускал)
    p25obzvon  порт 8014   (её смотрит владелец: адрес /p25/centro/park)

Код общий, а в памяти у каждой свой. Перезапуск одной оставлял вторую со старым кодом, и
проверка «снимком страницы» шла по 8012, то есть по починенной. Классическая ловушка: прибор
и глаз смотрели в разные места.

Теперь перезапускаются обе, и печатается статус каждой.
"""
import ast, os, shutil, subprocess, time

PARY = [(r"C:\sender\_novyy_routes_park.py", r"C:\seostat\app\api\routes_park.py"),
        (r"C:\sender\_novyy_park.html", r"C:\seostat\app\templates\park.html")]
SLUZHBY = ["obzvon", "p25obzvon"]
metka = time.strftime("%Y%m%d-%H%M%S")
for src, dst in PARY:
    if src.endswith(".py"):
        try:
            ast.parse(open(src, encoding="utf-8").read())
        except SyntaxError as e:
            raise SystemExit("НЕ КЛАДУ: синтаксис %s: %s" % (os.path.basename(src), e))
    if os.path.exists(dst):
        shutil.copyfile(dst, dst + ".bak-" + metka)
    shutil.copyfile(src, dst)
    print("polozhen", os.path.basename(dst), os.path.getsize(dst))
for imya in SLUZHBY:
    r = subprocess.run(["powershell", "-Command",
                        "Restart-Service %s -Force; Start-Sleep -Seconds 3;"
                        " (Get-Service %s).Status" % (imya, imya)],
                       capture_output=True, text=True, timeout=180)
    print("sluzhba %-10s %s" % (imya, (r.stdout or r.stderr).strip().splitlines()[-1][:40]))
