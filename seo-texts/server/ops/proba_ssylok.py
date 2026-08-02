# -*- coding: utf-8 -*-
"""Живая проверка ссылок-поисков по ИНН на торговых площадках.

Собрать URL из шаблона легко, и он выглядит настоящим. Работает ли он —
отдельный вопрос: площадка может требовать POST, авторизацию, отдавать 403 или
показывать пустую выдачу. Записать в базу 218 нерабочих ссылок хуже, чем
оставить поле пустым: пустое видно, а мёртвая ссылка выглядит как источник,
пока по ней не кликнут.

Проверяем каждый шаблон на живом ИНН из базы: код ответа, размер и есть ли
на странице сам ИНН.

Запуск: python proba_ssylok.py
"""
import urllib.error
import urllib.request

ШАБЛОНЫ = {
    'ЭТП ГПБ': 'https://etpgpb.ru/procedures/?searchString={inn}',
    'ТЭК-Торг': 'https://www.tektorg.ru/search?query={inn}',
    'Сбербанк-АСТ': 'http://utp.sberbank-ast.ru/Main/List/Procedures?searchString={inn}',
    'zakupki.gov (процедура)':
        'https://zakupki.gov.ru/223/purchase/public/purchase/info/'
        'common-info.html?regNumber=32110511492',
    'monitor-pb (ЭПБ)': 'https://monitor-pb.ru/conclusion/30-%D0%A2%D0%A3-01213-2015',
    'checko': 'https://checko.ru/search?query={inn}',
    'hh поиск': 'https://hh.ru/search/vacancy?text={inn}',
}
ИНН = '0266048970'   # Газпром нефтехим Салават, живой из базы
УА = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def main():
    for имя, шаб in ШАБЛОНЫ.items():
        url = шаб.format(inn=ИНН)
        try:
            зпр = urllib.request.Request(url, headers={'User-Agent': УА})
            with urllib.request.urlopen(зпр, timeout=40) as о:
                тело = о.read(400000).decode('utf-8', 'replace')
            есть_инн = ИНН in тело
            пусто = any(с in тело.lower() for с in
                        ('ничего не найдено', 'не найдено', 'нет результатов',
                         'по вашему запросу'))
            print(f'  {имя:<24} {о.status}  {len(тело):>7} байт  '
                  f'ИНН на странице: {"да" if есть_инн else "нет"}'
                  f'{"  ПУСТАЯ ВЫДАЧА" if пусто else ""}')
        except urllib.error.HTTPError as e:
            print(f'  {имя:<24} HTTP {e.code} — ссылка НЕ РАБОТАЕТ')
        except Exception as e:  # noqa: BLE001
            print(f'  {имя:<24} ОШИБКА: {str(e)[:90]}')


if __name__ == '__main__':
    main()
