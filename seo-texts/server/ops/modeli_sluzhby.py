# -*- coding: utf-8 -*-
"""Только переменные моделей (имя содержит MODEL/EFFORT/THINKING) в окружении
службы SenderPanel. Остальное окружение НЕ печатается — там пароли и ключи."""
import re
import subprocess
р = subprocess.run(["nssm", "get", "SenderPanel", "AppEnvironmentExtra"], capture_output=True)
т = (р.stdout or b"").decode("utf-16-le", errors="ignore") if b"\x00" in (р.stdout or b"") else (р.stdout or b"").decode("utf-8", "ignore")
for s in т.splitlines():
    к = s.split("=", 1)[0].strip()
    if re.search(r"MODEL|EFFORT|THINKING", к) and not re.search(r"KEY|TOKEN|PASS|SECRET", к):
        print(s.strip()[:120])
print("строк окружения всего:", len(т.splitlines()))
