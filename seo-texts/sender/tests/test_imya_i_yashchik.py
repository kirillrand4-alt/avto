# -*- coding: utf-8 -*-
"""Имя годится, только если его подтверждает ТОТ ЯЩИК, по которому пишем.

Владелец 17.08: «фио ещё бы с именем ящика проверять, и если не совпадает,
резать». Повод — живое письмо #1284 партии 935: в карточке контакт «Горынин
Андрей Сергеевич», ящик `mfz55@mail.ru`, и письмо начиналось «Добрый день,
Андрей Сергеевич!». Ящик про Горынина не знает ничего: карточка у компании
одна, а ящиков в ней пять, и имя относилось к другому.

Проверяем по левой части адреса: хватает одного слова имени от четырёх букв,
найденного там в транслите (`aldengof@` ↔ «Альденгоф», `d.plotnikov@` ↔
«Плотников»). Три буквы не берём — на них ложных совпадений больше, чем
верных.

Правило НЕ отменяет второй путь надёжности (имя со страницы собственного
сайта со ссылкой) и не отменяет запрет на именное приветствие в общий ящик.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import (_imya_soglasuetsya_s_yashchikom,  # noqa: E402
                              _recipient_block, _svesti, _translit)

БАЗА = dict(company_name='ООО «Момез»', okved='25.62', activity='металл',
            mode='GENERIC')


def блок(имя, email, **ex):
    r = dict(БАЗА)
    r['contact_name'] = имя
    r['extra'] = dict(ex, email=email)
    return _recipient_block(0, r, 'kc', 0)


# --- сама сверка ---------------------------------------------------------- #

def test_yashchik_podtverzhdaet_imya():
    """Живые пары из партии 935 — их резать нельзя."""
    for имя, почта in (
            ('Альденгоф Андрей Леонидович', 'aldengof@mashtechnology.ru'),
            ('Плотников Дмитрий', 'd.plotnikov@moroshka.ru'),
            ('Андрей Демченко', 'a.demchenko@momez.ru'),
            ('Кочергин Михаил', 'kochergin.m@vetin.su')):
        assert _imya_soglasuetsya_s_yashchikom(имя, почта), (имя, почта)


def test_yashchik_ne_podtverzhdaet():
    """#1284 и ему подобные: имя есть, а ящик про него не знает."""
    for имя, почта in (
            ('Горынин Андрей Сергеевич', 'mfz55@mail.ru'),
            ('Иванов Иван', 'petrov@zavod.ru'),
            ('Хачатрян Гоар Аветисовна', 'nks-nnov@yandex.ru'),
            ('Плотников Дмитрий', 'zakupka@syrodelovo.ru')):
        assert not _imya_soglasuetsya_s_yashchikom(имя, почта), (имя, почта)


def test_korotkoe_slovo_ne_schitaetsya():
    """Три буквы дают ложные совпадения: «Ким» найдётся в akimov@."""
    assert not _imya_soglasuetsya_s_yashchikom('Ким Ольга', 'akimov@z.ru')


def test_otchestvo_tozhe_ulika():
    """Ящик бывает по имени-отчеству, а не по фамилии."""
    assert _imya_soglasuetsya_s_yashchikom('Смирнов Пётр Ильич',
                                           'petr.ilich@zavod.ru')


def test_pusto_i_musor_ne_padaet():
    for имя, почта in ((None, 'a@b.ru'), ('Иванов Иван', None),
                       ('', ''), ('Иванов Иван', 'не-почта'),
                       ('Иванов Иван', '@zavod.ru'), (123, 'a@b.ru')):
        assert not _imya_soglasuetsya_s_yashchikom(имя, почта), (имя, почта)


def test_registr_i_razdeliteli_ne_meshayut():
    assert _imya_soglasuetsya_s_yashchikom('ПЛОТНИКОВ Дмитрий',
                                           'D.Plotnikov@Moroshka.RU')


def test_translit_grubyy_no_uznayot():
    assert _translit('Денгоф') == 'dengof'
    assert _translit('Плотников') == 'plotnikov'
    assert _translit('Щербак') == 'scherbak'


def test_chuzhaya_shkola_translita_ne_rezhet():
    """Одно имя пишут по-разному, и это не повод считать ящик чужим."""
    for имя, почта in (
            ('Горынин Андрей Сергеевич', 'andrey@mfz55.ru'),
            ('Плотников Дмитрий', 'dmitry.plotnikov@moroshka.ru'),
            ('Хачатрян Гоар', 'khachatryan@nks.ru'),
            ('Юрьев Пётр', 'yuriev@zavod.ru'),
            # найдено замером 17.08: ящик пишет Ю одной буквой, а первая
            # редакция правила посчитала личный ящик чужим
            ('Юминова Екатерина Васильевна', 'yminova.ev@szmk-nk.com')):
        assert _imya_soglasuetsya_s_yashchikom(имя, почта), (имя, почта)


def test_svodka_odinakova_dlya_oboih_napisaniy():
    assert _svesti('andrey') == _svesti(_translit('Андрей'))
    assert _svesti('khachatryan') == _svesti(_translit('Хачатрян'))
    assert _svesti('dmitry') == _svesti(_translit('Дмитрий'))


# --- как это видно в блоке получателя ------------------------------------- #

def test_soglasovannoe_imya_daet_privetstvie():
    б = блок('Плотников Дмитрий', 'd.plotnikov@moroshka.ru')
    assert 'ОБЯЗАТЕЛЬНО поздоровайся по имени' in б, б


def test_nesoglasovannoe_imya_ne_daet_privetstviya():
    """#1284 больше не здоровается по имени."""
    б = блок('Горынин Андрей Сергеевич', 'mfz55@mail.ru')
    assert 'ОБЯЗАТЕЛЬНО поздоровайся по имени' not in б, б
    assert 'по имени НЕ обращаться' in б, б


def test_nesoglasovannoe_imya_uhodit_v_prosbu_peredat():
    """Имя не выбрасываем: оно доводит письмо до нужного стола.

    Замер по партии 935: полных имён 606, ящик подтверждает 232. Выкинуть
    374 имени целиком - потеря; здороваться ими - ошибка человеком. Третий
    путь (тот же, что для приёмной) не платит ни тем, ни другим.
    """
    б = блок('Горынин Андрей Сергеевич', 'mfz55@mail.ru')
    assert 'передайте письмо ему' in б, б
    assert 'Горынин Андрей Сергеевич' in б, б


def test_nepolnoe_imya_v_prosbu_ne_idyot():
    """«Клюева Т.» пересказывает ящик — такое имя не называем вовсе."""
    б = блок('Клюева Т.', 'klyuevats@rushydro.ru')
    assert 'источник имени ненадёжен' in б, б
    assert 'передайте письмо ему' not in б, б


def test_svoy_sayt_so_ssylkoy_silnee_yashchika():
    """Второй путь надёжности правка не трогает: имя со страницы компании
    остаётся годным, даже если ящик его не пишет."""
    б = блок('Горынин Андрей Сергеевич', 'mfz55@mail.ru',
             contact_source='own-site',
             contact_source_url='https://mfz55.ru/about/')
    assert 'ОБЯЗАТЕЛЬНО поздоровайся по имени' in б, б


def test_obshchiy_yashchik_silnee_soglasovannogo_imeni():
    """Согласованное имя не открывает приёмную: там читает секретарь."""
    б = блок('Плотников Дмитрий', 'd.plotnikov@moroshka.ru', role='приёмная')
    assert 'по имени НЕ' in б, б


def test_email_iz_verhnego_urovnya_tozhe_beryotsya():
    """Адрес приходит то в extra, то в самой записи — читаем оба места."""
    r = dict(БАЗА)
    r['contact_name'] = 'Плотников Дмитрий'
    r['email'] = 'd.plotnikov@moroshka.ru'
    r['extra'] = {}
    assert 'ОБЯЗАТЕЛЬНО поздоровайся по имени' in _recipient_block(0, r, 'kc', 0)



def test_shkoly_transliteracii_ts_tc_shch():
    """Ц и Щ пишут в почте по-разному, и это не повод считать ящик чужим.

    Находка ручного разбора имён 18.08: «Гриценко» разворачивалось в
    gricenko, а её ящик пишет eagritsenko@ - личный ящик посчитался чужим и
    именное приветствие пропало. Живые ящики партии пишут Ц тремя способами.
    """
    for имя, почта in (
            ('Гриценко Елена Александровна', 'eagritsenko@ooo-kzm.ru'),
            ('Кузнецов Пётр Андреевич', 'kuznetcov_pa@kontirus.ru'),
            ('Кузнецов Пётр', 'kuznetsov@zavod.ru'),
            ('Цветков Игорь', 'tsvetkov@zavod.ru'),
            ('Щербак Олег', 'shcherbak@zavod.ru')):
        assert _imya_soglasuetsya_s_yashchikom(имя, почта), (имя, почта)


def test_svodka_ne_sklеila_chuzhih():
    """Расширение сводки не должно начать признавать чужие ящики."""
    for имя, почта in (('Иванов Иван', 'petrov@zavod.ru'),
                       ('Горынин Андрей Сергеевич', 'mfz55@mail.ru'),
                       ('Ким Ольга', 'akimov@zavod.ru')):
        assert not _imya_soglasuetsya_s_yashchikom(имя, почта), (имя, почта)


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:120]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
