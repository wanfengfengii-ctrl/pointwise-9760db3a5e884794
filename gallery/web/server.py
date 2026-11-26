import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from gallery.issues.admission import UnknownProof, UnreachableProof
from gallery.issues.receipts import UnknownGuide
from gallery.maps.revisions import get_revision
from gallery.maps.seed import seed_demo_map
from gallery.maps.validation import MapInputError
from gallery.routes.proofs import InvalidProofAttributes, InvalidProofEndpoint, UnknownRevision, get_proof
from gallery.signboards.shifts import InvalidShiftInput
from gallery.signboards.walking import WalkConflict
from gallery.walks.arrival import ArrivalConflict
from gallery.walks.history import UnknownWalk
from gallery.web.database import initialize_database, read_transaction, write_transaction
from gallery.web.guide_pages import (
    render_current_guide_link,
    render_guide_directory,
    render_guide_page,
    submit_publish,
)
from gallery.web.html import FormInputError, render_document, render_notice, require_identifier
from gallery.web.map_forms import render_map_form, render_revision, submit_map
from gallery.web.proof_pages import render_proof_form, render_proof_page, submit_proof
from gallery.web.walk_pages import (
    render_arrival_conflict,
    render_walk_lookup,
    render_walk_page,
    submit_arrival,
    submit_reading,
    submit_walk_start,
)


STYLESHEET = Path(__file__).with_name('gallery.css')
MAX_FORM_BYTES = 1_048_576
NOT_FOUND = (UnknownGuide, UnknownProof, UnknownRevision, UnknownWalk)


class UnknownPage(LookupError):
    pass


def _fields(encoded: str) -> dict[str, str]:
    try:
        values = parse_qs(encoded, keep_blank_values=True, errors='strict', max_num_fields=32)
    except ValueError as error:
        raise FormInputError('表单编码无效。') from error
    for name, items in values.items():
        if len(items) != 1:
            raise FormInputError(f'表单字段 {name} 重复。')
    return {name: items[0] for name, items in values.items()}


def initialize_demo_database(path):
    initialize_database(path)
    with write_transaction(path) as connection:
        return seed_demo_map(connection)


class GalleryRequestHandler(BaseHTTPRequestHandler):
    def _send(self, status: HTTPStatus, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

    def _html(self, status: HTTPStatus, body: str) -> None:
        page = render_document('青榆社区展馆导览', body)
        self._send(status, page.encode('utf-8'), 'text/html; charset=utf-8')

    def _error_page(self, status: HTTPStatus, error: Exception) -> None:
        titles = {400: '请核对输入', 404: '未找到', 409: '暂无法办理', 413: '表单过大', 415: '表单格式不支持'}
        self._html(status, f'<h1>{titles[status]}</h1>{render_notice(str(error))}')

    def _request_url(self):
        try:
            return urlsplit(self.path)
        except ValueError as error:
            raise FormInputError('请求地址无效。') from error

    def _read_form(self) -> dict[str, str]:
        if self.headers.get_content_type() != 'application/x-www-form-urlencoded':
            raise UnsupportedForm('请用网页表单提交。')
        length = self.headers.get('Content-Length', '')
        if not length.isascii() or not length.isdecimal():
            raise FormInputError('缺少有效的表单长度。')
        # Bound the conversion before reading the request body.
        length = length.lstrip('0') or '0'
        if len(length) > len(str(MAX_FORM_BYTES)) or int(length) > MAX_FORM_BYTES:
            raise OversizedForm('表单超过 1 MiB。')
        data = self.rfile.read(int(length))
        if len(data) != int(length):
            raise FormInputError('表单未传输完整。')
        try:
            return _fields(data.decode('utf-8'))
        except UnicodeDecodeError as error:
            raise FormInputError('表单需要 UTF-8 编码。') from error

    def _get_page(self, connection, path: str, query: dict[str, str]) -> str:
        if path == '/':
            return (
                '<section><h1>展馆导览</h1>'
                f'{render_current_guide_link(connection)}'
                '<p><a href="/maps">录入设施图</a> · <a href="/proofs">校样固定路线</a></p>'
                f'<h2>走览记录</h2>{render_walk_lookup()}</section>'
            )
        if path == '/maps':
            return '<h1>设施制图</h1>' + render_map_form()
        if path == '/proofs':
            return '<h1>路线校样</h1>' + render_proof_form()
        if path == '/guides':
            if 'guide_id' in query:
                guide_id = require_identifier(query['guide_id'], '发行号')
                return render_guide_page(connection, guide_id)
            return render_guide_directory(connection)
        if path == '/walks':
            if 'walk_id' in query:
                walk_id = require_identifier(query['walk_id'], '走览号')
                return render_walk_page(connection, walk_id)
            return '<section><h1>走览记录</h1>' + render_walk_lookup() + '</section>'

        parts = path.split('/')
        if len(parts) != 3 or parts[1] not in {'maps', 'proofs', 'guides', 'walks'}:
            raise UnknownPage('没有这个页面。')
        resource, identifier = parts[1:]
        resource_id = require_identifier(identifier, '资源编号')
        if resource == 'maps':
            revision = get_revision(connection, resource_id)
            if revision is None:
                raise UnknownRevision(f'没有设施修订 {resource_id}。')
            return render_revision(revision, include_editor=True)
        if resource == 'proofs':
            proof = get_proof(connection, resource_id)
            if proof is None:
                raise UnknownProof(f'没有校样 {resource_id}。')
            return render_proof_page(proof)
        if resource == 'guides':
            return render_guide_page(connection, resource_id)
        return render_walk_page(connection, resource_id)

    def do_GET(self) -> None:
        try:
            url = self._request_url()
            if url.path == '/gallery.css':
                self._send(HTTPStatus.OK, STYLESHEET.read_bytes(), 'text/css; charset=utf-8')
                return
            with read_transaction(self.server.database) as connection:
                page = self._get_page(connection, url.path, _fields(url.query))
            self._html(HTTPStatus.OK, page)
        except FormInputError as error:
            self._error_page(HTTPStatus.BAD_REQUEST, error)
        except (UnknownPage, *NOT_FOUND) as error:
            self._error_page(HTTPStatus.NOT_FOUND, error)

    def _post_page(self, path: str, fields: dict[str, str]) -> tuple[HTTPStatus, str]:
        creation_pages = {
            '/maps': submit_map,
            '/proofs': submit_proof,
            '/guides': submit_publish,
            '/walks': submit_walk_start,
        }
        create = creation_pages.get(path)
        if create is not None:
            with write_transaction(self.server.database) as connection:
                return HTTPStatus.CREATED, create(connection, fields)

        parts = path.split('/')
        if len(parts) != 4 or parts[1] != 'walks' or parts[3] not in {'arrivals', 'readings'}:
            raise UnknownPage('没有这个提交入口。')
        walk_id = require_identifier(parts[2], '走览号')
        try:
            with write_transaction(self.server.database) as connection:
                if parts[3] == 'readings':
                    return HTTPStatus.OK, submit_reading(connection, walk_id, fields)
                return HTTPStatus.OK, submit_arrival(connection, walk_id, fields)
        except (ArrivalConflict, WalkConflict) as error:
            with read_transaction(self.server.database) as connection:
                return HTTPStatus.CONFLICT, render_arrival_conflict(connection, walk_id, str(error))

    def do_POST(self) -> None:
        fields = {}
        try:
            url = self._request_url()
            fields = self._read_form()
            status, body = self._post_page(url.path, fields)
            self._html(status, body)
        except MapInputError as error:
            self._html(HTTPStatus.BAD_REQUEST, '<h1>设施制图</h1>' + render_map_form(fields, str(error)))
        except (FormInputError, InvalidProofEndpoint, InvalidProofAttributes, InvalidShiftInput) as error:
            self._error_page(HTTPStatus.BAD_REQUEST, error)
        except (UnknownPage, *NOT_FOUND) as error:
            self._error_page(HTTPStatus.NOT_FOUND, error)
        except UnreachableProof as error:
            self._error_page(HTTPStatus.CONFLICT, error)
        except OversizedForm as error:
            self._error_page(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, error)
        except UnsupportedForm as error:
            self._error_page(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, error)


class OversizedForm(ValueError):
    pass


class UnsupportedForm(ValueError):
    pass


class GalleryServer(ThreadingHTTPServer):
    def __init__(self, database, port: int):
        self.database = database
        super().__init__(('127.0.0.1', port), GalleryRequestHandler)


def create_server(database, port: int = 0) -> GalleryServer:
    initialize_database(database)
    return GalleryServer(database, port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='青榆社区展馆导览服务')
    parser.add_argument('--database', default='gallery.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seed', help='空设施库导入演示图')
    serve = commands.add_parser('serve', help='启动本机 HTTP 服务')
    serve.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == 'seed':
        revision = initialize_demo_database(args.database)
        if revision is None:
            print('已有设施修订。')
        else:
            print(f'演示设施修订 {revision.id}：/maps/{revision.id}')
        return 0

    with create_server(args.database, args.port) as server:
        print(f'http://127.0.0.1:{server.server_port}/', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
