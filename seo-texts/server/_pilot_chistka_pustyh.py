# Удалить из pilot-kontakty.jsonl записи, испорченные сбоем провайдера (сайт открылся, описания нет) — шаг их переделает.
# Бэкап рядом: pilot-kontakty.jsonl.bak-<время>
import io, json, os, shutil, time
DIR = r'C:\sender\server'
п = os.path.join(DIR, 'pilot-kontakty.jsonl')
shutil.copyfile(п, п + '.bak-' + time.strftime('%d%m-%H%M'))
оставить, убрано = [], 0
for s in io.open(п, encoding='utf-8', errors='replace'):
    з = json.loads(s)
    if any(ст == 'ok' for _, ст in з.get('страницы', [])) and not з.get('описание'):
        убрано += 1
        continue
    оставить.append(s if s.endswith('\n') else s + '\n')
with io.open(п, 'w', encoding='utf-8') as f:
    f.writelines(оставить)
    f.flush()
    os.fsync(f.fileno())
print('===ИТОГ==='); print(json.dumps({'осталось': len(оставить), 'убрано': убрано}))
