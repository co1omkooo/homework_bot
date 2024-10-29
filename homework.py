import logging
import os
import sys
import time
from http import HTTPStatus

from dotenv import load_dotenv
import requests
from telebot import TeleBot

from exceptions import StatusCodeException, DenialOfService

load_dotenv()

PRACTICUM_TOKEN = os.getenv('YP_TOKEN')
TELEGRAM_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)

NO_TOKEN = (
    'Программа принудительно остановлена. '
    'Отсутствует обязательная переменная окружения: {}'
)
tokens_name = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = True
    for name in tokens_name:
        if globals()[name] is None:
            tokens = False
            logging.critical(NO_TOKEN.format('name'))
        return tokens


START_OF_SENDING = 'Начало отправки сообщения в Telegram: {}'
SUCCESSFUL_SENDING = 'Удачная отправка сообщения в Telegram: {}'
MSG_NO_SEND = 'Сообщение {} не отправлено {}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.debug(START_OF_SENDING.format(message))
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(SUCCESSFUL_SENDING.format(message))
        return True
    except Exception as error:
        logging.exception(MSG_NO_SEND.format(message, error))
        return False


SANDING_REQUEST = (
    'Отправка запроса к API {url};\nзаголовки: {headers};\n'
    'параметры {params}'
)
UNAVAILABLE_ENDPOINT = (
    'Недоступность ендпоинта домашней работы: {}\n'
    'Request parameters: {}'
)
STATUS_CODE = (
    'HTTP response code {}\n'
    'Request parameters: {}'
)
DENIAL_SERVICE = (
    'Отказ от обслуживания - {}: {}\n'
    'Request parameters: {}'
)


def get_api_answer(timestamp):
    """
    Возвращает статус API сервиса.

        Параметры:
            timestamp (int): время в сек.
        Возвращаемое значение (str): статус сервиса.
    """
    request_params = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )
    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            UNAVAILABLE_ENDPOINT.format(error, request_params)
        )
    logger.debug(SANDING_REQUEST.format(**request_params))
    if response.status_code != HTTPStatus.OK:
        raise StatusCodeException(
            STATUS_CODE.format(response.status_code, request_params)
        )
    response_json = response.json()
    for key in ['code', 'error']:
        if key in response_json:
            raise DenialOfService(
                DENIAL_SERVICE.format(key, response[key], request_params)
            )
    return response_json


TYPE_DICT = 'Тип данных {} не соответстыует типу "dict"'
NO_KEY_HOMEWORKS = 'Отсутствует ключ homeworks в ответе'
TYPE_LIST = 'Тип данных {} под ключом "homeworks" получен не тип "list"'


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(TYPE_DICT.format(type(response)))
    if 'homeworks' not in response:
        raise KeyError(NO_KEY_HOMEWORKS)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(TYPE_LIST.format(type(homeworks)))
    return homeworks


UPDATE_STATUS = (
    'Изменился статус проверки работы "{}".\n'
    '{}'
)
KEY_ERROR_NAME = 'No "homework_name" at homework keys.'
KEY_ERROR_STATUS = 'No "status" at homework keys.'
VALUE_ERROR_STATUS = 'Неожиданный статус домашней работы: {}'


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(KEY_ERROR_NAME)
    if 'status' not in homework:
        raise KeyError(KEY_ERROR_STATUS)
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(VALUE_ERROR_STATUS.format(status))
    return UPDATE_STATUS.format(
        homework['homework_name'], HOMEWORK_VERDICTS[status]
    )


NO_NEW_STATUS = 'Отсутствие в ответе новых статусов'
FAILURE = 'Сбой в работе программы: {}.'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_status = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                new_status = parse_status(homeworks[0])
                if new_status != old_status and send_message(bot, new_status):
                    old_status = new_status
                    timestamp = response.get('current_date', timestamp)
                else:
                    logger.error(NO_NEW_STATUS)
        except Exception as error:
            new_status = FAILURE.format(error)
            logger.error(new_status)
            if new_status != old_status and send_message(bot, new_status):
                old_status = new_status
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            '%(lineno)d, %(funcName)s, %(asctime)s, %(levelname)s, %(message)s'
        ),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f'{__file__}.log')
        ]
    )
    main()
