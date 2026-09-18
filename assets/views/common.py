"""视图层共用工具：登录锁定参数、资产快照/标签、日期与价格解析、
admin_required 装饰器、资产库统一筛选口径。
"""

import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse

from ..models import Asset

ASSET_FIELD_LABELS = {
    'name': '资产名称',
    'category': '资产类别',
    'specification': '规格',
    'configuration': '配置',
    'responsible': '责任人',
    'serial': '序列号',
    'department': '所属部门',
    'user': '实际使用人',
    'status': '使用状态',
    'price': '资产价值',
    'purchase_date': '购置日期',
    'location': '存放位置',
}


LOGIN_LOCK_SECONDS = 5 * 60   # 锁定时长（秒）


LOGIN_MAX_ATTEMPTS = 5        # 连续输错次数上限


def _login_fail_key(username):
    return 'login_fail_' + (username or '').strip().lower()


def _asset_snapshot(asset):
    """把资产关键字段拍成 {字段名: 值} 快照，供变更前后对比。"""
    return {
        'name': asset.name,
        'category': asset.category,
        'specification': asset.specification,
        'configuration': asset.configuration,
        'responsible': asset.responsible,
        'serial': asset.serial,
        'department': asset.department.name if asset.department_id else '',
        'user': asset.user,
        'status': asset.status,
        'price': asset.price,
        'purchase_date': asset.purchase_date.strftime('%Y-%m-%d') if asset.purchase_date else '',
        'location': asset.location,
    }


def _asset_label(asset):
    """日志里标识一台资产的统一写法。"""
    return f'{asset.asset_id} {asset.name}'


def _parse_date(value):
    """兼容字符串日期 / datetime / 数值日期，返回 date 或 None。"""
    if value is None or str(value).strip() == '':
        return None
    if isinstance(value, datetime.datetime):
        return value.date() if hasattr(value, 'date') else None
    if isinstance(value, datetime.date):
        return value
    from openpyxl.utils.datetime import from_excel
    try:
        return from_excel(float(value)).date()
    except Exception:
        pass
    text = str(value).strip().replace('/', '-').replace('.', '-')
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y年%m月%d日'):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _parse_price(value):
    """把价格输入解析为 Decimal：空值视为 0，非法输入返回 None。"""
    text = str(value).strip() if value is not None else ''
    if not text:
        return Decimal('0')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _check_password_strength(user, password):
    """按 settings.AUTH_PASSWORD_VALIDATORS 校验密码强度。

    通过返回 None，否则返回可直接展示的错误文案。
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    try:
        validate_password(password, user=user)
        return None
    except ValidationError as exc:
        return '；'.join(exc.messages)


def admin_required(view_func):
    """仅管理员(staff/superuser)可访问；否则提示并回首页。"""
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, '仅管理员可访问该页面。')
            return redirect(reverse('dashboard'))
        return view_func(request, *args, **kwargs)
    return _wrapped


def _filtered_assets(request):
    """按 URL 查询参数过滤资产库，返回 (queryset, filters)。

    资产库列表与「标签打印」共用同一套筛选口径，避免两处规则漂移。
    """
    status = request.GET.get('status', '')
    category = request.GET.get('category', '')
    dept_id = request.GET.get('department', '')
    keyword = request.GET.get('q', '').strip()
    # 搜索模式：asset=按名称/资产编号；person=按责任人/实际使用人
    field = request.GET.get('field', 'asset')
    if field not in ('asset', 'person'):
        field = 'asset'

    qs = Asset.objects.select_related('department')
    if status:
        qs = qs.filter(status=status)
    if category:
        qs = qs.filter(category=category)
    if dept_id:
        qs = qs.filter(department_id=dept_id)
    if keyword:
        if field == 'person':
            # 责任人 / 实际使用人 模糊匹配
            qs = qs.filter(Q(responsible__icontains=keyword) | Q(user__icontains=keyword))
        else:
            # 资产名称 / 资产编号 模糊匹配（默认）
            qs = qs.filter(Q(name__icontains=keyword) | Q(asset_id__icontains=keyword))

    filters = {
        'status': status,
        'category': category,
        'department': dept_id,
        'q': keyword,
        'field': field,
    }
    return qs, filters


def _missing_required_asset(data):
    labels = {
        'asset_id': '资产编号', 'name': '资产名称', 'category': '资产类别',
        'department': '所属部门', 'responsible': '责任人', 'user': '实际使用人',
        'location': '存放位置', 'status': '使用状态',
    }
    return [labels[k] for k, v in data.items() if v in (None, '')]

