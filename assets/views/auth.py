"""登录 / 退出 / 修改密码（含防爆破锁定与单设备踢线）。"""

import datetime
import math

from django.contrib import messages
from django.contrib.auth import (
    authenticate, login, logout as auth_logout, update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .. import oplog
from .common import (
    LOGIN_LOCK_SECONDS, LOGIN_MAX_ATTEMPTS,
    _check_password_strength, _login_fail_key,
)

def login_view(request):
    if request.user.is_authenticated:
        return redirect(reverse('dashboard'))

    kicked = request.GET.get('kicked') == '1'

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        remember = request.POST.get('remember')

        # —— 防爆破：连错 5 次锁定 5 分钟（按用户名计数，锁定期间即使密码正确也拒绝）——
        fail_key = _login_fail_key(username)
        lock_key = fail_key + '_lock'
        locked_until = cache.get(lock_key)
        if locked_until:
            remain = max(1, math.ceil((locked_until - timezone.now()).total_seconds() / 60))
            oplog.log(request, 'auth', 'login_fail', target=username or '（空用户名）',
                      detail=f'账号处于锁定状态，拒绝登录（剩余约 {remain} 分钟）')
            return render(request, 'login.html', {
                'error': True,
                'error_msg': f'密码连续输错 {LOGIN_MAX_ATTEMPTS} 次，账号已临时锁定，请约 {remain} 分钟后再试。',
                'username': username,
            })

        user = authenticate(request, username=username, password=password)
        if user is not None:
            cache.delete(fail_key)
            cache.delete(lock_key)
            login(request, user)
            # 记住我：30 天；否则浏览器关闭即失效
            if remember:
                request.session.set_expiry(60 * 60 * 24 * 30)
            else:
                request.session.set_expiry(0)
            # —— 单设备登录：非超管只保留最近一次登录的会话，旧设备由中间件踢下线 ——
            profile = getattr(user, 'profile', None)
            if profile is not None and not user.is_superuser:
                profile.session_key = request.session.session_key
                profile.save(update_fields=['session_key'])
            oplog.log(request, 'auth', 'login', target=user.username,
                      detail=f'登录成功（{"记住我 30 天" if remember else "关闭浏览器即失效"}）')
            nxt = request.POST.get('next') or request.GET.get('next') or '/'
            if not url_has_allowed_host_and_scheme(
                nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                nxt = '/'
            return redirect(nxt)

        # 登录失败：计数并提示剩余机会
        fails = cache.get(fail_key, 0) + 1
        if fails >= LOGIN_MAX_ATTEMPTS:
            cache.set(lock_key, timezone.now() + datetime.timedelta(seconds=LOGIN_LOCK_SECONDS),
                      LOGIN_LOCK_SECONDS)
            cache.delete(fail_key)
            error_msg = f'密码连续输错 {LOGIN_MAX_ATTEMPTS} 次，账号已锁定 5 分钟，请稍后再试。'
            oplog.log(request, 'auth', 'login_fail', target=username or '（空用户名）',
                      detail=f'连续输错 {LOGIN_MAX_ATTEMPTS} 次，账号锁定 {LOGIN_LOCK_SECONDS // 60} 分钟')
        else:
            cache.set(fail_key, fails, LOGIN_LOCK_SECONDS)
            error_msg = (f'用户名或密码不正确，请重试。'
                         f'（第 {fails}/{LOGIN_MAX_ATTEMPTS} 次尝试，连续输错 {LOGIN_MAX_ATTEMPTS} 次将锁定 5 分钟）')
            oplog.log(request, 'auth', 'login_fail', target=username or '（空用户名）',
                      detail=f'用户名或密码不正确（第 {fails}/{LOGIN_MAX_ATTEMPTS} 次）')
        return render(request, 'login.html', {
            'error': True, 'error_msg': error_msg, 'username': username,
        })

    return render(request, 'login.html', {'kicked': kicked})


def logout_view(request):
    """退出登录（记录日志后走 Django 的 logout）。"""
    if request.user.is_authenticated:
        oplog.log(request, 'auth', 'logout', target=request.user.username, detail='主动退出登录')
    auth_logout(request)
    return redirect('login')


@login_required
def password_change(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if not request.user.check_password(old_password):
            messages.error(request, '当前密码不正确。')
        elif new_password != confirm_password:
            messages.error(request, '两次输入的新密码不一致。')
        else:
            pwd_err = _check_password_strength(request.user, new_password)
            if pwd_err:
                messages.error(request, f'新密码不符合要求：{pwd_err}')
            else:
                request.user.set_password(new_password)
                request.user.save()
                update_session_auth_hash(request, request.user)
                oplog.log(request, 'auth', 'update', target=request.user.username,
                          detail='用户自行修改登录密码')
                messages.success(request, '密码修改成功。')
                return redirect('dashboard')
    context = {'page_title': '修改密码', 'active': 'dashboard'}
    return render(request, 'password_change.html', context)

