import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from markitdown import MarkItDown

app = FastAPI(title="MarkItDown MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

md = MarkItDown()

# Endpoints d'OAuth2 per validar el registre de Claude
@app.get("/authorize")
async def authorize(redirect_uri: str = "", state: str = ""):
    return HTMLResponse(
        content=f'<script>window.location.href="{redirect_uri}?code=valid_code&state={state}";</script>'
    )

@app.post("/token")
async def token():
    return JSONResponse({
        "access_token": "mock_token_markitdown",
        "token_type": "bearer",
        "expires_in": 3600
    })

# Endpoint de comprovació d'estat
@app.get("/")
async def root():
    return {"status": "ok", "service": "MarkItDown MCP Server"}

# Eina de conversió accessible via HTTP / SSE
@app.post("/convert")
async def convert(filepath: str):
    try:
        result = md.convert(filepath)
        return {"success": True, "text": result.text_content}
    except Exception as e:
        return {"success": False, "error": str(e)}
