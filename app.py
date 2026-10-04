import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from llm_client import configured_provider
from logs import LOG_PATH
from orchastrator import agent_fun

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_FILE = PROJECT_ROOT / "front _end" / "index.html"


class ChatRequest(BaseModel):
	query: str = Field(min_length=1, max_length=2000)
	latitude: float | None = Field(default=None, ge=-90, le=90)
	longitude: float | None = Field(default=None, ge=-180, le=180)

	@field_validator("query")
	@classmethod
	def strip_query(cls, value: str) -> str:
		value = value.strip()
		if not value:
			raise ValueError("Query must not be blank")
		return value

	@model_validator(mode="after")
	def validate_coordinate_pair(self):
		if (self.latitude is None) != (self.longitude is None):
			raise ValueError("Provide both latitude and longitude, or neither.")
		return self


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
	logger.info("Connecting to MCP tools")
	async with agent_fun.open_mcp_session() as session:
		agent_fun._mcp_session = session
		app.state.mcp_session = session
		logger.info("MCP tools connected; logs are written to %s", LOG_PATH)
		try:
			yield
		finally:
			app.state.mcp_session = None
			agent_fun._mcp_session = None


app = FastAPI(title="Weekend Wizard", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
	return FileResponse(FRONTEND_FILE)


@app.get("/api/health")
async def health() -> dict[str, str]:
	connected = getattr(app.state, "mcp_session", None) is not None
	return {
		"status": "ok",
		"mcp": "connected" if connected else "disconnected",
		"provider": configured_provider(),
		"log_file": str(LOG_PATH),
	}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, object]:
	if getattr(app.state, "mcp_session", None) is None:
		raise HTTPException(status_code=503, detail="MCP tools are not connected")

	try:
		return await agent_fun.process_user_query(
			request.query,
			latitude=request.latitude,
			longitude=request.longitude,
			request_name="POST /api/chat",
		)
	except Exception as exc:
		logger.error("Agent request failed (%s)", type(exc).__name__)
		raise HTTPException(
			status_code=502,
			detail="The agent could not complete this request",
		) from exc


def _find_available_port(host: str, first_port: int = 8000) -> int:
	for port in range(first_port, min(first_port + 100, 65536)):
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
			try:
				server_socket.bind((host, port))
			except OSError:
				continue
			return port
	raise RuntimeError("No available local port found in the 8000-8099 range")


if __name__ == "__main__":
	import uvicorn

	host = "127.0.0.1"
	port = _find_available_port(host)
	uvicorn.run(app, host=host, port=port, log_level="info")
