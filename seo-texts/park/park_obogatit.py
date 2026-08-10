# -*- coding: utf-8 -*-
"""Обогащение контактами предприятий ПАРКА, у которых телефона нет.

Числа на 10.08: в парке 3 142 предприятия, телефон со ссылкой есть у 1 109. То есть
у двух третей парка машина доказана, а позвонить некому — это и есть главный пробел
задачи владельца («обогатить контактами всеми способами + перепроверить»).

Работаем ШТАТНЫМ конвейером `enrich_contacts.main()`, а не самопиской: он уже умеет
обход сайта с приоритетом staff-страниц, извлечение ролей провайдером, контакт закупщика
из карточки ЕИС, проверку owner_match (сайт вообще этой компании?). Аргументы он читает
из STDIN, поэтому подменяем stdin — на этом легко споткнуться.

Долговечность и резюмируемость обеспечивает сам конвейер: `write_db: true` пишет в
`enrich.db` по готовности каждой компании, `resume: true` + `stream_file` пропускают
уже сделанные ИНН. Сандбокс сессии тут ни при чём — всё серверное.

Запуск: panel_py, argv = [<сколько компаний за вызов>, <смещение>]
"""
import io, json, os, sys

sys.path.insert(0, r'C:\sender\server')

ZAD = r'C:\seostat\drop\drop-storage\park_obogashchenie_zadanie.json'
POTOK = r'C:\sender\park_obogashchenie_potok.jsonl'


def main():
    skolko = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    smeshch = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    spisok = json.load(open(ZAD, encoding='utf-8'))

    sdelano = set()
    if os.path.exists(POTOK):
        with open(POTOK, encoding='utf-8', errors='replace') as f:
            for ln in f:
                try:
                    d = json.loads(ln)
                except Exception:
                    continue
                if d.get('inn'):
                    sdelano.add(str(d['inn']))
    ochered = [c for c in spisok if str(c['inn']) not in sdelano][smeshch:smeshch + skolko]
    if not ochered:
        print(json.dumps({'vsego': len(spisok), 'sdelano': len(sdelano),
                          'k_rabote': 0, 'itog': 'очередь пуста'}, ensure_ascii=False))
        return

    import enrich_contacts as EC
    args = {
        'companies': ochered,
        'workers': 20,
        'browser_workers': 10,
        'zakupki_check': True,
        'hh_check': True,
        'opo_check': False,
        'extract_model': 'claude-haiku-4-5',
        'resume': True,
        'stream_file': POTOK,
        'write_db': True,
        'pace_min': 0.4,
        'pace_max': 1.2,
        'fetch_timeout': 25,
    }
    sys.stdin = io.StringIO(json.dumps(args, ensure_ascii=False))
    EC.main()
    print(json.dumps({'vsego': len(spisok), 'bylo_sdelano': len(sdelano),
                      'v_etom_vyzove': len(ochered)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
