# -*- coding: utf-8 -*-
r"""Вычистить из общего журнала ca-kontakty.jsonl контакты ЕИС, удалённые по решению владельца (10.11: «сомнительные и
ошибочные давай удалим»; список — ca\ca-zakupki-udaleny.jsonl от ca_zakupki_proverka.py).

Только после конца конвейера набора ca (журнал никто не пишет): проверяет, что замка ca_konveyer.lock нет. Копия —
ca-kontakty.jsonl.bak-<дата>-chistka-eis рядом; запись — во временный файл, потом замена. Убирается человек из
«люди» карточки закупки, если совпали url карточки и (ФИО, телефон, почта). Остальное в строке не меняется.
"""
import io, json, os, re, shutil, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ЖУРНАЛ = os.path.join(DIR, 'ca-kontakty.jsonl')


def ключ(url, фио, тел, почта):
    return (url or '', (фио or '').strip().lower(), re.sub(r'\D', '', тел or '')[-10:], (почта or '').strip().lower())


def main():
    if os.path.exists(os.path.join(ПАПКА, 'ca_konveyer.lock')):
        print('===ИТОГ=== стоп: конвейер набора ca идёт (есть замок) — журнал не трогаю')
        return
    уд = set()
    for s in io.open(os.path.join(ПАПКА, 'ca-zakupki-udaleny.jsonl'), encoding='utf-8'):
        x = json.loads(s)
        уд.add(ключ(x.get('url'), x.get('фио'), x.get('телефон'), x.get('почта')))
    копия = ЖУРНАЛ + '.bak-%s-chistka-eis' % time.strftime('%d%m-%H%M')
    shutil.copyfile(ЖУРНАЛ, копия)
    убрано, строк = 0, 0
    with io.open(ЖУРНАЛ, encoding='utf-8', errors='replace') as f, io.open(ЖУРНАЛ + '.tmp', 'w', encoding='utf-8') as g:
        for s in f:
            строк += 1
            try:
                з = json.loads(s)
            except ValueError:
                g.write(s)
                continue
            тронул = False
            for к in з.get('закупки') or []:
                люди = к.get('люди')
                if not люди:
                    continue
                новые = [ч for ч in люди if not (isinstance(ч, dict) and ключ(к.get('url'), ч.get('person'), ч.get('phone'),
                                                                            ч.get('email')) in уд)]
                if len(новые) != len(люди):
                    убрано += len(люди) - len(новые)
                    к['люди'] = новые
                    тронул = True
            g.write(json.dumps(з, ensure_ascii=False) + '\n' if тронул else s if s.endswith('\n') else s + '\n')
        g.flush()
        os.fsync(g.fileno())
    os.replace(ЖУРНАЛ + '.tmp', ЖУРНАЛ)
    print('===ИТОГ===', json.dumps({'строк': строк, 'к_удалению': len(уд), 'убрано_вхождений': убрано,
                                     'копия': os.path.basename(копия)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
