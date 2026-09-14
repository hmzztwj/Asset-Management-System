"""操作日志助手。

对外只暴露两个函数：

- ``log(request, category, action, target='', detail='')``
  写入一条操作日志。**内部吞掉所有异常**，日志失败绝不影响主业务流程
  （例如日志表被锁、字段超长等，都不应该让用户的正常操作报错）。

- ``diff(old, new, labels)``
  按字段对比前后快照，生成"字段：旧值 → 新值"的可读明细，用于资产编辑留痕。

用法示例::

    from . import oplog
    oplog.log(request, 'asset', 'update', target=f'{asset.asset_id} {asset.name}',
              detail=oplog.diff(before, after, {'name': '资产名称'}))
"""
from .models import OperationLog

# 单条明细最长保留字符数，避免异常输入把日志表撑爆
_DETAIL_LIMIT = 4000


def client_ip(request):
    """取客户端 IP；经过反向代理时优先用 X-Forwarded-For 的第一段。"""
    if request is None:
        return ''
    meta = getattr(request, 'META', None) or {}
    xff = (meta.get('HTTP_X_FORWARDED_FOR') or '').strip()
    if xff:
        return xff.split(',')[0].strip()[:45]
    return (meta.get('REMOTE_ADDR') or '')[:45]


def operator_name(request):
    """操作人显示名：优先姓名，其次用户名。"""
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return ''
    return (getattr(user, 'first_name', '') or getattr(user, 'username', '') or '')[:50]


def log(request, category, action, target='', detail=''):
    """写入一条操作日志（永不抛异常）。"""
    try:
        OperationLog.objects.create(
            category=category,
            action=action,
            target=str(target or '')[:200],
            detail=str(detail or '')[:_DETAIL_LIMIT],
            operator=operator_name(request),
            ip=client_ip(request),
        )
    except Exception:  # noqa: BLE001 — 日志失败不能影响主流程
        pass


def diff(old, new, labels):
    """对比前后快照，返回"字段：旧值 → 新值"明细。

    :param old: 变更前的 {字段名: 值} 字典
    :param new: 变更后的 {字段名: 值} 字典
    :param labels: {字段名: 中文标签}，只有出现在这里的字段才会被对比
    """
    def norm(v):
        if v is None:
            return ''
        return str(v).strip()

    parts = []
    for field, label in labels.items():
        before, after = norm(old.get(field)), norm(new.get(field))
        if before != after:
            parts.append(f'{label}：{before or "（空）"} → {after or "（空）"}')
    return '；'.join(parts)
