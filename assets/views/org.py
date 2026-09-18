"""组织架构：部门列表（树/平铺）与增删改（含防成环）。"""

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .. import oplog
from ..models import Asset, Department
from ..permissions import perm_required

@perm_required('view_org')
def org(request):
    mode = request.GET.get('mode', 'list')
    departments = Department.objects.annotate(asset_count=Count('assets')).order_by('id')

    # 汇总：每个部门统计其自身 + 所有下级部门的资产数（公司主体应包含下属全部）
    direct = {d.id: d.asset_count for d in departments}
    children = {}
    for d in departments:
        if d.parent_id:
            children.setdefault(d.parent_id, []).append(d.id)
    sub_memo = {}
    def subtree(nid):
        if nid not in sub_memo:
            total = direct.get(nid, 0)
            for cid in children.get(nid, []):
                total += subtree(cid)
            sub_memo[nid] = total
        return sub_memo[nid]
    for d in departments:
        d.subtree_count = subtree(d.id)

    # 构建树（仅树状模式需要）
    nodes = {d.id: {'dept': d, 'children': []} for d in departments}
    roots = []
    for d in departments:
        node = nodes[d.id]
        if d.parent_id and d.parent_id in nodes:
            nodes[d.parent_id]['children'].append(node)
        else:
            roots.append(node)

    context = {
        'departments': departments,
        'mode': mode,
        'tree_roots': roots,
        'total_departments': Department.objects.count(),
        'total_assets': Asset.objects.count(),
        'page_title': '组织架构',
        'active': 'org',
    }
    return render(request, 'org.html', context)


def _descendant_ids(dept):
    """返回某个部门所有下级部门的 id 列表（用于防止把上级设为下级造成成环）。"""
    ids = []
    stack = list(dept.children.all())
    while stack:
        child = stack.pop()
        ids.append(child.id)
        stack.extend(child.children.all())
    return ids


@perm_required('manage_org')
def department_form(request, pk=None):
    """新增/编辑部门（树状图与列表共用）。pk 为空则新增，否则编辑。"""
    is_edit = pk is not None
    department = get_object_or_404(Department, pk=pk) if is_edit else None
    preset_parent = request.GET.get('parent') or None
    mode = request.GET.get('mode', request.POST.get('mode', 'list'))

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        manager = request.POST.get('manager', '').strip()
        description = request.POST.get('description', '').strip()
        parent_id = request.POST.get('parent') or None
        mode = request.POST.get('mode', mode)

        # 校验是否成环：编辑时不能把上级设为自身或其下级
        cycle = False
        if is_edit and parent_id:
            pid = int(parent_id)
            if pid == department.pk or pid in _descendant_ids(department):
                cycle = True

        dup = Department.objects.filter(name=name)
        if is_edit:
            dup = dup.exclude(pk=department.pk)

        if not name:
            messages.error(request, '部门名称不能为空。')
        elif dup.exists():
            messages.error(request, f'部门 {name} 已存在。')
        elif cycle:
            messages.error(request, '上级部门不能设为自身或其下级部门。')
        else:
            if is_edit:
                department.name = name
                department.manager = manager
                department.description = description
                department.parent_id = parent_id
                department.save()
                oplog.log(request, 'org', 'update', target=f'部门 {name}',
                          detail=(f'负责人：{manager or "（空）"}；'
                                  f'上级部门：{department.parent.name if department.parent_id else "（无）"}'))
                messages.success(request, f'部门 {name} 更新成功。')
            else:
                created_dept = Department.objects.create(
                    name=name, manager=manager, description=description,
                    parent_id=parent_id,
                )
                oplog.log(request, 'org', 'create', target=f'部门 {name}',
                          detail=(f'负责人：{manager or "（空）"}；'
                                  f'上级部门：{created_dept.parent.name if created_dept.parent_id else "（无）"}'))
                messages.success(request, f'部门 {name} 创建成功。')
            return redirect(f"{reverse('org')}?mode={mode}")

    context = {
        'department': department,
        'departments': Department.objects.all(),
        'is_edit': is_edit,
        'mode': mode,
        'preset_parent': int(preset_parent) if preset_parent else None,
        'page_title': '编辑部门' if is_edit else '新增部门',
        'active': 'org',
    }
    return render(request, 'department_form.html', context)


@perm_required('manage_org')
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    mode = request.GET.get('mode', 'list')
    if request.method == 'POST':
        mode = request.POST.get('mode', mode)
        if department.children.exists():
            messages.error(request, f'部门 {department.name} 下还有下级部门，请先移除或删除下级部门后再删除。')
        elif department.assets.exists():
            n = department.assets.count()
            messages.error(
                request,
                f'部门 {department.name} 下仍挂靠 {n} 项资产，删除将导致这些资产失去所属部门。'
                '请先将资产转移/分配到其它部门后再删除。',
            )
        else:
            from django.db import transaction
            with transaction.atomic():
                dept_name = department.name
                department.delete()
            oplog.log(request, 'org', 'delete', target=f'部门 {dept_name}', detail='删除部门')
            messages.success(request, f'部门 {department.name} 已删除。')
    return redirect(f"{reverse('org')}?mode={mode}")

