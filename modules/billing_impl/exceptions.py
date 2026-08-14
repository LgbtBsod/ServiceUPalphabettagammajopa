"""
Исключения модуля Billing

Эти исключения автоматически загружаются в ModuleBase.ModuleError
при инициализации модуля.
"""


class BillingError(Exception):
    """Базовое исключение для ошибок биллинга"""
    pass


class PaymentError(BillingError):
    """Ошибка при обработке платежа"""
    pass


class InvoiceError(BillingError):
    """Ошибка при создании счета"""
    pass


class SubscriptionError(BillingError):
    """Ошибка подписки"""
    pass


__all__ = ["BillingError", "PaymentError", "InvoiceError", "SubscriptionError"]
