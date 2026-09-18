"""操作日志查询页。"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from ..models import OperationLog
from .common import admin_required

@admin_required
def oplog_list(request):
    """操作日志查询页（管理员）。支持按模块/动作/关键字/日期区间筛选。"""
    category = request.GET.get('category', '')
    action = request.GET.get('action', '')
    keyword = request.GET.get('q', '').strip()
    start = request.GET.get('start', '').strip()
    end = request.GET.get('end', '').strip()

    qs = OperationLog.objects.all()
    if category:
        qs = qs.filter(category=category)
    if action:
        qs = qs.filter(action=action)
    if keyword:
        qs = qs.filter(
            Q(operator__icontains=keyword) | Q(target__icontains=keyword)
            | Q(detail__icontains=keyword) | Q(ip__icontains=keyword)
        )
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'records': page_obj.object_list,
        'category_options': OperationLog.CATEGORY_CHOICES,
        'action_options': OperationLog.ACTION_CHOICES,
        'filters': {'category': category, 'action': action, 'q': keyword, 'start': start, 'end': end},
        'total_logs': OperationLog.objects.count(),
        'page_title': '操作日志',
        'active': 'oplog',
    }
    return render(request, 'oplog.html', context)

