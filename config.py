import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    SQLALCHEMY_DATABASE_URI = 'sqlite:///findjob.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY') or 'findjob-default-encryption-key-change-me'
    
    # Platform URLs
    PLATFORMS = {
        'boss': {
            'name': 'Boss直聘',
            'url': 'https://www.zhipin.com',
            'login_url': 'https://www.zhipin.com/web/user/?ka=header-login',
            'message_url': 'https://www.zhipin.com/web/geek/chat',
            'icon': '👔',
            'color': '#00beab'
        },
        'zhilian': {
            'name': '智联招聘',
            'url': 'https://www.zhaopin.com',
            'login_url': 'https://passport.zhaopin.com/login',
            'message_url': 'https://www.zhaopin.com/inbox',
            'icon': '🌐',
            'color': '#1e88e5'
        },
        'qiancheng': {
            'name': '前程无忧',
            'url': 'https://www.51job.com',
            'login_url': 'https://login.51job.com/login.php',
            'message_url': 'https://my.51job.com/myspace/corp_msg.php',
            'icon': '📋',
            'color': '#ff6b00'
        },
        'tongcheng': {
            'name': '58同城',
            'url': 'https://www.58.com',
            'login_url': 'https://passport.58.com/login',
            'message_url': 'https://user.58.com/message',
            'icon': '🏙️',
            'color': '#e64a19'
        },
        'yupao': {
            'name': '鱼泡直聘',
            'url': 'https://www.yupao.com',
            'login_url': 'https://www.yupao.com/login',
            'message_url': 'https://www.yupao.com/message',
            'icon': '🐟',
            'color': '#2196f3'
        },
        'liepin': {
            'name': '猎聘',
            'url': 'https://www.liepin.com',
            'login_url': 'https://passport.liepin.com/login',
            'message_url': 'https://www.liepin.com/message/',
            'icon': '🎯',
            'color': '#0d47a1'
        }
    }