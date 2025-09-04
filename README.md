# Battleship Revamp 2025

[![CI](https://github.com/Moonchichiii/battleship-revamp-2025/workflows/CI/badge.svg)](https://github.com/Moonchichiii/battleship-revamp-2025/actions/workflows/ci.yml)
[![Security](https://github.com/Moonchichiii/battleship-revamp-2025/workflows/Security/badge.svg)](https://github.com/Moonchichiii/battleship-revamp-2025/actions/workflows/security.yml)
[![Deploy](https://github.com/Moonchichiii/battleship-revamp-2025/workflows/Deploy%20to%20Render/badge.svg)](https://github.com/Moonchichiii/battleship-revamp-2025/actions/workflows/deploy.yml)

## Development Roadmap

The complete project roadmap and development tracking can be found on the [Battleship Revamp 2025 GitHub Project Board](https://github.com/users/Moonchichiii/projects/43).

A complete architectural overhaul of a Python terminal game, transformed into a production-ready web application featuring intelligent AI opponents, modern web technologies, FastAPI backend, HTMX + Jinja2 UI, strict linting/typing, Dockerized runtime, and CI/CD with security gates.

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Architecture](#2-technical-architecture)
3. [AI Implementation](#3-ai-implementation)
4. [Features](#4-features)
5. [Technology Stack](#5-technology-stack)
6. [Development Setup](#6-development-setup)
7. [Testing & Quality Assurance](#7-testing--quality-assurance)
8. [CI/CD & Security](#8-cicd--security)
9. [Deployment](#9-deployment)
10. [Project Evolution](#10-project-evolution)
11. [License](#11-license)

---

## 1. Project Overview

### Current state (implemented)

- FastAPI app with HTMX/Jinja2 templates
- Minimal in-memory game engine (random fleet placement, hits/misses, simple stats)
- Dev hygiene: Black, Ruff, mypy, pre-commit (hooks enforced)
- GitHub Actions: CI (lint+tests), **Security** (Trivy + Docker Scout), **Deploy** (Render) chained after Security

### Planned

- Real auth (OAuth/social logins), persistent users/scores
- Smarter AI levels (beyond random)
- PostgreSQL persistence & Redis cache

### Brief Description

Battleship Revamp 2025 represents a comprehensive transformation from a simple Python terminal script to a full-stack web application. The project demonstrates modern software engineering practices, AI algorithm implementation, and production-grade deployment strategies.

Originally conceived as a basic terminal game in 2022 with random AI opponents and Google Sheets integration for score tracking, this iteration showcases advanced development methodologies including containerization, continuous integration, security scanning, and sophisticated AI decision-making algorithms.

### Target Audience

This project serves multiple constituencies:

- **Gaming Enthusiasts**: Players seeking intelligent opponents with varying difficulty levels and strategic depth
- **Developers**: Those interested in AI algorithm implementation, full-stack architecture, and modern deployment practices
- **Technical Recruiters**: Demonstration of comprehensive software engineering skills across multiple domains
- **Students**: Learning resource for game development, AI implementation, and web application architecture

---

## 2. Technical Architecture

### System Design

- **Backend API:** FastAPI + Starlette
- **UI:** Jinja2 + HTMX (server-rendered with partials)
- **State:** In-memory (per process) for now

**Planned:**

- **Authentication:** OAuth 2.0 (e.g., GitHub/Google)
- **Database:** PostgreSQL (prod), SQLite (dev)
- **Caching:** Redis (sessions/caching)

### Performance considerations

- In use: FastAPI's async request handling (non-blocking I/O)
- *(Planned)* Redis caching for hot paths
- *(Planned)* DB connection pooling and query tuning
- *(Planned)* Optimized static asset delivery

---

## 3. AI Implementation

The game will feature tiered AI difficulty levels, each using different algorithmic approaches:

### Implemented now

- **Rookie:** basic random/heuristic behavior, simple stats

### Planned tiers

- **Veteran:** probability heatmap targeting
- **Admiral:** search/lookahead (e.g., heuristic-driven)

Each AI level maintains distinct personality characteristics, ensuring varied gameplay experiences while providing appropriate challenge scaling.

---

## 4. Features

### Core Functionality

#### Game Mechanics

- Traditional Battleship gameplay with modern interface
- Multiple ship types and placement strategies
- Real-time game state updates
- Turn-based interaction system

#### AI Opponents

- **Current:** Rookie only. **Planned:** add Veteran/Admiral tiers with smarter targeting.
- *(Planned)* Adaptive behavior patterns
- *(Planned)* Performance analytics and statistics
- *(Planned)* Scalable difficulty progression

#### User Experience

- **Planned:** GitHub OAuth integration for seamless authentication
- **Planned:** Persistent player profiles and statistics
- **Planned:** Match history tracking and analysis
- Responsive design supporting multiple device types

#### Visual Design

- Retro CRT terminal aesthetic with modern usability
- ASCII graphics with contemporary UI elements
- Customizable display options
- Accessibility-focused design patterns

### Technical Features

#### Development Infrastructure

- Comprehensive CI/CD pipeline implementation
- Automated security scanning with Trivy and Docker Scout
- Code quality enforcement with Black, Ruff, and Mypy
- Performance testing integration with Locust

#### Deployment & Operations

- Docker containerization for consistent environments
- Multi-environment configuration management
- Automated deployment workflows
- Health monitoring and logging systems

---

## 5. Technology Stack

| Area          | Tech                                 |
|---------------|--------------------------------------|
| Web framework | FastAPI (Starlette)                  |
| Templating    | Jinja2 + HTMX                        |
| Styling       | Custom CSS (`static/css/retro.css`)  |
| Runtime       | Uvicorn (ASGI)                       |
| Lint/Format   | Ruff, Black                          |
| Typing        | mypy (strict)                        |
| Tests         | pytest (+ pytest-asyncio)            |
| Containers    | Docker (Buildx)                      |
| CI/CD         | GitHub Actions (ci, security, deploy)|
| Security      | Trivy (SARIF), Docker Scout          |

---

## 6. Development Setup

### Prerequisites

- Python **3.12**
- (Optional) Docker

### Local Development

```bash
git clone https://github.com/Moonchichiii/battleship-revamp-2025.git
cd battleship-revamp-2025

python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
# source venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install git hooks
pre-commit install

# Run the dev server
uvicorn main:app --reload
```

Visit [http://localhost:8000](http://localhost:8000)

### Docker Development

```bash
# Build and start all services
docker compose up --build
```

Visit [http://localhost:8000](http://localhost:8000)

### Environment Variables

_Note: The app runs without DB/OAuth today; these variables are for future use.

Create a `.env` file with the following configuration:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/dbname
REDIS_URL=redis://localhost:6379

# GitHub OAuth
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Application Settings
SECRET_KEY=your_secret_key
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## 7. Testing & Quality Assurance

```bash
# Format
black .

# Lint (auto-fix)
ruff check --fix .

# Type check
mypy .

# Tests (with coverage)
pytest -q --cov --cov-report=term-missing

# Run all hooks on all files
pre-commit run --all-files
```

### Testing Strategy

The project implements comprehensive testing across multiple layers:

#### Unit Testing

```bash
# Run all unit tests
pytest tests/ -v

# Run tests with coverage reporting
pytest tests/ --cov=src/ --cov-report=html
```

#### Performance Testing

```bash
# Load testing with Locust
locust -f tests/performance/locustfile.py --host=http://localhost:8000
```

### Security Testing

Automated security scanning is integrated into the CI/CD pipeline:

- **Trivy**: Container vulnerability scanning
- **Docker Scout**: Dependency vulnerability assessment
- **SAST**: *(planned)* Static application security testing

---

## 8. CI/CD & Security

### Workflows

- **CI** (`.github/workflows/ci.yml`): Black, Ruff, mypy, pytest (+ coverage)
- **Security** (`.github/workflows/security.yml`): build once → scan with **Trivy** (fail High/Critical + upload SARIF) and **Docker Scout** (fail High/Critical)
- **Deploy** (`.github/workflows/deploy.yml`): triggers on `workflow_run` after **Security** succeeds for a push to `main`; builds & pushes image to Render and triggers deploy.

### Recommended branch protection

- Require checks from **CI** and **Security** before merging to `main`.

---

## 9. Deployment

### Production Deployment

The application supports multiple deployment strategies:

#### Docker Deployment

```bash
# Production build
docker compose -f docker-compose.prod.yml up --build -d

# Health check
curl http://localhost:8000/health
```

Visit [http://localhost:8000](http://localhost:8000)

#### Cloud Deployment

- Configured for deployment on major cloud platforms
- Environment-specific configuration management
- Automated database migrations
- Health monitoring and logging

### Monitoring & Observability

Production deployments include:

- Application performance monitoring
- Error tracking and alerting
- User analytics and engagement metrics
- Infrastructure monitoring

---

## 10. Project Evolution

### Development Timeline

| Phase              | Period   | Key Achievements                                      |
|--------------------|----------|------------------------------------------------------|
| **Initial Concept**| 2022     | Python terminal game with Google Sheets integration  |
| **Architecture Planning** | Early 2025 | System design and technology selection |
| **Core Development** | 2025 | Full-stack implementation with AI algorithms |
| **Production Release** | 2025 | Deployed application with CI/CD pipeline |

### Technical Achievements

#### From Simple Script to Production Application

- Transformed basic Python script into scalable web application
- Implemented sophisticated AI algorithms for game intelligence
- Established comprehensive development and deployment pipelines
- Achieved production-ready quality with security and performance optimization

#### Key Learning Outcomes

- Full-stack web development with modern frameworks
- AI algorithm implementation and optimization
- DevOps practices and CI/CD pipeline creation
- Security-first development approach
- Performance optimization and scalability planning

### Future Enhancements

#### Planned Features

- Multiplayer gameplay with real-time synchronization
- Tournament system with ranking algorithms
- Advanced AI customization options
- Mobile application development
- Analytics dashboard for gameplay insights

#### Technical Improvements

- Microservices architecture migration
- Advanced caching strategies
- Machine learning model optimization
- Enhanced security features
- Improved observability and monitoring

---

## 11. License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

### Acknowledgments

Special thanks to the open-source community for the foundational technologies that made this project possible, and to the Python and FastAPI communities for excellent documentation and support.

---

**From Terminal Script to Production Application** - A demonstration of modern software engineering practices and comprehensive full-stack development capabilities.
