"""自动备份中间件。

在每次请求结束后检查自动备份设置并视情况触发一次整库备份：

- 定时型（每天定时 / 每隔 3 天 / 每隔 7 天）：**任意请求**（包括只是
  打开页面浏览）都会参与判断，只要已过设定的备份时刻且满足间隔，
  就补做一次备份；判断完全基于时间，不依赖任何写操作。
- 每次数据变动：当请求为写操作（POST / PUT / PATCH / DELETE）且响应成功时触发。

设计要点：
- 一次操作（如一次导入）只在请求结束时触发一次，而不是每条记录触发一次；
- 所有异常均被吞掉，备份失败绝不影响正常请求；
- 备份管理页自身的操作不会再次触发自动备份（避免自我循环）。
"""
import time

_DEBOUNCE = 5  # 秒：极短时间内不重复触发，避免同一操作的后续请求造成重复备份
_last_auto = 0.0


class AutoBackupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._maybe_backup(request, response)
        except Exception:
            pass  # 备份出错绝不影响请求
        return response

    def _maybe_backup(self, request, response):
        global _last_auto

        # 仅处理正常响应
        if response.status_code >= 400:
            return
        # 跳过静态资源
        path = request.path or ''
        if path.startswith('/static/') or path.startswith('/media/'):
            return
        # 跳过备份管理页自身的操作（手动备份等已单独处理）
        if path.startswith('/admin/assets/backupsetting'):
            return

        from . import backup
        from .models import BackupSetting

        setting = BackupSetting.get_solo()
        if not setting.auto_enabled:
            return

        if setting.interval == 'on_change':
            # 仅在写操作且响应成功时触发
            trigger = request.method in ('POST', 'PUT', 'PATCH', 'DELETE')
        else:
            # 定时型：只看时间，不看请求方法（GET 浏览同样可以触发）
            trigger = backup.scheduled_backup_due()

        if not trigger:
            return

        # 防抖
        now = time.time()
        if now - _last_auto < _DEBOUNCE:
            return
        _last_auto = now

        backup.create_backup(reason='auto')
