from hashlib import md5  # либа для работы с сервисом gravatar
import jwt  # либа для создания токенов (сброс пароля)
from time import time
import json
from flask import current_app
from app import db, login
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.search import add_to_index, remove_from_index, query_index



@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class SearchableMixin(object):
    @classmethod
    def search(cls, expression, page, per_page):
        ids, total = query_index(cls.__tablename__, expression, page, per_page)
        if total == 0:
            return cls.query.filter_by(id=0), 0
        when = []
        for i in range(len(ids)):
            when.append((ids[i], i))
        return cls.query.filter(cls.id.in_(ids)).order_by(
            db.case(when, value=cls.id)), total

    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted)
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in cls.query:
            add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)

# Вспомогательная таблица для связи many-to-many User--User
followers = db.Table('followers',
                     db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),  # кто подписан
                     db.Column('followed_id', db.Integer, db.ForeignKey('user.id')))  # на кого подписан


class User(UserMixin, db.Model):  # add Mixin(flask-login)
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(64), index=True, unique=True)
    # поле заполняется из функции set_password
    password_hash = db.Column(db.String(128))
    about_me = db.Column(db.String(140))
    # время последнего логирования
    last_seen = db.Column(db.DateTime)
    # последний вход на страницу сообщений (необходимо для определения непрочитаных сообщений)
    last_message_read_time = db.Column(db.DateTime)

    # связь многие ко многими (в массиве будет храниться на кого подписан пользователь)
    followed = db.relationship(
        # User - таблица с которой делаем связь, secondary это название доп. таблицы связи
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic'
    )

    posts = db.relationship('Post', backref='author', lazy='dynamic')

    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='author', lazy='dynamic')

    messages_received = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient',
                                        lazy='dynamic')

    notifications = db.relationship('Notification', backref='user', lazy='dynamic')

    def new_messages(self):
        # вернет количество неппрочитаных сообщений
        last_read_time = self.last_message_read_time or datetime(1900, 1, 1)
        return Message.query.filter_by(recipient=self).filter(Message.timestamp > last_read_time).count()

    def add_notification(self, name, data):
        # добавление уведомления в базу
        # если имя то-же, то удалить
        self.notifications.filter_by(name=name).delete()
        notific = Notification(name=name, payload_json=json.dumps(data), user=self)
        db.session.add(notific)
        return notific


    def follow(self, user):
        if not self.is_following(user):
            # если пользователь не подписан на юзера то добавляем его в массив (на кого подписан пользователь)
            self.followed.append(user)

    def unfollow(self, user):
        # если подписан на юзера то удаляем его из массива на кого подписан пользователь
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        # проверка подписан ли залогированный пользователь на юзера. Если да то 1 если нет то 0
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def followed_posts(self):
        # запрос к БД для получения постов на которые подписан залог. пользователь
        # join временное слияние таблиц
        # условие объединений( на кого подписаны все с их постами,
        # за которыми следят разные пользователи)
        # filter выборка тех постов на которые подписан залог пользователь
        followed = Post.query.join(followers, (followers.c.followed_id == Post.user_id)) \
            .filter(followers.c.follower_id == self.id)
        # поиск постов которые принадлежат залог пользователю
        own = Post.query.filter_by(user_id=self.id)
        # совмещаем посты на которые подписан и собственные, сортируем по времени
        return followed.union(own).order_by(Post.timestamp.desc())

    def set_password(self, password):
        # метод создания пароля и записи хеша в таблице
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # метод сравнения пароля с значением в хеше (True/False)
        return check_password_hash(self.password_hash, password)

    def get_avatar(self, size):
        # временная логика для генерации аватаров загруженных на gravatar.com
        # grabatar позволяет к каждому email прикрепить фото
        # берем email из таблицы
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')

    @staticmethod  # статический метод
    def verify_reset_password_token(token):
        # проверка токена на подлинность
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])['rest_password']
        except:
            return
        return User.query.get(id)

    def __repr__(self):
        return f'<User {self.username}>'


class Post(SearchableMixin, db.Model):
    # метка для индексации поиском
    __searchable__ = ['body']
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return f'<Post {self.body}>'


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message {self.body}>'


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), index=True)
    timestamp = db.Column(db.Float, index=True, default=time)
    payload_json = db.Column(db.Text)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def get_data(self):
        return json.loads(str(self.payload_json))