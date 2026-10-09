import glob, io, json, os
D = r'C:\sender\server'
print('===ИТОГ===')
for m in ('gpt-6-luna', 'gpt-6-sol'):
    логи = sorted(glob.glob(os.path.join(D, 'pilot_ab_%s_*.log' % m)), key=os.path.getmtime)
    хв = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-400:] if логи else 'нет лога'
    п = os.path.join(D, 'pilot-ab-%s.jsonl' % m)
    зз = [json.loads(s) for s in io.open(п, encoding='utf-8')] if os.path.exists(п) else []
    ок = [з for з in зз if з.get('итог') == 'ok']
    print(m, 'записей', len(зз), 'сбоев', len(зз) - len(ок), 'с номерами', sum(1 for з in ок if з.get('номера')),
          'номеров', sum(len(з.get('номера') or []) for з in ок), 'сек ср', round(sum(з['сек'] for з in зз) / max(1, len(зз))))
    print('  лог:', хв.replace('\n', ' | ')[-300:])
    for з in зз:
        if з.get('итог') != 'ok':
            print('  сбой', з.get('ошибка')); break
