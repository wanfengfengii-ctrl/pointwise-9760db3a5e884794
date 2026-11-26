import json

from gallery.routes.proofs import RouteProof, create_proof
from gallery.signboards.shifts import InvalidShiftInput
from gallery.web.html import (
    render_attributes,
    render_form,
    render_hidden_field,
    render_input,
    render_itinerary,
    require_identifier,
    text,
)


def render_proof_form(revision_id: int | None = None) -> str:
    if revision_id is None:
        revision_field = render_input('revision_id', '设施修订号')
    else:
        revision_field = render_hidden_field('revision_id', revision_id)
        revision_field += f'<p>设施修订 {revision_id}</p>'
    fields = revision_field + ''.join((
        render_input('start', '起站'),
        render_input('end', '终站'),
        render_input('allowed', '访客可用通行属性，用逗号分隔', required=False),
        '<label>班况 JSON（留空办理固定路线）'
        '<textarea name="shifts" rows="7" spellcheck="false" required></textarea></label>'
        '<p class="hint">非空数组，每项含唯一 <code>name</code>、开放通道对 <code>open</code>'
        ' 和观察站读数 <code>signs</code>。</p>',
    ))
    return f'<section><h2>校样路线</h2>{render_form("/proofs", fields, "生成校样")}</section>'


def _render_shift_summary(proof: RouteProof) -> str:
    items = ''.join(
        f'<li data-kind="shift" data-name="{text(shift.name)}">'
        f'{text(shift.name)}：开放 {len(shift.open)} 条通道，'
        f'读牌点 {text("、".join(sorted(shift.signs))) or "（无）"}</li>'
        for shift in proof.shifts
    )
    return f'<h2>班况设置</h2><ol aria-label="班况">{items}</ol>'


def render_proof_page(proof: RouteProof) -> str:
    result = 'reachable' if proof.issuable else 'unreachable'
    body = (
        f'<section id="proof" data-id="{proof.id}" data-revision="{proof.revision_id}"'
        f' data-result="{result}">'
        f'<h1>路线校样 {proof.id}</h1>'
        f'<p><a href="/maps/{proof.revision_id}">设施修订 {proof.revision_id}</a>'
        f' · {text(proof.start)} → {text(proof.end)}</p>'
        f'{render_attributes(proof.allowed)}'
        f'<p><a href="/proofs/{proof.id}">保存此校样地址</a></p>'
    )
    if proof.shifts is not None:
        body += _render_shift_summary(proof)
        if not proof.issuable:
            return body + '<p class="notice">不存在满足按牌分流条件的有限走法，不可发行。</p></section>'
        fields = render_hidden_field('proof_id', proof.id)
        return body + render_form('/guides', fields, '签出导览') + '</section>'

    if proof.itinerary is None:
        return body + '<p class="notice">在这些通行条件下不可达。</p></section>'
    fields = render_hidden_field('proof_id', proof.id)
    return body + render_itinerary(proof.itinerary) + render_form('/guides', fields, '签出导览') + '</section>'


def submit_proof(connection, fields: dict[str, str]) -> str:
    revision_id = require_identifier(fields.get('revision_id', ''), '设施修订号')
    allowed = fields.get('allowed', '')
    tags = [tag.strip() for tag in allowed.split(',')] if allowed.strip() else []
    shift_text = fields.get('shifts', '').strip()
    if not shift_text:
        proof = create_proof(connection, revision_id, fields.get('start', ''), fields.get('end', ''), tags)
        return render_proof_page(proof)
    try:
        shift_rows = json.loads(shift_text)
    except (ValueError, RecursionError) as error:
        raise InvalidShiftInput('班况需要有效的 JSON 数组。') from error
    proof = create_proof(
        connection, revision_id, fields.get('start', ''), fields.get('end', ''), tags, shift_rows
    )
    return render_proof_page(proof)
