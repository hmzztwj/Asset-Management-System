"""逾期汇总邮件收件人筛选测试。

口径（用户确认）：
- 收信依据 = 角色 email_notify 勾选框（账号需填写邮箱）
- 超级管理员始终在名单内
- 未勾选角色 / 无邮箱账号不收
"""
from django.core import mail
from django.test import TestCase

from assets import mailconf
from assets.models import EmailConfig
from assets.tests.base import make_asset, make_department, make_role, make_user, make_superuser


class DigestRecipientTests(TestCase):
    def setUp(self):
        make_department()
        make_asset()
        # 勾选邮箱通知的角色 + 两个成员（一个有邮箱、一个没有）
        role = make_role(code='notify_role', email_notify=True)
        self.notified = make_user('notify1', role=role)
        self.notified.email = 'notify1@example.com'
        self.notified.save()
        self.no_email = make_user('notify2', role=role)

        # 未勾选邮箱通知的角色（即使有邮箱也不收）
        quiet_role = make_role(code='quiet_role', email_notify=False)
        self.quiet = make_user('quiet1', role=quiet_role)
        self.quiet.email = 'quiet1@example.com'
        self.quiet.save()

        # 超管（始终在名单内）
        self.su = make_superuser('mail_admin')
        self.su.email = 'admin@example.com'
        self.su.save()

    def test_recipients_follow_role_checkbox(self):
        names = set(mailconf.digest_recipients())
        self.assertIn('notify1@example.com', names)
        self.assertIn('admin@example.com', names)
        self.assertNotIn('quiet1@example.com', names)
        self.assertNotIn('', names)                        # 没邮箱的账号不会混进来

    def test_uncheck_removes_from_recipients(self):
        role = self.notified.profile.role
        role.email_notify = False
        role.save()
        names = set(mailconf.digest_recipients())
        self.assertNotIn('notify1@example.com', names)
        self.assertIn('admin@example.com', names)          # 超管不受影响

    def test_superuser_always_included_even_without_role(self):
        from django.contrib.auth.models import User
        extra = User.objects.create_user('su2', password='x', is_superuser=True)
        extra.email = 'su2@example.com'
        extra.save()
        self.assertIn('su2@example.com', set(mailconf.digest_recipients()))


class SendDigestCommandTests(TestCase):
    """send_overdue_digest 命令：配置关闭时不发。"""

    def test_disabled_config_skips_send(self):
        make_department()
        EmailConfig.objects.create(pk=1, enabled=False)
        from django.core.management import call_command
        call_command('send_overdue_digest', '--force')
        self.assertEqual(len(mail.outbox), 0)
