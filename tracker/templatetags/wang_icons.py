import os
import re
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()

_CORE_ICONS = set()
_svg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'templates', 'tracker', '_svg_symbols.html')
try:
    with open(_svg_path, 'r', encoding='utf-8') as f:
        _CORE_ICONS = set(re.findall(r'id="icon-([^"]+)"', f.read()))
except Exception:
    pass

def get_icon_href(name):
    if not name:
        return ""
    name_str = str(name).strip()
    if name_str in _CORE_ICONS:
        return f"#icon-{escape(name_str)}"
    return f"/static/img/icons.svg#icon-{escape(name_str)}"

@register.simple_tag
def icon_href(name):
    return get_icon_href(name)

@register.simple_tag
def icon(name, extra_class="", **kwargs):
    if not name:
        return ""
    href = get_icon_href(name)
    cls = f"icon {extra_class}".strip() if extra_class else "icon"
    style_attr = f' style="{escape(kwargs["style"])}"' if "style" in kwargs else ""
    id_attr = f' id="{escape(kwargs["id"])}"' if "id" in kwargs else ""
    return mark_safe(f'<svg class="{cls}"{id_attr}{style_attr} aria-hidden="true"><use href="{href}"></use></svg>')

@register.filter(name="as_icon")
def as_icon(name, extra_class=""):
    return icon(name, extra_class=extra_class)

