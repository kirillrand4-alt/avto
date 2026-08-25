import json, os, time
p = r'C:\sender\_tmp\dyra1_pochinka.json'
for _ in range(50):
    if os.path.exists(p):
        break
    time.sleep(10)
print('есть' if os.path.exists(p) else 'нет')
