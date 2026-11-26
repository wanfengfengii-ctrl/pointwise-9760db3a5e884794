from html import escape


class FormInputError(ValueError):
    pass


def text(value: object) -> str:
    return escape(str(value), quote=True)


def render_document(title: str, body: str) -> str:
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{text(title)}</title>
<link rel="stylesheet" href="/gallery.css">
</head>
<body>
<header><nav aria-label="展馆导航">
<a class="brand" href="/">青榆社区展馆</a>
<a href="/maps">设施录入</a><a href="/proofs">路线校样</a><a href="/guides">导览领取</a>
</nav></header>
<main>{body}</main>
</body>
</html>'''


def render_form(action: str, fields: str, submit_label: str, *, method: str = 'post') -> str:
    return (
        f'<form action="{text(action)}" method="{text(method)}">{fields}'
        f'<button type="submit">{text(submit_label)}</button></form>'
    )


def render_hidden_field(name: str, value: object) -> str:
    return f'<input type="hidden" name="{text(name)}" value="{text(value)}">'


def render_input(name: str, label: str, value: object = '', *, required: bool = True) -> str:
    requirement = ' required' if required else ''
    return (f'<label>{text(label)}<input name="{text(name)}" value="{text(value)}"'
            f'{requirement}></label>')


def render_notice(message: str) -> str:
    return f'<p class="notice" role="alert">{text(message)}</p>'


def parse_ordinal(value: str) -> int | None:
    # SQLite stores identifiers and arrival ordinals as signed 64-bit integers.
    if not value.isascii() or not value.isdecimal() or len(value) > 19:
        return None
    number = int(value)
    return number if number <= 2**63 - 1 else None


def require_identifier(value: str, label: str) -> int:
    number = parse_ordinal(value)
    if number is None or number == 0:
        raise FormInputError(f'{label}须为有效的正整数编号。')
    return number


def render_itinerary(itinerary) -> str:
    stops = ''.join(
        f'<li data-kind="route-stop" data-station="{text(station)}">{text(station)}</li>'
        for station in itinerary.stations
    )
    legs = ''.join(
        f'<li data-kind="leg" data-source="{text(leg.source)}" data-target="{text(leg.target)}"'
        f' data-minutes="{leg.minutes}">{text(leg.source)} → {text(leg.target)} · {leg.minutes} 分钟</li>'
        for leg in itinerary.legs
    )
    segment_list = f'<ol aria-label="步行分段">{legs}</ol>' if legs else ''
    return (
        '<section aria-label="路线明细">'
        f'<p id="route-total" data-minutes="{itinerary.total_minutes}">'
        f'预计共 {itinerary.total_minutes} 分钟</p>'
        f'<ol class="route" aria-label="站序">{stops}</ol>{segment_list}</section>'
    )


def render_attributes(allowed: tuple[str, ...]) -> str:
    labels = text('、'.join(allowed)) if allowed else '普通通道'
    return f'<p>通行条件：{labels}</p>'
