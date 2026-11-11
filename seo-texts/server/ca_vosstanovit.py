# -*- coding: utf-8 -*-
r"""Восстановить лучшие записи обхода набора ca, перезаписанные второй волной (11.11).

Что случилось: вторая волна шла без xmlriver (CA_POISK_SAYTA=0), и в пересобранном списке у компаний, чей сайт в первой
волне нашёлся поиском или агентом, сайта не было. Обход счёл их новыми (сайт '' ≠ прежний домен), прошёл без сайта и
дописал в журнал пустые записи; доразметка и следующие шаги берут ПОСЛЕДНЮЮ запись. Журнал только дописывается — прежние
записи целы.

Что делаем (только при остановленной второй волне — проверяем, что нет kc_kontakty / kc_dorazmetka / pilot_konveyer):
  1. копия ca-kontakty.jsonl (.bak-<дата>-vosstanovlenie);
  2. по каждому ИНН лучшая запись (есть сайт > открытых страниц > контактов); если последняя хуже — лучшую дописываем
     в конец с пометкой «восстановлено» (она становится последней);
  3. в ca-spisok.json у таких компаний возвращаем сайт из лучшей записи (атомарная замена файла).
"""
import io, json, os, shutil, subprocess, time

DIR = r'C:\sender\server'
ЖУРНАЛ = os.path.join(DIR, 'ca-kontakty.jsonl')
СПИСОК = os.path.join(DIR, 'ca-spisok.json')


def балл(з):
    стр = з.get('страницы') or []
    return (1 if з.get('сайт') else 0, sum(1 for _, ст in стр if ст == 'ok'),
            len([x for x in з.get('номера') or [] if x.get('чей') != 'другая']))


def main():
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like "
                        "'*kc_kontakty*' -or $_.CommandLine -like '*kc_dorazmetka*' -or $_.CommandLine -like '*pilot_konveyer*' } "
                        "| ForEach-Object { $_.ProcessId }"], capture_output=True, text=True, timeout=120)
    if r.stdout.split():
        print('===ИТОГ=== стоп: идут писатели журнала', r.stdout.split())
        return
    посл, лучш = {}, {}
    for s in io.open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') != 'ok':
            continue
        i = з['inn']
        посл[i] = з
        if i not in лучш or балл(з) > балл(лучш[i]):
            лучш[i] = з
    вернуть = {i: лучш[i] for i, з in посл.items() if балл(лучш[i]) > балл(з)}
    копия = ЖУРНАЛ + '.bak-%s-vosstanovlenie' % time.strftime('%d%m-%H%M')
    shutil.copyfile(ЖУРНАЛ, копия)
    with io.open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        for i, з in вернуть.items():
            f.write(json.dumps(dict(з, восстановлено=time.strftime('%Y-%m-%d %H:%M')), ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    сп = json.load(io.open(СПИСОК, encoding='utf-8'))
    сайтов = 0
    for i, з in лучш.items():
        к = сп['компании'].get(i)
        if к is not None and not к.get('сайт') and з.get('сайт'):
            к['сайт'], к['сайт_откуда'] = з['сайт'], 'прежний обход (восстановлено 11.11)'
            сайтов += 1
    with io.open(СПИСОК + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(сп, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(СПИСОК + '.tmp', СПИСОК)
    print('===ИТОГ===', json.dumps({'компаний_в_журнале': len(посл), 'восстановлено_записей': len(вернуть),
                                     'сайтов_возвращено_в_список': сайтов, 'копия': os.path.basename(копия)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
