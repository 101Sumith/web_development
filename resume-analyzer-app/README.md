# TalentLens Resume Analyzer

A responsive Flask application for a college placement cell. Students can upload PDF or DOCX resumes; placement officers can create roles, review explainable skill matches, compare applicants, shortlist candidates, and export reports.

The app starts in a free local-demo mode with fictional sample records. It uses a transparent local text-analysis pipeline by default; no AI API key or paid service is required. If an OpenAI-compatible API key is configured, the applicant profile can request an AI-written summary. See **Optional AI summaries** before enabling it.

## Run from VS Code on Windows

1. Install Python 3.10+ and the Python extension for VS Code.
2. Open the `resume-analyzer-app` folder in VS Code.
3. Open **Terminal → New Terminal** and run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   py app.py
   ```

   If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe app.py` instead.

4. Open [http://127.0.0.1:5000](http://127.0.0.1:5000).
5. Stop the local server with **Ctrl+C** in the terminal.

The SQLite database is created as `resume_analyzer.db` in this project folder and seeded with clearly fictional profiles and roles on first run. Uploaded source files are parsed in memory and are not retained; extracted resume text and analysis are stored in SQLite. To clear this demo database, stop the server and remove only `resume_analyzer.db` (and its optional `-shm`/`-wal` files).

## Features

- PDF/DOCX upload with an 8 MB size limit, text extraction, candidate profile summaries, and skill detection.
- Create job descriptions with essential and preferred skills. If the essential-skills field is empty, the app attempts a best-effort extraction from the description; review the extracted requirements before using them.
- Job-specific skill matching that reports matched, missing, and tentatively worded/unverified skills.
- Explainable score: essential skills contribute 75% and preferred skills 25%. If only one requirement group is provided, that group is 100% of the score. Unverified mentions do not earn match credit.
- Candidate search, role filters, score ranking, candidate comparison, and per-role shortlists.
- Suggested roles, skill-focused course/resource links, project ideas, resume improvement prompts, and CSV reports.
- Responsive overview, applicant, job, comparison, and reporting views.
- SQLite queries use parameters; browser inputs are rendered as text; state-changing API requests require a session CSRF token.

## Optional AI summaries

By default, summaries are generated locally from extracted resume sections and detected skills. To enable an OpenAI-compatible summary provider, set `OPENAI_API_KEY`; optionally set `OPENAI_BASE_URL` (defaults to `https://api.openai.com/v1`) and `OPENAI_MODEL` (defaults to `gpt-4o-mini`) before starting the server.

**Privacy notice:** with an API key configured, opening an applicant profile for a role sends up to 10,000 characters of that resume's extracted text to the configured provider. The provider's retention and processing terms apply. Obtain the necessary consent and use an approved provider before enabling this for real student records. If the provider is unavailable, the local summary is shown instead.

## Configuration

- `PORT`: local server port (default `5000`).
- `FLASK_SECRET_KEY`: stable secret for Flask sessions. If omitted, a random secret is generated on each server start, invalidating existing sessions after restart.
- `RESUME_ANALYZER_DB`: optional SQLite database path. Defaults to `resume_analyzer.db` beside `app.py`.

## Tests

From this folder, install dependencies as above and run:

```powershell
py -m unittest discover -s tests -v
```

Tests use a temporary SQLite database and do not alter the demo database.

## Important privacy and deployment limits

This is a local demonstration and decision-support tool, not a production applicant-tracking system. It has no user login, placement-officer/student roles, audit trail, consent workflow, encrypted database, or retention controls. SQLite data is protected only by the operating system's file permissions. Keep the service bound to `127.0.0.1`; do not expose it to a public or campus network or store real student records until authentication, access controls, encryption, backups, retention, and institutional privacy review are in place. Resume text extraction and keyword matching can miss context or misrepresent qualifications; officers must verify evidence and make decisions using consistent human-led review.
