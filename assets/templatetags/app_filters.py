from django import template

from ..permissions import user_has_perm

register = template.Library()


@register.filter
def has_perm(user, perm):
    """判断用户是否拥有某权限，模板用法：{{ user|has_perm:'manage_assets' }}"""
    return user_has_perm(user, perm)


@register.filter
def split(value, sep=','):
    """Split a string into a list by the given separator."""
    if value is None:
        return []
    return str(value).split(sep)


@register.filter
def getattr(value, arg):
    """返回对象的属性值（如 {{ obj|getattr:'field' }}）。"""
    try:
        return getattr(value, arg)
    except Exception:
        return ''
