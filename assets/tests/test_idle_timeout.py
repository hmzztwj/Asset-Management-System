"""空闲会话超时中间件测试。"""
import time

from django.test import TestCase, override_settings

from assets.middleware import IdleTimeoutMiddleware
from assets.tests.base import make_department, make_user


def _age_session(client, seconds):
    """把当前会话的活跃时间戳改成 seconds 秒之前。"""
    session = client.session
    session[IdleTimeoutMiddleware._KEY] = time.time() - seconds
    session.save()


class IdleTimeoutTests(TestCase):
    def setUp(self):
        make_department()
        self.user = make_user('idle_user')
        self.client.force_login(self.user)

    @override_settings(IDLE_TIMEOUT_MINUTES=30)
    def test_active_user_not_kicked(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        r = self.client.get('/library/')
        self.assertEqual(r.status_code, 200)          # 活跃期间持续可用

    @override_settings(IDLE_TIMEOUT_MINUTES=30)
    def test_idle_user_kicked_to_login(self):
        _age_session(self.client, 31 * 60)             # 空闲 31 分钟
        r = self.client.get('/library/')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r['Location'].endswith('/login/?idle=1'))
        # 已被注销：再访问业务页要求重新登录
        r2 = self.client.get('/library/')
        self.assertEqual(r2.status_code, 302)
        self.assertIn('/login/', r2['Location'])

    @override_settings(IDLE_TIMEOUT_MINUTES=30)
    def test_fresh_activity_extends_session(self):
        _age_session(self.client, 20 * 60)             # 空闲 20 分钟 < 30
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)          # 活跃刷新时间戳
        _age_session(self.client, 20 * 60)             # 又过了 20 分钟
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)          # 合计 40 分钟但从未连续空闲超 30

    @override_settings(IDLE_TIMEOUT_MINUTES=0)
    def test_disabled_when_zero(self):
        _age_session(self.client, 10 * 24 * 3600)      # 挂机十天
        r = self.client.get('/library/')
        self.assertEqual(r.status_code, 200)          # 配 0 = 关闭

    @override_settings(IDLE_TIMEOUT_MINUTES=30)
    def test_anonymous_unaffected(self):
        self.client.logout()
        r = self.client.get('/login/')
        self.assertEqual(r.status_code, 200)

    @override_settings(IDLE_TIMEOUT_MINUTES=30)
    def test_login_page_shows_idle_hint(self):
        _age_session(self.client, 31 * 60)
        r = self.client.get('/library/')
        follow = self.client.get(r['Location'])
        self.assertContains(follow, '长时间未操作，已自动退出')
