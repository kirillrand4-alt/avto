import os
П = r'C:\sender\server\ca'
print('===ИТОГ===', open(os.path.join(П, 'ca-agenty-dosyl.json'), encoding='utf-8').read() if os.path.exists(os.path.join(П, 'ca-agenty-dosyl.json')) else 'нет статуса', 'замок', os.path.exists(os.path.join(П, 'ca_agenty_dosyl.lock')))
л = os.path.join(П, 'ca_agenty_dosyl_sol.log')
if os.path.exists(л):
    print(open(л, encoding='utf-8', errors='replace').read()[-500:].replace('\n', ' | '))
