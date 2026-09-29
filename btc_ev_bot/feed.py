# feed.py
import aiohttp, asyncio, json, logging

WS_URL  = "wss://stream.binance.us:9443/ws"
# THIS IS THE CORRECTED SYMBOL
CHANNEL = "btcusdt@aggTrade"
log     = logging.getLogger(__name__)

# The global, shared queue that will act as our message bus.
TICK_BUS = asyncio.Queue(maxsize=4096)

async def _dial_and_listen(session):
    """The internal function that connects and listens for messages."""
    log.info(f"Attempting to connect to {WS_URL}...")
    async with session.ws_connect(WS_URL, heartbeat=30) as ws:
        await ws.send_json({"method":"SUBSCRIBE", "params":[CHANNEL], "id":1})
        log.info(f"✅ Subscribed to {CHANNEL}, now listening for messages.")

        # The first message is a confirmation, which we can ignore.
        await ws.receive()

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Put received trade data onto the shared message bus
                await TICK_BUS.put(json.loads(msg.data))
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                raise ConnectionError("WebSocket connection was closed or errored.")

async def run_feed_manager():
    """The main background task. This should be started only ONCE."""
    log.info("Feed Manager: Starting the single, persistent connection...")
    while True:
        try:
            # trust_env=True is safe for paid accounts (it does nothing)
            async with aiohttp.ClientSession(trust_env=True) as session:
                await _dial_and_listen(session)
        except aiohttp.WSServerHandshakeError as e:
            log.warning("Feed Manager: Handshake blocked by server. Backing off for 60s. Status: %s", e.status)
            await asyncio.sleep(60)
        except Exception:
            log.exception("Feed Manager: Connection crashed. Reconnecting in 5s.")
            await asyncio.sleep(5)

async def ticks():
    """The public generator that all other functions will use to get data."""
    while True:
        # Consumers will wait here until a new message is in the queue
        tick_data = await TICK_BUS.get()
        if tick_data.get("e") == "aggTrade":
            yield tick_data