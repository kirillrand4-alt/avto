# -*- coding: utf-8 -*-
"""Удаление с дропа (владелец 07.10 «да»): 13 частей kc-proekty-0610-1436.tar + его .ready.txt
и файлы kp0001_… первой (остановленной) заливки. Только после проверки распаковки."""
import io, json, os, re
ДРОП = r'C:\seostat\drop\drop-storage'
итог = json.load(io.open(r'C:\sender\server\kc-raspakovka.json', encoding='utf-8'))
o = {'sha_совпал': итог.get('sha256_совпал'), 'распаковано': итог.get('распаковано_файлов')}
папка = r'C:\seostat\kc-proekty\01. НАШИ ПРОЕКТЫ - КЦ'
o['папка_на_месте'] = os.path.isdir(папка)
if not (o['sha_совпал'] and o['папка_на_месте']):
    o['итог'] = 'СТОП: распакованная копия не подтверждена, ничего не удалял'
    print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False)); raise SystemExit
части = [f for f in os.listdir(ДРОП) if re.fullmatch(r'kc-proekty-0610-1436\.tar\.(part\d{3}|ready\.txt)', f)]
kp = [f for f in os.listdir(ДРОП) if re.match(r'kp\d{4}_', f)]
o['найдено_частей'] = len(части); o['найдено_kp'] = len(kp)
освобождено = 0; удалено = 0; ошибки = []
for f in части + kp:
    п = os.path.join(ДРОП, f)
    try:
        размер = os.path.getsize(п)
        os.remove(п)
        освобождено += размер; удалено += 1
    except OSError as e:
        ошибки.append('%s: %s' % (f[:60], str(e)[:60]))
o.update({'удалено': удалено, 'освобождено_ГБ': round(освобождено / 1e9, 2), 'ошибки': ошибки[:10],
          'осталось_частей': len([f for f in os.listdir(ДРОП) if f.startswith('kc-proekty-0610-1436.tar.')]),
          'осталось_kp': len([f for f in os.listdir(ДРОП) if re.match(r'kp\d{4}_', f)])})
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
