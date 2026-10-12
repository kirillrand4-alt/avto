# 12.10: наши строки очереди Зенки (защищённые сайты переобхода) — временно в meyer7-zenka-hold.txt, чтобы приёмник
# дочистил gotovo и оркестратор начал разбор; --vernut — обратно в голову очереди
import io, json, os, sys, time
Z = r'C:\seostat\drop\zenno'; D = r'C:\sender\server'
ОЧ = os.path.join(Z, 'ochered.txt'); HOLD = os.path.join(D, 'meyer7-zenka-hold.txt')
наши = {y.split(';')[0] for y in io.open(os.path.join(D, 'meyer7-server-ochered.txt'), encoding='utf-8').read().splitlines() if ';' in y}
print('===ИТОГ===', time.strftime('%H:%M:%S'))
for _ in range(6):
    было = [y for y in io.open(ОЧ, encoding='utf-8', errors='replace').read().splitlines() if y.strip()]
    if '--vernut' in sys.argv:
        держ = [y for y in io.open(HOLD, encoding='utf-8').read().splitlines() if y.strip()] if os.path.exists(HOLD) else []
        ключи = {y.split(';')[0] for y in держ}
        новое = держ + [y for y in было if y.split(';')[0] not in ключи]
    else:
        держ = [y for y in было if y.split(';')[0].strip() in наши]
        with io.open(HOLD, 'a', encoding='utf-8') as f:
            f.write('\n'.join(держ) + ('\n' if держ else ''))
            f.flush(); os.fsync(f.fileno())
        новое = [y for y in было if y.split(';')[0].strip() not in наши]
    with io.open(ОЧ + '.tmp', 'w', encoding='utf-8') as f:
        f.write('\n'.join(новое) + ('\n' if новое else ''))
        f.flush(); os.fsync(f.fileno())
    os.replace(ОЧ + '.tmp', ОЧ)
    time.sleep(3)
    теперь = [y for y in io.open(ОЧ, encoding='utf-8', errors='replace').read().splitlines() if y.strip()]
    if '--vernut' in sys.argv or not any(y.split(';')[0].strip() in наши for y in теперь):
        break
if '--vernut' in sys.argv and os.path.exists(HOLD):
    os.replace(HOLD, HOLD + '.vozvrascheno-' + time.strftime('%H%M'))
print(json.dumps({'режим': 'вернуть' if '--vernut' in sys.argv else 'убрать', 'строк было': len(было), 'строк сейчас': len(теперь),
                  'в hold': len(держ)}, ensure_ascii=False))
