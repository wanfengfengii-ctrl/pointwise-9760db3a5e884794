from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from tests.support import GalleryTestCase, MISSING_ID, level_map, map_input, passage, record, scenario


class WalkTests(GalleryTestCase):
    def level_guide(self):
        issued = self.publish(self.proof(self.save(level_map())))
        return self.receive(issued.id_for('guide'))

    def test_follow_guide(self):
        guide = self.level_guide()
        guide_id = guide.id_for('guide')
        opened = self.start(guide)
        walk_id = opened.id_for('walk')
        self.assertEqual(opened.walk(), record(guide_id, 'walking', ['S']))
        self.assertEqual(opened.by_id['next-stop']['data-minutes'], '2')
        middle = self.arrive(opened, 'J', 1)
        self.assertEqual(middle.walk(), record(guide_id, 'walking', ['S', 'J']))
        self.assertEqual(middle.by_id['next-stop']['data-minutes'], '3')
        end = self.arrive(middle, 'T', 2)
        expected = record(guide_id, 'complete', ['S', 'J', 'T'])
        self.assertEqual(end.walk(), expected)
        self.assert_no_arrival_form(end)
        readback = self.read_walk(walk_id)
        self.assertEqual(readback.walk(), expected)
        self.assert_no_arrival_form(readback)
        scenario(
            'n6', {'guide': guide_id, 'arrivals_submitted': ['J', 'T']},
            expected, end.walk(), expected, readback.walk(),
            ['gallery/walks/start.py', 'gallery/walks/arrival.py', 'gallery/walks/history.py'],
            '起点在序次 0 入账，随后按表单先后记入 J 和 T，终站受理即完成。',
        )

    def test_skip_and_stale_form(self):
        guide = self.level_guide()
        guide_id = guide.id_for('guide')
        opened = self.start(guide)
        walk_id = opened.id_for('walk')
        action = f'/walks/{walk_id}/arrivals'
        old = opened.form(action)
        skip = self.browser.post(action, {'station': 'T', 'ordinal': '2'})
        self.assertEqual(skip.status, 409)
        self.assertEqual(self.read_walk(walk_id).walk(), record(guide_id, 'walking', ['S']))
        self.arrive(opened, 'J', 1)
        stale = self.browser.post(action, old)
        self.assertEqual(stale.status, 409)
        self.assertEqual(self.read_walk(walk_id).walk(), record(guide_id, 'walking', ['S', 'J']))

    def test_unknown_guide(self):
        rejected = self.browser.post('/walks', {'guide_id': MISSING_ID})
        self.assertEqual(rejected.status, 404)
        self.assertEqual(self.rows('SELECT id FROM walks'), [])
        self.assertEqual(self.rows('SELECT walk_id FROM walk_arrivals'), [])

    def test_single_station(self):
        proof = self.proof(self.save(level_map()), start='J', end='J')
        self.assertEqual(proof.itinerary(), {'stations': ['J'], 'legs': [], 'total': 0})
        guide = self.publish(proof)
        opened = self.start(guide)
        walkthrough = record(guide.id_for('guide'), 'complete', ['J'])
        self.assertEqual(opened.walk(), walkthrough)
        self.assert_no_arrival_form(opened)
        self.assertEqual(self.read_walk(opened.id_for('walk')).walk(), walkthrough)

    def test_independent_walks(self):
        guide = self.level_guide()
        guide_id = guide.id_for('guide')
        first = self.start(guide)
        second = self.start(guide)
        self.assertNotEqual(first.id_for('walk'), second.id_for('walk'))
        self.assertEqual(self.arrive(first, 'J', 1).walk(), record(guide_id, 'walking', ['S', 'J']))
        unaffected = self.read_walk(second.id_for('walk'))
        self.assertEqual(unaffected.walk(), record(guide_id, 'walking', ['S']))
        self.assertEqual(unaffected.form(f'/walks/{second.id_for("walk")}/arrivals'), {
            'station': 'J', 'ordinal': '1',
        })

    def test_original_after_reissue(self):
        original = self.level_guide()
        original_id = original.id_for('guide')
        opened = self.start(original)
        walk_id = opened.id_for('walk')
        middle = self.arrive(opened, 'J', 1)
        replacement = map_input(('S', 'K', 'T'), [passage('S', 'K', 4), passage('K', 'T', 1)])
        new = self.publish(self.proof(self.save(replacement)))
        self.assertEqual(self.browser.get('/guides').id_for('current-guide'), new.id_for('guide'))
        self.assertEqual(self.start(new).by_id['walk']['data-guide'], str(new.id_for('guide')))
        for _ in range(2):
            self.assertEqual(self.read_walk(walk_id).walk(), record(original_id, 'walking', ['S', 'J']))
        self.assertEqual(self.receive(original_id).itinerary()['stations'], ['S', 'J', 'T'])
        self.arrive(middle, 'T', 2)
        for _ in range(2):
            current = self.read_walk(walk_id)
            self.assertEqual(current.walk(), record(original_id, 'complete', ['S', 'J', 'T']))
            self.assert_no_arrival_form(current)

    def test_completed_guard(self):
        guide = self.level_guide()
        opened = self.start(guide)
        walk_id = opened.id_for('walk')
        action = f'/walks/{walk_id}/arrivals'
        middle = self.arrive(opened, 'J', 1)
        final_form = middle.form(action)
        end = self.arrive(middle, 'T', 2)
        expected = record(guide.id_for('guide'), 'complete', ['S', 'J', 'T'])
        self.assertEqual(end.walk(), expected)
        self.assert_no_arrival_form(end)
        rejected = self.browser.post(action, final_form)
        self.assertEqual(rejected.status, 409)
        self.assertEqual(rejected.walk(), expected)
        self.assert_no_arrival_form(rejected)
        self.assertEqual(self.read_walk(walk_id).walk(), expected)

    def test_unknown_walk(self):
        self.assertEqual(self.browser.get(f'/walks/{MISSING_ID}').status, 404)
        self.assertEqual(self.browser.get(f'/walks?walk_id={MISSING_ID}').status, 404)
        self.assertEqual(self.browser.post(f'/walks/{MISSING_ID}/arrivals', {
            'station': 'J', 'ordinal': '1',
        }).status, 404)
        self.assertEqual(self.rows('SELECT id FROM walks'), [])

    def test_bound_action(self):
        guide = self.level_guide()
        opened = self.start(guide)
        walk_id = opened.id_for('walk')
        action = f'/walks/{walk_id}/arrivals'
        form = opened.form(action)
        for field, change in (('station', 'T'), ('ordinal', '2')):
            with self.subTest(field=field):
                changed = dict(form)
                changed[field] = change
                response = self.browser.post(action, changed)
                self.assertEqual(response.status, 409)
                self.assertEqual(self.read_walk(walk_id).walk(), record(guide.id_for('guide'), 'walking', ['S']))
        self.assertEqual(self.arrive(opened, 'J', 1).walk()['arrivals'], ['S', 'J'])

    def test_conflict_retry(self):
        guide = self.level_guide()
        guide_id = guide.id_for('guide')
        opened = self.start(guide)
        walk_id = opened.id_for('walk')
        action = f'/walks/{walk_id}/arrivals'
        stale = opened.form(action)
        self.arrive(opened, 'J', 1)
        conflict = self.browser.post(action, stale)
        self.assertEqual(conflict.status, 409)
        self.assertEqual(conflict.walk(), record(guide_id, 'walking', ['S', 'J']))
        expected_form = {'station': 'T', 'ordinal': '2'}
        current_form = conflict.form(action)
        self.assertEqual(current_form, expected_form)
        self.arrive(conflict, 'T', 2)
        final_record = self.read_walk(walk_id).walk()
        expected_record = record(guide_id, 'complete', ['S', 'J', 'T'])
        self.assertEqual(final_record, expected_record)
        scenario(
            'n7.conflict_retry', {'accepted_station': 'J', 'replayed_form': stale},
            {'status': 409, 'form': expected_form}, {'status': conflict.status, 'form': current_form},
            expected_record, final_record,
            ['gallery/walks/arrival.py', 'gallery/web/server.py', 'gallery/web/walk_pages.py'],
            'J 已经记过一次。旧表单拒绝后序次 2 对应 T，从回显完成后仍只有三个到站。',
        )

    def test_parallel_arrival(self):
        guide = self.level_guide()
        opened = self.start(guide)
        walk_id = opened.id_for('walk')
        action = f'/walks/{walk_id}/arrivals'
        fields = opened.form(action)
        barrier = Barrier(2, timeout=5)

        def submit():
            barrier.wait()
            return self.browser.post(action, fields)

        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(submit) for _ in range(2)]
            replies = [attempt.result(timeout=20) for attempt in attempts]
        self.assertEqual(sorted(reply.status for reply in replies), [200, 409])
        expected = record(guide.id_for('guide'), 'walking', ['S', 'J'])
        for reply in replies:
            self.assertEqual(reply.walk(), expected)
            self.assertEqual(reply.form(action), {'station': 'T', 'ordinal': '2'})
        self.assertEqual(self.read_walk(walk_id).walk(), expected)
        self.assertEqual(self.rows('SELECT ordinal, station FROM walk_arrivals ORDER BY ordinal'), [(0, 'S'), (1, 'J')])
