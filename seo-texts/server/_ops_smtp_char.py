# -*- coding: utf-8 -*-
"""Что на самом деле отвечает почтовый сервер домена: пять проб подряд.

Две пробы подряд дали РАЗНЫЕ ответы («smtp_reject», потом «catch-all»), а от
этого зависит, можно ли записывать угаданный адрес. Если сервер отвечает
непостоянно (грейлистинг, разные MX), то проверка ничего не доказывает и
записывать нельзя вовсе. Меряем: заведомо несуществующий адрес, заведомо
существующий и пара кандидатов.
"""
import json
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ДОМ = sys.argv[1] if len(sys.argv) > 1 else 'cryogenmash.ru'
ИЗВЕСТНЫЙ = sys.argv[2] if len(sys.argv) > 2 else 'root'


def main():
    out = {'домен': ДОМ, 'выдуманные': [], 'известный': [], 'кандидаты': {}}
    for i in range(4):
        out['выдуманные'].append(EC.smtp_verify(f'zz-net-takogo-{i}9x@{ДОМ}'))
        time.sleep(2.0)
    for i in range(2):
        out['известный'].append(EC.smtp_verify(f'{ИЗВЕСТНЫЙ}@{ДОМ}'))
        time.sleep(2.0)
    for лок in ('shipov', 'mihaylov', 'mikhailov', 'vasileva', 'barabanova'):
        out['кандидаты'][лок] = EC.smtp_verify(f'{лок}@{ДОМ}')
        time.sleep(2.0)
    ответы = set(out['выдуманные'])
    out['вывод'] = ('сервер отвечает НЕПОСТОЯННО — проверка ничего не доказывает'
                    if len(ответы) > 1 else
                    ('домен принимает любой адрес — проверить нельзя'
                     if out['выдуманные'][0] == 'catch-all'
                     else 'ответы устойчивы, проверке можно верить'))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
