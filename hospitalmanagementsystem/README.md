# Careflow Hospital Management

A responsive hospital operations dashboard for managing patients, doctors, and appointments. The frontend is plain HTML, CSS, and JavaScript. The backend uses Python's standard-library HTTP server and SQLite, so no package installation is required.

## Run locally

1. Install Python 3.10 or later.
2. Open PowerShell in this project folder. If you have closed VS Code, open PowerShell from the Start menu and enter:

   ```powershell
   cd "C:\Users\BMSIT\Documents\hospitalmanagementsystem"
   ```

3. Start the server:

   ```powershell
   py server.py
   ```

4. Visit [http://127.0.0.1:8000](http://127.0.0.1:8000).
5. Press `Ctrl+C` in the terminal to stop it.

You do not need to keep VS Code open: start `py server.py` in a separate PowerShell window, leave that window open while you use the website, and open the URL in your browser. The SQLite database (`hospital.db`) is stored next to `server.py`, so your records remain when the server or VS Code closes. The database is created and populated with clearly fictional sample records on first run. To reset the demo data, stop the server, remove `hospital.db`, and start the server again.

## Included features

- Overview with live patient, doctor, and appointment totals, department activity, and schedules.
- Patient registration, editing, search, archive, and restore.
- Doctor directory with profiles, specialty, experience, editing, and archiving.
- Appointment booking with active patient and doctor selection, date/time checks, and conflict prevention.
- Appointment search, status filters, completion, and cancellation.
- Responsive layouts for desktop, tablet, and mobile.

## Important

This is a local demonstration application, not a production or clinical system. It has no user authentication, role-based access, encryption-at-rest, audit trail, backups, or regulatory compliance controls. It is bound to `127.0.0.1` and uses fictional seed data. Do not enter real patient information or expose the development server to a network.
