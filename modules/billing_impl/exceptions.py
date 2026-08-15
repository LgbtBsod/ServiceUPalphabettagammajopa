"""Исключения модуля Billing

Эти исключения автоматически загружаются в ModuleBase.ModuleError
при инициализации модуля.
"""


class BillingError(Exception):
    """Базовое исключение для ошибок биллинга"""


class PaymentError(BillingError):
    """Ошибка при обработке платежа"""


class InvoiceError(BillingError):
    """Ошибка при создании счета"""


class SubscriptionError(BillingError):
    """Ошибка подписки"""


__all__ = ["BillingError", "InvoiceError", "PaymentError", "SubscriptionError"]
