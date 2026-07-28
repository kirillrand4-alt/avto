# -*- coding: utf-8 -*-
"""Согласование письма с полом менеджера-отправителя (скрин владельца 28.07:
подпись «Анастасия Мирошниченко», а в тексте «Прочитал»)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sender.gender_agree import agree, agree_for_mailbox, gender_of  # noqa: E402

_ПИСЬМО = ("Добрый день!\n\n"
           "Прочитал про запуск завода по переработке водорослей - мощность "
           "10 000 тонн готовой продукции в год.\n\n"
           "Завод запустил линию, подрядчик помог с монтажом.\n\n"
           "Я веду направление Meyer и буду рад помочь. Наткнулся на новость "
           "случайно. Готов посчитать.\n\nС уважением,")


def test_female_forms():
    r = agree(_ПИСЬМО, 'f')
    assert 'Прочитала' in r and 'Наткнулась' in r
    assert 'буду рада помочь' in r and 'Готова посчитать' in r


def test_third_person_untouched():
    """Главный риск приёма: «завод запустил», «подрядчик помог» - НЕ мы."""
    r = agree(_ПИСЬМО, 'f')
    assert 'Завод запустил линию' in r and 'подрядчик помог' in r


def test_idempotent_and_male_noop():
    r = agree(_ПИСЬМО, 'f')
    assert agree(r, 'f') == r
    assert agree(_ПИСЬМО, 'm') == _ПИСЬМО


def test_gender_of_names():
    assert gender_of('Анастасия Мирошниченко, Meyer') == 'f'
    assert gender_of('Владислав Мельников') == 'm'
    assert gender_of('Никита Смирнов') == 'm'          # -а, но мужское
    assert gender_of('Любовь Орлова') == 'f'           # без -а, но женское
    assert gender_of('') == 'm'                        # неизвестно - как было


def test_explicit_config_wins():
    assert gender_of('Женя Волков', 'f') == 'f'
    assert gender_of('Анастасия Иванова', 'm') == 'm'


class _Cfg:
    def __init__(self, карта):
        self._к = карта

    def get(self, key, default=None):
        return self._к if key == 'personalization.mailbox_gender' else default


def test_agree_for_mailbox_uses_config_then_name():
    cfg = _Cfg({'a.box@x.ru': 'f'})
    # пол из конфига, хотя имя мужское
    assert 'Прочитала' in agree_for_mailbox(_ПИСЬМО, 'Пётр Волков', cfg,
                                            'a.box@x.ru')
    # ящика в карте нет — по имени
    assert 'Прочитала' in agree_for_mailbox(_ПИСЬМО, 'Анастасия М.', cfg,
                                            'b.box@x.ru')
    assert 'Прочитал ' in agree_for_mailbox(_ПИСЬМО, 'Пётр Волков', cfg,
                                            'b.box@x.ru')


def test_broken_config_does_not_raise():
    class Bad:
        def get(self, *a, **k):
            raise RuntimeError('конфиг сломан')
    assert agree_for_mailbox(_ПИСЬМО, 'Анастасия', Bad(), 'x') == _ПИСЬМО
