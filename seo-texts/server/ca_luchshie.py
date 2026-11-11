# -*- coding: utf-8 -*-
r"""Срезы ЦА O2/N2 по полноте (11.11, владелец: «паспорт с продукцией, почта и отдельно лучшие — ЛПР с личной почтой,
продукция у паспорта одновременно заполнены; сколько таких»).

  * «паспорт+почта»: в паспорте (ca-pasport.jsonl) есть продукция и у компании есть хоть одна почта (сайт или чистые ЕИС);
  * «лучшие»: продукция в паспорте + ЛПР («лпр: да», не чужой) с ЛИЧНОЙ почтой — не общий/ролевой ящик (info@, sales@,
    snab@, ogm@ …); отдельно — где личная почта только у закупщика из чистых ЕИС.
Счётчики по категориям; список лучших — ca\ca-luchshie.csv (на сервере и в дропе; ФИО/почты — не в репозиторий).
"""
import collections, csv, io, json, os, re

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
РОЛЕВЫЕ = re.compile(
    r'^(info|office|mail|post|pochta|sales?|sale|zakaz|order|orders|priem|priemnaya|reception|secretar\w*|sekretar\w*|'
    r'snab\w*|zakup\w*|supply|tender\w*|ogm|oge|ogt|energ\w*|mehanik|hr|kadr\w*|buh\w*|account\w*|finance|market\w*|'
    r'reklama|pr|export|import|ved|support|help|admin|director|dir|gendir|ceo|contact\w*|kontakt\w*|feedback|hello|'
    r'service|servis|manager|managers|opt|roznica|retail|shop|store|logist\w*|dostavka|delivery|kanc\w*|general|'
    r'no-?reply|noreply|webmaster|press|smi|job|jobs|rabota|resume|vacancy|personal|otk|lab\w*|quality|kachestvo|'
    r'tech\w*|teh\w*|proizv\w*|production|glavinzh\w*|ogk|ok|yur\w*|legal|ur|security|sb|it|zavod|plant|company|firm\w*)'
    r'\d*$', re.I)


def личная(почта):
    лок = почта.split('@')[0].lower()
    return bool(лок) and not РОЛЕВЫЕ.match(лок) and not re.fullmatch(r'[\d._-]+', лок)


def main():
    сп = json.load(io.open(os.path.join(DIR, 'ca-spisok.json'), encoding='utf-8'))['компании']
    продукция = {}
    for s in io.open(os.path.join(DIR, 'ca-pasport.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        п = з.get('паспорт') or {}
        if isinstance(п, dict) and п.get('продукция'):
            продукция[str(з.get('inn'))] = п['продукция']
    зап = {}
    for s in io.open(os.path.join(DIR, 'ca-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok':
            зап[з['inn']] = з
    еис = collections.defaultdict(list)
    п = os.path.join(ПАПКА, 'ca-zakupki-chistye.jsonl')
    if os.path.exists(п):
        for s in io.open(п, encoding='utf-8'):
            x = json.loads(s)
            еис[x['inn']].append(x)
    сч = collections.Counter()
    по_кат = collections.defaultdict(collections.Counter)
    лучшие = []
    for инн, к in сп.items():
        ном = [x for x in (зап.get(инн) or {}).get('номера') or [] if x.get('чей') != 'другая']
        почты = {x['почта'] for x in ном if x.get('почта')} | {x['почта'] for x in еис.get(инн, []) if x.get('почта')}
        лпр_личн = [x for x in ном if x.get('лпр') == 'да' and x.get('почта') and личная(x['почта'])]
        еис_личн = [x for x in еис.get(инн, []) if x.get('почта') and личная(x['почта'])]
        прод = bool(продукция.get(инн))
        кат = [c for c in (к.get('сегм') or '').split(', ') if c]
        флаги = {'паспорт с продукцией': прод, 'почта': bool(почты), 'паспорт+почта': прод and bool(почты),
                 'ЛПР с личной почтой': bool(лпр_личн), 'ЛУЧШИЕ: продукция + ЛПР с личной почтой': прод and bool(лпр_личн),
                 'продукция + личная почта закупщика ЕИС (без ЛПР с сайта)': прод and not лпр_личн and bool(еис_личн)}
        for ф, v in флаги.items():
            сч[ф] += v
            for c in кат:
                по_кат[c][ф] += v
        сч['всего'] += 1
        for c in кат:
            по_кат[c]['всего'] += 1
        if прод and (лпр_личн or еис_личн):
            for x in (лпр_личн or []):
                лучшие.append({'ИНН': инн, 'Компания': к.get('имя') or '', 'Категории': ', '.join(кат),
                               'Выручка, млн': round((к.get('выручка') or 0) / 1e6), 'Сайт': (зап.get(инн) or {}).get('сайт') or '',
                               'ФИО': x.get('фио') or '', 'Должность': x.get('должность') or '', 'Роль': x.get('роль') or '',
                               'Почта': x['почта'], 'Телефон': x.get('номер') or '', 'Источник': 'сайт',
                               'Продукция': '; '.join(map(str, продукция[инн]))[:300]})
            if not лпр_личн:
                for x in еис_личн:
                    лучшие.append({'ИНН': инн, 'Компания': к.get('имя') or '', 'Категории': ', '.join(кат),
                                   'Выручка, млн': round((к.get('выручка') or 0) / 1e6), 'Сайт': (зап.get(инн) or {}).get('сайт') or '',
                                   'ФИО': x.get('фио') or '', 'Должность': x.get('должность') or 'закупки (ЕИС)',
                                   'Роль': 'Закупки / снабжение', 'Почта': x['почта'], 'Телефон': x.get('телефон') or '',
                                   'Источник': 'ЕИС: ' + x.get('вердикт', ''), 'Продукция': '; '.join(map(str, продукция[инн]))[:300]})
    лучшие.sort(key=lambda r: (r['Источник'] != 'сайт', -r['Выручка, млн']))
    вых = os.path.join(ПАПКА, 'ca-luchshie.csv')
    with io.open(вых, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(лучшие[0].keys()) if лучшие else ['ИНН'], delimiter=';')
        w.writeheader()
        w.writerows(лучшие)
    import shutil
    shutil.copyfile(вых, os.path.join(ДРОП, 'ca-luchshie.csv'))
    print('===ИТОГ===', json.dumps({'итого': dict(сч), 'строк_в_списке_лучших': len(лучшие),
                                     'компаний_в_списке_лучших': len({r['ИНН'] for r in лучшие}),
                                     'по_категориям': {c: dict(v) for c, v in по_кат.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
