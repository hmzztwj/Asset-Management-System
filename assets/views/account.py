"""用户与角色管理（需 manage_users 权限）。"""

from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404

from .. import mailconf
from .. import oplog
from ..models import Role, UserProfile
from ..permissions import perm_required
from .common import _check_password_strength

_PERM_GROUPS = [
    {'title': '系统权限', 'items': [('can_access_admin', '访问后台管理')]},
    {'title': '资产库', 'items': [('view_assets', '查看'), ('manage_assets', '管理')]},
    {'title': '组织架构', 'items': [('view_org', '查看'), ('manage_org', '管理')]},
    {'title': '资产领用', 'items': [('view_requisition', '查看'), ('manage_requisition', '管理')]},
    {'title': '资产变更', 'items': [('view_change', '查看'), ('manage_change', '管理')]},
    {'title': '用户/角色', 'items': [('manage_users', '管理用户/角色')]},
    {'title': '邮箱通知', 'items': [('email_notify', '接收逾期提醒等通知邮件（需账号填写邮箱）')]},
]


_PERM_FIELDS = [
    ('can_access_admin', '访问后台'),
    ('view_assets', '查看资产库'), ('manage_assets', '管理资产库'),
    ('view_org', '查看组织架构'), ('manage_org', '管理组织架构'),
    ('view_requisition', '查看资产领用'), ('manage_requisition', '管理资产领用'),
    ('view_change', '查看资产变更'), ('manage_change', '管理资产变更'),
    ('manage_users', '管理用户/角色'),
    ('email_notify', '接收邮箱通知'),
]


def _apply_role(user, role_obj):
    """给用户绑定角色，并同步 is_staff / is_superuser。"""
    from django.db import transaction
    with transaction.atomic():
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role_obj
        profile.save()
        user.is_superuser = bool(role_obj and role_obj.code == 'super_admin')
        user.is_staff = bool(role_obj and role_obj.can_access_admin)
        user.save(update_fields=['is_superuser', 'is_staff'])
    return profile


@perm_required('manage_users')
def user_list(request):
    users = User.objects.select_related('profile__role').order_by('id')
    context = {
        'users': users,
        'total_users': users.count(),
        'active_users': users.filter(is_active=True).count(),
        'admin_count': users.filter(is_staff=True).count(),
        'page_title': '用户管理',
        'active': 'users',
    }
    return render(request, 'user_list.html', context)


@perm_required('manage_users')
def user_create(request):
    roles = Role.objects.all()
    ctx = {
        'page_title': '新增用户', 'active': 'users', 'edit_user': None, 'roles': roles,
        'form_data': {},
    }
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        role_id = request.POST.get('role') or None

        # 失败时回显用户已填写内容
        ctx['form_data'] = {
            'username': username, 'password': password, 'first_name': first_name,
            'email': email, 'role_id': role_id,
        }

        pwd_err = _check_password_strength(None, password) if password else None

        if not username:
            messages.error(request, '用户名不能为空。')
        elif not password:
            messages.error(request, '密码不能为空。')
        elif not role_id:
            messages.error(request, '请为用户分配角色。')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f'用户名 {username} 已存在。')
        elif pwd_err:
            messages.error(request, f'密码不符合要求：{pwd_err}')
        elif email and not mailconf.valid_email_or_none(email):
            messages.error(request, '邮箱格式不正确，请检查后重试（留空表示不填写）。')
            return redirect('user_create')
        else:
            user = User.objects.create_user(
                username=username, password=password, email=email, first_name=first_name
            )
            role_obj = Role.objects.filter(pk=role_id).first()
            _apply_role(user, role_obj)
            oplog.log(request, 'user', 'create', target=f'用户 {username}',
                      detail=(f'姓名：{first_name or "（空）"}；邮箱：{email or "（空）"}；'
                              f'角色：{role_obj.name if role_obj else "（未分配）"}'))
            messages.success(request, f'用户 {username} 创建成功。')
            return redirect('user_list')
    return render(request, 'user_form.html', ctx)


@perm_required('manage_users')
def user_update(request, pk):
    user = get_object_or_404(User, pk=pk)
    roles = Role.objects.all()
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        email = request.POST.get('email', '').strip()
        role_id = request.POST.get('role') or None
        is_active = request.POST.get('is_active') == '1'
        password = request.POST.get('password', '')
        role_obj = Role.objects.filter(pk=role_id).first() if role_id else None

        # 重置密码时同样套用强度校验
        if password:
            pwd_err = _check_password_strength(user, password)
            if pwd_err:
                messages.error(request, f'密码不符合要求：{pwd_err}')
                return redirect('user_list')

        # 邮箱：服务端格式校验（空值允许 = 不填写）
        if email and not mailconf.valid_email_or_none(email):
            messages.error(request, '邮箱格式不正确，请检查后重试（留空表示不填写）。')
            return redirect('user_update', pk=pk)

        # 内置账号保护：不可停用、不可降级（避免系统被锁死）
        target_profile = getattr(user, 'profile', None)
        if target_profile is not None and target_profile.is_builtin:
            is_active = True  # 内置账号始终启用
            if not (role_obj and role_obj.code == 'super_admin'):
                messages.error(request, '内置账号不可降级，必须保持「超级管理员」角色。')
                return redirect('user_list')

        # 自我保护：不能停用自己、不能移除自己的用户管理权限
        if user == request.user:
            if not is_active:
                messages.error(request, '不能停用当前登录的账号。')
            elif not (role_obj and role_obj.manage_users):
                messages.error(request, '不能移除自己的用户管理权限。')
            else:
                user.first_name = first_name
                user.email = email
                user.is_active = is_active
                _apply_role(user, role_obj)
                if password:
                    user.set_password(password)
                    user.save()
                oplog.log(request, 'user', 'update', target=f'用户 {user.username}',
                          detail=(f'（本人资料）姓名：{first_name or "（空）"}；邮箱：{email or "（空）"}；'
                                  f'角色：{role_obj.name if role_obj else "（未分配）"}'
                                  + ('；已重置密码' if password else '')))
                messages.success(request, '个人信息已更新。')
            return redirect('user_list')

        # 最后一个超管不能降级
        if user.is_superuser and not (role_obj and role_obj.code == 'super_admin'):
            if User.objects.filter(is_superuser=True).count() <= 1:
                messages.error(request, '系统至少需要保留一个超级管理员。')
                return redirect('user_list')

        user.first_name = first_name
        user.email = email
        user.is_active = is_active
        _apply_role(user, role_obj)
        if password:
            user.set_password(password)
            user.save()
        oplog.log(request, 'user', 'update', target=f'用户 {user.username}',
                  detail=(f'姓名：{first_name or "（空）"}；邮箱：{email or "（空）"}；'
                          f'启用：{"是" if is_active else "否"}；'
                          f'角色：{role_obj.name if role_obj else "（未分配）"}'
                          + ('；已重置密码' if password else '')))
        messages.success(request, f'用户 {user.username} 更新成功。')
        return redirect('user_list')

    context = {'page_title': '编辑用户', 'active': 'users', 'edit_user': user, 'roles': roles}
    return render(request, 'user_form.html', context)


@perm_required('manage_users')
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        profile = getattr(user, 'profile', None)
        if profile is not None and profile.is_builtin:
            messages.error(request, '内置账号不可删除。')
        elif user == request.user:
            messages.error(request, '不能删除当前登录的账号。')
        elif user.is_superuser:
            messages.error(request, '不能删除超级管理员账号，请先将其降级。')
        else:
            uname = user.username
            user.delete()
            oplog.log(request, 'user', 'delete', target=f'用户 {uname}', detail='删除用户及其档案')
            messages.success(request, f'用户 {user.username} 已删除。')
    return redirect('user_list')


@perm_required('manage_users')
def role_list(request):
    roles = Role.objects.prefetch_related('profiles').order_by('id')
    context = {
        'roles': roles,
        'perm_fields': _PERM_FIELDS,
        'page_title': '角色管理',
        'active': 'roles',
    }
    return render(request, 'role_list.html', context)


@perm_required('manage_users')
def role_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        description = request.POST.get('description', '').strip()
        if not name or not code:
            messages.error(request, '角色名称与编码不能为空。')
        elif Role.objects.filter(code=code).exists():
            messages.error(request, f'编码 {code} 已存在。')
        else:
            role = Role.objects.create(name=name, code=code, description=description)
            _save_perm_fields(role, request.POST)
            oplog.log(request, 'user', 'create', target=f'角色 {name}',
                      detail=f'编码：{code}；权限：{"、".join(_perm_labels(role)) or "（无）"}')
            messages.success(request, f'角色 {name} 创建成功。')
            return redirect('role_list')
    context = {'page_title': '新增角色', 'active': 'roles', 'edit_role': None,
               'perm_fields': _PERM_FIELDS, 'perm_groups': _PERM_GROUPS}
    return render(request, 'role_form.html', context)


@perm_required('manage_users')
def role_update(request, pk):
    role = get_object_or_404(Role, pk=pk)
    is_super_role = role.code == 'super_admin'
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, '角色名称不能为空。')
        else:
            role.name = name
            role.description = description
            role.save()
            if is_super_role:
                # 超级管理员固定拥有全部权限（admin 账号是硬编码超管，这里的
                # 勾选只影响展示），防止被 POST 清空后与实际权限描述不符。
                for field, _label in _PERM_FIELDS:
                    setattr(role, field, True)
                role.save()
            else:
                _save_perm_fields(role, request.POST)
            oplog.log(request, 'user', 'update', target=f'角色 {name}',
                      detail=f'权限：{"、".join(_perm_labels(role)) or "（无）"}')
            messages.success(request, f'角色 {name} 更新成功。')
            return redirect('role_list')
    context = {'page_title': '编辑角色', 'active': 'roles', 'edit_role': role,
               'is_super_role': is_super_role,
               'perm_fields': _PERM_FIELDS, 'perm_groups': _PERM_GROUPS}
    return render(request, 'role_form.html', context)


def _save_perm_fields(role, post):
    for field, _label in _PERM_FIELDS:
        setattr(role, field, post.get(field) == '1')
    role.save()


@perm_required('manage_users')
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if request.method == 'POST':
        if role.is_system:
            messages.error(request, '系统内置角色不能删除。')
        elif role.profiles.exists():
            messages.error(request, f'还有 {role.profiles.count()} 个用户使用该角色，请先调整这些用户的角色。')
        else:
            rname = role.name
            role.delete()
            oplog.log(request, 'user', 'delete', target=f'角色 {rname}', detail='删除角色')
            messages.success(request, f'角色 {role.name} 已删除。')
    return redirect('role_list')


def _perm_labels(role):
    """把角色已开启的权限翻译成中文标签列表，用于操作日志。"""
    labels = []
    for field, label in _PERM_FIELDS:
        if getattr(role, field, False):
            labels.append(label)
    return labels

