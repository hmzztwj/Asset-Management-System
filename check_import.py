import os, io, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "assets_system.settings")
django.setup()
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from assets.models import Asset

c = Client()
c.post("/login/", {"username":"admin","password":"admin123"})

n = 0
def check(label, cond):
    global n; n += 1
    print(f"{'OK' if cond else 'FAIL'} [{n}] {label}")

# 1. 模板下载
r = c.get("/library/import/template/")
check("模板下载 200 且为xlsx", r.status_code == 200 and "spreadsheetml" in r["Content-Type"])

# 2. 构造工作簿上传
wb = Workbook()
ws = wb.active
ws.append(["资产编号","资产名称","类别","规格","配置","所属部门","实际使用人","状态","价格","购置日期","存放位置"])
ws.append(["XL-001","导入笔记本A","电脑","14寸","i7/16G","研发一部","张伟","在用",8999,"2023-01-01","A-101"])
ws.append(["XL-002","导入打印机","办公电器","标准","—","市场部","王强","库存",1500,"2023-05-01","C-301"])
ws.append(["XL-001","重复编号B","电脑","","","","","库存",100,"",""])  # 与第一行编号重复 -> 跳过
ws.append(["", "缺失编号C","电脑","","","","","库存",100,"",""])      # 缺编号 -> 警告
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)
up = SimpleUploadedFile("assets.xlsx", buf.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
r = c.post("/library/import/", {"file": up})
h = r.content.decode("utf-8")
check("导入页返回 200", r.status_code == 200)
check("成功导入2条", Asset.objects.filter(asset_id__startswith="XL-").count() == 2)
check("导入结果含「跳过」提示", "跳过" in h)
check("导入结果含「提示」", "提示" in h)
check("重复编号被跳过(XL-001唯一)", Asset.objects.filter(asset_id="XL-001").count() == 1)
a = Asset.objects.filter(asset_id="XL-001").first()
check("导入字段完整(部门/使用人/价格)", a.department.name=="研发一部" and a.user=="张伟" and float(a.price)==8999)
check("缺失编号未导入", not Asset.objects.filter(asset_id="").exists())

# 清理
Asset.objects.filter(asset_id__startswith="XL-").delete()
print(f"\n== {n} 项 ==")
