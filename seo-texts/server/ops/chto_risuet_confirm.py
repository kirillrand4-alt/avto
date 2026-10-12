# -*- coding: utf-8 -*-
"""Какие поля панели рисует экран подтверждения + можно ли собрать фронт."""
import io
import os
import re
import shutil

П = r"C:\sender\sender\web\src\screens\Confirm.tsx"
т = io.open(П, encoding="utf-8").read()
ключи = sorted(set(re.findall(r"panel\??\.([a-zA-Z_]+)", т)))
print("panel.* в Confirm.tsx: %s" % ", ".join(ключи))
for м in re.finditer(r".{0,60}(warnings|flags|notes|badges)\b.{0,80}", т):
    print("   …%s…" % м.group(0).replace("\n", " ")[:150])
    break
print("")
print("--- сборка фронта ---")
for к in ("node", "npm", "npx"):
    print("   %-5s %s" % (к, shutil.which(к)))
dist = r"C:\sender\sender\web\dist"
if os.path.isdir(dist):
    for ф in os.listdir(os.path.join(dist, "assets"))[:6] if os.path.isdir(
            os.path.join(dist, "assets")) else []:
        п = os.path.join(dist, "assets", ф)
        print("   dist/assets/%-34s %8d  %s" % (ф, os.path.getsize(п),
              __import__("time").strftime("%Y-%m-%d %H:%M",
              __import__("time").localtime(os.path.getmtime(п)))))
print("   package.json: %s" % os.path.exists(r"C:\sender\sender\web\package.json"))
print("   node_modules: %s" % os.path.isdir(r"C:\sender\sender\web\node_modules"))
print("")
print("=== ЧТО РИСУЕТ CONFIRM ===")
