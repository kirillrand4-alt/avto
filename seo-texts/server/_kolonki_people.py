import json, sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
print(json.dumps({'people': [r[1] for r in c.execute('pragma table_info(people)')],
                  'phone_contacts': [r[1] for r in c.execute('pragma table_info(phone_contacts)')]},
                 ensure_ascii=False))
