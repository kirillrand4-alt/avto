# -*- coding: utf-8 -*-
r"""Файл 5 (парк): чей номер на сайте компании, если в парке у номера не было ни ФИО, ни должности.
Тот же шаг, что в park5.py: живая страница, окна вокруг номеров, модель по подписи рядом
с номером (ПРОМПТ из park5). Только своих сайтов (checko выкинуты владельцем 07.10).
Выход (fsync): C:\sender\server\park5-roli.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
import park5 as P5  # noqa: E402
import meyer_proverka as MP  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import verify_company as VC  # noqa: E402

ВЫХОД = os.path.join(DIR, 'park5-roli.jsonl')
# свои сайты, прошедшие проверку «чья» (park5_chya.py + ручной разбор 07.10: mukomol.com — ВКХП
# «Мукомол» из Владимира, а ИНН из Рязанской обл.; созвездие, заман, сандугач — чужие организации)
ХОСТЫ = ['mtscentrrb.ru', 'mlkgroup.ru', 'kazanmez.ru', 'candy-factory.ru', 'biorosva.ru', 'kstovo-hleb.com']


def main():
    стр = [json.loads(s) for s in io.open(os.path.join(DIR, 'park5.jsonl'), encoding='utf-8')]
    комп = стр[0]['данные']
    по_url = {}
    for x in стр[1:]:
        if x.get('итог') == 'на странице' and not x.get('стр_класс') and any(х in x['url'] for х in ХОСТЫ):
            по_url.setdefault((x['inn'], x['url']), {})[x['номер']] = x
    if os.path.exists(ВЫХОД):
        os.remove(ВЫХОД)
    n = 0
    for (инн, url), номера in по_url.items():
        ст, html, _ = MN.скачать(url)
        текст = MP.в_текст(html) if ст == 'ok' else ''
        пары = [(ц, MP.найти(текст, ц[-10:])) for ц in номера]
        пары = [(ц, п[0]) for ц, п in пары if п]
        if not пары:
            continue
        окна = '\n…\n'.join(текст[max(0, п - 400):п + 150] for _, п in пары)[:6500]
        промпт = P5.ПРОМПТ.format(имя=комп[инн]['кандидат']['Название'], инн=инн, url=url, текст=окна,
                                  номера='\n'.join('%d. %s' % (i + 1, ц) for i, (ц, _) in enumerate(пары)))
        ответ = {}
        for попытка in range(3):
            try:
                out = VC._provider_call_stdlib(промпт)
                ответ = {int(x.get('n', 0)): x for x in json.loads(re.search(r'\[.*\]', out, re.S).group(0)) if isinstance(x, dict)}
                break
            except Exception:  # noqa: BLE001
                time.sleep(5)
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            for i, (ц, _) in enumerate(пары):
                x = ответ.get(i + 1) or {}
                f.write(json.dumps({'inn': инн, 'url': url, 'номер': ц, 'стр_фио': x.get('фио', ''),
                                    'стр_должность': x.get('должность', ''),
                                    'стр_класс': x.get('класс') if x.get('класс') in P5.КЛАССЫ else ''},
                                   ensure_ascii=False) + '\n')
                n += 1
            f.flush()
            os.fsync(f.fileno())
    shutil.copyfile(ВЫХОД, os.path.join(P5.ДРОП, 'park5-roli.jsonl'))
    print('===ИТОГ===')
    print(json.dumps({'страниц': len(по_url), 'номеров_размечено': n}, ensure_ascii=False))


if __name__ == '__main__':
    main()
