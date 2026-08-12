import json
import asyncio
import urllib.request
import tempfile
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
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

# --- MOCK D'AUTENTICACIÓ OAUTH ---
@app.get("/authorize")
async def authorize(redirect_uri: str = "", state: str = ""):
    return HTMLResponse(
        content=f'<script>window.location.href="{redirect_uri}?code=valid_code&state={state}";</script>'
    )

@app.post("/token")
async def token():
    return JSONResponse({
        "access_token": "mock_token",
        "token_type": "bearer",
        "expires_in": 3600
    })

# --- PROTOCOL MCP NADIU (SSE + JSON-RPC) ---
clients = {}

@app.get("/sse")
async def sse_endpoint(request: Request):
    client_id = "claude_user"
    queue = asyncio.Queue()
    clients[client_id] = queue

    async def event_generator():
        # Negociació inicial de l'MCP: indica on enviar els missatges
        yield f"event: endpoint\ndata: /messages?client_id={client_id}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await queue.get()
                yield f"data: {message}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            clients.pop(client_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/messages")
async def messages_endpoint(request: Request, client_id: str = "claude_user"):
    if client_id not in clients:
        return JSONResponse({"error": "Unknown client"}, status_code=400)

    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")

    response = None
    
    # 1. Inicialització del servidor MCP
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "markitdown-server", "version": "1.0.0"}
            }
        }
    
    # 2. Llista d'eines disponibles
    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": "convert_url_to_markdown",
                        "description": "Converteix un document des d'una URL publica a format Markdown.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "URL publica del document (PDF, DOCX, etc.)"}
                            },
                            "required": ["url"]
                        }
                    }
                ]
            }
        }
        
    # 3. Execució de l'eina per part de Claude
    elif method == "tools/call":
        tool_name = body.get("params", {}).get("name")
        args = body.get("params", {}).get("arguments", {})
        
        if tool_name == "convert_url_to_markdown":
            url = args.get("url")
            content = ""
            try:
                # Descarrega el document a un fitxer temporal i el converteix
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    urllib.request.urlretrieve(url, tmp.name)
                    result = md.convert(tmp.name)
                    content = result.text_content
            except Exception as e:
                content = f"Error convertint el document: {str(e)}"
                
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": content}]
                }
            }

    # Envia la resposta al canal SSE obert per Claude
    if response and msg_id is not None:
        await clients[client_id].put(json.dumps(response))

    return JSONResponse({"status": "accepted"})
