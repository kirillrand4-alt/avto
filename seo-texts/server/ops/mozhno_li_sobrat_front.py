# -*- coding: utf-8 -*-
"""Можно ли собрать фронт на сервере и совпадают ли якоря правки.

Каталог панели делят сессии, и web/src на сервере разошёлся с песочницей
(styles.css 40575 против 48856). Значит катить свой dist нельзя — он
перезапишет чужую вёрстку. Путь один: править серверные исходники по
якорям и собирать там же. Проверяем, чем собирать и куда править.
"""
import io
import os
import shutil
import subprocess

КОРЕНЬ = r"C:\sender\sender\web"
print("=== ЧЕМ СОБИРАТЬ ===")
for имя in ("npm", "npm.cmd", "node", "node.exe"):
    п = shutil.which(имя)
    print("   %-10s %s" % (имя, п or "нет в PATH"))
try:
    в = subprocess.run(["node", "-v"], capture_output=True, text=True, timeout=20)
    print("   node -v: %s" % (в.stdout or в.stderr).strip())
except Exception as e:  # noqa: BLE001
    print("   node не запустился: %s" % str(e)[:60])
print("   node_modules: %s" % ("есть" if os.path.isdir(
    os.path.join(КОРЕНЬ, "node_modules")) else "нет"))

ЯКОРЯ = {
    "src/components/ui.tsx": [
        'export function StatusBadge({ status, kind = "lead" }',
        'const label = kind === "lead" ? (LEAD_STATUS[status] || status) : status;',
    ],
    "src/screens/views.tsx": [
        "<thead><tr><th>#</th><th>Тип</th><th>Кампания</th>",
        '{["", "sent", "delivered", "bounce", "complaint", "reply", "unsubscribe", "suppress"].map((t) =>',
    ],
    "src/api/types.ts": ["export interface EventRow {"],
}
print("\n=== ЯКОРЯ В СЕРВЕРНЫХ ИСХОДНИКАХ ===")
for файл, якоря in ЯКОРЯ.items():
    п = os.path.join(КОРЕНЬ, файл.replace("/", os.sep))
    if not os.path.exists(п):
        print("   %-28s ФАЙЛА НЕТ" % файл)
        continue
    т = io.open(п, encoding="utf-8").read()
    print("   %-28s %6d б" % (файл, len(т)))
    for я in якоря:
        print("      %-64s %d" % (я[:64], т.count(я)))
