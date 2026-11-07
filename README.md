# Verity: AI brand governance before you publish

Built by Team STRAWHATS for the Inkloom AI problem statement (CodeNexus 2026). Verity reviews content BEFORE publication against a company's
approved guidelines, facts, terminology and assets, explains every issue, suggests fixes (never auto-applies them),
and requires human approval before anything is published.

## Demo
Live site: PASTE-RENDER-LINK-HERE (free hosting, first load can take about 1 minute)
Code: https://github.com/venkatsais2007-art/verity
Company ID: NORTHWIND, password for all users: demo123
Employee IDs: admin01, creator01, creator02, creator03, manager01, reviewer01

## Features
- Role-based login: Admin, Creator, Manager, Reviewer
- Knowledge base: paste or upload (PDF/DOCX/TXT) guidelines, facts, terminology, tone rules, assets; versioned
- Submit text, images, or documents (PDF/DOCX) with channel and purpose
- Automatic review with progress state: tone, terminology, messaging, unsupported claims, outdated facts,
  visual and accessibility checks
- Findings with severity, category, flagged text, reason, the exact guideline referenced, and a suggested fix
- Creator can Accept, Edit manually, or Dismiss (with reason); suggestions are never applied automatically
- Resubmit for re-check with before/after diff and brand-compliance score
- Human approval: comment, request changes, approve, reject; high-risk content needs a Manager;
  only human-approved content can be published (enforced on the server)
- Revision history and audit trail of every version, decision, comment and approval
- Insights: repeated violations, rule-breakers by team, guidelines often flagged or dismissed

## Architecture
React + Tailwind (Vite) frontend, FastAPI backend, SQLite database. One service serves both.
Review pipeline: built-in rule checks read banned terms and facts from the knowledge base and run instantly.
Optionally the content is also sent to Google Gemini for deeper analysis; its findings are merged and
duplicates removed. If the AI service is slow or unavailable, the rule checks still complete the review.

## AI and external services (disclosure)
- Built-in rule checks: run locally, no data leaves the server.
- Google Gemini API (optional, off by default in the hosted demo): receives the submitted content and the
  knowledge base text when enabled. Use only non-confidential data with this option.
- Libraries: FastAPI, React, Tailwind CSS, pypdf, python-docx, PyJWT.
- Data: all demo data is fictional (the brand "Northwind Wellness").

## Responsible design
Human sign-off is required to publish. AI suggestions are advisory. Every action is logged. Content is only
visible to its creator and reviewers in the same company. Secrets are kept in environment variables.

## Run locally
Backend: cd backend, create a venv, pip install -r requirements.txt, python -m uvicorn main:app --port 8000
Frontend: cd frontend, npm install, npm run dev
Settings in backend/.env: REVIEW_PROVIDER (rules or gemini), GEMINI_API_KEY, GEMINI_MODEL, SECRET_KEY

## Team STRAWHATS
- *Nikhil Petlu (Team Lead):* frontend development, UI and user experience
- *Venkat Sai Sura:* backend, AI review pipeline and system architecture
- *Monika Mallela:* product strategy, responsible AI design and documentation
- *Sandhya Kachipalli:* data, analytics and insights dashboard