"""Socket.IO server for real-time WebUI communication.

Provides real-time bidirectional event-based communication
for the Open WebUI frontend.
"""

from __future__ import annotations

import logging
from typing import Any

import socketio

logger = logging.getLogger(__name__)

# Create async Socket.IO server with CORS support
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,  # Disable socket.io's verbose logging
    engineio_logger=False,
)

# Wrap in ASGI app
socket_app = socketio.ASGIApp(sio)


@sio.event
async def connect(sid: str, environ: dict[str, Any]) -> None:
    """
    Handle client connection.

    Args:
        sid: Socket session ID.
        environ: WSGI environment dict.
    """
    logger.info(f"🌐 Socket.IO client connected: {sid}")


@sio.event
async def disconnect(sid: str) -> None:
    """
    Handle client disconnection.

    Args:
        sid: Socket session ID.
    """
    logger.info(f"💔 Socket.IO client disconnected: {sid}")


@sio.event
async def join_room(sid: str, data: dict[str, Any]) -> None:
    """
    Join a chat room for receiving chat-specific events.

    Args:
        sid: Socket session ID.
        data: Room data containing 'room' key.
    """
    room = data.get("room")
    if not room:
        logger.warning(f"⚠️ Client {sid} tried to join without room ID")
        return

    await sio.enter_room(sid, room)
    logger.info(f"👥 Client {sid} joined room {room}")

    # Notify user they joined successfully
    await sio.emit("room_joined", {"room": room}, room=sid)


@sio.event
async def leave_room(sid: str, data: dict[str, Any]) -> None:
    """
    Leave a chat room.

    Args:
        sid: Socket session ID.
        data: Room data containing 'room' key.
    """
    room = data.get("room")
    if not room:
        logger.warning(f"⚠️ Client {sid} tried to leave without room ID")
        return

    await sio.leave_room(sid, room)
    logger.info(f"👋 Client {sid} left room {room}")


@sio.event
async def ping(sid: str, data: dict[str, Any]) -> dict[str, str]:
    """
    Handle ping/pong for connection health checks.

    Args:
        sid: Socket session ID.
        data: Ping data.

    Returns:
        Pong response.
    """
    logger.debug(f"🏓 Ping from {sid}")
    return {"status": "pong"}


# Utility functions for emitting events from other parts of the app

async def emit_chat_message(room: str, message: dict[str, Any]) -> None:
    """
    Emit a chat message to a specific room.

    Args:
        room: Chat room ID.
        message: Message data to broadcast.
    """
    await sio.emit("chat_message", message, room=room)
    logger.debug(f"💬 Emitted message to room {room}")


async def emit_chat_update(room: str, update: dict[str, Any]) -> None:
    """
    Emit a chat update event (e.g., typing indicator, edit).

    Args:
        room: Chat room ID.
        update: Update data to broadcast.
    """
    await sio.emit("chat_update", update, room=room)
    logger.debug(f"📝 Emitted update to room {room}")


async def emit_model_status(status: dict[str, Any]) -> None:
    """
    Emit model status change to all connected clients.

    Args:
        status: Model status data.
    """
    await sio.emit("model_status", status)
    logger.debug("🤖 Emitted model status update")
