import os
п = r'C:\sender\server\ca\ca-meyer-nepisali-progress.json'
print('===ИТОГ===', open(п, encoding='utf-8').read() if os.path.exists(п) else 'нет')
