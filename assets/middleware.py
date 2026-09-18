"""会话与备份相关中间件。

- SingleDeviceMiddleware：单设备登录（非超管同账号仅一台设备在线）。
- IdleTimeoutMiddleware：空闲超时（长时间无操作自动退出，防共享电脑挂机）。
- AutoBackupMiddleware：请求结束后按设置触发整库自动备份
  （定时型任意请求参与判断；数据变动型仅写操作触发）。
"""
import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect
from django.utils.http import urlencode

_DEBOUNCE = 5  # 秒：极短时间内不重复触发，避免同一操作的后续请求造成重复备份
_last_auto = 0.0


class SingleDeviceMiddleware:
    """单设备登录限制：除超级管理员外，同一账号同时只允许一台设备在线。

    机制：
    - 登录时把当前会话 key 记到 UserProfile.session_key（见 views.login_view）；
    - 每次请求校验：若当前会话与记录的不一致，说明账号已在别处登录，
      立即注销本机并跳转到登录页；
    - profile.session_key 为空（旧会话兼容）时自动认领当前会话，不强制重登。
    """

    _EXEMPT_PREFIXES = ('/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self._check(request)
        if response is not None:
            return response
        return self.get_response(request)

    def _check(self, request):
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return None
        path = request.path or ''
        if path.startswith(self._EXEMPT_PREFIXES):
            return None
        profile = getattr(user, 'profile', None)
        if profile is None:
            return None
        current = request.session.session_key
        if not current:
            return None
        if not profile.session_key:
            # 兼容旧登录：首次访问时认领当前会话
            profile.session_key = current
            profile.save(update_fields=['session_key'])
            return None
        if profile.session_key != current:
            logout(request)
            return HttpResponseRedirect('/login/?kicked=1')
        return None


class IdleTimeoutMiddleware:
    """空闲会话超时：长时间无操作的登录态自动失效。

    - 超时时长由 env ``ASSETS_IDLE_TIMEOUT``（分钟）控制，默认 30，设 0 关闭；
    - 只对已登录用户生效；超管同样受控（共享电脑场景超管更不该挂机）；
    - 活跃时间戳记在会话里，节流写入（每分钟最多刷一次），不增加请求负担；
    - 被踢出的会话跳登录页并提示「长时间未操作」。
    """

    _KEY = '_last_activity'      # 会话里的活跃时间戳（Unix 秒）
    _WRITE_THRESHOLD = 60        # 秒：距上次写入不足该值就不重写会话

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timeout_min = int(getattr(settings, 'IDLE_TIMEOUT_MINUTES', 30) or 0)
        if timeout_min > 0:
            response = self._check(request, timeout_min * 60)
            if response is not None:
                return response
        return self.get_response(request)

    def _check(self, request, timeout_sec):
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return None
        path = request.path or ''
        if path.startswith(('/static/', '/media/')):
            return None

        now = time.time()
        last = request.session.get(self._KEY)
        if last and (now - float(last)) > timeout_sec:
            logout(request)
            query = urlencode({'idle': '1'})
            return HttpResponseRedirect('/login/?' + query)

        # 节流刷新活跃时间：避免每个请求都写一遍会话
        if not last or (now - float(last)) >= self._WRITE_THRESHOLD:
            request.session[self._KEY] = now
        return None


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
