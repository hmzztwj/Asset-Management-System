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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # 默认使用项目根目录的 db.sqlite3；
        # 可通过环境变量 ASSETS_DB_PATH 覆盖（例如生成/使用独立的演示库，避免触碰真实库）
        'NAME': os.environ.get('ASSETS_DB_PATH', str(BASE_DIR / 'db.sqlite3')),
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
