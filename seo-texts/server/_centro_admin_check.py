import subprocess, sys
код = r"""
import re, sqlite3, bcrypt
""" + r'''пары = {}
for s in open(r'C:\seostat\.env', encoding='utf-8', errors='replace'):
    if s.startswith('OBZVON_USERS='):
        for x in re.split(r'[,;]', s.split('=', 1)[1].strip()):
            if ':' in x:
                л, п = x.split(':', 1); пары[л.strip()] = п.strip()
c = sqlite3.connect(r'file:C:\seostat\data\centro_sales.db?mode=ro', uri=True)
хэши = {u: h for u, h in c.execute('select username, password_hash from users')}
for центро_логин, h in хэши.items():
    for env_логин, пароль in пары.items():
        ok = bcrypt.checkpw(пароль.encode(), h.encode())
        print('centro %s  <-  пароль обзвона «%s»: %s' % (центро_логин, env_логин, 'СОВПАЛ' if ok else 'нет'))
'''
r = subprocess.run([r'C:\seostat\.venv\Scripts\python.exe', '-c', код], capture_output=True, text=True, timeout=120)
print('===ИТОГ===')
print(r.stdout, r.stderr[-500:])
