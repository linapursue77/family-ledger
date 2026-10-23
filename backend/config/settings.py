# -*- coding: utf-8 -*-
"""钱来钱往记账 · 后端配置

设计对齐 TestHub：
- DRF + SimpleJWT 认证（双 Token + 刷新轮换 + 黑名单）
- 统一响应由 apps.core.response 接管（TestHub 缺失项，本项目补齐）
- Redis 三库分离：cache=1 / session=2 / queue=0
- Django-Q2 作为任务队列与定时任务
- 开发期开箱即用（SQLite），生产切 MySQL
"""
import logging
import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

# PyMySQL 作为 MySQLdb 驱动（必须在任何数据库后端加载前注册）
try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:  # pragma: no cover - 未安装时回退 mysqlclient
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- 基础
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-only-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 三方
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',
    'corsheaders',
    'django_q',
    # 自研
    'apps.core',
    'apps.users',
    'apps.families',
    'apps.accounts',
    'apps.ledger',
    'apps.loans',
    'apps.membership',
    # 管理后台接口（仅 is_staff）
    'apps.console',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # 自研
    'config.middleware.TraceIdMiddleware',
    'config.middleware.RequestTimingMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

AUTH_USER_MODEL = 'users.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------- 数据库
_DB_HOST = config('DB_HOST', default='')

if _DB_HOST:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME', default='family_ledger'),
            'USER': config('DB_USER', default='root'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': _DB_HOST,
            'PORT': config('DB_PORT', default='3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES', time_zone='+08:00'",
            },
            # ASGI 异步环境下必须关闭长连接，避免连接泄漏
            'CONN_MAX_AGE': 0,
            'ATOMIC_REQUESTS': True,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                # SQLite 同一时刻只允许一个写者。qcluster 的 worker 与 web 进程
                # 并发写时会直接抛 "database is locked"，定时任务因此失败。
                #   timeout          —— 抢不到锁时等待而不是立刻报错
                #   WAL              —— 读写不互相阻塞，大幅减少锁冲突
                #   IMMEDIATE 事务   —— 一开始就拿写锁，避免「读事务升级写事务」死等
                'timeout': 30,
                'init_command': 'PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;',
                'transaction_mode': 'IMMEDIATE',
            },
        }
    }

# ---------------------------------------------------------------- Redis
REDIS_HOST = config('REDIS_HOST', default='127.0.0.1')
REDIS_PORT = config('REDIS_PORT', default='6379')
REDIS_PASSWORD = config('REDIS_PASSWORD', default='')

# ---------------------------------------------------------------- DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.ApiPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # TestHub 缺失项：统一异常 → 统一响应
    'EXCEPTION_HANDLER': 'apps.core.response.api_exception_handler',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '2000/hour',
        'record': '120/min',      # 记账
        'import': '10/min',       # 账单导入
        'report': '30/hour',      # 报告生成
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ---------------------------------------------------------------- 缓存
if REDIS_HOST and not DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/1',
            'KEY_PREFIX': 'fl',
            'TIMEOUT': 300,
        },
        'sessions': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/2',
            'KEY_PREFIX': 'fl_sess',
            'TIMEOUT': 604800,
        },
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'family-ledger-default',
            'KEY_PREFIX': 'fl',
            'TIMEOUT': 300,
        },
        'sessions': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'family-ledger-sessions',
            'KEY_PREFIX': 'fl_sess',
            'TIMEOUT': 604800,
        },
    }

# ---------------------------------------------------------------- Django-Q2 任务队列
Q_CLUSTER = {
    'name': 'family-ledger',
    # SQLite 只支持单写者，多 worker 并发写必然撞锁 —— 本地默认 1 个 worker 串行跑；
    # 生产（MySQL）默认 2 个，也可用 Q_WORKERS 覆盖。
    'workers': int(os.environ.get('Q_WORKERS', '1' if not _DB_HOST else '2')),
    'timeout': 300,
    'retry': 600,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',
    'save_limit': 250,
    'label': '任务管理',
    'redis': {
        'host': REDIS_HOST,
        'port': int(REDIS_PORT),
        'db': 0,
        'password': REDIS_PASSWORD or None,
        'socket_connect_timeout': 5,
        'socket_timeout': 10,
    },
    'sync': False,
}

# ---------------------------------------------------------------- API 文档
SPECTACULAR_SETTINGS = {
    'TITLE': '钱来钱往记账 API',
    'DESCRIPTION': '钱来钱往记账 · 后端接口文档',
    'VERSION': '0.1.0 (MVP)',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': r'/api/v1',
}

# ---------------------------------------------------------------- 短信验证码（找回密码）
# 国内短信服务要求「企业主体 + 签名/模板报备」，个人主体办不了。
# 所以默认 provider=console：验证码只写日志、不真发短信，但整条找回密码流程
# 能完整跑通（从后端日志里抄验证码即可），零成本、零依赖。
# 有企业资质后：配 SMS_PROVIDER=aliyun|tencent + 密钥 + 签名 + 模板，代码无需改动。
SMS_PROVIDER = config('SMS_PROVIDER', default='console')
SMS_ACCESS_KEY = config('SMS_ACCESS_KEY', default='')
SMS_ACCESS_SECRET = config('SMS_ACCESS_SECRET', default='')
SMS_APP_ID = config('SMS_APP_ID', default='')          # 腾讯云专用 SDKAppID
SMS_SIGN_NAME = config('SMS_SIGN_NAME', default='')    # 短信签名，如「钱来钱往」
SMS_TEMPLATE_RESET = config('SMS_TEMPLATE_RESET', default='')   # 重置密码模板
SMS_TEMPLATE_BIND = config('SMS_TEMPLATE_BIND', default='')     # 绑定手机号模板
SMS_CODE_LENGTH = config('SMS_CODE_LENGTH', default=6, cast=int)
SMS_CODE_TTL = config('SMS_CODE_TTL', default=300, cast=int)          # 验证码有效期(秒)
SMS_SEND_INTERVAL = config('SMS_SEND_INTERVAL', default=60, cast=int)  # 重发间隔(秒)
SMS_MAX_TRIES = config('SMS_MAX_TRIES', default=5, cast=int)           # 最多校验几次
SMS_DAILY_LIMIT_PER_PHONE = config('SMS_DAILY_LIMIT_PER_PHONE', default=10, cast=int)
SMS_DAILY_LIMIT_PER_IP = config('SMS_DAILY_LIMIT_PER_IP', default=30, cast=int)

# ---------------------------------------------------------------- 会员权益闸门
# False（当前）：付费权益对所有人开放，先把功能用起来攒用户粘性；
# 判权代码原样保留，等要开始收费时把这里改成 True（或配环境变量 VIP_GATED=True）
# 即可恢复「非会员受限」，不需要再改任何业务接口。
VIP_GATED = config('VIP_GATED', default=False, cast=bool)

# ---------------------------------------------------------------- 微信支付
# 会员开通 / 续费走微信支付 v3：微信内 JSAPI 支付（公众号 / 小程序），
# 微信外浏览器走 H5 支付（mweb_url 跳转）。
#
# 开关关掉时（默认）下单接口只在 DEBUG 下走「直接开通」的联调模式，
# 正式环境会直接报错，避免忘记配置就白送会员。
WXPAY_ENABLED = config('WXPAY_ENABLED', default=False, cast=bool)
WXPAY_MCHID = config('WXPAY_MCHID', default='')
# 公众号 appid / secret：微信浏览器内 JSAPI 支付 + 网页授权取 openid
WXPAY_APPID = config('WXPAY_APPID', default='')
WXPAY_APP_SECRET = config('WXPAY_APP_SECRET', default='')
# 小程序 appid / secret：留空表示不区分，直接用公众号那套
WXPAY_MINI_APPID = config('WXPAY_MINI_APPID', default=WXPAY_APPID)
WXPAY_MINI_SECRET = config('WXPAY_MINI_SECRET', default=WXPAY_APP_SECRET)
# API v3 密钥（商户平台设置，32 位）：用于解密回调与平台证书
WXPAY_API_V3_KEY = config('WXPAY_API_V3_KEY', default='')
# 商户 API 证书序列号 + 私钥（apiclient_key.pem）
WXPAY_SERIAL_NO = config('WXPAY_SERIAL_NO', default='')
WXPAY_PRIVATE_KEY_PATH = config('WXPAY_PRIVATE_KEY_PATH',
                                default=str(BASE_DIR / 'certs' / 'apiclient_key.pem'))
# 也可以直接把 PEM 内容塞进环境变量（部署平台不方便挂文件时用）
WXPAY_PRIVATE_KEY = config('WXPAY_PRIVATE_KEY', default='')
# 支付结果通知地址：必须是公网可访问 https 地址
WXPAY_NOTIFY_URL = config('WXPAY_NOTIFY_URL', default='')
# H5 支付完成后的回跳页（微信会带着订单跳回这里）
WXPAY_H5_REDIRECT_URL = config('WXPAY_H5_REDIRECT_URL', default='')
# 平台证书缓存目录（自动从 /v3/certificates 下载并解密后缓存）
WXPAY_CERT_DIR = config('WXPAY_CERT_DIR', default=str(BASE_DIR / 'certs' / 'platform'))
WXPAY_TIMEOUT = config('WXPAY_TIMEOUT', default=10, cast=int)
# 订单有效期（秒）：超时未支付自动关单
WXPAY_ORDER_TTL = config('WXPAY_ORDER_TTL', default=15 * 60, cast=int)

# ---------------------------------------------------------------- 模板 / Admin
# ---------------------------------------------------------------- 前端静态托管
# 单端口部署（内网试用 / 单机云服务器）：vite build 的产物直接由 Django 吐出。
# 前端 API 走相对路径 /api/v1，同源部署天然没有跨域；hash 路由也不需要 history 回退。
# 有 nginx 时更建议让 nginx 直接发静态（见 docker-compose.yml），此项关掉即可。
WEB_DIST = config('WEB_DIST', default=str(BASE_DIR.parent / 'frontend' / 'dist'))
SERVE_WEB = config('SERVE_WEB', default=False, cast=bool)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', WEB_DIST],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# 密码规则：字母+数字组合、不低于 6 位。挂在全局校验器上，
# 注册 / 找回密码 / 设置密码 三处共用同一份规则，无需各写一遍。
# 顺序即提示优先级：组合规则放最前，用户最先看到「必须包含字母和数字」。
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'apps.users.validators.LetterAndDigitValidator'},
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 6}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------- CORS / 静态
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173,http://127.0.0.1:5173',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------- 国际化
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- AI 智能分析（可选）
# ★ 默认关闭：不配 AI_API_KEY 时，报告页「智能分析」自动走本地规则引擎，功能不受影响。
# 兼容 OpenAI 的 /chat/completions 协议：DeepSeek / 通义 / Moonshot / 本地 vLLM、Ollama 均可。
AI_ENABLED = config('AI_ENABLED', default=False, cast=bool)
AI_API_KEY = config('AI_API_KEY', default='')
AI_BASE_URL = config('AI_BASE_URL', default='https://api.deepseek.com/v1')
AI_MODEL = config('AI_MODEL', default='deepseek-chat')
AI_TIMEOUT = config('AI_TIMEOUT', default=20, cast=int)
AI_MAX_TOKENS = config('AI_MAX_TOKENS', default=900, cast=int)
AI_CACHE_TTL = config('AI_CACHE_TTL', default=900, cast=int)  # 同一区间分析结果缓存秒数

# ---------------------------------------------------------------- 日志
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
        'file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': str(LOG_DIR / 'app.log'),
            'when': 'midnight',
            'backupCount': 14,
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console', 'file'], 'level': 'INFO'},
    'loggers': {
        'django.utils.autoreload': {'level': 'WARNING', 'propagate': False},
    },
}

logging.getLogger(__name__).info(
    '数据库引擎：%s', DATABASES['default']['ENGINE'].rsplit('.', 1)[-1]
)

# ---------------------------------------------------------------- 生产安全闸门
# 宁可启动失败，也不要带着开发配置上线——下面每一条都对应一次真实事故
if not DEBUG:
    _problems = []

    # SECRET_KEY 泄露 = 任何人都能伪造 JWT 读你家账本
    if SECRET_KEY.startswith('django-insecure') or len(SECRET_KEY) < 32:
        _problems.append(
            'SECRET_KEY 仍是开发默认值或过短；生产必须换随机值（openssl rand -base64 64）'
        )
    # Host 头攻击：密码重置链接会被指到攻击者的域名
    if ALLOWED_HOSTS == ['*']:
        _problems.append("ALLOWED_HOSTS 不能为 '*'，需填真实域名或服务器 IP")
    # SQLite 单人写锁：两口之家同时记账必然 database is locked
    if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
        _problems.append(
            '生产禁止使用 SQLite（并发写会 database is locked）；请配 DB_HOST 切到 MySQL'
        )

    if _problems:
        raise ImproperlyConfigured(
            '生产配置不安全，已拒绝启动：\n  - ' + '\n  - '.join(_problems)
        )

    if not CSRF_TRUSTED_ORIGINS:
        logging.getLogger(__name__).warning(
            'CSRF_TRUSTED_ORIGINS 为空：/django-admin 的登录与表单提交会被拒绝'
            '（H5 走 JWT 不受影响；要用 admin 就配上 https://你的域名）'
        )
