"""Unit tests for sender.reply_classify.

Тестирует классификацию входящих ответов холодной B2B-рассылки:
автоответы, отписки, отказы, горячие/заинтересованные/нейтральные реплики,
извлечение телефона и контактов из подписи.
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.reply_classify import (  # noqa: E402
    ReplySignal,
    classify_reply,
    classify_reply_ai,
    extract_phone,
)


# --- Тесты автоответов ---


def test_auto_reply_header_auto_submitted():
    """Автоответ определяется по заголовку Auto-Submitted."""
    headers = {"Auto-Submitted": "auto-replied"}
    result = classify_reply("Re: Предложение", "Спасибо за письмо", headers)
    
    assert result.kind == "auto_reply"
    assert result.confidence == 0.9
    assert "header_auto_reply" in result.matched


def test_auto_reply_vacation_text():
    """Автоответ по тексту отпуска."""
    body = """Я в отпуске до 25.07, по срочным вопросам пишите коллеге
    ivanov@example.com
    
    С уважением,
    Петров Иван"""
    
    result = classify_reply("Re: Коммерческое", body)
    
    assert result.kind == "auto_reply"
    assert result.confidence == 0.9
    assert len(result.matched) > 0
    assert any("отпуск" in m for m in result.matched)


def test_auto_reply_out_of_office():
    """Автоответ Out of Office на английском."""
    body = "Out of office until Monday. For urgent matters contact manager@company.com"
    
    result = classify_reply("Re: Proposal", body)
    
    assert result.kind == "auto_reply"
    assert result.confidence == 0.9


def test_auto_reply_false_positive():
    """Не автоответ: упоминание отпуска в контексте интереса."""
    body = """Мы не в отпуске и работаем в обычном режиме.
    Интересует цена на оборудование, пришлите коммерческое предложение."""
    
    result = classify_reply("Re: Оборудование", body)
    
    # Должен быть hot из-за "пришлите коммерческое предложение"
    assert result.kind == "hot"


def test_auto_reply_precedence_header():
    """Автоответ по заголовку Precedence."""
    headers = {"Precedence": "auto_reply"}
    result = classify_reply("Re: Info", "Thank you", headers)
    
    assert result.kind == "auto_reply"


# --- Тесты отписок ---


def test_unsub_request_explicit():
    """Явная просьба отписать."""
    body = "Отпишите меня, пожалуйста, от рассылки."
    
    result = classify_reply("Re: Предложение", body)
    
    assert result.kind == "unsub_request"
    assert result.confidence == 0.9
    assert any("отпиш" in m for m in result.matched)


def test_unsub_request_remove_from_list():
    """Просьба убрать из рассылки."""
    body = "Уберите из рассылки, не интересует."
    
    result = classify_reply("Re: Акция", body)
    
    assert result.kind == "unsub_request"


def test_unsub_request_english():
    """Отписка на английском."""
    body = "Please unsubscribe me from this list"
    
    result = classify_reply("Re: Offer", body)
    
    assert result.kind == "unsub_request"


# --- Тесты отказов (не интересно) ---


def test_not_interested_explicit():
    """Явный отказ: спасибо, неактуально."""
    body = "Спасибо, неактуально на данный момент."
    
    result = classify_reply("Re: Услуги", body)
    
    assert result.kind == "not_interested"
    assert result.confidence == 0.9


def test_not_interested_have_supplier():
    """Отказ: есть поставщик."""
    body = """У нас есть поставщик по этой категории,
    смены не планируем."""
    
    result = classify_reply("Re: Поставка", body)
    
    assert result.kind == "not_interested"


def test_not_interested_no_need():
    """Отказ: нет потребности."""
    body = "Нет потребности в данной услуге, не требуется."
    
    result = classify_reply("Re: Предложение", body)
    
    assert result.kind == "not_interested"


# --- Тесты горячих лидов ---


def test_hot_invoice_request():
    """Горячий: просьба выставить счёт."""
    body = """Выставьте счёт на ООО Ромашка, ИНН 7712345678.
    
    Отгрузка по адресу: Москва, ул. Ленина 1.
    
    С уважением,
    Сидоров"""
    
    result = classify_reply("Re: Заказ", body)
    
    assert result.kind == "hot"
    assert result.confidence == 0.9
    assert any("счёт" in m or "счет" in m for m in result.matched)


def test_hot_kp_and_price_request():
    """Горячий: запрос КП и прайса."""
    body = "Пришлите КП и прайс на оборудование."
    
    result = classify_reply("Re: Оборудование", body)
    
    assert result.kind == "hot"


def test_hot_with_phone():
    """Горячий: телефон в теле письма."""
    body = """Интересует ваше предложение.
    Позвоните мне +7 (912) 345-67-89 для обсуждения деталей.
    
    Иван Петров"""
    
    result = classify_reply("Re: Сотрудничество", body)
    
    assert result.kind == "hot"
    assert result.phone == "+79123456789"
    assert "phone_found" in result.matched


def test_hot_call_me():
    """Горячий: просьба перезвонить."""
    body = "Перезвоните мне завтра после 14:00, обсудим условия."
    
    result = classify_reply("Re: Договор", body)
    
    assert result.kind == "hot"


# --- Тесты заинтересованных ---


def test_interested_request_info():
    """Заинтересован: запрос характеристик."""
    body = "Пришлите характеристики и сроки поставки."
    
    result = classify_reply("Re: Товар", body)
    
    assert result.kind == "interested"


def test_interested_more_details():
    """Заинтересован: просьба рассказать подробнее."""
    body = "Расскажите подробнее об условиях и ценах."
    
    result = classify_reply("Re: Предложение", body)
    
    assert result.kind == "interested"


def test_interested_short_question():
    """Заинтересован: короткий вопрос."""
    body = "Какие сроки поставки?"
    
    result = classify_reply("Re: Оборудование", body)
    
    assert result.kind == "interested"
    assert "short_question" in result.matched


# --- Тесты нейтральных ---


def test_neutral_thank_you():
    """Нейтральный: односложное спасибо."""
    body = "Спасибо"
    
    result = classify_reply("Re: Информация", body)
    
    assert result.kind == "neutral"
    assert result.confidence == 0.3


def test_neutral_empty():
    """Нейтральный: пустое тело."""
    result = classify_reply("Re: Test", "")
    
    assert result.kind == "neutral"


def test_neutral_acknowledgement():
    """Нейтральный: нейтральное подтверждение получения."""
    body = "Получил, ознакомлюсь."
    
    result = classify_reply("Re: Документы", body)
    
    assert result.kind == "neutral"


# --- Тесты извлечения телефона ---


def test_extract_phone_spaces():
    """Извлечение телефона с пробелами."""
    text = "Мой телефон: 8 912 345 67 89"
    phone = extract_phone(text)
    
    assert phone == "+79123456789"


def test_extract_phone_dashes():
    """Извлечение телефона с дефисами."""
    text = "Звоните: +7-912-345-67-89"
    phone = extract_phone(text)
    
    assert phone == "+79123456789"


def test_extract_phone_parentheses():
    """Извлечение телефона со скобками."""
    text = "Контакт: +7 (912) 345-67-89"
    phone = extract_phone(text)
    
    assert phone == "+79123456789"


def test_extract_phone_eight_prefix():
    """Извлечение телефона с префиксом 8."""
    text = "Тел: 8(912)345-67-89"
    phone = extract_phone(text)
    
    assert phone == "+79123456789"


def test_extract_phone_seven_prefix():
    """Извлечение телефона с префиксом 7."""
    text = "Телефон: 7 912 345 67 89"
    phone = extract_phone(text)
    
    assert phone == "+79123456789"


def test_extract_phone_not_inn():
    """ИНН не должен распознаваться как телефон."""
    text = "ИНН 7712345678 ОГРН 1234567890123"
    phone = extract_phone(text)
    
    assert phone is None


def test_extract_phone_first_match():
    """Приоритет первого телефона."""
    text = """Основной: +7 (912) 345-67-89
    Дополнительный: +7 (913) 111-22-33"""
    phone = extract_phone(text)
    
    assert phone == "+79123456789"


def test_extract_phone_none():
    """Отсутствие телефона."""
    text = "Напишите на email: info@example.com"
    phone = extract_phone(text)
    
    assert phone is None


def test_extract_phone_invalid_operator():
    """Телефон с невалидным кодом оператора."""
    text = "Тел: +7 (012) 345-67-89"
    phone = extract_phone(text)
    
    # Первая цифра 0 — невалидна для мобильных
    assert phone is None


# --- Тесты извлечения контактов ---


def test_contact_hint_signature():
    """Извлечение имени из подписи."""
    body = """Пришлите информацию.
    
    С уважением,
    Иван Петров
    Главный энергетик"""
    
    result = classify_reply("Re: Запрос", body)
    
    assert result.contact_hint is not None
    assert "Иван Петров" in result.contact_hint or "Главный энергетик" in result.contact_hint


def test_contact_hint_best_regards():
    """Извлечение из английской подписи."""
    body = """Please send details.
    
    Best regards,
    John Smith
    Technical Director"""
    
    result = classify_reply("Re: Request", body)
    
    assert result.contact_hint is not None


def test_contact_hint_double_dash():
    """Извлечение из подписи с двойным дефисом."""
    body = """Интересует предложение.
    
    --
    Сергей Иванов
    Менеджер закупок"""
    
    result = classify_reply("Re: Покупка", body)
    
    assert result.contact_hint is not None


def test_contact_hint_no_signature():
    """Отсутствие подписи."""
    body = "Спасибо за информацию"
    
    result = classify_reply("Re: Info", body)
    
    # Может быть None или короткий текст
    if result.contact_hint:
        assert len(result.contact_hint) < 80


def test_contact_hint_filters_url():
    """Фильтрация строк с URL из контактов."""
    body = """Жду ответа.
    
    С уважением,
    Петр Сидоров
    https://company.com"""
    
    result = classify_reply("Re: Вопрос", body)
    
    # URL не должен попасть в contact_hint
    if result.contact_hint:
        assert "https" not in result.contact_hint
        assert "company.com" not in result.contact_hint


def test_contact_hint_filters_email():
    """Фильтрация строк с email."""
    body = """Напишите детали.
    
    Best regards,
    Anna Smith
    anna@company.com"""
    
    result = classify_reply("Re: Details", body)
    
    if result.contact_hint:
        assert "@" not in result.contact_hint


# --- Тесты classify_reply_ai ---


class FakeAiUpgrade:
    """Фейковый AI-классификатор, уточняющий neutral->hot при наличии телефона."""
    
    def classify(self, subject: str, body: str) -> dict:
        """Имитация AI-классификации."""
        phone = extract_phone(body)
        
        if phone:
            return {
                "kind": "hot",
                "confidence": 0.85,
                "phone": phone,
            }
        
        return {
            "kind": "interested",
            "confidence": 0.7,
            "phone": None,
        }


def test_classify_reply_ai_upgrade_neutral_to_hot():
    """AI уточняет neutral -> hot: правила уверенности не дали (телефона в
    теле НЕТ — иначе правила сами скажут hot и AI не зовётся по спеке)."""
    body = "Получил, спасибо."

    class Ai:
        def classify(self, subject, body):
            return {"kind": "hot", "confidence": 0.85, "phone": "+79123456789"}

    result = classify_reply_ai("Re: Info", body, ai=Ai())

    assert result.kind == "hot"
    assert result.phone == "+79123456789"
    assert "ai_classified" in result.matched


def test_classify_reply_ai_no_upgrade_on_confident():
    """AI не применяется для уверенных результатов (auto_reply)."""
    body = "Я в отпуске до конца месяца."
    
    ai = FakeAiUpgrade()
    result = classify_reply_ai("Re: Request", body, ai=ai)
    
    assert result.kind == "auto_reply"
    assert "ai_classified" not in result.matched


def test_classify_reply_ai_upgrade_interested():
    """AI уточняет neutral -> interested."""
    body = "Спасибо, получил письмо."
    
    ai = FakeAiUpgrade()
    result = classify_reply_ai("Re: Offer", body, ai=ai)
    
    assert result.kind == "interested"
    assert result.confidence == 0.7
    assert "ai_classified" in result.matched


class BrokenAiClassifier:
    """Битый AI-классификатор, возвращающий мусор."""
    
    def classify(self, subject: str, body: str) -> dict:
        """Возвращает невалидный kind."""
        return {
            "kind": "garbage_category",
            "confidence": 0.9,
            "phone": None,
        }


def test_classify_reply_ai_invalid_kind_fallback():
    """AI с невалидным kind — откат к правилам."""
    body = "Пришлите информацию."
    
    ai = BrokenAiClassifier()
    result = classify_reply_ai("Re: Request", body, ai=ai)
    
    # Должны получить результат правил (interested)
    assert result.kind == "interested"
    assert "ai_classified" not in result.matched


class ExceptionAiClassifier:
    """AI-классификатор, выбрасывающий исключение."""
    
    def classify(self, subject: str, body: str) -> dict:
        """Выбрасывает исключение."""
        raise RuntimeError("AI service unavailable")


def test_classify_reply_ai_exception_fallback():
    """AI с исключением — откат к правилам."""
    body = "Интересует предложение"
    
    ai = ExceptionAiClassifier()
    result = classify_reply_ai("Re: Offer", body, ai=ai)
    
    # Получаем neutral (нет явных маркеров interested)
    assert result.kind in ("neutral", "interested")
    assert "ai_classified" not in result.matched


def test_classify_reply_ai_no_ai_provided():
    """Без AI получаем результат правил."""
    body = "Спасибо"
    
    result = classify_reply_ai("Re: Info", body, ai=None)
    
    assert result.kind == "neutral"
    assert "ai_classified" not in result.matched


class InvalidConfidenceAi:
    """AI с невалидным значением confidence."""
    
    def classify(self, subject: str, body: str) -> dict:
        """Возвращает невалидный confidence."""
        return {
            "kind": "hot",
            "confidence": 2.5,  # > 1.0
            "phone": None,
        }


def test_classify_reply_ai_invalid_confidence():
    """AI с невалидным confidence — используется дефолтное значение."""
    body = "Выставьте счёт"
    
    ai = InvalidConfidenceAi()
    result = classify_reply_ai("Re: Order", body, ai=ai)
    
    # kind должен быть применён, confidence скорректирован
    assert result.kind == "hot"
    # Проверяем, что confidence в допустимом диапазоне
    assert 0 <= result.confidence <= 1


# --- Интеграционные тесты ---


def test_full_hot_lead_with_all_fields():
    """Полный hot лид: телефон, контакт, маркеры."""
    body = """Выставьте счёт на оплату оборудования.
    
    Мой телефон для связи: +7 (912) 345-67-89
    
    С уважением,
    Петров Иван Сергеевич
    Главный инженер
    ООО "Техсервис"
    """
    
    result = classify_reply("Re: Заказ оборудования", body)
    
    assert result.kind == "hot"
    assert result.phone == "+79123456789"
    assert result.contact_hint is not None
    assert "Петров" in result.contact_hint or "инженер" in result.contact_hint
    assert result.confidence == 0.9


def test_priority_unsub_over_interested():
    """Приоритет отписки над interested."""
    body = "Пришлите подробности. Хотя нет, лучше отпишите меня."
    
    result = classify_reply("Re: Offer", body)
    
    # unsub проверяется раньше interested
    assert result.kind == "unsub_request"


def test_priority_auto_reply_over_hot():
    """Приоритет автоответа над hot."""
    body = "Выставьте счёт. Я в отпуске до понедельника."
    
    result = classify_reply("Re: Order", body)
    
    # auto_reply проверяется первым
    assert result.kind == "auto_reply"


def test_subject_included_in_classification():
    """Тема учитывается при классификации."""
    subject = "Выставьте счёт, пожалуйста"
    body = "Спасибо."
    
    result = classify_reply(subject, body)
    
    # Маркер в теме должен сработать
    assert result.kind == "hot"


def test_phone_normalization_various_formats():
    """Нормализация разных форматов телефона."""
    formats = [
        "8 (912) 345-67-89",
        "+7-912-345-67-89",
        "7 912 345 67 89",
        "8(912)345-67-89",
        "+7 912 345 67 89",
    ]
    
    for fmt in formats:
        phone = extract_phone(f"Звоните: {fmt}")
        assert phone == "+79123456789", f"Failed for format: {fmt}"


def test_edge_case_empty_inputs():
    """Граничный случай: пустые входы."""
    result = classify_reply("", "")
    
    assert result.kind == "neutral"
    assert result.phone is None
    assert result.contact_hint is None


def test_edge_case_very_long_body():
    """Граничный случай: очень длинное тело письма."""
    body = "Спасибо за предложение. " * 500  # ~12000 символов
    
    result = classify_reply("Re: Info", body)
    
    # Должно корректно обработаться
    assert result.kind == "neutral"


def test_yo_normalization():
    """Нормализация ё -> е при классификации."""
    body = "Выставьте счёт на оплату."
    
    result = classify_reply("Re: Заказ", body)
    
    assert result.kind == "hot"


def test_case_insensitive_markers():
    """Маркеры работают независимо от регистра."""
    body = "ВЫСТАВЬТЕ СЧЁТ"
    
    result = classify_reply("RE: ORDER", body)
    
    assert result.kind == "hot"
