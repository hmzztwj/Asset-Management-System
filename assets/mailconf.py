"""邮件提醒的支撑逻辑：SMTP 配置加密、逾期数据收集、汇总邮件构建与发送。

设计要点：
- SMTP 授权码**加密入库**：用 ``SECRET_KEY`` 派生密钥做对称加密（HMAC-SHA256
  密钥流 + 随机 nonce），后台展示时打码。内网系统够用，且不引入新依赖。
- 发送永远**吞掉异常只记日志**（与 oplog 同原则）：邮件发不出去不能影响
  系统任何其它功能。
- 收件人 = 拥有「管理资产领用」权限的账号 + 超管中**填写了有效邮箱**的人，
  按邮箱去重；无有效收件人则不发。
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import EmailValidator, ValidationError
from django.utils import timezone

logger = logging.getLogger('assets')

ENC_PREFIX = 'enc1:'


# ---------- 密码加密（无第三方依赖） ----------

def _keystream(key_material: bytes, length: int) -> bytes:
    """从 SECRET_KEY + nonce 派生密钥流（HMAC-SHA256 计数器模式）。"""
    out = b''
    counter = 0
    while len(out) < length:
        out += hmac.new(key_material, counter.to_bytes(4, 'big'), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def seal_password(plain: str) -> str:
    """加密 SMTP 密码，返回 ``enc1:`` 前缀的密文。空串原样返回。"""
    if not plain:
        return ''
    key = hashlib.sha256(str(settings.SECRET_KEY).encode('utf-8')).digest()
    nonce = secrets.token_bytes(16)
    plain_b = plain.encode('utf-8')
    mac = hmac.new(key, nonce + plain_b, hashlib.sha256).digest()[:16]
    stream = _keystream(key + nonce, len(plain_b))
    cipher = bytes(a ^ b for a, b in zip(plain_b, stream))
    token = base64.urlsafe_b64encode(nonce + mac + cipher).decode('ascii')
    return ENC_PREFIX + token


def unseal_password(token: str) -> str:
    """解密 ``seal_password`` 的产物；不是密文（如历史明文/空值）原样返回。"""
    if not token:
        return ''
    if not token.startswith(ENC_PREFIX):
        return token
    try:
        key = hashlib.sha256(str(settings.SECRET_KEY).encode('utf-8')).digest()
        raw = base64.urlsafe_b64decode(token[len(ENC_PREFIX):].encode('ascii'))
        nonce, mac, cipher = raw[:16], raw[16:32], raw[32:]
        stream = _keystream(key + nonce, len(cipher))
        plain = bytes(a ^ b for a, b in zip(cipher, stream))
        expect = hmac.new(key, nonce + plain, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(mac, expect):
            raise ValueError('mac mismatch')
        return plain.decode('utf-8')
    except Exception as exc:  # noqa: BLE001
        raise ValueError('SMTP 密码解密失败（SECRET_KEY 是否变过？）') from exc


def mask_password(token: str) -> str:
    """后台展示用：已配置则显示打码标记，未配置显示空。"""
    return '********（已保存，留空不修改）' if token else ''


# ---------- 收件人 / 逾期数据 ----------

def valid_email_or_none(raw) -> str:
    """邮箱格式校验；合法返回去掉首尾空白的地址，非法/为空返回 None。"""
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        EmailValidator()(raw)
        return raw
    except ValidationError:
        return None


def digest_recipients():
    """逾期提醒收件人：勾选了「邮箱通知」的角色下的账号 + 超管里填了有效邮箱的人。

    「邮箱通知」是角色上独立的勾选框（角色管理里设置），与页面访问权限解耦，
    只决定这个账号收不收通知邮件。按邮箱去重，无效/为空跳过。
    """
    from django.contrib.auth.models import User

    emails = []
    users = (
        User.objects.filter(is_active=True)
        .select_related('profile__role')
        .filter(is_superuser=True) | User.objects.filter(
            is_active=True, profile__role__email_notify=True,
        )
    ).distinct()
    for u in users:
        addr = valid_email_or_none(u.email)
        if addr and addr.lower() not in {e.lower() for e in emails}:
            emails.append(addr)
    return emails


def collect_overdue():
    """逾期领用记录：状态=借出 且 应还日期早于今天。按逾期最久排序。"""
    from .models import Requisition

    today = timezone.localdate()
    qs = (
        Requisition.objects.filter(status='借出', due_date__lt=today)
        .select_related('asset', 'department')
        .order_by('due_date')
    )
    rows = []
    for req in qs:
        overdue_days = (today - req.due_date).days
        rows.append({
            'asset_id': req.asset.asset_id,
            'asset_name': req.asset.name,
            'user': req.actual_user or req.user,
            'department': req.department.name if req.department else '—',
            'borrow_date': req.borrow_date,
            'due_date': req.due_date,
            'overdue_days': overdue_days,
        })
    return rows


def render_digest(rows, base_url=''):
    """构建汇总邮件的标题与正文（纯文本 + HTML 双版本）。"""
    n = len(rows)
    subject = f'【资产管理系统】逾期领用提醒：{n} 条待归还'
    lines = [f'截至 {timezone.localdate()}，共有 {n} 条逾期未归还的资产领用记录：', '']
    for r in rows:
        lines.append(
            f"- {r['asset_name']}（{r['asset_id']}）｜借用人 {r['user']}｜"
            f"{r['department']}｜应还 {r['due_date']}｜已逾期 {r['overdue_days']} 天"
        )
    if base_url:
        lines += ['', f'处理入口：{base_url.rstrip("/")}/requisition/']
    text = '\n'.join(lines)

    tr = ''.join(
        f"<tr><td>{r['asset_name']}</td><td>{r['asset_id']}</td><td>{r['user']}</td>"
        f"<td>{r['department']}</td><td>{r['due_date']}</td>"
        f"<td style='color:#c00;font-weight:700'>{r['overdue_days']} 天</td></tr>"
        for r in rows
    )
    link = (
        f"<p><a href='{base_url.rstrip('/')}/requisition/'>点此进入系统处理</a></p>"
        if base_url else ''
    )
    html = (
        f"<p>截至 <b>{timezone.localdate()}</b>，共有 <b style='color:#c00'>{n}</b> 条"
        f"逾期未归还的资产领用记录：</p>"
        f"<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse'>"
        f"<tr style='background:#f0f4f8'><th>资产</th><th>编号</th><th>借用人</th>"
        f"<th>部门</th><th>应还日期</th><th>逾期</th></tr>{tr}</table>{link}"
    )
    return subject, text, html


# ---------- 发送 ----------

def smtp_params_from_env():
    """环境变量兜底配置（后台未启用时使用）。返回参数字典或 None。"""
    host = (os.environ.get('ASSETS_SMTP_HOST') or '').strip()
    user = (os.environ.get('ASSETS_SMTP_USER') or '').strip()
    if not host or not user:
        return None
    return {
        'host': host,
        'port': int(os.environ.get('ASSETS_SMTP_PORT') or 465),
        'use_ssl': (os.environ.get('ASSETS_SMTP_SSL', '1') == '1'),
        'username': user,
        'password': os.environ.get('ASSETS_SMTP_PASS') or '',
        'from_email': (os.environ.get('ASSETS_SMTP_FROM') or user).strip(),
    }


def send_mail(smtp, to_list, subject, text, html, backend=None):
    """发送邮件。``smtp`` 为参数字典；``backend`` 供测试注入（如 locmem）。

    返回成功发出的收件人数；失败抛异常（由调用方决定如何记录）。
    """
    conn = get_connection(
        backend=backend,
        host=smtp['host'], port=smtp['port'],
        username=smtp['username'], password=smtp['password'],
        use_ssl=smtp['use_ssl'], use_tls=(not smtp['use_ssl'] and smtp['port'] == 587),
    )
    msg = EmailMultiAlternatives(
        subject=subject, body=text,
        from_email=smtp['from_email'], to=to_list, connection=conn,
    )
    msg.attach_alternative(html, 'text/html')
    sent = msg.send()
    return sent
