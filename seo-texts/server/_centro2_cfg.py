import re
print('===ИТОГ===')
for п in (r'C:\centro2\zapusk.py', r'C:\centro2\app\config.py', r'C:\centro2\app\tools\centro_users.py'):
    т = open(п, encoding='utf-8', errors='replace').read()
    т = re.sub(r'((?:SECRET|PASSWORD|TOKEN|KEY)[A-Z_]*\s*[=:]\s*)["\'][^"\']{6,}["\']', r'\1"<скрыто>"', т)
    print('=====', п); print(т[:3200])
