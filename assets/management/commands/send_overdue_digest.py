"""发送逾期领用每日汇总邮件（由计划任务定时调用）。

用法：
    python manage.py send_overdue_digest                 # 正常定时调用
    python manage.py send_overdue_digest --force         # 忽略时间闸门立即发送
    python manage.py send_overdue_digest --to a@b.com    # 测试邮件（发到指定地址）

时间闸门：只发「启用中 + 当前小时 == 配置的发送小时 + 今天还没发过」的邮件，
所以计划任务可以放心配成每小时跑一次，改后台配置的发送时间即时生效。
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from assets import mailconf
from assets.models import EmailConfig


class Command(BaseCommand):
    help = '发送逾期领用每日汇总邮件给管理员（计划任务调用；详见 --help）'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='忽略发送时间闸门，立即发送一次（发送后正常记录时间）')
        parser.add_argument('--to', metavar='邮箱',
                            help='测试模式：发送到指定邮箱（忽略闸门；无逾期也发送）')
        parser.add_argument('--backend', metavar='BACKEND',
                            help='邮件后端覆盖（测试用），如 django.core.mail.backends.locmem.EmailBackend')

    def handle(self, *args, **opts):
        now = timezone.localtime()
        cfg = EmailConfig.load()
        smtp = cfg.smtp_params() or mailconf.smtp_params_from_env()
        if not smtp:
            self.stdout.write('邮箱功能未启用（后台未配置且无环境变量），跳过。')
            return

        force = opts['force'] or bool(opts['to'])
        if not force:
            today = now.date()
            already = bool(cfg.last_sent_at and timezone.localtime(cfg.last_sent_at).date() == today)
            if now.hour != cfg.send_hour or already:
                self.stdout.write(
                    f'未到发送时间（配置 {cfg.send_hour} 点，当前 {now.hour} 点；'
                    f'今日{"已发" if already else "未发"}），跳过。'
                )
                return

        rows = mailconf.collect_overdue()
        if opts['to']:
            to_list = [mailconf.valid_email_or_none(opts['to'])]
            if not to_list or not to_list[0]:
                self.stderr.write('测试收件邮箱格式不正确。')
                raise SystemExit(2)
            note = '（测试邮件：验证邮箱配置通路，内容为当前逾期情况）'
        else:
            to_list = mailconf.digest_recipients()
            note = ''
            if not to_list:
                self.stderr.write(
                    '没有可用的收件人：拥有「管理资产领用」权限的账号和超管均未填写有效邮箱，跳过。'
                )
                return
        if not rows and not opts['to']:
            self.stdout.write('当前无逾期领用记录，无需发送。')
            return

        base_url = (getattr(settings, 'PUBLIC_BASE_URL', '') or '').strip()
        subject, text, html = mailconf.render_digest(rows, base_url)
        if opts['to']:
            subject = '【测试】' + subject + note
            text = note + '\n\n' + text
            html = f'<p>{note}</p>' + html

        try:
            sent = mailconf.send_mail(smtp, to_list, subject, text, html, backend=opts['backend'])
        except Exception as exc:  # noqa: BLE001
            logger.error('逾期提醒邮件发送失败：%s', exc, exc_info=True)
            self.stderr.write(f'发送失败：{exc}')
            raise SystemExit(1)

        cfg.last_sent_at = timezone.now()
        cfg.save(update_fields=['last_sent_at'])
        if rows:
            worst = max(r['overdue_days'] for r in rows)
            self.stdout.write(
                f'已发送给 {sent} 个收件人：{len(rows)} 条逾期（最久 {worst} 天）。'
            )
        else:
            self.stdout.write(f'测试邮件已发送给 {sent} 个收件人（当前无逾期数据）。')
