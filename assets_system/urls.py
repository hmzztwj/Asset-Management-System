"""URL configuration for the asset management system."""
from django.contrib import admin
from django.templatetags.static import static
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('assets.urls')),
    # 浏览器默认还会请求 /favicon.ico（尤其 /admin/ 未声明 SVG 图标），
    # 301 到静态目录里的 SVG，消掉日志里的 404 刷屏。
    path('favicon.ico', RedirectView.as_view(url=static('img/favicon.svg'), permanent=True)),
]
