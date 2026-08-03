# -*- coding: utf-8 -*-
"""Найти опы, которые падают на первом же запуске: имя используется, но нигде
не определено.

ЗАЧЕМ. `leadership.py` числился в отчётах главным источником ФИО с должностью
и не работал ВООБЩЕ: в файле не было ни `замок`, ни `out`, ни файла резюма,
хотя воркер пользуется всеми тремя, а список целей ссылался на удалённую
переменную `todo`. Падал он на первой же компании — то есть канал был мёртв, а
снаружи выглядел живым. Заметить это можно было только запуском, а запуска не
было: оп «перевели на общий выбор целей» и на этом успокоились.

Раз один такой нашёлся случайно, остальные надо искать нарочно. Запускать все
опы подряд нельзя — они ходят в сеть, пишут в базы и стоят денег. Поэтому
проверка ЧИСТО СТАТИЧЕСКАЯ: разбираем файл в дерево и ищем чтение имени,
которого нет ни среди присваиваний, ни среди импортов, ни среди аргументов, ни
среди встроенных.

ЧЕГО ОНА НЕ ЛОВИТ, и это надо знать: динамику (`globals()[имя]`), имена из
`from X import *`, ошибки времени выполнения вроде неверного SQL. Она ловит
ровно один класс — «переменная исчезла при правке» — тот самый, что убил
leadership. Пустой ответ здесь означает «этого класса нет», а не «всё
работает».

Запуск: python proverka_opov.py [папка] [--tihо]
"""
import ast
import builtins
import os
import sys

ПАПКА = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--')
         else os.path.dirname(os.path.abspath(__file__)))
ТИХО = '--tiho' in sys.argv
ВСТРОЕННЫЕ = set(dir(builtins)) | {
    '__file__', '__name__', '__doc__', '__builtins__', '__spec__',
    '__package__', '__loader__', 'WindowsError'}


class Сбор(ast.NodeVisitor):
    """Все имена, которые файл где-либо определяет.

    Намеренно БЕЗ учёта области видимости: цель — не строгая проверка, а
    отсутствие ложных тревог. Если имя присваивается хоть где-то в файле,
    считаем определённым. Ошибка leadership всё равно ловится: `замок` не
    присваивался нигде.
    """

    def __init__(self):
        self.имена = set()

    def _цель(self, узел):
        if isinstance(узел, ast.Name):
            self.имена.add(узел.id)
        elif isinstance(узел, (ast.Tuple, ast.List)):
            for э in узел.elts:
                self._цель(э)
        elif isinstance(узел, ast.Starred):
            self._цель(узел.value)

    def visit_Assign(self, узел):
        for ц in узел.targets:
            self._цель(ц)
        self.generic_visit(узел)

    def visit_AnnAssign(self, узел):
        self._цель(узел.target)
        self.generic_visit(узел)

    def visit_AugAssign(self, узел):
        self._цель(узел.target)
        self.generic_visit(узел)

    def visit_NamedExpr(self, узел):
        self._цель(узел.target)
        self.generic_visit(узел)

    def visit_For(self, узел):
        self._цель(узел.target)
        self.generic_visit(узел)

    def visit_AsyncFor(self, узел):
        self.visit_For(узел)

    def visit_comprehension(self, узел):
        self._цель(узел.target)
        self.generic_visit(узел)

    def visit_withitem(self, узел):
        if узел.optional_vars is not None:
            self._цель(узел.optional_vars)
        self.generic_visit(узел)

    def visit_ExceptHandler(self, узел):
        if узел.name:
            self.имена.add(узел.name)
        self.generic_visit(узел)

    def visit_Import(self, узел):
        for а in узел.names:
            self.имена.add((а.asname or а.name).split('.')[0])

    def visit_ImportFrom(self, узел):
        for а in узел.names:
            self.имена.add(а.asname or а.name)

    def _функция(self, узел):
        self.имена.add(узел.name)
        а = узел.args
        for арг in (list(а.posonlyargs) + list(а.args) + list(а.kwonlyargs)
                    + [а.vararg, а.kwarg]):
            if арг is not None:
                self.имена.add(арг.arg)
        self.generic_visit(узел)

    def visit_FunctionDef(self, узел):
        self._функция(узел)

    def visit_AsyncFunctionDef(self, узел):
        self._функция(узел)

    def visit_Lambda(self, узел):
        а = узел.args
        for арг in (list(а.posonlyargs) + list(а.args) + list(а.kwonlyargs)
                    + [а.vararg, а.kwarg]):
            if арг is not None:
                self.имена.add(арг.arg)
        self.generic_visit(узел)

    def visit_ClassDef(self, узел):
        self.имена.add(узел.name)
        self.generic_visit(узел)

    def visit_Global(self, узел):
        self.имена.update(узел.names)

    def visit_Nonlocal(self, узел):
        self.имена.update(узел.names)


def _ложь(узел):
    """Условие, которое заведомо ложно: `if False`, `if 0`, `if ''`."""
    return isinstance(узел, ast.Constant) and not узел.value


def _мертво(дерево):
    """Узлы, до которых исполнение не доходит НИКОГДА.

    Первый прогон дал три находки, и все три оказались одним и тем же:
    `орг.get('items') or orг if False else (…)`. Ветка при ложном условии не
    вычисляется, имя в ней не читается, падения нет. Если их не отсеять,
    проверка гонит следующего человека по тем же трём призракам — а доверие к
    инструменту, который трижды соврал, кончается раньше, чем находки.
    """
    мёртвые = set()
    for узел in ast.walk(дерево):
        ветки = []
        if isinstance(узел, ast.IfExp) and _ложь(узел.test):
            ветки = [узел.body]
        elif isinstance(узел, ast.If) and _ложь(узел.test):
            ветки = list(узел.body)
        elif isinstance(узел, ast.While) and _ложь(узел.test):
            ветки = list(узел.body)
        for в in ветки:
            for под in ast.walk(в):
                мёртвые.add(id(под))
    return мёртвые


def читатели(дерево):
    """Имена, которые файл ЧИТАЕТ, с номерами строк. Мёртвый код не в счёт."""
    мёртвые = _мертво(дерево)
    из = {}
    for узел in ast.walk(дерево):
        if (isinstance(узел, ast.Name) and isinstance(узел.ctx, ast.Load)
                and id(узел) not in мёртвые):
            из.setdefault(узел.id, узел.lineno)
    return из


def проверить(путь):
    сыр = open(путь, encoding='utf-8', errors='replace').read()
    try:
        дерево = ast.parse(сыр)
    except SyntaxError as e:
        return [('СИНТАКСИС', e.lineno or 0, str(e)[:80])]
    с = Сбор()
    с.visit(дерево)
    беды = []
    for имя, строка in sorted(читатели(дерево).items(), key=lambda x: x[1]):
        if имя in с.имена or имя in ВСТРОЕННЫЕ:
            continue
        беды.append(('НЕТ ИМЕНИ', строка, имя))
    return беды


def main():
    файлы = sorted(f for f in os.listdir(ПАПКА)
                   if f.endswith('.py') and f != os.path.basename(__file__))
    битых = 0
    всего_бед = 0
    for имя in файлы:
        беды = проверить(os.path.join(ПАПКА, имя))
        if not беды:
            continue
        битых += 1
        всего_бед += len(беды)
        print(f'{имя}:')
        for вид, строка, что in беды[:6]:
            print(f'    строка {строка}: {вид} — {что}')
        if len(беды) > 6:
            print(f'    … и ещё {len(беды) - 6}')
    print(f'\nпроверено файлов: {len(файлы)}; с бедой: {битых}; '
          f'находок: {всего_бед}')
    if not битых:
        print('этого класса поломок нет. Другие классы проверка не видит.')


if __name__ == '__main__':
    main()
