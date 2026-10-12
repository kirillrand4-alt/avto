# -*- coding: utf-8 -*-
"""Вывести «письмо писал: <модель>» в карточку «Кому пишем» экрана
подтверждения и пересобрать фронт.

Владелец 12.10: «сделай подпись кто писал письмо». Генератор уже кладёт
модель в panel_json (ключ model_pisma); здесь — строка на экране.

Собираем `npx vite build` (без tsc): дерево исходников и без нашей
правки не проходит tsc из-за старых ошибок в views.tsx.

Безопасность пересборки: исходников новее прошлой сборки (25.08) нет,
значит сборка не притащит чужих незаконченных правок. Перед правкой —
копия Confirm.tsx и всего dist; сборка упала — откатываем оба.
"""
import io
import os
import shutil
import subprocess
import sys
import time

WEB = r"C:\sender\sender\web"
TSX = os.path.join(WEB, "src", "screens", "Confirm.tsx")
DIST = os.path.join(WEB, "dist")
метка = int(time.time())

т = io.open(TSX, encoding="utf-8").read()
if "model_pisma" in т:
    print("строка уже на экране — пересобирать нечего")
    print("=== ПОДПИСЬ НА ЭКРАНЕ: УЖЕ БЫЛА ===")
    sys.exit(0)

ЯКОРЬ = """          {c.provenance_conflict && (
            <div className="soft-bad">
              источник контакта не подтверждён — проверьте вручную
            </div>
          )}
        </Row>
"""
ВСТАВКА = ЯКОРЬ + """        {/* Подпись «кто писал письмо» (владелец 12.10): генератор кладёт в
            панель модель, ответившую на вызовы-черновики. Две модели через
            «+» значат, что opus отказал и часть дописала запасная. */}
        {(p as unknown as { model_pisma?: string }).model_pisma && (
          <Row label="письмо писал">
            {(p as unknown as { model_pisma?: string }).model_pisma}
          </Row>
        )}
"""
if т.count(ЯКОРЬ) != 1:
    print("якорь в Confirm.tsx не найден (%d) — ничего не трогаю" % т.count(ЯКОРЬ))
    print("=== ПОДПИСЬ НА ЭКРАНЕ: НЕ ПРИМЕНЕНА ===")
    sys.exit(0)

бэкап_tsx = TSX + ".bak-%d" % метка
бэкап_dist = DIST + ".bak-%d" % метка
shutil.copy2(TSX, бэкап_tsx)
shutil.copytree(DIST, бэкап_dist)
io.open(TSX, "w", encoding="utf-8").write(т.replace(ЯКОРЬ, ВСТАВКА))
print("Confirm.tsx поправлен, копии: %s, %s"
      % (os.path.basename(бэкап_tsx), os.path.basename(бэкап_dist)))

начало = time.time()
# `npm run build` гоняет сначала tsc, а дерево исходников не проходит его
# и без нашей правки: views.tsx ссылается на типы QuotaDay и SentMessage,
# которых нет в api/types (замер 12.10, ошибки до нашей строки). Сборка
# 25.08 сделана тем же vite без tsc — им и собираем, правка типобезопасна.
р = subprocess.run("npx vite build", cwd=WEB, shell=True,
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=600)
print("сборка: код %s, %.0f сек" % (р.returncode, time.time() - начало))
хвост = (р.stdout or "")[-900:] + (р.stderr or "")[-600:]
if р.returncode != 0:
    print(хвост)
    shutil.copy2(бэкап_tsx, TSX)
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.copytree(бэкап_dist, DIST)
    print("ОТКАТ: исходник и dist возвращены")
    print("=== ПОДПИСЬ НА ЭКРАНЕ: ОТКАТ ===")
    sys.exit(0)

собрано = []
for ф in os.listdir(os.path.join(DIST, "assets")):
    if ф.endswith(".js"):
        п = os.path.join(DIST, "assets", ф)
        if "письмо писал" in io.open(п, encoding="utf-8", errors="replace").read():
            собрано.append(ф)
print("строка «письмо писал» в собранном бандле: %s" % (собрано or "НЕТ"))
print(хвост[-400:])
print("=== ПОДПИСЬ НА ЭКРАНЕ: %s ===" % ("СОБРАНО" if собрано else "СБОРКА БЕЗ СТРОКИ"))
