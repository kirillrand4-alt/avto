import os
п = r'C:\sender\server\ca\ca-meyer-win-loss2-progress.json'
print('===ИТОГ===', open(п, encoding='utf-8').read() if os.path.exists(п) else 'нет')
