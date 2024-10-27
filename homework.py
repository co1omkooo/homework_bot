import logging
import os
import sys
import time

from dotenv import load_dotenv
from http import HTTPStatus
import requests
from telebot import TeleBot

from exceptions import StatusCodeException

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


def check_tokens():
    """Проверяет доступность переменных окружения."""
    for key in (PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ENDPOINT):
        if not key:
            logging.critical(f'Переменная окружения: {key} отсутствует')
            return False
    return True


START_OF_SENDING = 'Начало отправки сообщения в Telegram: {}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.debug(START_OF_SENDING.format(message))
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Удачная отправка сообщения в Telegram: {message}')
        return True
    except Exception as error:
        logging.exception(f'Сообщение {message} не отправлено {error}')
        return False


SANDING_REQUEST = (
    'Отправка запроса к API {url};\nзаголовки: {headers};\n'
    'параметры {params}'
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
        raise Exception(
            f'Недоступность ендпоинта домашней работы: {error}\n'
            f'Request parameters: {request_params}'
        )
    logger.debug(SANDING_REQUEST.format(**request_params))
    if response.status_code != HTTPStatus.OK:
        raise StatusCodeException(
            f'HTTP response code {response.status_code}\n'
            f'Request parameters: {request_params}'
        )
    for key in ['code', 'error']:
        if key in response.json():
            raise KeyError(f'Request parameters: {request_params}')
    return response.json()


WRONG_DATA_TYPE = 'Тип данных {} не соответстыует типу "dict"'
NO_KEY = 'Отсутствует ключ homeworks в ответе'
TYPE_LIST = 'Тип данных {} под ключом "homeworks" получен не тип "list"'


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(WRONG_DATA_TYPE.format(type))
    if 'homeworks' not in response:
        raise KeyError(NO_KEY)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(TYPE_LIST.format(type))
    return homeworks


UPDATE_STATUS = (
    'Изменился статус проверки работы "{}".\n'
    '{}'
)
KEY_ERROR_NAME = 'No "homework_name" at homework keys.'
KEY_ERROR_STATUS = 'No "status" at homework keys.'


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError(KEY_ERROR_NAME)
    if 'status' not in homework:
        raise KeyError(KEY_ERROR_STATUS)
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданный статус домашней работы: {status}')
    return UPDATE_STATUS.format(
        homework['homework_name'], HOMEWORK_VERDICTS[status]
    )


NO_NEW_STATUS = 'Отсутствие в ответе новых статусов'
FAILURE = 'Сбой в работе программы: {}.'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_status = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                new_status = parse_status(homeworks[0])
                if new_status != old_status:
                    if send_message(bot, new_status) is True:
                        old_status = new_status
                else:
                    logger.error(NO_NEW_STATUS)
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            new_status = FAILURE.format(error)
            logger.error(new_status)
            if new_status != old_status:
                if send_message(bot, new_status) is True:
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
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    main()
