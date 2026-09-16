"""
Django settings for the asset management system.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ('1', 'true', 'yes', 'on')


def _module_available(name):
    """模块是否可导入（用于可选依赖，如生产环境的 whitenoise）。"""
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# 部署安全配置（均可用环境变量覆盖，见 README「部署与安全」）
# SECRET_KEY：生产环境请通过 ASSETS_SECRET_KEY 设置一个随机值
SECRET_KEY = os.environ.get(
    'ASSETS_SECRET_KEY',
    'django-insecure-asset-management-system-secret-key-2024',
)

# 调试开关：默认关闭，避免错误页把源码与 SQL 暴露给局域网访问者；
# 本地排查问题时可用 ASSETS_DEBUG=1 临时打开
DEBUG = _env_bool('ASSETS_DEBUG', False)

# 允许访问的主机：默认放开（内网小团队），如需收紧用 ASSETS_ALLOWED_HOSTS 逗号分隔指定
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('ASSETS_ALLOWED_HOSTS', '*').split(',') if h.strip()
] or ['*']

# ---- 反向代理（Nginx/OpenResty/1Panel 网站）支持 ----
# 经过 HTTPS 反代访问时，Nginx 会带 X-Forwarded-Proto 头；
# 信任该头后 Django 才能正确识别 https，避免表单 CSRF 校验 403 与重定向到 http。
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# 跨域来源白名单：用域名（尤其 https）访问时按需设置，
# 例：ASSETS_CSRF_ORIGINS=https://assets.example.com（可逗号分隔多个）
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('ASSETS_CSRF_ORIGINS', '').split(',') if o.strip()
]

# 二维码扫码地址：留空则按「当前访问地址」生成（在本机用 localhost / 127.0.0.1
# 访问时，打出来的二维码就指向 127.0.0.1，手机扫了打不开）。
# 正式使用请固定成手机能访问的内网/公网地址，例：
#   ASSETS_PUBLIC_BASE_URL=http://192.168.1.50:12036
#   ASSETS_PUBLIC_BASE_URL=http://www.mdassetsmg.com
PUBLIC_BASE_URL = (os.environ.get('ASSETS_PUBLIC_BASE_URL') or '').strip().rstrip('/')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'assets',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise：生产环境（Docker/gunicorn）下由它提供静态文件；
    # 本机未安装 whitenoise 时自动跳过，行为不变
    *([] if not _module_available('whitenoise') else ['whitenoise.middleware.WhiteNoiseMiddleware']),
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 单设备登录：普通账号同一时间仅允许一台设备在线，超管不受限
    'assets.middleware.SingleDeviceMiddleware',
    # 自动备份：按设置（每 1/3/7 天 或 每次数据库变动）触发整库备份
    'assets.middleware.AutoBackupMiddleware',
]

ROOT_URLCONF = 'assets_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'assets.context_processors.messages_json',
                'assets.context_processors.device_type',
                'assets.context_processors.overdue_alert',
            ],
        },
    },
]

WSGI_APPLICATION = 'assets_system.wsgi.application'

# 登录相关
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
# 勾选“记住我”时通过 set_expiry 覆盖为长会话；未勾选则浏览器关闭即失效
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

# 数据库默认路径：项目根目录下的 data/db.sqlite3（与部署文档、Docker 挂载卷结构一致）
# 可通过环境变量 ASSETS_DB_PATH 覆盖（例如生成/使用独立的演示库，避免触碰真实库）
_DB_PATH = os.environ.get('ASSETS_DB_PATH', str(BASE_DIR / 'data' / 'db.sqlite3'))
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': _DB_PATH,
        # SQLite 并发加固：gunicorn 为多线程，写冲突时不再立刻抛
        # "database is locked"，而是最多等待 20 秒（配合 apps.py 里开启的 WAL）。
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

# 附件存放目录（发票/照片等），默认放在 data/ 下，与数据库同在挂载卷内，
# 重建容器不丢；可用 ASSETS_MEDIA_ROOT 覆盖。
MEDIA_ROOT = Path(os.environ.get('ASSETS_MEDIA_ROOT', str(BASE_DIR / 'data' / 'media')))
MEDIA_URL = '/media/'

# 缓存后端：
# - 默认 LocMemCache（单进程够用，适合本机 runserver / 单 worker 部署）
# - 设置 ASSETS_REDIS_URL（如 redis://redis:6379/0）后切换为 Redis，
#   多 worker / 多实例部署时登录锁定等跨进程状态才能共享
#
# 这里缓存的不只是登录锁定计数，还有资产二维码图片（按内容缓存，见 views.asset_qr）。
# LocMemCache 默认 MAX_ENTRIES=300，资产上千条时会把二维码缓存挤掉、
# 甚至把登录锁定计数挤掉，所以显式放大（每条约几 KB）。
if os.environ.get('ASSETS_REDIS_URL'):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': os.environ['ASSETS_REDIS_URL'],
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'OPTIONS': {'MAX_ENTRIES': 2000},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# collectstatic 输出目录（生产部署用；配合 WhiteNoise 提供静态文件）
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---- 运行日志：控制台 + 按大小轮转的文件 ----
# 容器/终端日志被清理后仍可回溯（文件默认落在 data/logs/app.log，随数据卷一起持久化）
LOGS_DIR = Path(os.environ.get('ASSETS_LOG_DIR', str(BASE_DIR / 'data' / 'logs')))
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_LEVEL = (os.environ.get('ASSETS_LOG_LEVEL') or 'INFO').upper()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'app.log'),
            'maxBytes': 5 * 1024 * 1024,   # 单文件 5MB
            'backupCount': 5,              # 最多保留 5 个历史文件
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console', 'file'], 'level': LOG_LEVEL},
    'loggers': {
        'django.request': {'handlers': ['console', 'file'], 'level': 'WARNING', 'propagate': False},
        'django.security': {'handlers': ['console', 'file'], 'level': 'WARNING', 'propagate': False},
    },
}
