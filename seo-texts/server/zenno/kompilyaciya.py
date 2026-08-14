# -*- coding: utf-8 -*-
"""Скомпилировать код кубика НАСТОЯЩИМ csc перед отправкой владельцу.

Зачем: ZennoPoster на ошибку компиляции говорит только «произошла ошибка
компиляции проекта» — ни строки, ни причины. 14.08 владелец вставил кубик
дважды и дважды получил красный крест: сперва переменная была объявлена не в
той области, потом имя `prichina` совпало с переменной объемлющей области
(CS0136). Регулярками второе не ловится, компилятором — ловится сразу.

Как: код кубика заворачивается в класс-заглушку, где project/instance/
ZennoPoster/SyncObjects объявлены как dynamic, и компилируется в библиотеку
csc.exe из .NET Framework (он есть на сервере владельца). Все ошибки C# —
области видимости, повторные имена, типы, скобки — всплывают с номерами строк.

Запуск (со стороны песочницы):
    python run_script_on_server.py zenno/kompilyaciya.py 400
— перед этим положить проверяемый файл в C:\\sender\\_tmp\\obhod_stranic.cs.
"""
import glob
import json
import os
import subprocess

ФАЙЛ = os.environ.get('KUBIK', r'C:\sender\_tmp\obhod_stranic.cs')
CSC = r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
ОБЁРТКА = '''using System;
using System.Collections.Generic;
using System.Text;
using System.Linq;
using ZennoLab.CommandCenter;
using ZennoLab.InterfacesLibrary;
public class Kubik {
  static dynamic project = null;
  static dynamic instance = null;
  static dynamic ZennoPoster = null;
  static dynamic SyncObjects = null;
  public static object Main() {
%s
  }
}
'''


def проверить(путь=ФАЙЛ):
    код = open(путь, encoding='utf-8').read()
    обёртка = r'C:\sender\_tmp\kubik_obertka.cs'
    with open(обёртка, 'w', encoding='utf-8') as f:
        f.write(ОБЁРТКА % код)
    ssylki = ['/r:Microsoft.CSharp.dll', '/r:System.Core.dll', '/r:System.Drawing.dll']
    # НАСТОЯЩИЕ сборки ZennoPoster, а не заглушки: без них проверка спотыкалась
    # на явных типах вроде HtmlElement и объявляла живой код битым (14.08).
    # Берём ПОИМЕННО: срез первых попавшихся давал одни ZennoLab.AI.*, и
    # пространство CommandCenter так и не находилось.
    НУЖНЫ = ('ZennoLab.CommandCenter.dll', 'ZennoLab.InterfacesLibrary.dll',
             'ZennoLab.Emulation.dll', 'ZennoLab.Macros.dll')
    # по ОДНОМУ файлу на имя сборки: у ZennoPoster те же dll лежат в нескольких
    # папках установки, и csc падает на «assembly with the same simple name»
    vzyato = set()
    for d in sorted(glob.glob(r'C:\Program Files\ZennoLab\**\ZennoLab.*.dll',
                              recursive=True)):
        imya = os.path.basename(d)
        if imya in НУЖНЫ and imya not in vzyato:
            vzyato.add(imya)
            ssylki.append('/r:' + d)
    r = subprocess.run([CSC, '/nologo', '/t:library', '/out:' + r'C:\sender\_tmp\kubik.dll']
                       + ssylki + [обёртка],
                       capture_output=True, text=True, timeout=300)
    строки = [s for s in (r.stdout + r.stderr).splitlines() if s.strip()]
    ошибки = [s for s in строки if ': error ' in s]
    # номер строки в обёртке сдвинут на шапку класса — вычитаем её
    сдвиг = ОБЁРТКА.split('%s')[0].count('\n')
    красиво = []
    for s in ошибки:
        try:
            н = int(s.split('(', 1)[1].split(',', 1)[0])
            красиво.append('строка %d кубика: %s' % (н - сдвиг, s.split(': ', 1)[1]))
        except Exception:  # noqa: BLE001
            красиво.append(s)
    return {'файл': путь, 'ошибок': len(ошибки), 'ошибки': красиво[:15],
            'вердикт': 'компилируется' if not ошибки else 'НЕ КОМПИЛИРУЕТСЯ'}


if __name__ == '__main__':
    print(json.dumps(проверить(), ensure_ascii=False))
