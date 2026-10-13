# -*- coding: utf-8 -*-
"""ai_letter: нет просьбы перенаправить — вставляем фразу перед подписью, а не бракуем
(157 писем брака за 13.10). Правка по якорям, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\ai_letter.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "_ПОЛУПРОСЬБА" in т:
    print("=== ПОЛУПРОСЬБА: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [(')\n\n\ndef vstavit_prosbu(body: str) -> str:\n    """Вставить просьбу перенаправить перед «С уважением» (или в конец)."""\n', ')\n\n\n_ПОЛУПРОСЬБА = re.compile(\n    r\'Если[^.!?\\n]{0,120}?(?:друг\\w*\\s+специалист|не\\s+к\\s+вам|не\\s+ваш\\w*\\s+зон|\'\n    r\'коллег|не\\s+по\\s+адресу)[^.!?\\n]*[.!?]\')\n\n\ndef vstavit_prosbu(body: str) -> str:\n    """Вставить просьбу перенаправить перед «С уважением» (или в конец)."""\n'), ("    if _prosba_perenapravit(т):\n        return т\n    фраза = _PROSBA_VARIANTY[sum(map(ord, т[:400])) % len(_PROSBA_VARIANTY)]\n    м = re.search(r'\\n\\s*С\\s+уважением', т)\n    if м:\n", "    if _prosba_perenapravit(т):\n        return т\n    фраза = _PROSBA_VARIANTY[sum(map(ord, т[:400])) % len(_PROSBA_VARIANTY)]\n    # Полупросьба уже есть («Если этим занимается другой специалист, буду\n    # признателен за короткий ответ») — заменяем её, а не пишем вторую рядом.\n    пол = _ПОЛУПРОСЬБА.search(т)\n    if пол:\n        return т[:пол.start()] + фраза + т[пол.end():]\n    м = re.search(r'\\n\\s*С\\s+уважением', т)\n    if м:\n")]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ПОЛУПРОСЬБА: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ПОЛУПРОСЬБА: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ПОЛУПРОСЬБА: ПРИМЕНЕНО ===")
