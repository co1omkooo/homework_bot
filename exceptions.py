class StatusCodeException(Exception):
    """Получен HTTP response code отличный от 200."""


class DenialOfService(Exception):
    """Отказ от обслуживания."""
