import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
	# создание секретного ключа
	SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

	# конфигурация подключения к БД
	SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'app.db')
	SQLALCHEMY_TRACK_MODIFICATIONS = False

	# количество постов на странице
	POSTS_PER_PAGE = 3

	# конфигурация babel
	LANGUAGES = ['en', 'ru']

	# поиск текста на станицах
	#ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL')
	ELASTICSEARCH_URL = 'http://localhost:9200'

	# конфигурация отправки электронной почты
	MAIL_SERVER = os.environ.get('MAIL_SERVER')
	MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
	MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
	MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
	MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
	ADMINS = ['admin@domain.com']
