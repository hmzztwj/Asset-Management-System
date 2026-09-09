from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse


def user_has_perm(user, perm):
    """判断用户是否拥有某权限码（字段名）。超级管理员始终拥有全部权限。"""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    role = profile.role if profile else None
    if not role:
        return False
    return bool(getattr(role, perm, False))


def perm_required(perm_code):
    """装饰器：要求登录且拥有指定权限，否则提示并回首页。"""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not user_has_perm(request.user, perm_code):
                messages.error(request, '当前账号无访问该页面的权限。')
                return redirect(reverse('dashboard'))
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
