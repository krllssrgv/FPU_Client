# This Python file uses the following encoding: utf-8
import os
import sys

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, upgrade, init, migrate
from flask_login import LoginManager, login_user, UserMixin, current_user, logout_user
from flask_cors import CORS
from flask_restx import Api, Resource, Namespace, fields

import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from data import Data
from apscheduler.schedulers.background import BackgroundScheduler



# App
app = Flask(__name__)
app.config['SECRET_KEY'] = '8f42a73054b1749f8f58848be5e6502c'
CORS(app)


# API
api = Api(app)
user_api = Namespace('user')


# Login
login_manager = LoginManager(app)
login_manager.login_view = 'log'


# DataBase
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)

@app.cli.command("init-db")
def init_db():
    init()
    migrate()
    upgrade()


class users(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(80), nullable=False)
    password = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(40), nullable=False)
    surname = db.Column(db.String(40), nullable=False)
    
    current_week = db.Column(db.Integer, nullable=False, default=0)
    day_one = db.Column(db.Boolean, nullable=False, default=False)
    day_two = db.Column(db.Boolean, nullable=False, default=False)
    day_three = db.Column(db.Boolean, nullable=False, default=False)
    success = db.Column(db.String(2), nullable=False, default='')

    def __repr__(self):
        return '<users %r>' % self.id



@login_manager.user_loader
def load_user(user_id):
    return db.session.get(users, user_id)



# Models
user_login_model = user_api.model('user_login', {
    'email': fields.String(required=True, description='Email'),
    'password': fields.String(required=True, description='Password')
})



# API
@user_api.route('/api/user/register')
class Register(Resource):
    def post(self):
        if (not current_user.is_authenticated):
            data = request.json
            check = True
            result = {}

            if (users.query.filter(users.email == data['email']).all()):
                check = False
                result['email'] = 'Пользователь уже существует'

            if (len(data['password']) < 6):
                check = False
                result['password'] = 'Минимальная длина 6 символов'

            if (data['password'] != data['repeatedPassword']):
                check = False
                result['repeatedPassword'] = 'Пароли не совпадают'

            if check:
                new_user = users(
                    email=data['email'],
                    password=generate_password_hash(data['password']),
                    name=data['name'],
                    surname=data['surname']
                )
                try:
                    db.session.add(new_user)
                    db.session.commit()
                    return '', 204
                except:
                    return '', 500
            else:
                return jsonify(result), 400

        else:
            return '', 400


@user_api.route('/api/user/login')
class Login(Resource):
    @user_api.expect(user_login_model)
    def post(self):
        if (not current_user.is_authenticated):
            data = request.json
            user = users.query.filter_by(email=data['email']).first()

            if user:
                if check_password_hash(user.password, data['password']):
                    login_user(user)
                    return '', 204
                else:
                    return jsonify({'password': 'Неправильный пароль'}), 401
            else:
                return jsonify({'email': 'Нет такого пользователя'}), 401
            
        else:
            return '', 400


@user_api.route('/api/user/logout')
class Logout(Resource):
    def post(self):
        logout_user()
        return '', 204


@user_api.route('/api/user/acts')
class Acts(Resource):
    def get(self):
        if (current_user.is_authenticated):
            user = db.session.get(users, int(current_user.get_id()))
            user_data = Data.get_week(user.current_week)
            days = [
                {
                    'number': 1,
                    'done': user.day_one,
                    'acts': user_data[1]
                },
                {
                    'number': 2,
                    'done': user.day_two,
                    'acts': user_data[2]
                },
                {
                    'number': 3,
                    'done': user.day_three,
                    'acts': user_data[3]
                }
            ]

            return jsonify({
                'name': user.name,
                'progress': int((round(user.current_week / 13, 2)) * 100),
                'success': user.success,
                'current_week': user.current_week,
                'types': user_data[0],
                'days': days
            })
        else:
            return '', 401


@user_api.route('/api/user/set_day_as_done')
class Day(Resource):
    def post(self):
        if (current_user.is_authenticated):
            data = request.json
            user = db.session.get(users, int(current_user.get_id()))
            if (user):
                if ('set_day' in data):
                    if (data['set_day'] == 1):
                        user.day_one = True
                        if (user.day_two and user.day_three):
                            user.success = '0'

                    elif (data['set_day'] == 2):
                        user.day_two = True
                        if (user.day_one and user.day_three):
                            user.success = '0'

                    elif (data['set_day'] == 3):
                        user.day_three = True
                        if (user.day_one and user.day_two):
                            user.success = '0'

                    try:
                        db.session.commit()
                        return '', 200
                    except:
                        return '', 500
                else:
                    return '', 400
            
        else:
            return '', 401


@user_api.route('/api/user/send_result')
class Result(Resource):
    def post(self):
        if (current_user.is_authenticated):
            data = request.json
            user = db.session.get(users, int(current_user.get_id()))
            if (user):
                if ('success' in data):
                    if (data['success']):
                        user.success = '1'
                    else:
                        user.success = '-1'
                    
                    try:
                        db.session.commit()
                        return jsonify({'success': user.success}), 200
                    except:
                        return '', 500
                    
                else:
                    return '', 400

            else:
                return '', 401
        else:
            return '', 401



# BackgroundScheduler
def update_weeks():
    with app.app_context():
        all_users = users.query.all()
        for user in all_users:
            user.day_one = False
            user.day_two = False
            user.day_three = False

            if (user.success == '1'):
                user.current_week += 1

            user.success = ''
        db.session.commit()

scheduler = BackgroundScheduler()
scheduler.add_job(update_weeks, 'cron', day_of_week='wed', hour=19, minute=15)
scheduler.start()



api.add_namespace(user_api)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
