# -*- coding: utf-8 -*-
"""fixD: повторная проверка после записи (venv + TestClient) – вызывает 3s_fixD_zapis.py --proverka."""
import os
import subprocess
import sys
r = subprocess.run([r'C:\seostat\.venv\Scripts\python.exe', r'C:\sender\_ops\3s_fixD_zapis.py', '--proverka'],
                   capture_output=True, timeout=1200, cwd=r'C:\centro2', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
out = r.stdout.decode('utf-8', 'replace')
open(r'C:\seostat\drop\drop-storage\fixD-proverka.txt', 'w', encoding='utf-8').write(out + '\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
print(out[:5800])
sys.exit(r.returncode)
