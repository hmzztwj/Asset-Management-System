"""权限三层控制测试：URL 层（perm_required 装饰器）。

口径：
- 未登录 → 跳登录页
- 已登录但角色无权限 → 302 回首页并提示
- 角色有权限 → 200
- 超级管理员（is_superuser）始终通过
- 只读角色能 GET 列表页，但 POST 管理操作被拒
"""
from django.test import TestCase

from assets.tests.base import make_asset, make_department, make_role, make_user


class PermGateTests(TestCase):
    """URL 层权限门禁。"""

    def setUp(self):
        make_department()
        make_asset()

    def test_anonymous_redirected_to_login(self):
        r = self.client.get('/library/')
        self.assertRedirects(r, '/login/?next=/library/')

    def test_viewer_can_view_library(self):
        viewer = make_user('viewer1')
        self.client.force_login(viewer)
        r = self.client.get('/library/')
        self.assertEqual(r.status_code, 200)

    def test_viewer_cannot_access_users(self):
        viewer = make_user('viewer2')
        self.client.force_login(viewer)
        r = self.client.get('/users/')
        self.assertRedirects(r, '/')                          # 提示并回首页（dashboard 路由是 /）

    def test_viewer_cannot_open_asset_create(self):
        viewer = make_user('viewer3')
        self.client.force_login(viewer)
        r = self.client.get('/library/add/')
        self.assertRedirects(r, '/')

    def test_manager_can_open_asset_create(self):
        manager = make_user('manager1', manage_assets=True)
        self.client.force_login(manager)
        r = self.client.get('/library/add/')
        self.assertEqual(r.status_code, 200)

    def test_superuser_passes_all(self):
        from assets.tests.base import make_superuser
        su = make_superuser('root1')
        self.client.force_login(su)
        for url in ('/library/', '/library/add/', '/users/', '/roles/',
                    '/requisition/', '/change/', '/org/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_role_without_requisition_perm_blocked(self):
        """默认全关的角色一个业务页都进不去。"""
        role = make_role(
            code='ghost', view_assets=False, view_org=False,
            view_requisition=False, view_change=False,
        )
        ghost = make_user('ghost1', role=role)
        self.client.force_login(ghost)
        for url in ('/library/', '/requisition/', '/change/', '/org/'):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), '/')

    def test_no_role_user_blocked(self):
        """没有档案/角色的账号同样被拒。"""
        from django.contrib.auth.models import User
        orphan = User.objects.create_user('orphan1', password='Passw0rd!123')
        self.client.force_login(orphan)
        self.assertRedirects(self.client.get('/library/'), '/')


class DashboardAlwaysAccessibleTests(TestCase):
    """登录后首页人人可见（无业务权限也可看数据总览）。"""

    def test_dashboard_200_for_viewer(self):
        viewer = make_user('viewer_dash')
        self.client.force_login(viewer)
        self.assertEqual(self.client.get('/').status_code, 200)
