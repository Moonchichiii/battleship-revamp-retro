⚓ Battleship Revamp 2025
A complete overhaul of my original Python terminal game — now a full-blown web application with smart AI opponents, clean architecture, and a retro twist. This is my take on blending nostalgia with modern tech.

🎯 Why I Built This
Back in 2022, I wrote a simple terminal version of Battleship in Python. It was fun, but basic: random AI, no interface, and Google Sheets for saving scores.

Fast forward to 2025 — I wanted to challenge myself: take that humble script and turn it into something production-grade. This project is my playground for applying serious software practices, exploring AI algorithms, and shipping a real web app from scratch.

✨ What Makes It Cool
🤖 Smarter AI Opponents
I didn’t want to settle for dumb luck. The AI here actually thinks:

Rookie: Just shoots randomly with a few tricks.

Veteran: Uses probability heatmaps to make better guesses.

Admiral: Runs Monte Carlo Tree Search simulations.

Legendary: Learns your behavior and adapts over time.

🎨 Retro Aesthetic
I'm a sucker for old-school vibes — so I styled the interface like a classic CRT terminal:

ASCII graphics, scan lines, and green-on-black goodness

Fully responsive, works on phones too

🔐 GitHub Login & Player Stats
OAuth 2.0 via GitHub

Each player gets a profile and match history

⚡ Fast and Responsive
Async FastAPI backend

HTMX for snappy, real-time interactions

Redis caching where it counts

🛠 Stack I Used
Area	Tech Used
Backend	Python, FastAPI, Redis, OAuth2
Frontend	HTMX, Jinja2, Vanilla JS, Tailwind CSS
Database	PostgreSQL (prod), SQLite (dev)
DevOps	Docker, CI/CD pipelines
Testing	Pytest, Black, Ruff, Mypy, Locust

🚀 Getting Started
bash
Kopiera
Redigera
# Clone the repo
git clone https://github.com/yourusername/battleship-revamp-2025.git
cd battleship-revamp-2025

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
# Edit .env and add your GitHub OAuth credentials

# Launch the app
python main.py
Now open your browser at http://localhost:8000

🎮 Evolution Timeline
Year	Milestone
2022	Terminal game with Google Sheets leaderboard
2023–2024	Refactoring and prototyping with AI logic
2025	Full stack web app with CI/CD and OAuth

What started as a basic script is now a live, production-ready app with AI strategy layers and a custom UI. It's been a wild ride.

🧠 AI Details
Each difficulty level uses a different algorithm:

Rookie – Simple heuristics

Veteran – Probabilistic targeting

Admiral – Monte Carlo simulations

Legendary – Adaptive logic with learning behavior

It’s not just about difficulty — it’s about personality. Each opponent plays differently.

🧪 Dev & Testing Tools
bash
Kopiera
Redigera
# Run unit tests
pytest tests/ -v

# Lint & type-check
black src/
ruff check src/
mypy src/

# Performance testing
locust -f tests/performance/locustfile.py

# Deploy with Docker
docker-compose up --build
📄 License
MIT – do whatever you want, just give credit.

<div align="center"> ⚓ From solo dev script to full-stack app — one commit at a time Built for fun, learning, and a little nostalgia </div>