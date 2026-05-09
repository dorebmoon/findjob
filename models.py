from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import hashlib

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    credentials = db.relationship('PlatformCredential', backref='user', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='user', lazy=True, cascade='all, delete-orphan')

class PlatformCredential(db.Model):
    __tablename__ = 'platform_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False)  # boss, zhilian, etc.
    # Fernet ciphertext has no fixed upper bound; use Text to avoid truncation.
    username = db.Column(db.Text, nullable=False)  # encrypted
    password = db.Column(db.Text, nullable=False)  # encrypted
    cookie_data = db.Column(db.Text, nullable=True)  # encrypted JSON
    is_logged_in = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime, nullable=True)
    last_check = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'platform'),)


class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    sender_name = db.Column(db.String(200), nullable=True)
    sender_company = db.Column(db.String(200), nullable=True)
    sender_title = db.Column(db.String(200), nullable=True)
    content = db.Column(db.Text, nullable=True)
    job_title = db.Column(db.String(500), nullable=True)
    salary_range = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    message_type = db.Column(db.String(50), default='chat')  # chat, invite, system
    external_id = db.Column(db.String(200), nullable=True)
    external_url = db.Column(db.String(500), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Cipher:
    """Simple encryption helper using Fernet symmetric encryption."""
    
    def __init__(self, secret_key: str):
        key = hashlib.sha256(secret_key.encode()).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key))
    
    def encrypt(self, text: str) -> str:
        return self.fernet.encrypt(text.encode()).decode()
    
    def decrypt(self, token: str) -> str:
        return self.fernet.decrypt(token.encode()).decode()