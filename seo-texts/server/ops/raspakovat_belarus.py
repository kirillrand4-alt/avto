# -*- coding: utf-8 -*-
"""Забрать архив с дропом и распаковать на сервере. Показать, что внутри.

Дроп живёт на этой же машине, поэтому качаем по локальному адресу — внешний
GET у сервера рвётся на 384 КБ через hairpin-NAT, а тут 24 МБ.
"""
import glob
import os
import subprocess
import sys

ИМЯ = "belarus-meyer.rar"
КУДА = r"C:\sender\_ops\belarus"
АРХИВ = os.path.join(КУДА, ИМЯ)
UNRAR = r"C:\Program Files\WinRAR\UnRAR.exe"
os.makedirs(КУДА, exist_ok=True)

# 1. Ищем файл там, где дроп его хранит.
кандидаты = []
for корень in (r"C:\drop", r"C:\sender\drop", r"C:\inetpub\drop",
               r"C:\sender\_drop", r"C:\Users"):
    if os.path.isdir(корень):
        кандидаты += glob.glob(os.path.join(корень, "**", ИМЯ), recursive=True)
print("найдено копий в хранилище дропа: %s" % (кандидаты or "нет"))

if кандидаты:
    import shutil
    shutil.copy2(кандидаты[0], АРХИВ)
    print("скопирован: %s -> %s" % (кандидаты[0], АРХИВ))
else:
    # 2. Иначе тянем по HTTP с локального адреса дропа.
    токен = ""
    for п in (r"C:\sender\server\runner-secrets.env", r"C:\sender\runner-secrets.env"):
        if os.path.exists(п):
            for с in open(п, encoding="utf-8", errors="replace"):
                if с.startswith("DROP_TOKEN="):
                    токен = с.split("=", 1)[1].strip()
    if not токен:
        print("токен дропа не найден — скачать не смогу")
        sys.exit(1)
    к = ("$ProgressPreference='SilentlyContinue'; "
         "Invoke-WebRequest -Uri 'https://parsercompressor.online/drop/%s' "
         "-Headers @{'X-Drop-Token'='%s'} -OutFile '%s'" % (ИМЯ, токен, АРХИВ))
    в = subprocess.run(["powershell", "-NoProfile", "-Command", к],
                       capture_output=True, timeout=600)
    print("скачивание: rc=%s %s"
          % (в.returncode, (в.stderr or b"").decode("cp866", "replace")[:200]))

if not os.path.exists(АРХИВ):
    print("архива нет — дальше некуда")
    sys.exit(1)
print("архив: %d байт" % os.path.getsize(АРХИВ))

в = subprocess.run([UNRAR, "x", "-o+", "-y", АРХИВ, КУДА + os.sep],
                   capture_output=True, timeout=900)
хвост = (в.stdout or b"").decode("cp866", "replace").splitlines()
print("распаковка: rc=%s" % в.returncode)
for с in хвост[-6:]:
    print("   %s" % с.strip()[:120])

print("\n=== ЧТО ВНУТРИ ===")
всего = 0
for корень, _д, файлы in os.walk(КУДА):
    for ф in sorted(файлы):
        if ф == ИМЯ:
            continue
        п = os.path.join(корень, ф)
        всего += 1
        if всего <= 25:
            print("   %-58s %9d б" % (os.path.relpath(п, КУДА), os.path.getsize(п)))
print("   файлов всего: %d" % всего)
