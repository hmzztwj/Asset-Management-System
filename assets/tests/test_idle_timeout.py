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


class FaviconRedirectTests(TestCase):
    """浏览器默认会请求 /favicon.ico，应 301 到静态 SVG 而不是 404。"""

    def test_favicon_redirects_to_svg(self):
        r = self.client.get('/favicon.ico')
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r['Location'], '/static/img/favicon.svg')


class AllowedHostsBuilderTests(TestCase):
    """ALLOWED_HOSTS 收紧时自动放行 127.0.0.1/localhost（容器健康检查依赖）。"""

    def test_wildcard_stays_wildcard(self):
        from assets_system.settings import _build_allowed_hosts
        self.assertEqual(_build_allowed_hosts('*'), ['*'])

    def test_tightened_list_gets_local_hosts(self):
        from assets_system.settings import _build_allowed_hosts
        hosts = _build_allowed_hosts('10.0.0.1,www.example.com,example.com')
        self.assertEqual(hosts[:3], ['10.0.0.1', 'www.example.com', 'example.com'])
        self.assertIn('127.0.0.1', hosts)
        self.assertIn('localhost', hosts)

    def test_no_duplicate_local_hosts(self):
        from assets_system.settings import _build_allowed_hosts
        hosts = _build_allowed_hosts('127.0.0.1,10.0.0.1')
        self.assertEqual(hosts.count('127.0.0.1'), 1)
        self.assertIn('localhost', hosts)

    def test_empty_falls_back_to_wildcard(self):
        from assets_system.settings import _build_allowed_hosts
        self.assertEqual(_build_allowed_hosts(''), ['*'])

    def test_blank_items_skipped(self):
        from assets_system.settings import _build_allowed_hosts
        hosts = _build_allowed_hosts(' 10.0.0.1 , , www.x.com ')
        self.assertEqual(hosts, ['10.0.0.1', 'www.x.com', '127.0.0.1', 'localhost'])
