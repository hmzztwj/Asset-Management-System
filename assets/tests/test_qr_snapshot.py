"""二维码快照与免登录信息卡测试。

口径（用户确认，勿改回跳资产库检索页）：
- 二维码内容 = <访问地址>/a/?d=<快照 token>，快照内嵌资产信息
- /a/ 免登录、只读、不查库、noindex
- 快照损坏/缺失时给可读提示页而不是 500
"""
from django.test import TestCase

from assets import asset_snapshot
from assets.tests.base import make_asset, make_department


class SnapshotPayloadTests(TestCase):
    def setUp(self):
        self.dept = make_department('研发一部')
        self.asset = make_asset(
            asset_id='ZC-QR-01', name='扫码测试机', department=self.dept,
        )

    def _payload(self):
        return asset_snapshot.card_payload('http://example.com/a/', self.asset)

    def test_payload_embeds_base_and_token(self):
        payload = self._payload()
        self.assertTrue(payload.startswith('http://example.com/a/?d='))
        token = payload.split('?d=', 1)[1]
        self.assertTrue(token)

    def test_token_roundtrip(self):
        data = asset_snapshot.decode(self._payload().split('?d=', 1)[1])
        self.assertIsNotNone(data)
        self.assertEqual(data['asset_id'], 'ZC-QR-01')
        self.assertEqual(data['name'], '扫码测试机')
        self.assertEqual(data['department'], '研发一部')

    def test_snapshot_date_only_day_precision(self):
        """快照时间只精确到日（缓存键要求，勿改成时分秒）。"""
        data = asset_snapshot.decode(self._payload().split('?d=', 1)[1])
        self.assertIn('snapshot_date', data)
        # 长度 10 = YYYY-MM-DD，无时间部分
        self.assertEqual(len(data['snapshot_date']), 10)


class AssetCardViewTests(TestCase):
    """免登录扫码落地页。"""

    def setUp(self):
        self.dept = make_department('研发一部')
        self.asset = make_asset(asset_id='ZC-QR-02', name='信息卡测试机',
                                department=self.dept, status='在用')

    def _token(self):
        payload = asset_snapshot.card_payload('http://example.com/a/', self.asset)
        return payload.split('?d=', 1)[1]

    def test_card_accessible_without_login(self):
        r = self.client.get(f'/a/?d={self._token()}')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '信息卡测试机')

    def test_card_noindex(self):
        r = self.client.get(f'/a/?d={self._token()}')
        self.assertEqual(r.get('X-Robots-Tag'), 'noindex, nofollow')

    def test_card_with_bad_token_renders_hint_not_500(self):
        r = self.client.get('/a/?d=not-a-valid-token')
        self.assertEqual(r.status_code, 200)               # 可读提示页

    def test_card_missing_param_renders_hint_not_500(self):
        r = self.client.get('/a/')
        self.assertEqual(r.status_code, 200)

    def test_card_get_only(self):
        self.assertEqual(self.client.post('/a/?d=x').status_code, 405)


class AssetQrViewTests(TestCase):
    """二维码图片本身需要登录 + 权限。"""

    def setUp(self):
        make_department()
        self.asset = make_asset(asset_id='ZC-QR-03')

    def test_qr_requires_login(self):
        r = self.client.get(f'/library/{self.asset.pk}/qr/')
        self.assertRedirects(r, f'/login/?next=/library/{self.asset.pk}/qr/')

    def test_qr_svg_for_permitted_user(self):
        from assets.tests.base import make_user
        self.client.force_login(make_user('qr_viewer'))
        r = self.client.get(f'/library/{self.asset.pk}/qr/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/svg+xml')
        self.assertIn('no-cache', r['Cache-Control'])
