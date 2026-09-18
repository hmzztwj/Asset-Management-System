"""邮箱配置的后台管理：仅超管可读写，密码加密存储、打码展示。

页面提供「保存并发送测试邮件」按钮：填好 SMTP 后输一个收件地址点按钮，
立刻验证通路（走与定时提醒完全相同的发送代码）。
"""
import logging

from django import forms
from django.conf import settings
from django.contrib import admin, messages

from . import mailconf, oplog
from .models import EmailConfig

logger = logging.getLogger('assets')


class EmailConfigForm(forms.ModelForm):
    """密码留空 = 不修改；填写则加密保存。另含不发库的测试收件地址输入框。"""

    test_recipient = forms.CharField(
        label='测试收件邮箱', required=False,
        help_text='点「保存并发送测试邮件」时使用；仅本次有效，不保存。',
    )

    class Meta:
        model = EmailConfig
        fields = '__all__'
        widgets = {
            'smtp_password': forms.PasswordInput(
                render_value=False,
                attrs={'autocomplete': 'new-password'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.smtp_password:
            self.fields['smtp_password'].help_text = (
                '已保存（加密存储）。留空表示不修改，填写则覆盖。'
            )

    def clean_smtp_password(self):
        raw = self.cleaned_data.get('smtp_password') or ''
        if raw:
            return mailconf.seal_password(raw)
        # 留空：编辑时保留原值，新增时为空
        if self.instance and self.instance.pk:
            return self.instance.smtp_password
        return ''

    def clean_send_hour(self):
        hour = self.cleaned_data.get('send_hour')
        if hour is None or not (0 <= hour <= 23):
            raise forms.ValidationError('发送时间必须是 0-23 之间的整数。')
        return hour


@admin.register(EmailConfig)
class EmailConfigAdmin(admin.ModelAdmin):
    form = EmailConfigForm
    list_display = ('enabled', 'smtp_host', 'smtp_user', 'send_hour', 'last_sent_at', 'updated_at')

    # ---------- 权限：仅超管 ----------
    def _only_superuser(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_module_permission(self, request):
        return self._only_superuser(request)

    def has_view_permission(self, request, obj=None):
        return self._only_superuser(request)

    def has_change_permission(self, request, obj=None):
        return self._only_superuser(request)

    def has_add_permission(self, request):
        # 单例：已有配置就不再提供"新增"入口。
        # 防御：迁移未执行（表不存在）时查库会抛 OperationalError——
        # 不能让它把整个 /admin/ 拖成 500，这里静默按"无权限"处理。
        if not self._only_superuser(request):
            return False
        try:
            return not EmailConfig.objects.exists()
        except Exception:  # noqa: BLE001（表缺失等数据库异常）
            return False

    def has_delete_permission(self, request, obj=None):
        return self._only_superuser(request)

    # ---------- 展示 ----------
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # 密码展示为空（PasswordInput 本就不回显），仅保留帮助文案
        return form

    # ---------- 保存 + 测试发送 ----------
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        changes = (
            f'启用={"开" if obj.enabled else "关"}；SMTP={obj.smtp_host}:{obj.smtp_port}'
            f'（SSL={"是" if obj.use_ssl else "否"}）；账号={obj.smtp_user or "（空）"}；'
            f'每日 {obj.send_hour} 点'
        )
        oplog.log(request, 'system', 'update', target='邮箱配置', detail=changes)
        messages.success(request, '邮箱配置已保存。')

    def response_change(self, request, obj):
        """处理「保存并发送测试邮件」按钮：先正常保存，再向测试地址发一封。"""
        if '_send_test' in request.POST:
            to_addr = mailconf.valid_email_or_none(request.POST.get('test_recipient'))
            if not to_addr:
                messages.error(request, '请先在「测试收件邮箱」里填写一个合法的邮箱地址。')
                return self._rerender(request, obj)
            smtp = obj.smtp_params()
            if not smtp:
                messages.error(request, '请先勾选「启用邮件提醒」并填写 SMTP 服务器与账号，再保存。')
                return self._rerender(request, obj)
            try:
                rows = mailconf.collect_overdue()
                subject, text, html = mailconf.render_digest(
                    rows, (getattr(settings, 'PUBLIC_BASE_URL', '') or ''),
                )
                subject = f'【测试】{subject}'
                text = '（测试邮件：验证邮箱配置通路，内容为当前逾期情况）\n\n' + text
                html = '<p>（测试邮件：验证邮箱配置通路，内容为当前逾期情况）</p>' + html
                mailconf.send_mail(smtp, [to_addr], subject, text, html)
            except Exception as exc:  # noqa: BLE001
                logger.error('邮箱配置测试邮件发送失败：%s', exc, exc_info=True)
                messages.error(request, f'测试邮件发送失败：{exc}')
                oplog.log(request, 'system', 'other', target='邮箱配置测试邮件',
                          detail=f'发送失败：{exc}')
            else:
                messages.success(request, f'测试邮件已发送到 {to_addr}，请查收（注意垃圾箱）。')
                oplog.log(request, 'system', 'other', target='邮箱配置测试邮件',
                          detail=f'发送成功：{to_addr}')
            return self._rerender(request, obj)
        return super().response_change(request, obj)

    def _rerender(self, request, obj):
        """保存后重新打开本页（提示消息随本次响应展示）。"""
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(request.path)
