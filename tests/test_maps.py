import json

from gallery.maps.revisions import get_revision
from gallery.web.database import read_transaction
from gallery.web.server import initialize_demo_database
from tests.support import GalleryTestCase, MISSING_ID, level_map, map_fields, map_input, passage, running_gallery


LEVEL = {'stations': ['S', 'J', 'T'], 'legs': [['S', 'J', 2], ['J', 'T', 3]], 'total': 5}


class MapTests(GalleryTestCase):
    def test_save_and_proof(self):
        saved = self.save(level_map())
        revision_id = saved.id_for('revision')
        self.assertEqual(saved.form('/proofs')['revision_id'], str(revision_id))
        proof = self.proof(saved)
        self.assertEqual(proof.by_id['proof']['data-result'], 'reachable')
        self.assertEqual(proof.by_id['proof']['data-revision'], str(revision_id))
        self.assertEqual(proof.itinerary(), LEVEL)
        readback = self.browser.get(f'/proofs/{proof.id_for("proof")}')
        self.assertEqual(readback.status, 200)
        self.assertEqual(readback.itinerary(), LEVEL)

    def test_bad_edge_rejected(self):
        original = self.save(level_map())
        broken = map_input(('S', 'J', 'T'), [passage('S', 'J', 2), passage('J', 'X', 3)])
        response = self.browser.post('/maps', map_fields(broken))
        self.assertEqual(response.status, 400)
        self.assertIn('J → X', response.body)
        self.assertEqual(self.rows('SELECT id FROM map_revisions'), [(original.id_for('revision'),)])
        self.assertEqual(self.proof(original).itinerary(), LEVEL)

    def test_revision_identity(self):
        first = self.save(level_map())
        new_graph = map_input(('S', 'K', 'T'), [passage('S', 'K', 3), passage('K', 'T', 4)])
        second = self.save(new_graph)
        self.assertNotEqual(first.id_for('revision'), second.id_for('revision'))
        self.assertEqual(first.form('/proofs')['revision_id'], str(first.id_for('revision')))
        self.assertEqual(second.form('/proofs')['revision_id'], str(second.id_for('revision')))
        self.assertEqual(self.proof(first).itinerary(), LEVEL)
        expected = {'stations': ['S', 'K', 'T'], 'legs': [['S', 'K', 3], ['K', 'T', 4]], 'total': 7}
        self.assertEqual(self.proof(second).itinerary(), expected)
        original_page = self.browser.get(f'/maps/{first.id_for("revision")}')
        self.assertEqual(original_page.status, 200)
        self.assertEqual(self.proof(original_page).itinerary(), LEVEL)

    def test_unknown_revision(self):
        result = self.browser.post('/proofs', {'revision_id': MISSING_ID, 'start': 'S', 'end': 'T'})
        self.assertEqual(result.status, 404)
        self.assertEqual(self.browser.get(f'/maps/{MISSING_ID}').status, 404)
        self.assertEqual(self.rows('SELECT id FROM route_proofs'), [])

    def test_seed_repeat(self):
        self.assertEqual(self.rows('SELECT id FROM map_revisions'), [])
        first = initialize_demo_database(self.database)
        self.assertIsNotNone(first)
        before = self.rows('SELECT id, document FROM map_revisions ORDER BY id')
        self.assertEqual([row[0] for row in before], [first.id])
        actual_map = json.loads(before[0][1])
        self.assertEqual(actual_map, map_input(
            ('S', 'J', 'T'),
            [passage('S', 'J', 2), passage('J', 'T', 3), passage('S', 'T', 3, 'stairs')],
        ))
        # A fresh server and independent initializer connections open the same database.
        with running_gallery(self.database) as reopened:
            self.assertIsNone(initialize_demo_database(self.database))
            saved_page = reopened.get(f'/maps/{first.id}')
            self.assertEqual(saved_page.status, 200)
            fields = saved_page.form('/proofs')
            fields.update(start='S', end='T')
            proof = reopened.post('/proofs', fields)
            self.assertEqual(proof.status, 201)
            self.assertEqual(proof.itinerary(), LEVEL)
        self.assertEqual(self.rows('SELECT id, document FROM map_revisions ORDER BY id'), before)

        edited_map = map_input(('S', 'T'), [passage('S', 'T', 9)])
        changed = self.save(edited_map)
        after_edit = self.rows('SELECT id, document FROM map_revisions ORDER BY id')
        self.assertEqual(len(after_edit), 2)
        self.assertEqual(after_edit[0], before[0])
        self.assertEqual(json.loads(after_edit[1][1]), edited_map)
        self.assertIsNone(initialize_demo_database(self.database))
        self.assertEqual(self.rows('SELECT id, document FROM map_revisions ORDER BY id'), after_edit)
        self.assertEqual(self.proof(changed).itinerary(), {
            'stations': ['S', 'T'], 'legs': [['S', 'T', 9]], 'total': 9,
        })

        staff_first = self.database.with_name('staff-first.sqlite3')
        with running_gallery(staff_first) as browser:
            own = browser.post('/maps', map_fields(edited_map))
            self.assertEqual(own.status, 201)
            own_id = own.id_for('revision')
        self.assertIsNone(initialize_demo_database(staff_first))
        with read_transaction(staff_first) as connection:
            self.assertEqual(connection.execute('SELECT id FROM map_revisions').fetchall(), [(own_id,)])
            saved = get_revision(connection, own_id)
            self.assertEqual(json.loads(json.dumps(saved.document())), edited_map)

    def test_minutes(self):
        saved = self.save(level_map())
        for value in (0, -1, 1.5, 2.0, True, False, '2'):
            with self.subTest(value=value):
                invalid = map_input(('S', 'T'), [passage('S', 'T', value)])
                result = self.browser.post('/maps', map_fields(invalid))
                self.assertEqual(result.status, 400)
                self.assertIn('正整数', result.body)
                self.assertEqual(self.rows('SELECT id FROM map_revisions'), [(saved.id_for('revision'),)])
        self.assertEqual(self.proof(saved).itinerary(), LEVEL)

    def test_duplicate_station(self):
        saved = self.save(level_map())
        invalid = map_input(('S', 'T', 'S'), [passage('S', 'T', 4)])
        result = self.browser.post('/maps', map_fields(invalid))
        self.assertEqual(result.status, 400)
        self.assertIn('站号 S 重复', result.body)
        self.assertEqual(self.rows('SELECT id FROM map_revisions'), [(saved.id_for('revision'),)])
        self.assertEqual(self.proof(saved).itinerary(), LEVEL)
