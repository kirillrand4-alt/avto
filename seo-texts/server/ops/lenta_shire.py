# -*- coding: utf-8 -*-
"""Панель шире (владелец 16.10: «сделай пошире окно» — колонка «Взять/перевести»
обрезалась) и подписи статусов лида в значке (perepiska/v_otpuske/avtootvet
светились латиницей). Правка по якорям, сборка vite, выкладка в C:\\sender\\web\\dist
(откуда отдаёт служба). Откат: lenta_shire.py --otkat"""
import glob, io, os, shutil, subprocess, sys, time
WEB = r"C:\sender\sender\web"
CSS, UI = os.path.join(WEB, "src", "styles.css"), os.path.join(WEB, "src", "components", "ui.tsx")
SRV = r"C:\sender\web\dist"
if "--otkat" in sys.argv:
    for п in (CSS, UI):
        б = sorted(glob.glob(п + ".bak-shire-*"))
        if б: shutil.copy2(б[-1], п)
    б = sorted(glob.glob(SRV + ".bak-shire-*"))
    if б: shutil.rmtree(SRV); shutil.copytree(б[-1], SRV)
    print("=== ШИРЕ: ОТКАЧЕНО ==="); sys.exit()
ПРАВКИ = {CSS: [("--content-max: 1280px", "--content-max: 1920px")],
          UI: [('not_qualified: "не квал", in_bitrix: "в Bitrix",',
                'not_qualified: "не квал", in_bitrix: "в Bitrix",\n'
                '  perepiska: "переписка", v_otpuske: "в отпуске", avtootvet: "автоответ",')]}
т = {п: io.open(п, encoding="utf-8").read() for п in ПРАВКИ}
if 'perepiska: "переписка"' in т[UI]:
    print("=== ШИРЕ: УЖЕ БЫЛО ==="); sys.exit()
for п, пп in ПРАВКИ.items():
    for с, _ in пп:
        if т[п].count(с) != 1: print("якорь", п, т[п].count(с)); print("=== ШИРЕ: НЕ ПРИМЕНЕНО ==="); sys.exit()
м = int(time.time())
for п in ПРАВКИ: shutil.copy2(п, п + ".bak-shire-%d" % м)
for п, пп in ПРАВКИ.items():
    x = т[п]
    for с, н in пп: x = x.replace(с, н)
    io.open(п, "w", encoding="utf-8").write(x)
р = subprocess.run("npx vite build", cwd=WEB, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
print("сборка:", р.returncode)
if р.returncode != 0:
    for п in ПРАВКИ: shutil.copy2(п + ".bak-shire-%d" % м, п)
    print((р.stderr or "")[-600:]); print("=== ШИРЕ: ОТКАТ ==="); sys.exit()
shutil.copytree(SRV, SRV + ".bak-shire-%d" % м)
shutil.rmtree(SRV); shutil.copytree(os.path.join(WEB, "dist"), SRV)
print("отдаётся:", os.listdir(os.path.join(SRV, "assets"))); print("=== ШИРЕ: ПРИМЕНЕНО ===")
