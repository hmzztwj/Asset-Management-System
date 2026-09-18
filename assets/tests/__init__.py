"""assets 应用的自动化测试。

覆盖四个核心面：
- test_requisition.py  领用/归还/删除的资产联动（业务口径的命脉）
- test_permissions.py  三层权限控制（URL 层装饰器）
- test_qr_snapshot.py  二维码快照与免登录信息卡
- test_mail.py         逾期汇总邮件的收件人筛选

运行方式（隔离数据库，不碰真实 data/db.sqlite3）：
    ASSETS_DB_PATH=<临时目录>/db.sqlite3 python manage.py test assets -v 1
"""
