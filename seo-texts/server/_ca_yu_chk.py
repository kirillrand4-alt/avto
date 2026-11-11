import os
П = r'C:\sender\server\ca'
п = os.path.join(П, 'ca-yadro-uzkoe-progress.json')
print('===ИТОГ===', open(п, encoding='utf-8').read() if os.path.exists(п) else 'нет', 'замок', os.path.exists(os.path.join(П, 'ca_yadro_uzkoe.lock')))
