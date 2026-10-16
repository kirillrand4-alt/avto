# Только параметры запуска службы (без окружения: там секреты).
import subprocess
print(subprocess.run(["nssm", "get", "SenderPanel", "AppParameters"], capture_output=True, text=True, errors="replace").stdout.replace("\x00", "").strip())
