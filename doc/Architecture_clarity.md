# Clarity Architecture

## What is MCP?

**Model Context Protocol (MCP)** is a standard by Anthropic for connecting AI assistants to external tools and data. Think of it as a REST API specifically designed for LLMs:

- ChatGPT calls **tools** (like API endpoints) on the MCP server
- The server returns **structured data** that ChatGPT can use
- Tools can also return **widgets** (React components) that render in the ChatGPT UI

**Key difference from REST**: MCP responses include `structuredContent` with both data AND instructions for the AI on how to respond to the user (`assistant_guidance`).

---

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              ChatGPT                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐   │
│  │   User Chat  │───▶│  AI Reasoning │───▶│  Widget Renderer (React) │   │
│  └──────────────┘    └──────────────┘    └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
          │                    │                         ▲
          │                    │ MCP Tool Call           │ Widget HTML/JS
          │                    ▼                         │
┌─────────────────────────────────────────────────────────────────────────┐
│                         Clarity MCP Server                               │
│                    (Python / FastMCP / Starlette)                        │
└─────────────────────────────────────────────────────────────────────────┘
          │                                              │
          │ HTTP (sync)                                  │ HTTP (sync)
          ▼                                              ▼
┌─────────────────────────┐                 ┌─────────────────────────┐
│   Shared Backend        │                 │   OAuth 2.1 Provider    │
│   (FastAPI)             │                 │   (JWT/RS256)           │
└─────────────────────────┘                 └─────────────────────────┘
          │                                              │
          ▼                                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL + Redis                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Architecture

```mermaid
flowchart TB
    subgraph "ChatGPT (OpenAI Infrastructure)"
        UI["User Interface"]
        LLM["LLM Reasoning<br/>(clusters thoughts, decides tools)"]
        Widget["Widget Renderer<br/>(React in iframe)"]
    end

    subgraph "OAuth 2.1 Flow (One-time per user)"
        Auth["/oauth/authorize<br/>+ PKCE Challenge"]
        Consent["Consent Screen<br/>(User approves scopes)"]
        Token["/oauth/token<br/>Returns JWT"]
        JWKS["/.well-known/jwks.json<br/>Public Keys for Validation"]
    end

    subgraph "Clarity MCP Server (Render)"
        Middleware["Middleware<br/>- Fix ChatGPT headers<br/>- Extract Auth token"]
        MCP["server.py<br/>FastMCP Endpoint /mcp"]
        MCPAuth["mcp_auth.py<br/>JWT Validation via JWKS"]

        subgraph "Request Handlers"
            ToolDispatcher["handlers/tools.py<br/>Route to correct tool"]
            ResourceHandler["handlers/resources.py<br/>Serve widget HTML/JS"]
        end

        subgraph "Tools (7 total)"
            Organize["organize_thoughts<br/>Cluster user's thoughts"]
            Prioritize["prioritize_clusters<br/>Set P1/P2/P3 priorities"]
            Save["save_board<br/>Persist to database"]
            Load["load_saved_board<br/>Load + show widget"]
            Read["read_saved_board<br/>Load data only"]
            Edit["edit_board<br/>Modify clusters"]
            Delete["delete_my_data<br/>GDPR deletion"]
        end

        Logic["tool_logic.py<br/>Pure functions (no I/O)"]
        Persist["persistence.py<br/>HTTP calls to Backend"]
    end

    subgraph "Shared Backend (Render)"
        FastAPI["backend/main.py<br/>FastAPI Application"]

        subgraph "OAuth Provider"
            AuthService["authorization_service.py"]
            TokenService["token_service.py"]
            JWKSService["jwks_service.py"]
        end

        subgraph "Clarity API"
            ClarityRouter["/api/clarity/clusters<br/>CRUD for boards"]
        end

        Models["models.py<br/>SQLAlchemy ORM"]
        Crypto["crypto.py<br/>Encryption utilities"]
    end

    subgraph "Data Layer"
        PG[("PostgreSQL<br/>- Users<br/>- OAuth tokens<br/>- Clarity boards")]
        Redis[("Redis<br/>- JWKS cache<br/>- Rate limiting")]
    end

    %% OAuth Flow (numbered)
    UI -->|"1. User clicks Connect"| Auth
    Auth -->|"2. Show consent"| Consent
    Consent -->|"3. User approves"| Token
    Token -->|"4. JWT (RS256)"| UI

    %% MCP Request Flow (numbered)
    UI -->|"User: 'help me organize my thoughts'"| LLM
    LLM -->|"5. MCP call + Bearer JWT"| Middleware
    Middleware -->|"6. Fixed headers"| MCP
    MCP -->|"7. Validate JWT"| MCPAuth
    MCPAuth -.->|"Fetch public keys"| JWKS
    MCPAuth -->|"8. Authorized"| ToolDispatcher

    %% Tool dispatch
    ToolDispatcher --> Organize
    ToolDispatcher --> Prioritize
    ToolDispatcher --> Save
    ToolDispatcher --> Load
    ToolDispatcher --> Read
    ToolDispatcher --> Edit
    ToolDispatcher --> Delete

    %% Tool logic
    Organize --> Logic
    Prioritize --> Logic

    %% Persistence
    Save --> Persist
    Load --> Persist
    Read --> Persist
    Edit --> Persist
    Delete --> Persist
    Persist -->|"HTTP POST/GET/DELETE"| ClarityRouter
    ClarityRouter --> Models
    Models --> PG

    %% Widget serving
    Load -->|"Returns widget URI"| ResourceHandler
    Organize -->|"Returns widget URI"| ResourceHandler
    ResourceHandler -->|"9. Widget HTML/JS"| Widget
    Widget --> UI

    %% Backend connections
    Auth --> AuthService
    Token --> TokenService
    JWKS --> JWKSService
    AuthService --> Redis
    TokenService --> PG
    TokenService --> Crypto
    MCPAuth -.-> Redis

    %% Styling - dark text for readability
    classDef oauth fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef mcp fill:#e8f4e8,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef chatgpt fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000
    classDef default color:#000,stroke:#333,stroke-width:1px

    class Auth,Consent,Token,JWKS,AuthService,TokenService,JWKSService oauth
    class MCP,MCPAuth,ToolDispatcher,ResourceHandler,Organize,Prioritize,Save,Load,Read,Edit,Delete,Middleware mcp
    class PG,Redis data
    class UI,LLM,Widget chatgpt
```

---

## Key Concepts for Reviewers

### 1. Stateless Design
- No server-side sessions
- Every request includes JWT in `Authorization: Bearer` header
- Enables horizontal scaling (just add more instances)

### 2. Separation of Concerns

| Layer | Responsibility |
|-------|----------------|
| **ChatGPT LLM** | Reasoning, clustering thoughts, deciding which tool to call |
| **MCP Server** | Validation, formatting, scope enforcement |
| **Backend API** | Database CRUD, encryption |
| **Widget** | Visual rendering of clusters |



### 3. Security Model

```
User ──OAuth──▶ JWT (RS256, 1h expiry)
                    │
                    ▼
            MCP Server validates:
            1. Signature (via JWKS)
            2. Expiry
            3. Scopes (clarity.read, clarity.write)
                    │
                    ▼
            Tool executes if authorized
```

### 4. Widget Integration

Tools can return a `widget_uri` pointing to a React component:
```
organize_thoughts returns:
├── content: "" (empty, LLM uses assistant_guidance instead)
├── structuredContent:
│   ├── clusters: [...data for widget...]
│   ├── thoughts_exhausted: bool
│   └── assistant_guidance: "Say this to user..."
└── _meta:
    └── openai/outputTemplate: "resource://clarity-widget"
```

ChatGPT fetches the widget via `ResourceHandler` and renders it in an iframe.

---

## Data Flow Example

**User says**: "I'm overwhelmed, help me organize my thoughts"

1. **ChatGPT LLM** recognizes intent, collects thoughts through conversation
2. **LLM clusters** the thoughts (AI reasoning happens here, not in backend)
3. **LLM calls** `organize_thoughts` tool with clustered data
4. **MCP Server** validates JWT, checks `clarity.write` scope
5. **Tool** validates input schema, enriches clusters (adds counts)
6. **Response** includes widget URI + `assistant_guidance`
7. **ChatGPT** renders widget, follows guidance to ask about priorities
8. **User** selects P1/P2/P3, LLM calls `prioritize_clusters`
9. **User** says "save this", LLM calls `save_board`
10. **Backend** persists to PostgreSQL

---

## Deployment

| Component | Platform | URL Pattern |
|-----------|----------|-------------|
| MCP Server | Render | `https://clarity-mcp.onrender.com/mcp` |
| Backend API | Render | `https://priority-guardian.onrender.com/api/...` |
| PostgreSQL | Render | Managed database |
| Redis | Render | Managed Redis |
