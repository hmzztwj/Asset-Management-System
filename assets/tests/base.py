"""测试共用脚手架：造角色 / 用户 / 资产 / 部门的快捷方法。"""
from django.contrib.auth.models import User

from assets.models import Asset, Department, Role, UserProfile


def make_department(name='综合管理部'):
    return Department.objects.create(name=name)


def make_asset(asset_id='ZC-0001', name='测试笔记本', status='库存',
               department=None, responsible='资产管理员', user='资产管理员'):
    return Asset.objects.create(
        asset_id=asset_id, name=name, category='电脑',
        specification='', configuration='',
        responsible=responsible, serial='SN-1',
        department=department, user=user, status=status,
        price=100, location='A-101',
    )


def make_role(code='viewer', name=None, **perm_flags):
    defaults = dict(
        can_access_admin=False,
        view_assets=True, manage_assets=False,
        view_org=True, manage_org=False,
        view_requisition=True, manage_requisition=False,
        view_change=True, manage_change=False,
        manage_users=False, email_notify=False,
    )
    defaults.update(perm_flags)
    if name is None:
        name = f'角色-{code}'          # name 唯一，默认值跟 code 走避免撞名
    return Role.objects.create(code=code, name=name, **defaults)


def make_user(username='alice', password='Passw0rd!123', role=None, **role_kwargs):
    """建一个带角色的用户；role 传 None 则新建默认只读角色。"""
    if role is None:
        role = make_role(code=f'role_{username}', **role_kwargs)
    user = User.objects.create_user(
        username=username, password=password, first_name=username.title(),
    )
    UserProfile.objects.create(user=user, role=role)
    return user


def make_superuser(username='admin', password='Admin123!'):
    user = User.objects.create_user(
        username=username, password=password, is_superuser=True, is_staff=True,
    )
    UserProfile.objects.create(user=user, is_builtin=True)
    return user
