# Battleship Revamp: Retro Command

[![CI Status](https://github.com/Moonchichiii/battleship-revamp-retro/actions/workflows/ci.yml/badge.svg)](https://github.com/Moonchichiii/battleship-revamp-retro/actions/workflows/ci.yml)
[![Security Check](https://github.com/Moonchichiii/battleship-revamp-retro/actions/workflows/security.yml/badge.svg)](https://github.com/Moonchichiii/battleship-revamp-retro/actions/workflows/security.yml)
[![Python Version](https://img.shields.io/badge/python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Deployment](https://img.shields.io/badge/Deploy-Render-black?logo=render&logoColor=white)](https://render.com)

> *"Sometimes the real enemy is your own targeting system."*

A hyper-optimized, retro-styled Battleship game built for the modern web. Features a **CRT-terminal UI**, server-side state validation, advanced **AI opponents** (including LLM-powered "Psy-Ops"), and secure OAuth authentication.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Local Development](#local-development)
- [Deployment](#deployment)
- [Code Quality](#code-quality)
- [License](#license)

---

## Features

- **Tactical AI:** Challenge 3 tiers of algorithmic opponents (Rookie, Veteran, Admiral) plus a GPT-4 powered "Psy-Ops" tier.
- **Retro UI:** Custom CRT shaders, glowing phosphorus text, and raw ASCII art.
- **Sound Engine:** Procedural audio synthesis via Web Audio API (no heavy assets).
- **Secure Auth:** OAuth (GitHub/Google) and local Argon2 hashing with secure session management.
- **Leaderboards:** Optimized PostgreSQL composite indexes for instant ranking queries.
- **Zero-Lag:** Powered by **FastAPI** and **HTMX** for SPA-like performance without the bundle size.

[Back to top](#table-of-contents)

---

## Tech Stack

- **Core:** Python 3.12, FastAPI
- **Frontend:** HTMX, Jinja2, CSS3 (No JS Frameworks)
- **Database:** PostgreSQL 14+ (Async + Sync support)
- **Security:** Argon2, OAuth2, Secure Cookies
- **Deployment:** Docker, Render
- **DevOps:** Ruff (Linting), Pytest, Pre-commit

[Back to top](#table-of-contents)

---

## Local Development

### 1. Clone & Env

```bash
git clone https://github.com/Moonchichiii/battleship-revamp-retro.git
cd [REPO_NAME]
cp .env.example .env
```

### 2. Run with Docker (Recommended)

This spins up the App and PostgreSQL instantly.

```bash
docker-compose up --build
```

Access the tactical interface at: `http://localhost:8000`

### 3. Run Manually

If you prefer running without Docker:

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run Postgres (ensure variables in .env match your local DB)
# Then start server:
uvicorn src.battleship.main:app --reload
```

[Back to top](#table-of-contents)

---

## Deployment

This project is configured for **Render.com** (Docker runtime).

1. **New Web Service:** Select "Deploy from Git" → "Docker".
2. **Environment Variables:** Add the variables required (referenced in `.env.example`).
3. **Production Settings:**
   - `DISABLE_RATE_LIMIT`: `0`
   - `EMAIL_SYNTAX_ONLY`: `0`
   - `DB_AUTO_CREATE`: `1` (First run only)

[Back to top](#table-of-contents)

---

## Code Quality

We strictly enforce code quality using **Ruff**.

```bash
# Run linting
ruff check .

# Run tests
pytest
```

[Back to top](#table-of-contents)

---

## License

MIT License. Declassified for civilian use.
