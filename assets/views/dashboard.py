"""首页数据总览仪表盘。"""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from ..models import Asset, AssetChange, Department, Requisition

@login_required
def dashboard(request):
    # 各部门资产数量统计（用于饼图占比 与 柱状图）
    dept_counts = (
        Department.objects.annotate(asset_count=Count('assets'))
        .order_by('-asset_count')
    )
    labels = [d.name for d in dept_counts]
    counts = [d.asset_count for d in dept_counts]

    # 状态分布（饼图补充）
    status_counts = (
        Asset.objects.values('status')
        .annotate(n=Count('id'))
        .order_by('-n')
    )

    # 类别分布
    category_counts = (
        Asset.objects.values('category')
        .annotate(n=Count('id'))
        .order_by('-n')
    )

    # 各部门资产总值
    value_per_dept = (
        Department.objects.annotate(total_value=Sum('assets__price'))
        .filter(total_value__isnull=False)
        .exclude(total_value=0)
        .order_by('-total_value')
    )
    value_labels = [d.name for d in value_per_dept]
    value_counts = [float(d.total_value or 0) for d in value_per_dept]

    total_assets = Asset.objects.count()
    in_use = Asset.objects.filter(status='在用').count()
    total_departments = Department.objects.count()
    # 逾期为派生状态（借出且超过预计归还日期），用与列表页一致的动态口径统计
    pending_return = Requisition.objects.filter(status='借出').count()
    overdue = Requisition.objects.filter(
        status='借出', due_date__lt=timezone.localdate()
    ).count()
    # 逾期清单（按超期天数倒序：预计归还最早 = 超期最久在前），
    # 首页「逾期提醒」卡片每页 5 条，超出走分页（?page=N）
    overdue_qs = (
        Requisition.objects.filter(status='借出', due_date__lt=timezone.localdate())
        .select_related('asset', 'department')
        .order_by('due_date')
    )
    overdue = overdue_qs.count()
    page_obj = Paginator(overdue_qs, 5).get_page(request.GET.get('page'))
    overdue_records = list(page_obj.object_list)
    for r in overdue_records:
        r.overdue_days = (timezone.localdate() - r.due_date).days
    total_value = Asset.objects.aggregate(v=Sum('price'))['v'] or 0

    context = {
        'labels': labels,
        'counts': counts,
        'status_labels': [s['status'] for s in status_counts],
        'status_values': [s['n'] for s in status_counts],
        'category_labels': [c['category'] for c in category_counts],
        'category_values': [c['n'] for c in category_counts],
        'value_labels': value_labels,
        'value_counts': value_counts,
        'total_assets': total_assets,
        'in_use': in_use,
        'total_departments': total_departments,
        'overdue': overdue,
        'overdue_records': overdue_records,
        'page_obj': page_obj,  # 逾期清单分页（复用 _pagination.html）
        'total_value': total_value,
        'pending_return': pending_return,
        'recent_changes': AssetChange.objects.select_related('asset')[:6],
        'recent_requisitions': Requisition.objects.select_related('asset', 'department')[:6],
        'page_title': '数据总览',
    }
    return render(request, 'dashboard.html', context)

