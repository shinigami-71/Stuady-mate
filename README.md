# Study Planner

Study Planner is a local XAMPP-based web application that helps students turn uploaded PDF files into study summaries, difficulty estimates, study plans, suggested questions, and document-based chat answers. The project uses PHP and MySQL for the web app, with a local Python backend for PDF analysis.

## Features

- User registration and login with PHP sessions.
- PDF upload with file validation and local storage.
- AI-style PDF analysis through a local Python service.
- Structured PDF summaries based on sections such as objectives, theory, procedure, results, discussion, and conclusion.
- Difficulty estimation and suggested study hours.
- Generated study plans and active recall questions.
- Dashboard showing uploaded PDFs, summaries, estimated study time, and revision actions.
- PDF chat page for asking questions from uploaded documents.
- Suggested one-click questions for revision, quiz practice, concepts, and study strategy.
- Study reminder console with focus timer and browser notification support.

## Tech Stack

- Frontend: HTML, CSS, JavaScript
- Backend: PHP
- Database: MySQL or MariaDB through XAMPP
- AI/PDF Service: Python local HTTP server
- Local server: XAMPP Apache

## Project Structure

```text
Study_Planner/
+-- index.html              # Landing page
+-- features.html           # Feature overview page
+-- study-guide.html        # Study workflow guide
+-- register.html/php       # Account creation
+-- login.html/php          # Login flow
+-- dashboard.php           # Main study dashboard
+-- upload.html/php         # PDF upload and analysis
+-- chat.php                # Ask questions from uploaded PDFs
+-- reanalyze.php           # Refresh PDF summaries
+-- ai_service.php          # PHP bridge to the Python AI backend
+-- config.php              # MySQL connection settings
+-- app.js                  # Dashboard reminder and UI behavior
+-- style.css               # Application styling
+-- assets/                 # Project images
+-- uploads/                # Runtime PDF uploads, ignored by Git
+-- ai_backend/
    +-- main.py             # Local PDF analysis API
    +-- requirements.txt    # Python dependency notes
```

## Prerequisites

- XAMPP with Apache and MySQL enabled.
- PHP included with XAMPP.
- Python 3.12 or another recent Python 3 version.
- Git, if cloning from GitHub.

The Python backend does not require external API keys. It can run with the standard library. `pymupdf` is optional and may improve PDF text extraction if installed.

## Installation

Clone the repository inside the XAMPP `htdocs` folder:

```powershell
cd C:\xampp\htdocs
git clone https://github.com/shinigami-71/Stuady-mate.git
```

If the folder is named `Stuady-mate`, open the site at:

```text
http://localhost/Stuady-mate/
```

If the folder is renamed to `Study_Planner`, open:

```text
http://localhost/Study_Planner/
```

## Database Setup

Start Apache and MySQL from XAMPP, then open phpMyAdmin:

```text
http://localhost/phpmyadmin
```

Run this SQL:

```sql
CREATE DATABASE IF NOT EXISTS study_planner;
USE study_planner;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ai_results (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  file_name VARCHAR(512) NOT NULL,
  study_hours INT NOT NULL DEFAULT 1,
  difficulty VARCHAR(50) NOT NULL DEFAULT 'Medium',
  summary TEXT NOT NULL,
  study_plan TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

The database connection is configured in `config.php`:

```php
$conn = new mysqli("localhost", "root", "", "study_planner");
```

This matches the default local XAMPP MySQL setup. If MySQL has a password on another computer, update `config.php`.

## AI Backend Setup

Run the backend setup once from the project folder:

```powershell
setup_ai_backend.bat
```

Then start the project helper:

```powershell
start_project.bat
```

The AI backend runs locally at:

```text
http://127.0.0.1:8000
```

Available backend endpoints:

- `GET /health`
- `GET /openapi.json`
- `POST /analyze`
- `POST /ask`
- `POST /suggest`

Upload and chat features need this backend running. Normal pages, registration, login, and dashboard layout can load through XAMPP, but PDF analysis requires the Python service.

## How The App Works

1. A user creates an account or logs in.
2. The user uploads a PDF file.
3. PHP saves the file in the `uploads/` folder.
4. `ai_service.php` sends the file name to the local Python backend.
5. The Python backend extracts readable text from the PDF.
6. It estimates difficulty, study time, summary, suggested questions, and a study plan.
7. PHP saves the result in the `ai_results` table.
8. The dashboard displays the study plan, summary, reminders, and chat actions.

## Notes And Limitations

- This project is designed for local academic use with XAMPP.
- Scanned image-only PDFs may not analyze well because the backend depends on readable PDF text.
- Uploaded PDFs are runtime files and are not included in GitHub.
- The local AI backend must stay running while using upload, refresh, and chat features.
- Before deploying publicly, add stronger production security, environment variables, and server-side hardening.
