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
    resumes = db.relationship('Resume', backref='user', lazy=True, cascade='all, delete-orphan')
    deliveries = db.relationship('Delivery', backref='user', lazy=True, cascade='all, delete-orphan')

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
    external_id = db.Column(db.String(200), nullable=True, index=True)
    external_url = db.Column(db.String(500), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('ix_messages_user_platform_ext', 'user_id', 'platform', 'external_id'),
    )


class Resume(db.Model):
    """
    A user's résumé / greeting template used when delivering to jobs.
    Stored in plain text (not encrypted) because the user edits it via UI.
    """
    __tablename__ = 'resumes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)                  # 简历名称
    title = db.Column(db.String(200), nullable=True)                  # 期望职位
    years_exp = db.Column(db.Integer, nullable=True)                  # 工作年限
    education = db.Column(db.String(50), nullable=True)               # 学历
    expected_salary = db.Column(db.String(100), nullable=True)        # 期望薪资
    expected_city = db.Column(db.String(100), nullable=True)          # 期望城市
    skills = db.Column(db.Text, nullable=True)                        # 技能标签 (comma-separated)
    summary = db.Column(db.Text, nullable=True)                       # 自我介绍/简介
    greeting = db.Column(db.Text, nullable=True)                      # 投递打招呼语
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deliveries = db.relationship('Delivery', backref='resume', lazy=True)


class JobPost(db.Model):
    """
    A job listing scraped from a platform. Cached so we can show it in the UI
    and link deliveries to it. Unique by (platform, external_id).
    """
    __tablename__ = 'job_posts'

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(50), nullable=False, index=True)
    external_id = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(300), nullable=True)
    company = db.Column(db.String(200), nullable=True)
    salary_range = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    experience = db.Column(db.String(100), nullable=True)
    education = db.Column(db.String(100), nullable=True)
    tags = db.Column(db.Text, nullable=True)          # comma-separated
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(500), nullable=True)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('platform', 'external_id', name='uq_jobpost_platform_extid'),)


class Delivery(db.Model):
    """A resume delivery record. One row per job the user submits to."""
    __tablename__ = 'deliveries'

    # Canonical statuses. Kept as strings for portability.
    STATUS_PENDING = 'pending'
    STATUS_SENDING = 'sending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_REPLIED = 'replied'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), nullable=True)
    job_post_id = db.Column(db.Integer, db.ForeignKey('job_posts.id'), nullable=True)
    platform = db.Column(db.String(50), nullable=False)
    job_title = db.Column(db.String(300), nullable=True)
    company = db.Column(db.String(200), nullable=True)
    salary_range = db.Column(db.String(100), nullable=True)
    greeting_sent = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)
    error_message = db.Column(db.Text, nullable=True)
    external_url = db.Column(db.String(500), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    job_post = db.relationship('JobPost', lazy=True)


class Cipher:
    """Simple encryption helper using Fernet symmetric encryption."""
    
    def __init__(self, secret_key: str):
        key = hashlib.sha256(secret_key.encode()).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key))
    
    def encrypt(self, text: str) -> str:
        return self.fernet.encrypt(text.encode()).decode()
    
    def decrypt(self, token: str) -> str:
        return self.fernet.decrypt(token.encode()).decode()