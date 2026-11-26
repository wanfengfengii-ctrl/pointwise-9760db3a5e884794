import json

from gallery.maps.revisions import MapRevision, save_revision
from gallery.maps.validation import MapInputError
from gallery.web.html import render_form, render_notice, text
from gallery.web.proof_pages import render_proof_form


def render_map_form(values: dict[str, str] | None = None, error: str | None = None) -> str:
    values = values or {}
    stations = text(values.get('stations', '[]'))
    passages = text(values.get('passages', '[]'))
    notice = render_notice(error) if error else ''
    fields = f'''<label>站点 JSON
<textarea name="stations" rows="7" spellcheck="false" required>{stations}</textarea></label>
<p class="hint">每项包含 <code>id</code> 和 <code>enabled</code>。</p>
<label>单向通道 JSON
<textarea name="passages" rows="8" spellcheck="false" required>{passages}</textarea></label>
<p class="hint">每项包含 <code>source</code>、<code>target</code> 和正整数 <code>minutes</code>，可附 <code>requires</code> 标签数组。</p>'''
    return f'<section><h2>录入设施图</h2>{notice}{render_form("/maps", fields, "保存为新修订")}</section>'


def render_revision(revision: MapRevision, *, include_editor: bool = False) -> str:
    active = sum(station.enabled for station in revision.stations)
    summary = (
        f'<section id="revision" data-id="{revision.id}">'
        f'<h1>设施修订 {revision.id}</h1>'
        f'<p>{active} 个启用站，共 {len(revision.stations)} 站、{len(revision.passages)} 条单向通道。</p>'
        f'<p><a href="/maps/{revision.id}">打开本版设施图</a></p></section>'
    )
    editor = ''
    if include_editor:
        values = {
            key: json.dumps(rows, indent=2, ensure_ascii=False)
            for key, rows in revision.document().items()
        }
        editor = render_map_form(values)
    return summary + render_proof_form(revision.id) + editor


def submit_map(connection, fields: dict[str, str]) -> str:
    def decode(field: str, label: str):
        try:
            return json.loads(fields.get(field, ''))
        except (ValueError, RecursionError) as error:
            raise MapInputError(f'{label}需要有效的 JSON 数组。') from error

    revision = save_revision(connection, decode('stations', '站点'), decode('passages', '通道'))
    return render_revision(revision)
