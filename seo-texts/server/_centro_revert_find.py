import sqlite3, glob, os
print('===ИТОГ===')
ЖИВАЯ = r'C:\seostat\data\centro_sales.db'
КОПИЯ = sorted(glob.glob(ЖИВАЯ + '.bak-adminpw-*'))[-1]
старый = sqlite3.connect('file:%s?mode=ro' % КОПИЯ, uri=True).execute("select password_hash, updated_at from users where username='admin'").fetchone()
c = sqlite3.connect(ЖИВАЯ, timeout=60)
c.execute("update users set password_hash=?, updated_at=? where username='admin'", старый)
c.commit()
сейчас = c.execute("select password_hash from users where username='admin'").fetchone()[0]
print('откат admin в C:\\seostat:', 'хэш как до смены' if сейчас == старый[0] else 'НЕ СОВПАЛ', '| копия', КОПИЯ)
c.close()
# centro2: файлы и базы с пользователями
for п in sorted(glob.glob(r'C:\centro2\**\*', recursive=True)):
    if os.path.isdir(п) or '\\_bekap' in п or '.bak' in п: continue
    if п.endswith(('.db', '.sqlite', '.sqlite3')):
        try:
            cc = sqlite3.connect('file:%s?mode=ro' % п, uri=True)
            for т in [r[0] for r in cc.execute("select name from sqlite_master where type='table'")]:
                if 'user' in т.lower():
                    кол = [r[1] for r in cc.execute('pragma table_info(%s)' % т)]
                    строки = cc.execute('select * from %s' % т).fetchall()
                    print(п, т, кол, [(dict(zip(кол, r)).get('username') or dict(zip(кол, r)).get('login'), dict(zip(кол, r)).get('role')) for r in строки])
        except Exception as e:
            print(п, 'ошибка', e)
    elif п.endswith(('.py', '.env', '.json', '.ini', '.toml')) and os.path.getsize(п) < 200000:
        т = open(п, encoding='utf-8', errors='replace').read()
        if any(x in т for x in ('password', 'PASSWORD', 'admin', 'ADMIN', 'SALES_DB', 'SESSION')):
            print('файл', п, os.path.getsize(п))
