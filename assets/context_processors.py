from django.contrib.messages import get_messages

# 常见移动端 UA 特征（覆盖 iOS / Android / 鸿蒙及主流国产浏览器）
_MOBILE_UA_MARKS = (
    'Mobile', 'Android', 'iPhone', 'iPad', 'iPod', 'HarmonyOS', 'HMOS',
    'Windows Phone', 'OPPO', 'vivo', 'HUAWEI', 'MIUI', 'MiniProgramApp',
)


def device_type(request):
    """根据 User-Agent 识别访问设备，模板可据此切换移动端/桌面端布局。"""
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    return {'is_mobile': any(mark in ua for mark in _MOBILE_UA_MARKS)}


def messages_json(request):
    """把 Django 消息整理为列表，供模板用 json_script 安全输出（避免直接拼进 script）。"""
    return {
        'messages_json': [
            {'level': m.level_tag, 'message': str(m)}
            for m in get_messages(request)
        ]
    }


def overdue_alert(request):
    """逾期主动提醒：为已登录用户提供逾期领用数量与前若干条明细。

    供两类位置使用：
    - 侧栏「资产领用」菜单上的红色徽标（数量）；
    - 页面顶部的全局提醒条（前 5 条 + 跳转「逾期」筛选）。

    未登录、或数据库尚未就绪时一律返回 0，绝不影响页面渲染。
    """
    empty = {'overdue_alert_count': 0, 'overdue_alert_items': []}
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return empty
    try:
        from django.utils import timezone
        from .models import Requisition

        today = timezone.localdate()
        qs = (
            Requisition.objects
            .filter(status='借出', due_date__lt=today)
            .select_related('asset')
            .order_by('due_date')
        )
        items = [
            {
                'asset': r.asset.name,
                'asset_id': r.asset.asset_id,
                'user': r.user,
                'due_date': r.due_date,
                'days': (today - r.due_date).days,
            }
            for r in qs[:5]
        ]
        return {'overdue_alert_count': qs.count(), 'overdue_alert_items': items}
    except Exception:  # noqa: BLE001 — 提醒功能失败不能影响正常页面
        return empty
