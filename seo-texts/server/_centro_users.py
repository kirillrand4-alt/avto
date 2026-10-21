import sqlite3, glob, os
print('===ИТОГ===')
for п in sorted(set(glob.glob(r'C:\seostat\data*\centro_sales*.db') + glob.glob(r'C:\seostat\**\centro_sales*.db', recursive=True))):
    if '.bak' in п: continue
    c = sqlite3.connect('file:%s?mode=ro' % п, uri=True)
    тт = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    print(п, 'изменён', __import__('time').ctime(os.path.getmtime(п)))
    for т in тт:
        if 'user' in т.lower():
            кол = [r[1] for r in c.execute('pragma table_info(%s)' % т)]
            print('  таблица', т, кол)
            for r in c.execute('select * from %s' % т):
                d = dict(zip(кол, r))
                for k in list(d):
                    if any(x in k.lower() for x in ('hash', 'pass', 'salt')):
                        v = str(d[k] or ''); d[k] = '<%s, %d симв., начало %s…>' % (k, len(v), v[:7])
                print('   ', d)
    c.close()
# где задаются доступы обзвона (Basic) и админы
for env in glob.glob(r'C:\seostat\*.env') + glob.glob(r'C:\seostat\.env*') + glob.glob(r'C:\seostat\app\*.env'):
    for s in open(env, encoding='utf-8', errors='replace'):
        k = s.split('=', 1)[0].strip()
        if any(x in k.upper() for x in ('ADMIN', 'USER', 'AUTH', 'PASS', 'LOGIN')):
            print(env, k, '= <задано>' if '=' in s and s.split('=', 1)[1].strip() else '= <пусто>')
