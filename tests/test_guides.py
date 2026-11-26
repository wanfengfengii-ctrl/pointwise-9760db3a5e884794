from gallery.web.server import initialize_demo_database
from tests.support import GalleryTestCase, MISSING_ID, map_input, passage, scenario


LEVEL = {'stations': ['S', 'J', 'T'], 'legs': [['S', 'J', 2], ['J', 'T', 3]], 'total': 5}
TIED = {'stations': ['S', 'A', 'Z', 'T'], 'legs': [['S', 'A', 3], ['A', 'Z', 1], ['Z', 'T', 1]], 'total': 5}


def tied_map(*, reversed_input=False):
    stations = ('S', 'A', 'Z', 'B', 'C', 'T')
    edges = [
        passage('S', 'A', 3), passage('A', 'Z', 1), passage('Z', 'T', 1),
        passage('S', 'B', 1), passage('B', 'C', 2), passage('C', 'T', 2),
    ]
    if reversed_input:
        return map_input(reversed(stations), reversed(edges))
    return map_input(stations, edges)


class GuideTests(GalleryTestCase):
    def assert_unreachable(self, proof):
        self.assertEqual(proof.by_id['proof']['data-result'], 'unreachable')
        self.assertIn('不可达', proof.body)
        self.assertNotIn('route-total', proof.by_id)
        self.assertFalse(any(action == '/guides' for action, _ in proof.forms))

    def test_step_free_guide(self):
        revision = initialize_demo_database(self.database)
        saved = self.browser.get(f'/maps/{revision.id}')
        self.assertEqual(saved.status, 200)
        unrestricted = self.proof(saved, allowed='stairs')
        self.assertEqual(unrestricted.itinerary(), {
            'stations': ['S', 'T'], 'legs': [['S', 'T', 3]], 'total': 3,
        })
        proof = self.proof(saved)
        self.assertEqual(proof.itinerary(), LEVEL)
        issued = self.publish(proof)
        receipt = self.receive(issued.id_for('guide'))
        self.assertEqual(receipt.itinerary(), LEVEL)
        self.assertEqual(receipt.by_id['guide']['data-proof'], str(proof.id_for('proof')))
        self.assertEqual(receipt.form('/walks')['guide_id'], str(issued.id_for('guide')))
        scenario(
            'n3', {'allowed': [], 'ordinary_leg_minutes': [2, 3], 'stairs_minutes': 3},
            LEVEL, proof.itinerary(), LEVEL, receipt.itinerary(),
            ['gallery/routes/eligibility.py', 'gallery/routes/shortest.py', 'gallery/issues/snapshots.py'],
            '禁用阶梯后只剩 S 到 J 到 T，手算 2 + 3 为 5，按原顺序核对领取的分段。',
        )

    def test_unreachable_proof_cannot_publish(self):
        closed = self.save(map_input(('S', 'T'), [passage('S', 'T', 3, 'stairs')]))
        proof = self.proof(closed)
        self.assert_unreachable(proof)
        proof_id = proof.id_for('proof')
        rejection = self.browser.post('/guides', {'proof_id': proof_id})
        self.assertEqual(rejection.status, 409)
        saved = self.browser.get(f'/proofs/{proof_id}')
        self.assertEqual(saved.status, 200)
        self.assert_unreachable(saved)
        self.assertEqual(self.rows('SELECT id FROM guides'), [])
        self.assertEqual(self.rows('SELECT guide_id FROM guide_directory'), [])

    def test_tie_and_old_release(self):
        old = self.publish(self.proof(self.save(tied_map())))
        old_id = old.id_for('guide')
        changed = map_input(('S', 'B', 'T'), [passage('S', 'B', 2), passage('B', 'T', 4)])
        new = self.publish(self.proof(self.save(changed)))
        self.assertNotEqual(new.id_for('guide'), old_id)
        old_route = self.receive(old_id).itinerary()
        self.assertEqual(old_route['stations'], ['S', 'A', 'Z', 'T'])
        self.assertEqual(old_route['total'], 5)
        self.assertEqual(self.receive(new.id_for('guide')).itinerary()['stations'], ['S', 'B', 'T'])

    def test_directed_and_enabled(self):
        document = map_input(
            ('S', 'D', 'J', 'T'),
            [passage('S', 'D', 1), passage('D', 'T', 1),
             passage('S', 'J', 1, 'stairs'), passage('S', 'J', 4), passage('J', 'T', 2),
             passage('S', 'T', 2, 'permit', 'stairs')],
            disabled=('D',),
        )
        saved = self.save(document)
        self.assertEqual(self.proof(saved).itinerary(), {
            'stations': ['S', 'J', 'T'], 'legs': [['S', 'J', 4], ['J', 'T', 2]], 'total': 6,
        })
        self.assertEqual(self.proof(saved, allowed='stairs').itinerary(), {
            'stations': ['S', 'J', 'T'], 'legs': [['S', 'J', 1], ['J', 'T', 2]], 'total': 3,
        })
        self.assertEqual(self.proof(saved, allowed='stairs, permit').itinerary(), {
            'stations': ['S', 'T'], 'legs': [['S', 'T', 2]], 'total': 2,
        })
        self.assert_unreachable(self.proof(saved, start='T', end='S', allowed='stairs,permit'))

    def test_invalid_endpoints(self):
        saved = self.save(map_input(('S', 'D', 'T'), [passage('S', 'T', 4)], disabled=('D',)))
        for start, end in (('D', 'T'), ('S', 'D'), ('D', 'D'), ('X', 'T'), ('S', 'X'), ('', 'T')):
            with self.subTest(start=start, end=end):
                fields = saved.form('/proofs')
                fields.update(start=start, end=end)
                self.assertEqual(self.browser.post('/proofs', fields).status, 400)
        self.assertEqual(self.rows('SELECT id FROM route_proofs'), [])

    def test_unknown_proof(self):
        self.assertEqual(self.browser.get(f'/proofs/{MISSING_ID}').status, 404)
        self.assertEqual(self.browser.post('/guides', {'proof_id': MISSING_ID}).status, 404)
        self.assertEqual(self.rows('SELECT id FROM guides'), [])
        self.assertEqual(self.rows('SELECT guide_id FROM guide_directory'), [])

    def test_issue_preserved(self):
        valid = self.save(map_input(('S', 'T'), [passage('S', 'T', 4)]))
        original = self.publish(self.proof(valid))
        original_id = original.id_for('guide')
        closed = self.save(map_input(('S', 'T'), [passage('S', 'T', 1, 'stairs')]))
        proof = self.proof(closed)
        self.assert_unreachable(proof)
        for proof_id, status in ((proof.id_for('proof'), 409), (MISSING_ID, 404)):
            self.assertEqual(self.browser.post('/guides', {'proof_id': proof_id}).status, status)
            self.assertEqual(self.rows('SELECT id FROM guides'), [(original_id,)])
            self.assertEqual(self.rows('SELECT guide_id FROM guide_directory'), [(original_id,)])
            listing = self.browser.get('/guides')
            self.assertEqual(listing.id_for('current-guide'), original_id)
            self.assertEqual(self.receive(original_id).itinerary(), original.itinerary())

    def test_full_sequence_tie(self):
        for reversed_input in (False, True):
            with self.subTest(reversed_input=reversed_input):
                proof = self.proof(self.save(tied_map(reversed_input=reversed_input)))
                self.assertEqual(proof.itinerary(), TIED)

    def test_frozen_legs(self):
        saved = self.save(tied_map())
        proof = self.proof(saved)
        self.assertEqual(proof.itinerary(), TIED)
        issued = self.publish(proof)
        guide_id = issued.id_for('guide')
        self.assertEqual(self.receive(guide_id).itinerary(), TIED)
        changed = self.save(map_input(('S', 'A', 'Z', 'T'), [
            passage('S', 'A', 1), passage('A', 'Z', 5), passage('Z', 'T', 6),
        ]))
        newer = self.publish(self.proof(changed))
        self.assertEqual(self.receive(newer.id_for('guide')).itinerary(), {
            'stations': ['S', 'A', 'Z', 'T'], 'legs': [['S', 'A', 1], ['A', 'Z', 5], ['Z', 'T', 6]], 'total': 12,
        })
        old = self.receive(guide_id)
        self.assertEqual(old.itinerary(), TIED)
        self.assertEqual(old.by_id['guide']['data-revision'], str(saved.id_for('revision')))
        self.assertEqual(old.form('/walks'), {'guide_id': str(guide_id)})
        self.assertEqual(self.browser.get('/guides').id_for('current-guide'), newer.id_for('guide'))

    def test_old_proof_after_edit(self):
        first = self.save(tied_map())
        proof = self.proof(first)
        later = self.save(map_input(('S', 'T'), [passage('S', 'T', 8)]))
        self.assertNotEqual(first.id_for('revision'), later.id_for('revision'))
        self.assertEqual(self.proof(later).itinerary()['total'], 8)
        original = self.publish(proof)
        receipt = self.receive(original.id_for('guide'))
        self.assertEqual(receipt.by_id['guide']['data-revision'], str(first.id_for('revision')))
        self.assertEqual(receipt.by_id['guide']['data-proof'], str(proof.id_for('proof')))
        self.assertEqual(receipt.itinerary(), TIED)

    def test_unknown_guide_get(self):
        self.assertEqual(self.browser.get(f'/guides/{MISSING_ID}').status, 404)
        self.assertEqual(self.browser.get(f'/guides?guide_id={MISSING_ID}').status, 404)
        self.assertEqual(self.rows('SELECT id FROM guides'), [])

    def test_integer_minutes_are_exact(self):
        large = 2**53 + 1
        saved = self.save(map_input(('S', 'A', 'T'), [
            passage('S', 'T', large + 4), passage('S', 'A', large), passage('A', 'T', 3),
        ]))
        guide = self.publish(self.proof(saved))
        self.assertEqual(self.receive(guide.id_for('guide')).itinerary(), {
            'stations': ['S', 'A', 'T'], 'legs': [['S', 'A', large], ['A', 'T', 3]], 'total': large + 3,
        })
