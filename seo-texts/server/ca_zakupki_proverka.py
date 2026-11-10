# -*- coding: utf-8 -*-
r"""Перепроверка контактов из закупок ЕИС набора ca без новых запросов (10.11, владелец: «контакты из закупок ЕИС
1 075 — перепроверить бы как-то, верны ли контакты»).

Каждый контакт карточки (ФИО, телефон, почта) получает вердикт:
  * «ошибочен» — тот же телефон/почта в карточках >= 3 разных заказчиков: это организатор торгов, агент или площадка,
    а не сотрудник компании;
  * «подтверждён» — телефон или почта есть среди контактов, найденных на сайте этой компании, или почта на домене её
    сайта;
  * «сомнителен» — почта на чужом корпоративном домене (не сайт компании, не бесплатная) или ИНН компании нет на
    странице карточки;
  * «правдоподобен» — остальное (ИНН на странице, противоречий нет; бесплатная почта или только телефон).
Свежесть (дата закупки) здесь не проверяется — нужен повторный заход в ЕИС, отдельным мягким шагом.
Выход (fsync, на сервере — ФИО и телефоны в репозиторий и чат не выводить): ca\ca-zakupki-proverka.jsonl;
счётчики — ca\ca-zakupki-proverka-itog.json (+ дроп). Только чтение. Запуск: run_script_on_server.py.
"""
import collections, io, json, os, re

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')
ДРОП = r'C:\seostat\drop\drop-storage'
БЕСПЛАТНЫЕ = re.compile(r'@(?:mail|inbox|list|bk|internet|yandex|ya|gmail|rambler|hotmail|outlook|icloud|lenta|ro)\.(?:ru|com|ua|by|kz)$',
                        re.I)


def цифры(т):
    return re.sub(r'\D', '', str(т or ''))[-10:]


def домен(u):
    u = re.sub(r'^https?://', '', str(u or '').lower()).split('/')[0]
    return re.sub(r'^www\.', '', u)


def main():
    # по компании в журнале бывает несколько записей (доразметка дописывает) — берём последнюю, а карточки закупок
    # с людьми собираем из всех записей (без повторов по url)
    зап, карты = {}, collections.defaultdict(dict)
    for s in io.open(os.path.join(DIR, 'ca-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('итог') == 'ok':
            зап[з['inn']] = з
            for к in з.get('закупки') or []:
                if к.get('люди') and к.get('url'):
                    карты[з['inn']][к['url']] = к
    for инн, з in зап.items():
        з['закупки'] = list(карты.get(инн, {}).values())
    # кто из заказчиков делит телефон/почту
    у_кого = collections.defaultdict(set)
    for инн, з in зап.items():
        for к in з.get('закупки') or []:
            for ч in к.get('люди') or []:
                if isinstance(ч, dict):
                    for ключ in (цифры(ч.get('phone')), (ч.get('email') or '').lower().strip()):
                        if ключ and len(ключ) >= 6:
                            у_кого[ключ].add(инн)
    вердикты = collections.Counter()
    компании = collections.Counter()
    п = os.path.join(ПАПКА, 'ca-zakupki-proverka.jsonl')
    with io.open(п, 'w', encoding='utf-8') as f:
        for инн, з in зап.items():
            сайт = домен(з.get('сайт'))
            тел_сайта = {цифры(x.get('номер')) for x in з.get('номера') or [] if x.get('номер') and x.get('чей') != 'другая'}
            почты_сайта = {(x.get('почта') or '').lower() for x in з.get('номера') or [] if x.get('почта') and x.get('чей') != 'другая'}
            лучш = ''
            for к in з.get('закупки') or []:
                for ч in к.get('люди') or []:
                    if not isinstance(ч, dict):
                        continue
                    т, п_ = цифры(ч.get('phone')), (ч.get('email') or '').lower().strip()
                    дом = п_.split('@')[-1] if '@' in п_ else ''
                    общий = max(len(у_кого.get(т, ())), len(у_кого.get(п_, ())))
                    if общий >= 3:
                        в, почему = 'ошибочен', 'тот же контакт у %d заказчиков (организатор/агент)' % общий
                    elif (т and т in тел_сайта) or (п_ and п_ in почты_сайта) or (дом and сайт and (дом == сайт or дом.endswith('.' + сайт))):
                        в, почему = 'подтверждён', 'совпал с сайтом компании'
                    elif дом and not БЕСПЛАТНЫЕ.search(п_) and сайт and дом != сайт:
                        в, почему = 'сомнителен', 'почта на чужом домене %s (сайт %s)' % (дом, сайт)
                    elif not к.get('инн_на_странице'):
                        в, почему = 'сомнителен', 'ИНН компании нет на странице карточки'
                    else:
                        в, почему = 'правдоподобен', 'ИНН на странице, противоречий нет'
                    вердикты[в] += 1
                    порядок = ['ошибочен', 'сомнителен', 'правдоподобен', 'подтверждён']
                    if порядок.index(в) > порядок.index(лучш) if лучш else True:
                        лучш = в
                    f.write(json.dumps({'inn': инн, 'url': к.get('url'), 'фио': ч.get('person') or '', 'должность': ч.get('post') or '',
                                        'телефон': ч.get('phone') or '', 'почта': п_, 'вердикт': в, 'почему': почему},
                                       ensure_ascii=False) + '\n')
            if лучш:
                компании[лучш] += 1
        f.flush()
        os.fsync(f.fileno())
    итог = {'контактов': dict(вердикты), 'компаний_по_лучшему_контакту': dict(компании),
            'компаний_с_контактом_ЕИС': sum(компании.values())}
    пи = os.path.join(ПАПКА, 'ca-zakupki-proverka-itog.json')
    with open(пи, 'w', encoding='utf-8') as f:
        json.dump(итог, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    import shutil
    shutil.copyfile(пи, os.path.join(ДРОП, 'ca-zakupki-proverka-itog.json'))
    print('===ИТОГ===', json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    main()
