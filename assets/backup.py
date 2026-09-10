"""数据备份核心逻辑。

以 SQLite 在线备份 API（Connection.backup）生成整库一致性快照（*.sqlite3），
并负责：备份目录解析、超出上限自动清理最旧文件、按备份恢复数据库。

说明：
- 备份为"整库"级别，包含资产、部门、领用、变更、用户、角色等全部数据，
  恢复时直接换回文件即可，不存在外键关联断裂问题。
- 文件名以日期为主：YYYY-MM-DD.sqlite3；同一天再次备份则追加时间，避免相互覆盖。
"""
import os
import glob
import shutil
import sqlite3
from datetime import datetime, time

from django.conf import settings
from django.db import connections
from django.utils import timezone


MAX_BACKUPS = 9  # backup 目录内最多保留的备份份数，超出自动删除最旧的


def get_backup_dir():
    """解析并确保备份目录存在。相对路径按项目根目录处理。"""
    from .models import BackupSetting

    raw = (BackupSetting.get_solo().backup_dir or 'backup').strip()
    path = raw if os.path.isabs(raw) else os.path.join(str(settings.BASE_DIR), raw)
    os.makedirs(path, exist_ok=True)
    return path


def _db_path():
    """当前数据库文件路径（遵循 ASSETS_DB_PATH 覆盖）。"""
    return connections['default'].settings_dict['NAME']


def list_backups():
    """返回备份文件列表（按修改时间倒序）。"""
    bdir = get_backup_dir()
    items = []
    for path in glob.glob(os.path.join(bdir, '*.sqlite3')):
        st = os.stat(path)
        items.append({
            'name': os.path.basename(path),
            'path': path,
            'size': st.st_size,
            'mtime': datetime.fromtimestamp(st.st_mtime),
        })
    items.sort(key=lambda x: x['mtime'], reverse=True)
    return items


def cleanup_old(bdir=None):
    """备份超过 MAX_BACKUPS 份时删除最旧的。返回被删除的文件名列表。"""
    bdir = bdir or get_backup_dir()
    files = glob.glob(os.path.join(bdir, '*.sqlite3'))
    files.sort(key=os.path.getmtime)  # 旧 -> 新
    removed = []
    while len(files) > MAX_BACKUPS:
        victim = files.pop(0)
        try:
            os.remove(victim)
            removed.append(os.path.basename(victim))
        except OSError:
            pass
    return removed


def create_backup(reason='manual'):
    """生成一份整库一致性备份，返回 (文件名, 完整路径)。"""
    from .models import BackupSetting

    bdir = get_backup_dir()
    now = timezone.localtime()

    # 文件名以日期为主；同日再次备份时追加时间，避免相互覆盖
    fname = f'{now:%Y-%m-%d}.sqlite3'
    dest = os.path.join(bdir, fname)
    if os.path.exists(dest):
        fname = f'{now:%Y-%m-%d_%H%M%S}.sqlite3'
        dest = os.path.join(bdir, fname)
        seq = 2
        while os.path.exists(dest):
            fname = f'{now:%Y-%m-%d_%H%M%S}_{seq}.sqlite3'
            dest = os.path.join(bdir, fname)
            seq += 1

    # 用 SQLite 在线备份 API 复制，保证一致性（即使有并发写）
    src = sqlite3.connect(_db_path())
    try:
        dst = sqlite3.connect(dest)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    cleanup_old(bdir)

    setting = BackupSetting.get_solo()
    setting.last_backup_at = timezone.now()
    setting.save(update_fields=['last_backup_at'])

    return fname, dest


def restore_backup(name):
    """从指定备份恢复整库。恢复前会先把当前库另存一份以防误操作。"""
    from .models import BackupSetting

    bdir = get_backup_dir()
    src = os.path.join(bdir, os.path.basename(name))
    if not os.path.exists(src):
        raise FileNotFoundError(name)

    # 记录当前备份设置（恢复整库会连同设置表一并被旧值覆盖，稍后写回）
    cur = BackupSetting.get_solo()
    keep = {
        'auto_enabled': cur.auto_enabled,
        'interval': cur.interval,
        'schedule_time': cur.schedule_time,
        'backup_dir': cur.backup_dir,
    }

    # 恢复前先备份当前库
    create_backup(reason='before_restore')

    # 关闭所有连接（Windows 下否则无法覆盖文件），再替换数据库
    connections.close_all()
    shutil.copyfile(src, _db_path())
    connections.close_all()

    # 写回备份设置，避免被旧备份里的设置回滚
    setting = BackupSetting.get_solo()
    setting.auto_enabled = keep['auto_enabled']
    setting.interval = keep['interval']
    setting.schedule_time = keep['schedule_time']
    setting.backup_dir = keep['backup_dir']
    setting.save()

    return True


def scheduled_backup_due():
    """定时型自动备份是否到期（不影响写操作，纯按时间判断）。

    判断顺序：
    1. 未开启自动备份 → 否；
    2. 频率为「每次数据变动」→ 否（该模式由中间件按请求方法单独处理）；
    3. 当前时间尚未到达设定的备份时刻 → 否（到点前不备份）；
    4. 按自然日计算间隔：
       - 每天定时：今天已经备过 → 否；
       - 每隔 N 天：距上次备份不足 N 个自然日 → 否；
    5. 其余情况 → 是，触发一次备份。

    该函数只读取时间，不关心请求是读还是写，因此在任意一次访问
    （包括仅仅打开页面）时都会被调用，用于判断是否该补一次备份。
    """
    from .models import BackupSetting

    setting = BackupSetting.get_solo()
    if not setting.auto_enabled or setting.interval == 'on_change':
        return False

    now = timezone.localtime()
    # 设定的每日备份时刻，未配置时按 22:00 兜底
    sched = setting.schedule_time or time(22, 0)
    if now.time() < sched:
        return False

    last = setting.last_backup_at
    if last is None:
        return True  # 从未备份过，到点即补一份

    last_day = timezone.localtime(last).date()
    if setting.interval == 'daily':
        return last_day < now.date()

    days = {'3d': 3, '7d': 7}.get(setting.interval, 1)
    return (now.date() - last_day).days >= days


def human_size(num):
    """字节数转可读大小。"""
    if num < 1024:
        return f'{num} B'
    for unit in ('KB', 'MB', 'GB'):
        num /= 1024.0
        if num < 1024 or unit == 'GB':
            return f'{num:.1f} {unit}'
