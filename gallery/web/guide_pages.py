from gallery.issues.directory import get_current_guide_id, publish_guide
from gallery.issues.receipts import GuideReceipt, get_guide_receipt
from gallery.web.html import (
    render_attributes,
    render_form,
    render_hidden_field,
    render_input,
    render_itinerary,
    require_identifier,
    text,
)


def _render_shift_guide(guide: GuideReceipt) -> str:
    items = ''.join(
        f'<li data-kind="shift" data-name="{text(shift.name)}">'
        f'{text(shift.name)}：开放 {len(shift.open)} 条通道，'
        f'读牌点 {text("、".join(sorted(shift.signs))) or "（无）"}</li>'
        for shift in guide.shifts
    )
    fields = render_hidden_field('guide_id', guide.id)
    return (
        f'<section id="guide" data-id="{guide.id}" data-proof="{guide.proof_id}"'
        f' data-revision="{guide.revision_id}" data-routing="signboard">'
        f'<h1>导览发行 {guide.id}</h1>'
        f'<p><a href="/proofs/{guide.proof_id}">校样 {guide.proof_id}</a>'
        f' · 设施修订 {guide.revision_id}</p>'
        f'<p>{text(guide.start)} → {text(guide.end)} · 按现场指示牌分流</p>'
        f'{render_attributes(guide.allowed)}'
        f'<h2>班况设置</h2><ol aria-label="班况">{items}</ol>'
        f'<p><a href="/guides/{guide.id}">保存此发行地址</a></p>'
        f'{render_form("/walks", fields, "开始走览")}</section>'
    )


def _render_guide(guide: GuideReceipt) -> str:
    if guide.shifts is not None:
        return _render_shift_guide(guide)
    fields = render_hidden_field('guide_id', guide.id)
    return (
        f'<section id="guide" data-id="{guide.id}" data-proof="{guide.proof_id}"'
        f' data-revision="{guide.revision_id}" data-routing="fixed">'
        f'<h1>导览发行 {guide.id}</h1>'
        f'<p><a href="/proofs/{guide.proof_id}">校样 {guide.proof_id}</a>'
        f' · 设施修订 {guide.revision_id}</p>'
        f'{render_attributes(guide.allowed)}{render_itinerary(guide.itinerary)}'
        f'<p><a href="/guides/{guide.id}">保存此发行地址</a></p>'
        f'{render_form("/walks", fields, "开始走览")}</section>'
    )


def render_guide_page(connection, guide_id: int) -> str:
    return _render_guide(get_guide_receipt(connection, guide_id))


def submit_publish(connection, fields: dict[str, str]) -> str:
    proof_id = require_identifier(fields.get('proof_id', ''), '校样号')
    return _render_guide(publish_guide(connection, proof_id))


def render_current_guide_link(connection) -> str:
    current = get_current_guide_id(connection)
    if current is None:
        return '<p id="current-guide">当前尚未发行导览。</p>'
    return f'<p><a id="current-guide" data-id="{current}" href="/guides/{current}">领取当前导览 {current}</a></p>'


def render_guide_directory(connection) -> str:
    lookup = render_form('/guides', render_input('guide_id', '发行号'), '按号领取', method='get')
    return f'<section><h1>导览领取</h1>{render_current_guide_link(connection)}{lookup}</section>'
