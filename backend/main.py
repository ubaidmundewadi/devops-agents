import os
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.infra_agent import InfraAgentSession

# Setup Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

app = FastAPI(title="AWS Infra Agent Server")

# Root directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
TERRAFORM_DIR = os.path.join(BASE_DIR, "terraform")

os.makedirs(TERRAFORM_DIR, exist_ok=True)

# Active connections registry
sessions = {}

@app.get("/.well-known/agent-card.json")
async def agent_card():
    """Kagent-native readiness probe endpoint."""
    return {"schema_version": "v1", "name": "infra-agent"}


@app.get("/")
async def get_index():
    """Serves the main frontend page."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Frontend build files not found. Place index.html in frontend/"}



@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket, session_id: str = "default_session"):
    await websocket.accept()
    client_id = f"{websocket.client.host}:{websocket.client.port}"
    logger.info(f"WebSocket client connected: {client_id}")
    
    # Callback to send data to this websocket client
    async def send_to_client(data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")

    # Create a new session for this client
    session = InfraAgentSession(
        send_to_client=send_to_client,
        workspace_dir=TERRAFORM_DIR,
        conversation_id=session_id
    )
    sessions[client_id] = session
    
    # Send credentials status immediately upon connection
    await session.send_credentials_status()

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning(f"Malformed JSON from client: {data_str}")
                continue
                
            mtype = data.get("type")
            if mtype == "start":
                prompt = data.get("prompt", "")
                logger.info(f"Starting agent run for client {client_id} with prompt: {prompt}")
                await session.start(prompt)
            else:
                # Forward other actions (approval, text inputs) to the session handler
                logger.info(f"Forwarding message type '{mtype}' to session.")
                await session.handle_client_message(data)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    finally:
        # Cleanup
        if client_id in sessions:
            sess = sessions.pop(client_id)
            if sess.agent_task and not sess.agent_task.done():
                sess.agent_task.cancel()
                logger.info(f"Cancelled agent task for client {client_id}")

# Mount remaining static assets (CSS, JS) after root route
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
