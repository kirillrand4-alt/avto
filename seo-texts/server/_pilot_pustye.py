# Сколько записей обхода пострадали от сбоя провайдера (сайт открылся, а описания нет / подписанные номера без роли)
import io, json, os
DIR = r'C:\sender\server'
всего = плохих = 0
первый_плохой = None
for n, s in enumerate(io.open(os.path.join(DIR, 'pilot-kontakty.jsonl'), encoding='utf-8', errors='replace')):
    з = json.loads(s)
    всего += 1
    открылся = any(ст == 'ok' for _, ст in з.get('страницы', []))
    if открылся and not з.get('описание'):
        плохих += 1
        if первый_плохой is None:
            первый_плохой = n
print('===ИТОГ==='); print(json.dumps({'записей': всего, 'открылся_без_описания': плохих, 'первая_такая_строка': первый_плохой}))
