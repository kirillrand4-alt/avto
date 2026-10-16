# -*- coding: utf-8 -*-
"""Лента лидов (владелец 16.10): очередь «ведётся переписка» (perepiska) и
перевод из любой очереди в любую, кроме «отдали в Bitrix» (оттуда только
«закрыт», как было). Правит leaddesk.py, store.py, web/src/screens/Leads.tsx
по якорям, собирает фронт `npx vite build`. Сбой — откат всех трёх и dist.
Откат вручную: lidy_perepiska.py --otkat. После — Restart-Service SenderPanel."""
import glob, io, os, py_compile, shutil, subprocess, sys, time
S = r"C:\sender\sender"
WEB = os.path.join(S, "web")
DIST = os.path.join(WEB, "dist")
LD, ST, TSX = os.path.join(S, "leaddesk.py"), os.path.join(S, "store.py"), os.path.join(WEB, "src", "screens", "Leads.tsx")
if "--otkat" in sys.argv:
    for п in (LD, ST, TSX):
        б = sorted(glob.glob(п + ".bak-perepiska-*"))
        if б: shutil.copy2(б[-1], п); print("откат", б[-1])
    б = sorted(glob.glob(DIST + ".bak-perepiska-*"))
    if б: shutil.rmtree(DIST, ignore_errors=True); shutil.copytree(б[-1], DIST); print("откат", б[-1])
    print("=== ПЕРЕПИСКА: ОТКАЧЕНО ==="); sys.exit(0)
ПРАВКИ = {
 LD: [('_СИНОНИМЫ = {"not_qualified": "unqualified"}',
       '# «ВЕДЁТСЯ ПЕРЕПИСКА» И ПЕРЕВОД ИЗ ЛЮБОЙ ОЧЕРЕДИ В ЛЮБУЮ (владелец 16.10):\n'
       '# «сделай очередь ведётся переписка… и из всех очередей чтобы можно было в\n'
       '# любую другую перекинуть… тех кого отдали в битрикс не трогай». Поэтому\n'
       '# in_bitrix сохраняет свой узкий выход, остальные ходят куда угодно.\n'
       '_TRANSITIONS["perepiska"] = set()\n'
       'for _с in list(_TRANSITIONS):\n'
       '    if _с != "in_bitrix":\n'
       '        _TRANSITIONS[_с] = set(_TRANSITIONS) - {_с}\n'
       '_СИНОНИМЫ = {"not_qualified": "unqualified"}')],
 ST: [("                    'v_otpuske', 'avtootvet', 'closed')",
       "                    'v_otpuske', 'avtootvet', 'closed', 'perepiska')")],
 TSX: [('  { key: "avtootvet", label: "автоответ" },\n  { key: "not_interested", label: "не интересно" },',
        '  { key: "avtootvet", label: "автоответ" },\n  { key: "perepiska", label: "ведётся переписка" },\n  { key: "not_interested", label: "не интересно" },'),
       ('  closed: [],\n};',
        '  closed: [],\n};\n'
        '// Из любой очереди в любую (владелец 16.10), кроме «отдали в Bitrix» —\n'
        '// повторяет leaddesk._TRANSITIONS.\n'
        'const ВСЕ_СТАТУСЫ = ["new", "taken", "called", "qualified", "unqualified",\n'
        '  "in_bitrix", "perepiska", "v_otpuske", "avtootvet", "not_interested", "closed"];\n'
        'for (const с of [...Object.keys(ПЕРЕХОДЫ), "perepiska"]) {\n'
        '  if (с !== "in_bitrix") ПЕРЕХОДЫ[с] = ВСЕ_СТАТУСЫ.filter((x) => x !== с);\n'
        '}'),
       ('  avtootvet: "автоответ",\n  not_interested: "не интересно",',
        '  avtootvet: "автоответ",\n  perepiska: "ведётся переписка",\n  not_interested: "не интересно",'),
       ('const СВОИ_ОЧЕРЕДИ = ["in_bitrix", "unqualified", "v_otpuske", "avtootvet",',
        'const СВОИ_ОЧЕРЕДИ = ["in_bitrix", "perepiska", "unqualified", "v_otpuske", "avtootvet",')],
}
тексты = {п: io.open(п, encoding="utf-8").read() for п in ПРАВКИ}
if "perepiska" in тексты[LD]:
    print("=== ПЕРЕПИСКА: УЖЕ БЫЛО ==="); sys.exit(0)
for п, пары in ПРАВКИ.items():
    for с, _ in пары:
        if тексты[п].count(с) != 1:
            print("якорь %s (%d): %r" % (os.path.basename(п), тексты[п].count(с), с[:80]))
            print("=== ПЕРЕПИСКА: НЕ ПРИМЕНЕНО ==="); sys.exit(0)
м = int(time.time())
for п in ПРАВКИ: shutil.copy2(п, п + ".bak-perepiska-%d" % м)
shutil.copytree(DIST, DIST + ".bak-perepiska-%d" % м)
def откат(why):
    for п in ПРАВКИ: shutil.copy2(п + ".bak-perepiska-%d" % м, п)
    shutil.rmtree(DIST, ignore_errors=True); shutil.copytree(DIST + ".bak-perepiska-%d" % м, DIST)
    print("ОТКАТ:", why); print("=== ПЕРЕПИСКА: ОТКАТ ==="); sys.exit(0)
for п, пары in ПРАВКИ.items():
    т = тексты[п]
    for с, н in пары: т = т.replace(с, н)
    io.open(п, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(LD, doraise=True); py_compile.compile(ST, doraise=True)
except Exception as е:
    откат(е)
р = subprocess.run("npx vite build", cwd=WEB, shell=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=600)
print("сборка: код", р.returncode)
if р.returncode != 0:
    print((р.stdout or "")[-800:] + (р.stderr or "")[-600:]); откат("сборка")
print("бэкапы: *.bak-perepiska-%d" % м)
print("=== ПЕРЕПИСКА: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
