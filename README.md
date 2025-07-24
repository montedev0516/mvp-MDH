# MDH For Supply Chain (MVP)

- **MDH** is an AI-powered, cloud-based transportation management platform that seamlessly integrates with supply chain operations to provide end-to-end visibility, control, and optimization of logistics processes.
- **MDH** is an AI-powered SaaS application designed for comprehensive dispatch management in the transportation industry. The system provides end-to-end fleet management, dispatch coordination, expense tracking, and financial reporting capabilities.

### **Overview**
- **Platform**: SaaS-based transportation management system
- **Architecture**: Multi-tenant, cloud-native with real-time capabilities
- **Technology Stack**: Django, PostgreSQL, Redis, OpenAI model, AI/ML integration, AWS, Docker, Celery
- **Deployment**: AWS cloud infrastructure with containerization
- **Security**: Enterprise-grade with role-based access control

### **Mission & Vision**
- **Mission**: Transform transportation management into a comprehensive supply chain solution
- **Vision**: Become the leading integrated platform for transportation and supply chain operations

### **Video***
- https://drive.google.com/file/d/1HqXoI6p0ULSP1uq7pFQa7g0UGXLZB3rg/view
- https://drive.google.com/file/d/14Ml1j1oRw2uKIXEo4pVndfKIN0Hvyqs2/view
- https://drive.google.com/file/d/1Z2pvYoZO4PV3nevUKv5d33Eb2d1lod5r/view
- https://drive.google.com/file/d/1ODE5ADxzIMc7cxiSnou8FAcyD1T3aTpw/view

## System Architecture

### High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │   Web Servers   │    │   Background    │
│    (Caddy)      │────│    (Django)     │────│   Workers       │
│                 │    │                 │    │   (Celery)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Database      │    │     Cache       │
                       │ (PostgreSQL)    │    │    (Redis)      │
                       └─────────────────┘    └─────────────────┘
```

## Technology Stack

### Backend Framework
- **Django 5.1.2**: Main web framework
- **Python 3.12+**: Programming language
- **PostgreSQL**: Primary database (with SQLite fallback for development)
- **Redis**: Caching and session storage

### Asynchronous Processing
- **Celery**: Background task processing
- **Celery Beat**: Scheduled task management
- **Flower**: Celery monitoring interface

### Frontend Technologies
- **Django Templates**: Server-side rendering
- **Bootstrap 5**: CSS framework for responsive design
- **HTMX**: Dynamic frontend interactions without JavaScript frameworks
- **Crispy Forms**: Enhanced form rendering
- **Django Tables2**: Advanced table rendering with sorting/filtering

### Infrastructure & Deployment
- **Docker & Docker Compose**: Containerization
- **Gunicorn**: WSGI server for production
- **WhiteNoise**: Static file serving
- **Caddy**: Reverse proxy and SSL termination
- **AWS Services**: Cloud deployment platform

### Development Tools
- **UV**: Fast Python package manager
- **Pre-commit**: Code quality hooks
- **Ruff**: Python linting and formatting
- **Safety & Bandit**: Security scanning
- **Debug Toolbar**: Development debugging

### Third-Party Integrations
- **OpenAI API**: AI-powered document processing
- **AWS S3**: File storage
- **Plotly**: Data visualization
- **WeasyPrint**: PDF generation

---
  
## For ground zero pre-requisite instructions [click here](https://github.com/montedev0516/mvp-MDH/blob/main/MDH_Introduction.md)

### Setup

```bash
git clone git@github.com:montedev0516/mvp-MDH.git && cd mvp-MDH
pip install -U uv
cd web && uv sync --frozen
cd ../ && uv run pre-commit install
# Set Python interpreter from .venv folder (VSCode)
```

### Local Development

```bash
make dev-build dev-up
make dev-migrate dev-createsuperuser # first time setup
make dev-logs-web
```

> Author - montedev

### Made in montedev for a better 🌎
