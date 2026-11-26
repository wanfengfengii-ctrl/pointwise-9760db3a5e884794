import json
import tempfile
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

from gallery.web.database import read_transaction
from gallery.web.server import create_server


MISSING_ID = 999999


class Page(HTMLParser):
    def __init__(self, status: int, body: str):
        super().__init__(convert_charrefs=True)
        self.status = status
        self.body = body
        self.elements = []
        self.by_id = {}
        self.forms = []
        self._form = None
        self.feed(body)
        self.close()

    def handle_starttag(self, tag, attributes):
        data = dict(attributes)
        self.elements.append(data)
        if 'id' in data:
            self.by_id[data['id']] = data
        if tag == 'form':
            self._form = (data['action'], {})
            self.forms.append(self._form)
        if tag == 'input' and self._form is not None and 'name' in data:
            self._form[1][data['name']] = data.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self._form = None

    def form(self, action: str) -> dict[str, str]:
        matches = [fields for candidate, fields in self.forms if candidate == action]
        if len(matches) != 1:
            raise AssertionError(f'Expected one form for {action}, observed {len(matches)}')
        return dict(matches[0])

    def id_for(self, element_id: str) -> int:
        return int(self.by_id[element_id]['data-id'])

    def itinerary(self) -> dict:
        stops = [node['data-station'] for node in self.elements if node.get('data-kind') == 'route-stop']
        legs = [
            [node['data-source'], node['data-target'], int(node['data-minutes'])]
            for node in self.elements if node.get('data-kind') == 'leg'
        ]
        return {'stations': stops, 'legs': legs, 'total': int(self.by_id['route-total']['data-minutes'])}

    def walk(self) -> dict:
        info = self.by_id['walk']
        arrivals = [node for node in self.elements if node.get('data-kind') == 'arrival']
        return {
            'guide': int(info['data-guide']),
            'status': info['data-status'],
            'arrivals': [node['data-station'] for node in arrivals],
            'ordinals': [int(node['data-ordinal']) for node in arrivals],
        }


class Browser:
    def __init__(self, port: int):
        self.port = port

    def request(self, method: str, path: str, fields: dict | None = None) -> Page:
        connection = HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            body = urlencode(fields).encode('ascii') if fields is not None else None
            headers = {'Content-Type': 'application/x-www-form-urlencoded'} if fields is not None else {}
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            return Page(response.status, response.read().decode('utf-8'))
        finally:
            connection.close()

    def get(self, path: str) -> Page:
        return self.request('GET', path)

    def post(self, path: str, fields: dict) -> Page:
        return self.request('POST', path, fields)


@contextmanager
def running_gallery(path):
    with create_server(path) as server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        try:
            yield Browser(server.server_port)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError('Gallery HTTP thread did not shut down')


def passage(source: str, target: str, minutes: int, *requires: str) -> dict:
    return {'source': source, 'target': target, 'minutes': minutes, 'requires': list(requires)}


def map_input(stations, passages, *, disabled=()) -> dict:
    return {
        'stations': [{'id': station, 'enabled': station not in disabled} for station in stations],
        'passages': list(passages),
    }


def map_fields(document: dict) -> dict:
    return {key: json.dumps(rows, ensure_ascii=False) for key, rows in document.items()}


def level_map() -> dict:
    return map_input(('S', 'J', 'T'), [passage('S', 'J', 2), passage('J', 'T', 3)])


def record(guide_id: int, status: str, stations: list[str]) -> dict:
    return {'guide': guide_id, 'status': status, 'arrivals': stations, 'ordinals': list(range(len(stations)))}


def scenario(case_id, input_data, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    result = {
        'case_id': case_id,
        'input': input_data,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': paths,
        'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


class GalleryTestCase(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='gallery-test-'))
        self.database = Path(temporary) / 'gallery.sqlite3'
        self.browser = self.enterContext(running_gallery(self.database))

    def rows(self, sql: str, parameters: tuple = ()) -> list[tuple]:
        with read_transaction(self.database) as connection:
            return connection.execute(sql, parameters).fetchall()

    def save(self, document: dict) -> Page:
        page = self.browser.post('/maps', map_fields(document))
        self.assertEqual(page.status, 201, page.body)
        return page

    def proof(self, saved: Page, start='S', end='T', allowed='') -> Page:
        fields = saved.form('/proofs')
        self.assertEqual(fields['revision_id'], str(saved.id_for('revision')))
        fields.update(start=start, end=end, allowed=allowed)
        page = self.browser.post('/proofs', fields)
        self.assertEqual(page.status, 201, page.body)
        return page

    def publish(self, proof: Page) -> Page:
        fields = proof.form('/guides')
        self.assertEqual(fields['proof_id'], str(proof.id_for('proof')))
        issued = self.browser.post('/guides', fields)
        self.assertEqual(issued.status, 201, issued.body)
        return issued

    def receive(self, guide_id: int) -> Page:
        page = self.browser.get(f'/guides/{guide_id}')
        self.assertEqual(page.status, 200, page.body)
        self.assertEqual(page.id_for('guide'), guide_id)
        return page

    def start(self, guide: Page) -> Page:
        fields = guide.form('/walks')
        self.assertEqual(fields['guide_id'], str(guide.id_for('guide')))
        page = self.browser.post('/walks', fields)
        self.assertEqual(page.status, 201, page.body)
        return page

    def read_walk(self, walk_id: int) -> Page:
        page = self.browser.get(f'/walks/{walk_id}')
        self.assertEqual(page.status, 200, page.body)
        self.assertEqual(page.id_for('walk'), walk_id)
        return page

    def arrive(self, page: Page, station: str, ordinal: int) -> Page:
        action = f'/walks/{page.id_for("walk")}/arrivals'
        fields = page.form(action)
        self.assertEqual(fields, {'station': station, 'ordinal': str(ordinal)})
        arrived = self.browser.post(action, fields)
        self.assertEqual(arrived.status, 200, arrived.body)
        return arrived

    def assert_no_arrival_form(self, page: Page):
        self.assertFalse(any(action.endswith('/arrivals') for action, _ in page.forms))
