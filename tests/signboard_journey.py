import json
import unittest
from copy import deepcopy
from pathlib import Path

from tests.support import GalleryTestCase


FIXTURE = Path(__file__).resolve().parents[1] / "samples" / "signboard-example.json"


def trace(page):
    return [
        (node["data-kind"], node["data-station"], node.get("data-reading"))
        for node in page.elements
        if node.get("data-kind") in {"arrival", "report"}
    ]


class SignboardJourney(GalleryTestCase):
    def branch_proof(self, example):
        saved = self.save({key: example[key] for key in ("stations", "passages")})
        fields = saved.form("/proofs")
        fields.update(
            start=example["start"],
            end=example["end"],
            allowed=",".join(example["allowed"]),
            shifts=json.dumps(example["shifts"], ensure_ascii=False),
        )
        proof = self.browser.post("/proofs", fields)
        self.assertEqual(proof.status, 201, proof.body)
        self.assertEqual(proof.by_id["proof"]["data-revision"], str(saved.id_for("revision")))
        return proof

    def follow_move(self, page, station, ordinal):
        walk_id = page.id_for("walk")
        path = f"/walks/{walk_id}/arrivals"
        fields = page.form(path)
        self.assertEqual((fields["station"], fields["ordinal"]), (station, str(ordinal)))
        arrived = self.browser.post(path, fields)
        self.assertEqual(arrived.status, 200, arrived.body)
        return arrived

    def test_two_walks_after_reissue(self):
        example = json.loads(FIXTURE.read_text(encoding="utf-8"))
        guide = self.publish(self.branch_proof(example))
        guide_id = guide.id_for("guide")
        at_sign = []
        for _ in range(2):
            opened = self.start(self.receive(guide_id))
            walk_id = opened.id_for("walk")
            move_path = f"/walks/{walk_id}/arrivals"
            read_path = f"/walks/{walk_id}/readings"
            stale = opened.form(move_path)
            premature = self.browser.post(read_path, {"station": "J", "ordinal": "0", "reading": "左"})
            self.assertEqual(premature.status, 409, premature.body)
            self.assertEqual(trace(premature), [("arrival", "S", None)])
            middle = self.follow_move(opened, example["expected"]["first_destination"], 1)
            conflict = self.browser.post(move_path, stale)
            self.assertEqual(conflict.status, 409, conflict.body)
            self.assertEqual(trace(conflict), trace(middle))
            at_sign.append((walk_id, read_path, conflict))

        revised = deepcopy(example)
        revised["passages"][2]["minutes"] += 1
        revised["shifts"][0]["signs"]["J"] = "右"
        revised["shifts"][1]["signs"]["J"] = "左"
        latest = self.publish(self.branch_proof(revised))
        self.assertNotEqual(guide_id, latest.id_for("guide"))

        for (walk_id, read_path, page), reading, side in zip(at_sign, ("左", "右"), ("left", "right")):
            with self.subTest(reading=reading):
                fields = page.form(read_path)
                self.assertEqual((fields["station"], fields["ordinal"]), ("J", "1"))
                wrong = self.browser.post(read_path, dict(fields, reading="直行"))
                self.assertEqual(wrong.status, 409, wrong.body)
                self.assertEqual(trace(wrong), trace(page))
                accepted = self.browser.post(read_path, dict(wrong.form(read_path), reading=reading))
                self.assertEqual(accepted.status, 200, accepted.body)
                expected = [("arrival", "S", None), ("arrival", "J", None), ("report", "J", reading)]
                self.assertEqual(trace(accepted), expected)
                for ordinal, station in enumerate(example["expected"][f"arrivals_after_{side}_report"], 2):
                    accepted = self.follow_move(accepted, station, ordinal)
                    expected.append(("arrival", station, None))
                finished = self.read_walk(walk_id)
                self.assertEqual(finished.by_id["walk"]["data-status"], "complete")
                self.assertEqual(finished.by_id["walk"]["data-guide"], str(guide_id))
                actual = trace(finished)
                self.assertEqual(actual, expected)
                print(f"发行 {guide_id}，走览 {walk_id}：{actual}")

    def test_equal_readings_cannot_publish(self):
        example = json.loads(FIXTURE.read_text(encoding="utf-8"))
        example["shifts"][1]["signs"]["J"] = "左"
        proof = self.branch_proof(example)
        proof_id = proof.id_for("proof")
        self.assertEqual(proof.by_id["proof"]["data-result"], "unreachable")
        issue = self.browser.post("/guides", {"proof_id": proof_id})
        self.assertEqual(issue.status, 409, issue.body)
        print(f"校样 {proof_id}：两班都显示左，发行返回 {issue.status}")


if __name__ == "__main__":
    unittest.main()
