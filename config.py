from datetime import timedelta
import os

class Config:
    # Basic Configuration
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'
    TESTING = False
    
    # Security Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32)
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SESSION_COOKIE_SECURE = os.environ.get('PRODUCTION', 'False') == 'True'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # MySQL Database Configuration
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '752002')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'City_Star_Supermarket')
