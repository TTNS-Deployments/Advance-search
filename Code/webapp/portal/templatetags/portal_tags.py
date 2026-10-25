from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "upload": '<path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5"/><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"/>',
    "open": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    "trash": '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7"/><path d="M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5h.01"/>',
    "sync": '<path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5"/><path d="M20 4v4.5h-4.5"/><path d="M20 12a8 8 0 0 1-13.7 5.6L4 15.5"/><path d="M4 20v-4.5h4.5"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/><path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13"/><path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5"/>',
    "folder": '<path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5Z"/>',
    "alert": '<path d="M12 3.5 2.5 20h19Z"/><path d="M12 10v4.5"/><path d="M12 17.5h.01"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "logout": '<path d="M15 4h3.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H15"/><path d="M10 16.5 5.5 12 10 7.5"/><path d="M5.5 12H15"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.8"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3"/>',
    "sparkle": '<path d="M12 3.5 13.8 10.2 20.5 12l-6.7 1.8L12 20.5l-1.8-6.7L3.5 12l6.7-1.8Z"/>',
}

_FILE_COLOURS = {"pdf": ("#d93a2b", "PDF"), "docx": ("#2b5fd9", "DOC"), "xlsx": ("#1d8a4e", "XLS")}


@register.simple_tag
def icon(name, size=20, label=""):
    paths = _ICONS[name]
    aria = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true" focusable="false"'
    return mark_safe(f'<svg class="icon icon-{name}" width="{int(size)}" height="{int(size)}" viewBox="0 0 24 24" '
                     f'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
                     f'stroke-linejoin="round" {aria}>{paths}</svg>')


@register.simple_tag
def file_icon(file_type, size=40):
    colour, label = _FILE_COLOURS.get(file_type, ("#6b7280", "FILE"))
    name = {"pdf": "PDF document", "docx": "Word document", "xlsx": "Excel workbook"}.get(file_type, "File")
    return mark_safe(
        f'<svg class="file-icon file-icon-{escape(file_type)}" width="{int(size)}" height="{int(size * 1.2)}" '
        f'viewBox="0 0 40 48" role="img" aria-label="{name}">'
        f'<path d="M6 2h20l10 10v32a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z" class="fi-bg" '
        f'stroke="{colour}" stroke-width="2"/>'
        f'<path d="M26 2v8a2 2 0 0 0 2 2h8" fill="none" stroke="{colour}" stroke-width="2"/>'
        f'<rect x="0" y="26" width="30" height="13" rx="3" fill="{colour}"/>'
        f'<text x="15" y="35.6" text-anchor="middle" font-family="system-ui, sans-serif" font-size="8.5" '
        f'font-weight="700" fill="#fff">{label}</text></svg>')


@register.filter
def filesize(value):
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "bytes" else f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return ""


@register.filter
def match_level(percent):
    try:
        percent = int(percent)
    except (TypeError, ValueError):
        return "low"
    return "high" if percent >= 70 else "medium" if percent >= 40 else "low"


@register.filter
def snippet_html(segments):
    """Render (text, highlighted) segments safely: text is escaped, highlights wrapped in <mark>."""
    return mark_safe("".join(f"<mark>{escape(t)}</mark>" if h else escape(t) for t, h in segments))
