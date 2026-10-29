import io
import re
import tempfile
import unittest
from pathlib import Path

from docx import Document

import app as analyzer


class ResumeAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        analyzer.DATABASE = Path(self.temp_dir.name) / "test.sqlite3"
        analyzer.app.config.update(TESTING=True)
        analyzer.app._database_ready = False
        analyzer.init_db()
        analyzer.app._database_ready = True
        self.client = analyzer.app.test_client()
        page = self.client.get("/")
        self.csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
        self.headers = {"X-CSRF-Token": self.csrf}

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_docx(self, text):
        document = Document()
        for line in text.splitlines():
            document.add_paragraph(line)
        stream = io.BytesIO()
        document.save(stream)
        stream.seek(0)
        return stream

    def test_dashboard_and_seed_records(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["candidate_count"], 3)
        self.assertEqual(response.json["job_count"], 3)
        self.assertGreaterEqual(response.json["average_match"], 0)

    def test_role_creation_infers_skills_from_description(self):
        response = self.client.post(
            "/api/jobs",
            json={"title": "QA Intern", "department": "Engineering", "description": "Essential Python and Git skills. Docker is preferred."},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["required"], ["python", "git"])
        self.assertEqual(response.json["preferred"], ["docker"])

    def test_docx_upload_and_profile_evidence(self):
        resume = self.make_docx(
            "Education:\nB.Tech Computer Science\nExperience:\nFamiliar with Python and used SQL in a project.\nProjects:\nStudent database."
        )
        response = self.client.post(
            "/api/candidates",
            data={"name": "Test Student", "email": "student@example.edu", "resume": (resume, "resume.docx")},
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.json)
        candidate_id = response.json["id"]
        self.assertIn("python", response.json["unverified"])
        self.assertEqual(response.json["education"], "B.Tech Computer Science")
        job = self.client.get("/api/jobs").json[0]
        profile = self.client.get(f"/api/candidates/{candidate_id}?job_id={job['id']}")
        self.assertEqual(profile.status_code, 200)
        self.assertIn("recommendations", profile.json)
        self.assertIn("improvements", profile.json)

    def test_skill_match_excludes_tentative_evidence_and_explains_score(self):
        candidate = {"skills": ["python", "flask", "teamwork"], "unverified": ["python"]}
        job = {"required": ["python", "flask"], "preferred": ["teamwork"]}
        match = analyzer.score_candidate(candidate, job)
        self.assertEqual(match["score"], 63)
        self.assertEqual(match["required_matched"], ["flask"])
        self.assertEqual(match["required_unverified"], ["python"])
        self.assertIn("75%", match["explanation"])

    def test_strong_evidence_overrides_a_tentative_mention(self):
        analysis = analyzer.analyze_resume(
            "Familiar with Python. Later built a Python service. Collaborated with a team."
        )
        self.assertNotIn("python", analysis["unverified"])
        self.assertIn("teamwork", analysis["skills"])

    def test_compare_shortlist_and_csv_report(self):
        candidates = self.client.get("/api/candidates").json[:2]
        job = self.client.get("/api/jobs").json[0]
        comparison = self.client.post(
            "/api/compare",
            json={"job_id": job["id"], "candidate_ids": [person["id"] for person in candidates]},
            headers=self.headers,
        )
        self.assertEqual(comparison.status_code, 200)
        scores = [person["match"]["score"] for person in comparison.json["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        shortlist = self.client.post(
            "/api/shortlist",
            json={"job_id": job["id"], "candidate_id": candidates[0]["id"]},
            headers=self.headers,
        )
        self.assertEqual(shortlist.json["shortlisted"], True)
        report = self.client.get(f"/api/reports.csv?job_id={job['id']}")
        self.assertEqual(report.status_code, 200)
        self.assertIn(b"Unverified essential", report.data)

    def test_upload_rejects_unsupported_file(self):
        response = self.client.post(
            "/api/candidates",
            data={"name": "Student", "resume": (io.BytesIO(b"no"), "resume.txt")},
            headers=self.headers,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("PDF or DOCX", response.json["error"])

    def test_state_change_requires_csrf_token(self):
        response = self.client.post("/api/jobs", json={"title": "No token", "required": ["python"]})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
