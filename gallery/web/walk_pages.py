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


def _render_walk(view: WalkView, *, conflict: str | None = None) -> str:
    record = view.record
    status_label = '已完成' if record.status == WalkStatus.COMPLETE else '在走'
    arrivals = ''.join(
        f'<li data-kind="arrival" data-ordinal="{index}" data-station="{text(station)}">'
        f'{text(station)}</li>'
        for index, station in enumerate(record.arrivals)
    )
    body = (
        f'<section id="walk" data-id="{record.id}" data-guide="{record.guide_id}"'
        f' data-status="{record.status.value}">'
        f'<h1>走览 {record.id}</h1>'
        f'<p><a href="/guides/{record.guide_id}">原发行 {record.guide_id}</a> · {status_label}</p>'
    )
    if conflict:
        body += render_notice(conflict)
    body += (
        f'<p>当前站：<strong>{text(record.arrivals[-1])}</strong></p>'
        f'<h2>实际到站</h2><ol start="0" aria-label="实际到站">{arrivals}</ol>'
        f'<p><a href="/walks/{record.id}">保存此走览地址</a></p></section>'
    )
    if view.next_leg is None:
        return body

    leg = view.next_leg
    fields = render_hidden_field('station', leg.target) + render_hidden_field('ordinal', view.next_ordinal)
    return body + (
        f'<section class="next-stop" id="next-stop" data-minutes="{leg.minutes}">'
        f'<h2>下一站 {text(leg.target)}</h2><p>预计步行 {leg.minutes} 分钟。</p>'
        f'{render_form(f"/walks/{record.id}/arrivals", fields, "确认已到达")}</section>'
    )


def submit_walk_start(connection, fields: dict[str, str]) -> str:
    guide_id = require_identifier(fields.get('guide_id', ''), '发行号')
    return _render_walk(start_walk(connection, guide_id))


def submit_arrival(connection, walk_id: int, fields: dict[str, str]) -> str:
    station = fields.get('station', '')
    ordinal = parse_ordinal(fields.get('ordinal', ''))
    return _render_walk(confirm_arrival(connection, walk_id, station, ordinal))


def render_walk_page(connection, walk_id: int) -> str:
    return _render_walk(get_walk_view(connection, walk_id))


def render_arrival_conflict(connection, walk_id: int, message: str) -> str:
    return _render_walk(get_walk_view(connection, walk_id), conflict=message)


def render_walk_lookup() -> str:
    return render_form('/walks', render_input('walk_id', '走览号'), '查走览', method='get')
