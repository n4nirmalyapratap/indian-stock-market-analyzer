import uuid
import datetime
from typing import Dict, List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()

_rooms: Dict[str, List[dict]] = {}
_connections: Dict[str, Set[WebSocket]] = {}

MAX_HISTORY = 100


@router.get("/chat/history/{symbol}")
async def chat_history(symbol: str, limit: int = Query(default=50, ge=1, le=100)):
    symbol = symbol.upper()
    msgs = _rooms.get(symbol, [])
    return {"symbol": symbol, "messages": msgs[-limit:]}


@router.websocket("/chat/ws/{symbol}")
async def chat_websocket(websocket: WebSocket, symbol: str):
    symbol = symbol.upper()
    await websocket.accept()

    if symbol not in _connections:
        _connections[symbol] = set()
    _connections[symbol].add(websocket)

    try:
        while True:
            data = await websocket.receive_json()

            username = str(data.get("username", "Guest")).strip()[:32] or "Guest"
            text = str(data.get("text", "")).strip()[:500]

            if not text:
                continue

            msg = {
                "id": str(uuid.uuid4()),
                "symbol": symbol,
                "username": username,
                "text": text,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }

            if symbol not in _rooms:
                _rooms[symbol] = []
            _rooms[symbol].append(msg)
            if len(_rooms[symbol]) > MAX_HISTORY:
                _rooms[symbol] = _rooms[symbol][-MAX_HISTORY:]

            dead: Set[WebSocket] = set()
            for conn in list(_connections.get(symbol, set())):
                try:
                    await conn.send_json(msg)
                except Exception:
                    dead.add(conn)
            if dead:
                _connections[symbol] -= dead

    except WebSocketDisconnect:
        _connections.get(symbol, set()).discard(websocket)
    except Exception:
        _connections.get(symbol, set()).discard(websocket)
