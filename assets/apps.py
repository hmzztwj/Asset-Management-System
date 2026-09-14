from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _sqlite_pragmas(sender, connection, **kwargs):  # noqa: ARG001
    """每个数据库连接建立时设置 SQLite PRAGMA。

    - ``journal_mode=WAL``：读写不再互相阻塞，多线程（gunicorn threads）下
      明显减少 "database is locked"；崩溃恢复也更安全。
    - ``synchronous=NORMAL``：WAL 下的推荐值，兼顾安全与写入性能。
    - ``busy_timeout``：与 settings 里的 OPTIONS.timeout 双重兜底。
    """
    if connection.vendor != 'sqlite':
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
            cursor.execute('PRAGMA busy_timeout=20000;')
    except Exception:  # noqa: BLE001 — PRAGMA 失败不阻塞正常使用
        pass


class AssetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assets'
    verbose_name = '资产管理系统'

    def ready(self):
        # dispatch_uid 保证自动重载时不会重复连接信号
        connection_created.connect(
            _sqlite_pragmas, dispatch_uid='assets.sqlite_pragmas'
        )
