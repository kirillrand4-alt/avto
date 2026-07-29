# -*- coding: utf-8 -*-
"""Проверка гипотезы об адресе конкретных людей SMTP-пробой RCPT TO.

У АО «Криогенмаш» в исходной базе продажников видно полтора десятка адресов
вида ФАМИЛИЯ@cryogenmash.ru (barabanova, chekunova, demina, fadeeva, havroshin,
melchenko, mohova, rtischev). Домен на выдуманный адрес отвечает отказом, а не
принимает всё подряд, — значит проверка что-то доказывает, и найденные фамилии
технарей можно превратить в адреса.

Письма НЕ отправляются: диалог обрывается на RCPT TO командой QUIT. Пишем в
базу только те адреса, которые сервер подтвердил.

Запуск: python _ops_smtp_guess.py ИНН домен "Фамилия Имя|должность" ... [--apply]
"""
import json
import sys
import time

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402
import email_schema as ES        # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
арг = [a for a in sys.argv[1:] if not a.startswith('--')]
ИНН, ДОМ = (арг + ['', ''])[0], (арг + ['', ''])[1]
ЛЮДИ = арг[2:]

db = EDB.EnrichDB()
e = db.cx


def main():
    out = {'инн': ИНН, 'домен': ДОМ, 'проверки': [], 'подтверждено': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)'}
    # контроль: домен обязан ОТКАЗЫВАТЬ выдуманному адресу, иначе проверка
    # ничего не значит и весь прогон бессмыслен
    out['контроль_выдуманный_адрес'] = EC.smtp_verify(f'zz-nikogo-net-77@{ДОМ}')
    if out['контроль_выдуманный_адрес'] in ('catch-all', 'no_mx', 'port25_blocked'):
        out['вывод'] = 'проверять нечем — домен не даёт различимого ответа'
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    for зап in ЛЮДИ:
        фио, _, пост = зап.partition('|')
        части = ES.части(фио)
        if not части:
            continue
        варианты = sorted(ES.варианты(части['ф']))
        и1 = (sorted(ES.варианты(части['и']))[0][:1] if части['и'] else '')
        кандидаты = []
        for ф in варианты:
            for лок in (ф, f'{и1}.{ф}' if и1 else '', f'{ф}.{и1}' if и1 else '',
                        f'{ф}{и1}' if и1 else ''):
                if лок and лок not in кандидаты:
                    кандидаты.append(лок)
        для_фио = []
        for лок in кандидаты[:10]:
            адрес = f'{лок}@{ДОМ}'
            итог = EC.smtp_verify(адрес)
            для_фио.append({'адрес': адрес, 'ответ': итог})
            if итог == 'smtp_ok':
                out['подтверждено'] += 1
                if ПРИМЕНИТЬ:
                    db.add_email(ИНН, адрес,
                                 role=EDB.EnrichDB._canon_role(пост),
                                 person=фио, mx_ok=1, source='схема+smtp',
                                 source_url='схема фамилия@ + проба RCPT TO')
                break      # нашли — дальше по этому человеку не долбим сервер
            time.sleep(1.4)
        out['проверки'].append({'фио': фио, 'должность': пост,
                                'пробы': для_фио})
    if ПРИМЕНИТЬ:
        e.commit()
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])


if __name__ == '__main__':
    main()
