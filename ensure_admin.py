"""确保内置角色与内置超管账号存在。用法: python ensure_admin.py

本脚本由 start.bat 在启动服务前调用，规则是**完全幂等**的：

1. 内置角色（超级管理员 / 管理员 / 普通用户）
   —— 仅在数据库里没有该编码时才创建，绝不覆盖你在「角色管理」里调过的权限。
2. 内置超管账号 admin
   —— 仅首次部署时创建，初始密码 admin123；
      已存在时**不再改动密码**，只兜底确保它仍是可登录的超级管理员，
      并标记为「内置账号」，使其无法被删除、停用或降级，避免系统被锁死。

日常增删用户请使用系统内的「用户管理」页面，本脚本不参与。
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "assets_system.settings")
django.setup()

from django.contrib.auth.models import User  # noqa: E402

from assets.models import Role, UserProfile  # noqa: E402

# 系统内置超管账号（首次部署写入数据库，永久保留）
BUILTIN_ADMIN_USERNAME = "admin"
BUILTIN_ADMIN_PASSWORD = "admin123"

ROLE_DATA = {
    'super_admin': dict(name='超级管理员', description='拥有系统全部权限',
                        can_access_admin=True, view_assets=True, manage_assets=True,
                        view_org=True, manage_org=True, view_requisition=True,
                        manage_requisition=True, view_change=True, manage_change=True,
                        manage_users=True, email_notify=True, is_system=True),
    'admin': dict(name='管理员', description='管理各模块数据',
                  can_access_admin=True, view_assets=True, manage_assets=True,
                  view_org=True, manage_org=True, view_requisition=True,
                  manage_requisition=True, view_change=True, manage_change=True,
                  manage_users=True, email_notify=True, is_system=True),
    'user': dict(name='普通用户', description='只读浏览各模块',
                 can_access_admin=False, view_assets=True, manage_assets=False,
                 view_org=True, manage_org=False, view_requisition=True,
                 manage_requisition=False, view_change=True, manage_change=False,
                 manage_users=False, email_notify=False, is_system=True),
}


def ensure_roles():
    """内置角色只在缺失时创建，已存在的一律不动。返回本次新建的角色名列表。"""
    created = []
    for code, data in ROLE_DATA.items():
        _, is_new = Role.objects.get_or_create(code=code, defaults=data)
        if is_new:
            created.append(data['name'])
    return created


def ensure_builtin_admin():
    """创建内置超管；已存在则不改密码，只兜底保证其可用且不可被删除。"""
    admin, created = User.objects.get_or_create(
        username=BUILTIN_ADMIN_USERNAME,
        defaults=dict(email='', first_name='系统管理员',
                      is_superuser=True, is_staff=True, is_active=True),
    )

    if created:
        admin.set_password(BUILTIN_ADMIN_PASSWORD)
        admin.save()

    # 内置标记 + 超级管理员角色（兜底，不涉及密码）
    super_role = Role.objects.get(code='super_admin')
    profile, _ = UserProfile.objects.get_or_create(user=admin)
    changed = False
    if not profile.is_builtin:
        profile.is_builtin = True
        changed = True
    if profile.role_id != super_role.id:
        profile.role = super_role
        changed = True
    if changed:
        profile.save()

    # 保证内置账号始终是可用的超级管理员（即使有人绕过界面直接改库）
    fix = []
    if not admin.is_superuser:
        admin.is_superuser = True
        fix.append('is_superuser')
    if not admin.is_staff:
        admin.is_staff = True
        fix.append('is_staff')
    if not admin.is_active:
        admin.is_active = True
        fix.append('is_active')
    if fix:
        admin.save(update_fields=fix)

    return created


def ensure_profiles():
    """给尚未建档的用户补一个默认「普通用户」角色（仅在缺失时补）。"""
    user_role = Role.objects.get(code='user')
    filled = 0
    for u in User.objects.filter(profile__isnull=True):
        UserProfile.objects.create(user=u, role=user_role)
        filled += 1
    return filled


def main():
    new_roles = ensure_roles()
    created = ensure_builtin_admin()
    filled = ensure_profiles()

    if created:
        print(f"首次部署：已创建内置超管 {BUILTIN_ADMIN_USERNAME} / {BUILTIN_ADMIN_PASSWORD}"
              f"（请登录后尽快修改密码）")
    else:
        print(f"内置超管 {BUILTIN_ADMIN_USERNAME} 已存在，密码与资料保持原样，未做改动。")
    if new_roles:
        print(f"已补充内置角色：{'、'.join(new_roles)}")
    if filled:
        print(f"已为 {filled} 个未建档用户补默认角色。")
    print(f"当前角色 {Role.objects.count()} 个 | 用户 {User.objects.count()} 个")


if __name__ == '__main__':
    main()
