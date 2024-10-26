import json
import logging
import os
import sys
import time
from logging import StreamHandler

import requests
from dotenv import load_dotenv
from http import HTTPStatus
from telebot import TeleBot

from exceptions import (StatusCodeException, StatusError)

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

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    filemode='w',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(__file__ + '.log')
    ]
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(lineno)d, %(funcName)s, %(asctime)s, %(levelname)s, %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    env = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    if not all(env):
        logging.critical('Отсутствует переменная окружения')
    return all(env)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.debug(f'Начало отправки сообщения в Telegram: {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Удачная отправка сообщения в Telegram: {message}')
        return True
    except Exception as error:
        logging.exception(f'Сообщение {message} не отправлено {error}')
        return False


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
        raise StatusCodeException(
            f'Недоступность ендпоинта домашней работы: {error}\n'
            f'Request parameters: {request_params}'
        )
    except json.JSONDecodeError as error:
        logger.error(
            f'Ответ от API адреса не преобразован в json(): {error}.'
        )
    logger.debug(
        'Отправка запроса к API {url};\nзаголовки: {headers};\n'
        'параметры {params}'.format(**request_params)
    )
    if response.status_code != HTTPStatus.OK:
        raise StatusCodeException(
            f'HTTP response code {response.status_code} отличный от 200\n'
            f'Request parameters: {request_params}'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не соответстыует типу "dict"')
    if 'homeworks' not in response:
        raise KeyError('Отсутствует ключ homeworks в ответе')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            'В Ответе API под ключом "homeworks" получен не тип "list"'
        )
    return homeworks


UPDATE_STATUS = (
    'Изменился статус проверки работы "{}".\n'
    '{}'
)


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('No "homework_name" at homework keys.')
    if 'status' not in homework:
        raise KeyError('No "status" at homework keys.')
    name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise StatusError(f'Неожиданный статус домашней работы: {status}')
    return (
        UPDATE_STATUS.format(name, HOMEWORK_VERDICTS[status])
    )


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise SystemExit('Отсутствует один из токенов')
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    old_status = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date', timestamp)
            homeworks = check_response(response)
            if homeworks:
                new_status = parse_status(homeworks[0])
                if new_status != old_status:
                    send_message(bot, new_status) is True
                    old_status = new_status
                else:
                    logger.error('Отсутствие в ответе новых статусов')
        except Exception as error:
            new_status = f'Сбой в работе программы: {error}.'
            logger.error(new_status)
            if new_status != old_status:
                send_message(bot, new_status) is True
                old_status = new_status
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
