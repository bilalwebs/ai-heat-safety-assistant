# 🔥 AI Heat Safety Assistant

An AI-powered heat safety and risk assistant that provides real-time heat intelligence, heat-risk analysis, personalized safety recommendations, and outdoor activity guidance.

## 🚀 Project Overview

The **AI Heat Safety Assistant** is a hackathon project designed to help users understand current heat conditions and make safer decisions about outdoor activities.

The system combines real-time/hyperlocal temperature intelligence, heat-risk analysis, AI-powered recommendations, and an AI assistant to provide practical and data-grounded heat safety guidance.

## ✨ Key Features

- 🌡️ Real-time/hyperlocal temperature intelligence
- 🔥 Heat-risk analysis and scoring
- 🤖 AI-powered heat safety recommendations
- 🏃 Outdoor activity guidance
- 💬 AI heat safety assistant
- 📍 Location-based heat information
- 🔗 FortyGuard API integration
- ⚡ FastAPI backend
- 📊 Data-driven heat intelligence

## 🏗️ System Architecture

```text
User
  ↓
Next.js Frontend
  ↓
FastAPI Backend
  ↓
FortyGuard Temperature API
  ↓
Heat Intelligence & Risk Analysis
  ↓
AI Agent
  ↓
Personalized Heat Safety Response
```

## 🛠️ Tech Stack

### Backend

- Python
- FastAPI
- Uvicorn
- Pydantic
- Pydantic Settings
- HTTPX
- Pytest

### AI / Data

- AI Agent
- Heat-risk analysis
- Data processing
- AI-powered recommendations

### Frontend

- Next.js
- TypeScript

### External API

- FortyGuard Temperature API

## 📁 Project Structure

```text
ai-heat-safety-assistant/
│
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── exceptions.py
│   │   │   └── logging.py
│   │   │
│   │   ├── routers/
│   │   │   ├── health.py
│   │   │   ├── temperature.py
│   │   │   ├── heat_risk.py
│   │   │   ├── recommendations.py
│   │   │   ├── outdoor_plan.py
│   │   │   └── chat.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── temperature.py
│   │   │   ├── heat_risk.py
│   │   │   ├── recommendations.py
│   │   │   ├── outdoor_plan.py
│   │   │   └── chat.py
│   │   │
│   │   ├── services/
│   │   │   ├── fortyguard_service.py
│   │   │   ├── heat_service.py
│   │   │   └── ai_service.py
│   │   │
│   │   └── main.py
│   │
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_health.py
│   │   ├── test_temperature.py
│   │   ├── test_heat_risk.py
│   │   └── test_ai_service.py
│   │
│   ├── .env.example
│   ├── .gitignore
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── run.py
│   └── README.md
│
├── README.md
└── .gitignore
```

## 👥 Team

### 👨‍💻 Bilal — Backend & API

Responsibilities:

- FastAPI backend development
- FortyGuard / weather API integration
- Location and temperature data handling
- Backend API endpoint development
- API data processing and validation
- Backend testing
- Backend integration with the AI agent and frontend

### 🤖 Hanzala — AI/ML & Data Science

Responsibilities:

- Heat-risk analysis and scoring
- Define Low, Moderate, High, and Extreme risk levels
- Analyze temperature and other available heat-related data
- Perform data processing and analysis
- Explore ML-based risk prediction if suitable data is available
- Assist with project management and overall coordination

### 🧠 Hammad Ur Rehman — AI Agent & Frontend

#### AI Agent

- Build the AI agent
- Tool/function calling
- Personalized heat-safety recommendations
- AI chatbot
- Best-time outdoor activity recommendations

#### Frontend

- Next.js + TypeScript
- Dashboard UI
- Heat-risk cards
- Temperature charts
- Heat-safe city/map view
- AI chatbot interface
- Responsive design

## 🔌 Backend API

The FastAPI backend provides the following endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health/system check |
| POST | `/api/v1/temperature` | Get temperature and heat intelligence |
| POST | `/api/v1/heat-risk` | Analyze current heat risk |
| POST | `/api/v1/recommendations` | Generate heat-safety recommendations |
| POST | `/api/v1/outdoor-plan` | Provide outdoor activity guidance |
| POST | `/api/v1/chat` | AI heat-safety assistant |

Detailed backend documentation is available in [`backend/README.md`](backend/README.md).

## ⚙️ Backend Setup

### 1. Open the project

```powershell
cd D:\ai-heat-safety-assistant\backend
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

### 3. Activate the virtual environment

```powershell
.venv\Scripts\activate
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Configure environment variables

Create a `.env` file inside the `backend` directory based on `.env.example`.

```powershell
Copy-Item .env.example .env
```

Configure the required FortyGuard API settings in `.env`.

**Never commit `.env` to GitHub.**

### 6. Start the FastAPI server

```powershell
uvicorn app.main:app --reload --port 8000
```

The backend will be available at:

```text
http://127.0.0.1:8000
```

## 🔐 Environment Variables

The backend uses environment variables for configuration and secrets.

Important variables include:

```text
FORTYGUARD_API_KEY
FORTYGUARD_BASE_URL
FORTYGUARD_TEMPERATURE_PATH
FORTYGUARD_AUTH_HEADER
FORTYGUARD_AUTH_SCHEME
FORTYGUARD_HTTP_METHOD
FORTYGUARD_REQUEST_STYLE
FORTYGUARD_LOCATION_PARAM
FORTYGUARD_LAT_PARAM
FORTYGUARD_LON_PARAM
FORTYGUARD_TIMEOUT_SECONDS
```

Optional AI provider configuration:

```text
AI_API_KEY
AI_BASE_URL
AI_MODEL
AI_TIMEOUT_SECONDS
```

Actual secret values must only be stored in `.env`.

## 📚 API Documentation

Once the backend is running, open:

### Swagger UI

```text
http://127.0.0.1:8000/docs
```

### ReDoc

```text
http://127.0.0.1:8000/redoc
```

FastAPI automatically provides interactive API documentation through Swagger UI and ReDoc.

## 🧪 Testing

The backend uses `pytest` for automated testing.

Run the complete test suite:

```powershell
cd backend
pytest
```

The automated tests cover:

- Health endpoint
- Request validation
- Temperature processing
- FortyGuard success responses
- FortyGuard timeout handling
- Connection errors
- HTTP errors
- Invalid API responses
- Heat-risk processing
- AI service behavior
- AI fallback behavior

External FortyGuard API calls are not used in automated tests. External API behavior is tested using mocked HTTP responses.

## 🔗 Real FortyGuard Integration

The FortyGuard integration is isolated inside:

```text
backend/app/services/fortyguard_service.py
```

The application does not invent or fabricate FortyGuard API endpoints, authentication methods, request parameters, or response structures.

The real integration requires the official FortyGuard API configuration and credentials.

Before marking the integration as fully complete, the following must be verified against the official API documentation:

- Base URL
- Temperature endpoint
- Authentication method
- HTTP method
- Required request parameters/body
- Actual response structure

The real API should then be tested manually using the configured `.env` file.

## 🛡️ Error Handling

The backend uses consistent HTTP error handling.

Supported error categories include:

- `400` — Invalid request
- `404` — Resource/location not found when applicable
- `422` — Validation error
- `500` — Unexpected internal server error
- `502` — Third-party API failure
- `503` — External service unavailable
- `504` — External API timeout

Raw stack traces and sensitive third-party API information are not exposed to clients.

## 🔒 Security

The project follows basic security practices:

- API keys are stored in environment variables.
- `.env` files are excluded from Git.
- API keys are never returned in API responses.
- Secrets are not hard-coded.
- External API requests use configured timeouts.
- Sensitive information is not written to logs.
- Incoming API data is validated using Pydantic schemas.

## 📊 Development Status

### Backend — Bilal

- [x] FastAPI backend development
- [x] Backend project architecture
- [x] Configuration management
- [x] Health endpoint
- [x] Temperature endpoint
- [x] Heat-risk endpoint
- [x] AI recommendations endpoint
- [x] Outdoor planner endpoint
- [x] AI chat endpoint
- [x] Request validation
- [x] Error handling
- [x] Logging
- [x] CORS configuration
- [x] Swagger/OpenAPI documentation
- [x] ReDoc documentation
- [x] Automated backend tests
- [ ] Real FortyGuard API verification
- [ ] Frontend integration
- [ ] AI agent integration

### AI/ML — Hanzala

- [ ] Heat-risk analysis and scoring
- [ ] Low / Moderate / High / Extreme risk methodology
- [ ] Heat-related data analysis
- [ ] Data processing
- [ ] ML-based risk prediction evaluation
- [ ] Risk-analysis integration with backend

### AI Agent & Frontend — Hammad Ur Rehman

#### AI Agent

- [ ] AI agent
- [ ] Tool/function calling
- [ ] Personalized recommendations
- [ ] AI chatbot
- [ ] Best-time outdoor activity recommendations

#### Frontend

- [ ] Next.js + TypeScript setup
- [ ] Dashboard UI
- [ ] Heat-risk cards
- [ ] Temperature charts
- [ ] Heat-safe city/map view
- [ ] AI chatbot interface
- [ ] Responsive design

### Final Integration

- [ ] Frontend → FastAPI integration
- [ ] FastAPI → FortyGuard integration
- [ ] Risk analysis integration
- [ ] AI Agent integration
- [ ] End-to-end testing
- [ ] Bug fixing
- [ ] Final UI/UX
- [ ] Hackathon demo
- [ ] Hackathon presentation

## ⚠️ Development Note

The real FortyGuard API integration will only be marked complete after the official API contract is configured and the live API response has been successfully verified.

No third-party API endpoint, authentication method, request format, or response structure is guessed or fabricated.

## 🔄 Final System Flow

```text
Frontend
   ↓
FastAPI Backend
   ↓
FortyGuard Temperature API
   ↓
Verified Temperature / Heat Data
   ↓
Heat Risk Analysis
   ↓
AI Agent
   ↓
Personalized Heat Safety Recommendations
   ↓
Frontend
```

## 🎯 Project Goal

The goal of the AI Heat Safety Assistant is to help people make safer outdoor decisions during periods of extreme heat by combining real-time heat intelligence, risk analysis, and AI-powered safety guidance.

## 📄 License

This project is currently being developed as a hackathon project.
