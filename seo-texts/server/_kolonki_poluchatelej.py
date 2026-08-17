import json, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
print(json.dumps({'recipients': [r[1] for r in c.execute('pragma table_info(recipients)')]},
                 ensure_ascii=False))
