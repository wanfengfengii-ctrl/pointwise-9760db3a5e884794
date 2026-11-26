from gallery.signboards.planner import CompleteAction, MoveAction, ReadAction
from gallery.signboards.walking import (
    SignboardWalkView,
    accept_signboard_reading,
    confirm_signboard_arrival,
    get_signboard_view,
)
from gallery.walks.arrival import confirm_arrival
from gallery.walks.completion import WalkStatus
from gallery.walks.history import WalkView, get_walk_view
from gallery.walks.start import start_walk
from gallery.web.html import (
    parse_ordinal,
    render_form,
    render_hidden_field,
    render_input,
    render_notice,
    require_identifier,
    text,
)


def _render_timeline(record) -> str:
    items = []
    for kind, payload in record.timeline():
        if kind == 'arrival':
            items.append(
                f'<li data-kind="arrival" data-ordinal="{payload["ordinal"]}"'
                f' data-station="{text(payload["station"])}">{text(payload["station"])}</li>'
            )
        else:
            items.append(
                f'<li data-kind="report" data-station="{text(payload["station"])}"'
                f' data-reading="{text(payload["reading"])}">'
                f'{text(payload["station"])} 报牌：{text(payload["reading"])}</li>'
            )
    return f'<ol start="0" aria-label="实际记录">{"".join(items)}</ol>'


def _walk_header(record) -> str:
    status_label = '已完成' if record.status == WalkStatus.COMPLETE else '在走'
    return (
        f'<section id="walk" data-id="{record.id}" data-guide="{record.guide_id}"'
        f' data-status="{record.status.value}">'
        f'<h1>走览 {record.id}</h1>'
        f'<p><a href="/guides/{record.guide_id}">原发行 {record.guide_id}</a> · {status_label}</p>'
        f'<p>当前站：<strong>{text(record.arrivals[-1])}</strong></p>'
        f'<h2>实际到站与报牌</h2>{_render_timeline(record)}'
        f'<p><a href="/walks/{record.id}">保存此走览地址</a></p></section>'
    )


def _render_fixed_walk(view: WalkView, *, conflict: str | None = None) -> str:
    record = view.record
    body = _walk_header(record)
    if conflict:
        body += render_notice(conflict)
    if view.next_leg is None:
        return body
    leg = view.next_leg
    fields = render_hidden_field('station', leg.target) + render_hidden_field('ordinal', view.next_ordinal)
    return body + (
        f'<section class="next-stop" id="next-stop" data-minutes="{leg.minutes}">'
        f'<h2>下一站 {text(leg.target)}</h2><p>预计步行 {leg.minutes} 分钟。</p>'
        f'{render_form(f"/walks/{record.id}/arrivals", fields, "确认已到达")}</section>'
    )


def _render_signboard_walk(view: SignboardWalkView, *, conflict: str | None = None) -> str:
    record = view.record
    body = _walk_header(record)
    if conflict:
        body += render_notice(conflict)
    action = view.action
    if isinstance(action, CompleteAction):
        return body + '<section class="next-stop"><h2>已抵达终厅，走览完成。</h2></section>'
    if isinstance(action, MoveAction):
        fields = (
            render_hidden_field('station', action.station)
            + render_hidden_field('ordinal', view.next_ordinal)
        )
        return body + (
            f'<section class="next-stop" id="next-stop" data-minutes="{action.minutes}">'
            f'<h2>下一站 {text(action.station)}</h2><p>预计步行 {action.minutes} 分钟。</p>'
            f'{render_form(f"/walks/{record.id}/arrivals", fields, "确认已到达")}</section>'
        )
    if isinstance(action, ReadAction):
        ordinal = len(record.arrivals) - 1
        fields = (
            render_hidden_field('station', action.station)
            + render_hidden_field('ordinal', ordinal)
            + render_input('reading', '本站指示牌读数')
        )
        return body + (
            f'<section class="next-stop" id="next-reading" data-station="{text(action.station)}">'
            f'<h2>请在 {text(action.station)} 读牌</h2>'
            f'{render_form(f"/walks/{record.id}/readings", fields, "报告读数")}</section>'
        )
    return body


def _is_signboard(connection, walk_id: int) -> bool:
    from gallery.issues.receipts import get_guide_receipt
    from gallery.walks.history import get_walk_record

    record = get_walk_record(connection, walk_id)
    guide = get_guide_receipt(connection, record.guide_id)
    return guide.shifts is not None


def _render(connection, walk_id: int, *, conflict: str | None = None) -> str:
    if _is_signboard(connection, walk_id):
        return _render_signboard_walk(get_signboard_view(connection, walk_id), conflict=conflict)
    return _render_fixed_walk(get_walk_view(connection, walk_id), conflict=conflict)


def submit_walk_start(connection, fields: dict[str, str]) -> str:
    guide_id = require_identifier(fields.get('guide_id', ''), '发行号')
    view = start_walk(connection, guide_id)
    if isinstance(view, SignboardWalkView):
        return _render_signboard_walk(view)
    return _render_fixed_walk(view)


def submit_arrival(connection, walk_id: int, fields: dict[str, str]) -> str:
    station = fields.get('station', '')
    ordinal = parse_ordinal(fields.get('ordinal', ''))
    if _is_signboard(connection, walk_id):
        return _render_signboard_walk(confirm_signboard_arrival(connection, walk_id, station, ordinal))
    return _render_fixed_walk(confirm_arrival(connection, walk_id, station, ordinal))


def submit_reading(connection, walk_id: int, fields: dict[str, str]) -> str:
    station = fields.get('station', '')
    ordinal = parse_ordinal(fields.get('ordinal', ''))
    reading = fields.get('reading', '')
    return _render_signboard_walk(
        accept_signboard_reading(connection, walk_id, station, ordinal, reading)
    )


def render_walk_page(connection, walk_id: int) -> str:
    return _render(connection, walk_id)


def render_arrival_conflict(connection, walk_id: int, message: str) -> str:
    return _render(connection, walk_id, conflict=message)


def render_walk_lookup() -> str:
    return render_form('/walks', render_input('walk_id', '走览号'), '查走览', method='get')
