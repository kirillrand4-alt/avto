# -*- coding: utf-8 -*-
"""Какие VK-ключи уже есть в окружении панели. Значения НЕ печатаем — только
наличие и длину, чтобы секреты не уехали в лог задания."""
import json
import os
import re

PANEL_ENV = r'C:\sender\panel.env'
ИМЕНА = ('VK_APP_ID', 'VK_APP_SECRET', 'VK_SERVICE_TOKEN', 'VK_TOKEN_USER',
         'VK_TOKEN', 'VK_USE_DOLPHIN', 'VK_DOLPHIN_PROFILE')


def main():
    из_файла = {}
    try:
        with open(PANEL_ENV, encoding='utf-8-sig') as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith('#') and '=' in ln:
                    k, _, v = ln.partition('=')
                    из_файла[k.strip()] = re.sub(r'\s+#.*$', '', v).strip()
    except OSError as ex:
        print(json.dumps({'ошибка': f'нет {PANEL_ENV}: {ex}'}, ensure_ascii=False))
        return
    out = {'файл': PANEL_ENV, 'всего_строк_env': len(из_файла), 'ключи': {}}
    for имя in ИМЕНА:
        v = из_файла.get(имя) or os.environ.get(имя) or ''
        # VK_APP_ID и VK_USE_DOLPHIN не секреты — их показываем целиком
        if имя in ('VK_APP_ID', 'VK_USE_DOLPHIN', 'VK_DOLPHIN_PROFILE'):
            out['ключи'][имя] = v or 'НЕТ'
        else:
            out['ключи'][имя] = (f'есть, {len(v)} символов' if v else 'НЕТ')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
