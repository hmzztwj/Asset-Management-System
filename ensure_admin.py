"""确保角色与默认管理员账号存在。用法: python ensure_admin.py"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "assets_system.settings")
django.setup()

from django.contrib.auth.models import User
from assets.models import Role, UserProfile

ROLE_DATA = {
    'super_admin': dict(name='超级管理员', description='拥有系统全部权限',
                        can_access_admin=True, view_assets=True, manage_assets=True,
                        view_org=True, manage_org=True, view_requisition=True,
                        manage_requisition=True, view_change=True, manage_change=True,
                        manage_users=True, is_system=True),
    'admin': dict(name='管理员', description='管理各模块数据',
                  can_access_admin=True, view_assets=True, manage_assets=True,
                  view_org=True, manage_org=True, view_requisition=True,
                  manage_requisition=True, view_change=True, manage_change=True,
                  manage_users=True, is_system=True),
    'user': dict(name='普通用户', description='只读浏览各模块',
                 can_access_admin=False, view_assets=True, manage_assets=False,
                 view_org=True, manage_org=False, view_requisition=True,
                 manage_requisition=False, view_change=True, manage_change=False,
                 manage_users=False, is_system=True),
}
for code, data in ROLE_DATA.items():
    Role.objects.update_or_create(code=code, defaults=data)

username, password = "admin", "admin123"
admin, created = User.objects.get_or_create(
    username=username,
    defaults=dict(email="", is_superuser=True, is_staff=True),
)
admin.is_superuser = True
admin.is_staff = True
admin.set_password(password)  # 确保可登录
admin.save()

admin_role = Role.objects.get(code="super_admin")
profile, _ = UserProfile.objects.get_or_create(user=admin)
profile.role = admin_role
profile.save()

# 给没有档案的用户补默认「普通用户」角色
user_role = Role.objects.get(code="user")
for u in User.objects.filter(profile__isnull=True):
    UserProfile.objects.create(user=u, role=user_role)

print(f"管理员账号就绪: {username} / {password} | 角色: {Role.objects.count()} 个 | 用户: {User.objects.count()} 个")
