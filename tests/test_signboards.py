import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from tests.support import GalleryTestCase, MISSING_ID, map_fields, map_input, passage


def signboard_map():
    return map_input(
        ('S', 'J', 'L', 'R', 'T'),
        [
            passage('S', 'L', 1), passage('S', 'R', 1), passage('S', 'J', 1),
            passage('J', 'L', 1), passage('J', 'R', 1),
            passage('L', 'T', 1), passage('R', 'T', 1),
        ],
    )


def shifts(*, left='左', right='右'):
    return [
        {'name': '甲班',
         'open': [['S', 'L'], ['S', 'R'], ['S', 'J'], ['J', 'L'], ['J', 'R'], ['L', 'T']],
         'signs': {'J': left}},
        {'name': '乙班',
         'open': [['S', 'L'], ['S', 'R'], ['S', 'J'], ['J', 'L'], ['J', 'R'], ['R', 'T']],
         'signs': {'J': right}},
    ]


class SignboardProofTests(GalleryTestCase):
    def create_branch_proof(self, shift_rows):
        saved = self.save(signboard_map())
        fields = saved.form('/proofs')
        fields.update(start='S', end='T', allowed='', shifts=json.dumps(shift_rows, ensure_ascii=False))
        return self.browser.post('/proofs', fields)

    def test_valid_branch_proof_is_issuable(self):
        page = self.create_branch_proof(shifts())
        self.assertEqual(page.status, 201, page.body)
        self.assertEqual(page.by_id['proof']['data-result'], 'reachable')
        self.assertTrue(any(action == '/guides' for action, _ in page.forms))

    def test_invalid_shift_payloads_are_400(self):
        saved = self.save(signboard_map())
        base = saved.form('/proofs')
        base.update(start='S', end='T')
        bad_payloads = [
            [],
            [{'name': '甲班'}],
            [{'name': '甲班', 'open': [['S', 'Z']], 'signs': {}}],
            [{'name': '甲班', 'open': [['S', 'J']], 'signs': {'Z': '左'}}],
        ]
        good = shifts()
        bad_payloads.append([good[0], dict(good[1], name='甲班')])  # 班名重复
        bad_payloads.append([good[0], dict(good[1], signs={'J': '右', 'L': '右'})])  # 观察站不一致
        bad_payloads.append([dict(good[0], name='甲 班'), good[1]])  # 班名含空白
        bad_payloads.append([dict(good[0], signs={'J': '左 '}), good[1]])  # 读数含空白
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                fields = dict(base, shifts=json.dumps(payload, ensure_ascii=False))
                response = self.browser.post('/proofs', fields)
                self.assertEqual(response.status, 400, response.body)
        self.assertEqual(self.rows('SELECT id FROM route_proofs'), [])

    def test_bad_shift_json_is_400(self):
        saved = self.save(signboard_map())
        fields = saved.form('/proofs')
        fields.update(start='S', end='T', shifts='{not json')
        response = self.browser.post('/proofs', fields)
        self.assertEqual(response.status, 400)

    def test_unknown_revision_still_404(self):
        response = self.browser.post('/proofs', {
            'revision_id': MISSING_ID, 'start': 'S', 'end': 'T',
            'shifts': json.dumps(shifts(), ensure_ascii=False),
        })
        self.assertEqual(response.status, 404)

    def test_equal_readings_not_issuable(self):
        page = self.create_branch_proof(shifts(left='左', right='左'))
        self.assertEqual(page.status, 201)
        self.assertEqual(page.by_id['proof']['data-result'], 'unreachable')
        proof_id = page.id_for('proof')
        rejection = self.browser.post('/guides', {'proof_id': proof_id})
        self.assertEqual(rejection.status, 409)
        readback = self.browser.get(f'/proofs/{proof_id}')
        self.assertEqual(readback.by_id['proof']['data-result'], 'unreachable')
        self.assertEqual(self.rows('SELECT id FROM guides'), [])
        self.assertEqual(self.rows('SELECT guide_id FROM guide_directory'), [])

    def test_single_station_shift_proof(self):
        page = self.create_branch_proof(shifts())
        guide = self.publish(page)
        saved = self.browser.get(f"/maps/{guide.by_id['guide']['data-revision']}")
        fields = saved.form('/proofs')
        fields.update(start='T', end='T', shifts=json.dumps(shifts(), ensure_ascii=False))
        proof = self.browser.post('/proofs', fields)
        self.assertEqual(proof.status, 201)
        self.assertEqual(proof.by_id['proof']['data-result'], 'reachable')
        issued = self.publish(proof)
        opened = self.start(issued)
        self.assertEqual(opened.by_id['walk']['data-status'], 'complete')
        self.assertEqual(opened.walk()['arrivals'], ['T'])

    def test_requires_tags_still_apply(self):
        document = map_input(
            ('S', 'J', 'T'),
            [passage('S', 'J', 1, 'stairs'), passage('J', 'T', 1)],
        )
        saved = self.save(document)
        shift_rows = [
            {'name': '甲班', 'open': [['S', 'J'], ['J', 'T']], 'signs': {'J': '左'}},
            {'name': '乙班', 'open': [['S', 'J'], ['J', 'T']], 'signs': {'J': '右'}},
        ]
        fields = saved.form('/proofs')
        fields.update(start='S', end='T', allowed='', shifts=json.dumps(shift_rows, ensure_ascii=False))
        proof = self.browser.post('/proofs', fields)
        self.assertEqual(proof.by_id['proof']['data-result'], 'unreachable')


class SignboardWalkTests(GalleryTestCase):
    def open_at_junction(self):
        saved = self.save(signboard_map())
        fields = saved.form('/proofs')
        fields.update(start='S', end='T', allowed='', shifts=json.dumps(shifts(), ensure_ascii=False))
        proof = self.browser.post('/proofs', fields)
        self.assertEqual(proof.status, 201, proof.body)
        guide = self.publish(proof)
        opened = self.start(self.receive(guide.id_for('guide')))
        return guide, opened

    def test_page_does_not_leak_future_information(self):
        _guide, opened = self.open_at_junction()
        body = opened.body
        self.assertNotIn('甲班', body)
        self.assertNotIn('乙班', body)
        self.assertNotIn('左', body)
        self.assertNotIn('右', body)
        self.assertIn('value="J"', body)

    def test_premature_reading_and_wrong_station_are_409(self):
        _guide, opened = self.open_at_junction()
        walk_id = opened.id_for('walk')
        read_path = f'/walks/{walk_id}/readings'
        # 入口处提前报牌
        premature = self.browser.post(read_path, {'station': 'J', 'ordinal': '0', 'reading': '左'})
        self.assertEqual(premature.status, 409)
        self.assertEqual(premiere_records(premature), [('arrival', 'S', None)])
        # 错站到站
        move_path = f'/walks/{walk_id}/arrivals'
        wrong_station = self.browser.post(move_path, {'station': 'L', 'ordinal': '1'})
        self.assertEqual(wrong_station.status, 409)
        # 正确到 J
        middle = self.browser.post(move_path, opened.form(move_path))
        self.assertEqual(middle.status, 200)
        # 重复提交同一到站表单（序次 1 已入账）-> 409，记录保留
        duplicate = self.browser.post(move_path, {'station': 'J', 'ordinal': '1'})
        self.assertEqual(duplicate.status, 409)
        self.assertEqual(
            premiere_records(duplicate),
            [('arrival', 'S', None), ('arrival', 'J', None)],
        )
        # J 上不存在的读数
        unknown = self.browser.post(read_path, {'station': 'J', 'ordinal': '1', 'reading': '直行'})
        self.assertEqual(unknown.status, 409)
        self.assertEqual(
            premiere_records(unknown),
            [('arrival', 'S', None), ('arrival', 'J', None)],
        )
        # 错站报牌
        wrong_read_station = self.browser.post(read_path, {'station': 'S', 'ordinal': '1', 'reading': '左'})
        self.assertEqual(wrong_read_station.status, 409)
        # 当前动作仍是读牌，表单可继续
        self.assertEqual(unknown.form(read_path)['station'], 'J')
        accepted = self.browser.post(read_path, dict(unknown.form(read_path), reading='左'))
        self.assertEqual(accepted.status, 200)
        self.assertEqual(
            premiere_records(accepted),
            [('arrival', 'S', None), ('arrival', 'J', None), ('report', 'J', '左')],
        )

    def test_identical_history_gives_identical_action(self):
        guide, first = self.open_at_junction()
        second = self.start(self.receive(guide.id_for('guide')))
        move_path = f'/walks/{first.id_for("walk")}/arrivals'
        first_middle = self.browser.post(move_path, first.form(move_path))
        second_path = f'/walks/{second.id_for("walk")}/arrivals'
        second_middle = self.browser.post(second_path, second.form(second_path))
        # 同在 J、报牌历史相同（均为空），动作一致：都是读牌
        self.assertTrue(any(action.endswith('/readings') for action, _ in first_middle.forms))
        self.assertTrue(any(action.endswith('/readings') for action, _ in second_middle.forms))
        for page in (first_middle, second_middle):
            walk_id = page.id_for('walk')
            form = page.form(f'/walks/{walk_id}/readings')
            self.assertEqual((form['station'], form['ordinal']), ('J', '1'))

    def test_old_walk_keeps_original_release_after_reissue(self):
        guide, opened = self.open_at_junction()
        walk_id = opened.id_for('walk')
        move_path = f'/walks/{walk_id}/arrivals'
        middle = self.browser.post(move_path, opened.form(move_path))
        read_path = f'/walks/{walk_id}/readings'
        page_at_junction = self.read_walk(walk_id)

        # 新发行（互换读数、改图），不影响旧走览
        revised_document = signboard_map()
        for passage_row in revised_document['passages']:
            if passage_row['source'] == 'S' and passage_row['target'] == 'J':
                passage_row['minutes'] = 5
        saved = self.save(revised_document)
        fields = saved.form('/proofs')
        fields.update(start='S', end='T', allowed='',
                      shifts=json.dumps(shifts(left='右', right='左'), ensure_ascii=False))
        new_proof = self.browser.post('/proofs', fields)
        self.publish(new_proof)

        # 旧走览仍按原发行解释：J 报“左”仍受理
        form = page_at_junction.form(read_path)
        accepted = self.browser.post(read_path, dict(form, reading='左'))
        self.assertEqual(accepted.status, 200, accepted.body)
        next_move = accepted.form(f'/walks/{walk_id}/arrivals')
        self.assertEqual(next_move['station'], 'L')
        for ordinal, station in ((2, 'L'), (3, 'T')):
            arrived = self.browser.post(f'/walks/{walk_id}/arrivals', next_move)
            self.assertEqual(arrived.status, 200)
            if station != 'T':
                next_move = arrived.form(f'/walks/{walk_id}/arrivals')
        finished = self.read_walk(walk_id)
        self.assertEqual(finished.by_id['walk']['data-status'], 'complete')
        self.assertEqual(finished.by_id['walk']['data-guide'], str(guide.id_for('guide')))
        self.assertEqual(
            premiere_records(finished),
            [('arrival', 'S', None), ('arrival', 'J', None), ('report', 'J', '左'),
             ('arrival', 'L', None), ('arrival', 'T', None)],
        )

    def test_completed_walk_rejects_further_submissions(self):
        _guide, opened = self.open_at_junction()
        walk_id = opened.id_for('walk')
        move_path = f'/walks/{walk_id}/arrivals'
        read_path = f'/walks/{walk_id}/readings'
        self.browser.post(move_path, opened.form(move_path))
        junction = self.read_walk(walk_id)
        self.browser.post(read_path, dict(junction.form(read_path), reading='右'))
        after_read = self.read_walk(walk_id)
        first = self.browser.post(move_path, after_read.form(move_path))
        self.assertEqual(first.form(move_path)['station'], 'T')
        self.browser.post(move_path, first.form(move_path))
        finished = self.read_walk(walk_id)
        self.assertEqual(finished.by_id['walk']['data-status'], 'complete')
        late_arrival = self.browser.post(move_path, {'station': 'T', 'ordinal': '4'})
        self.assertEqual(late_arrival.status, 409)
        late_reading = self.browser.post(read_path, {'station': 'R', 'ordinal': '2', 'reading': '右'})
        self.assertEqual(late_reading.status, 409)

    def test_unknown_walk_reading_is_404(self):
        response = self.browser.post(f'/walks/{MISSING_ID}/readings', {
            'station': 'J', 'ordinal': '1', 'reading': '左',
        })
        self.assertEqual(response.status, 404)

    def test_parallel_readings_only_one_accepted(self):
        _guide, opened = self.open_at_junction()
        walk_id = opened.id_for('walk')
        move_path = f'/walks/{walk_id}/arrivals'
        self.browser.post(move_path, opened.form(move_path))
        junction = self.read_walk(walk_id)
        read_path = f'/walks/{walk_id}/readings'
        payload = dict(junction.form(read_path), reading='左')
        barrier = Barrier(2, timeout=5)

        def submit():
            barrier.wait()
            return self.browser.post(read_path, payload)

        with ThreadPoolExecutor(max_workers=2) as executor:
            replies = [attempt.result(timeout=20) for attempt in
                       [executor.submit(submit) for _ in range(2)]]
        self.assertEqual(sorted(reply.status for reply in replies), [200, 409])
        records = premiere_records(self.read_walk(walk_id))
        self.assertEqual(
            records,
            [('arrival', 'S', None), ('arrival', 'J', None), ('report', 'J', '左')],
        )


def premiere_records(page):
    return [
        (node['data-kind'], node['data-station'], node.get('data-reading'))
        for node in page.elements
        if node.get('data-kind') in {'arrival', 'report'}
    ]
