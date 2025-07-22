# Polymarket WebSocket Streaming Client

A production-ready Python script for connecting to Polymarket's WebSocket API with automatic API key derivation and market/user channel subscription.

## Features

- **Automatic API Key Derivation**: Uses `py_clob_client` to automatically derive API keys based on environment configuration
- **Multiple Authentication Paths**: Supports email/magic, browser wallet, or EOA initialization based on `POLYMARKET_PROXY_ADDRESS` and `SIGNATURE_TYPE`
- **Dual Channel Subscription**: Subscribes to both "market" and "user" channels simultaneously
- **Automatic Reconnection**: Implements exponential backoff (capped at 30s) for connection failures
- **Graceful Shutdown**: Handles SIGINT/SIGTERM signals for clean termination
- **Environment Configuration**: Fully configurable via environment variables for container/CI usage
- **Production Ready**: Comprehensive error handling, logging, and type safety

## Installation

```bash
pip install py-clob-client aiohttp python-dotenv backoff
```

## Usage

### Basic Usage
```bash
python polymarket_ws_stream.py
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `wss://ws-subscriptions-clob.polymarket.com/ws` | WebSocket endpoint URL |
| `KEY` | `None` | Pre-derived API key (optional) |
| `CHAIN_ID` | `137` | Blockchain network ID (137=Polygon mainnet, 80001=Mumbai testnet) |
| `POLYMARKET_PROXY_ADDRESS` | `None` | Proxy contract address for browser wallet auth |
| `SIGNATURE_TYPE` | `None` | Signature type: `EOA`, `POLY_GNOSIS_SAFE`, or `POLY_PROXY` |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `PUBLIC_KEY` | Required | Your wallet's public address (hex string) |
| `PRIVATE_KEY` | Required | Your wallet's private key (hex string) |
| `POLYMARKET_API_BASE` | `https://clob.polymarket.com` | Polymarket API base URL |

### Examples

#### Standard EOA Authentication
```bash
export PUBLIC_KEY=0x976d899C1A2e2c7efb0C94df2959e4B35d0D0b51
export PRIVATE_KEY=your_private_key_here
python polymarket_ws_stream.py
```

#### Browser Wallet with Proxy
```bash
export PUBLIC_KEY=0x976d899C1A2e2c7efb0C94df2959e4B35d0D0b51
export PRIVATE_KEY=your_private_key_here
export POLYMARKET_PROXY_ADDRESS=0x1234567890abcdef
export SIGNATURE_TYPE=POLY_PROXY
python polymarket_ws_stream.py
```

#### Custom Host and Testnet
```bash
export HOST=wss://test-ws.polymarket.com/ws
export CHAIN_ID=80001
export PUBLIC_KEY=0x976d899C1A2e2c7efb0C94df2959e4B35d0D0b51
export PRIVATE_KEY=your_private_key_here
python polymarket_ws_stream.py
```

#### Docker/Container Usage
```bash
docker run -e HOST=wss://ws-subscriptions-clob.polymarket.com/ws \
           -e PUBLIC_KEY=0x976d899C1A2e2c7efb0C94df2959e4B35d0D0b51 \
           -e PRIVATE_KEY=your_private_key_here \
           polymarket-ws-stream
```

## Output Format

The script prints each incoming WebSocket message as a single-line JSON string to stdout:

```json
{"type":"book","market":"0x123...","data":{"bids":[...],"asks":[...]}}
{"type":"trade","market":"0x123...","data":{"price":0.65,"size":100}}
{"type":"order_status","order_id":"0xabc...","status":"filled"}
```

## Error Handling

- **Connection Failures**: Automatic reconnection with exponential backoff (max 30s)
- **Authentication Errors**: Clear error messages for invalid credentials
- **Network Issues**: Comprehensive logging and retry logic
- **Graceful Shutdown**: Clean termination on SIGINT/SIGTERM

## Development

### Testing Configuration
```bash
python test_ws_config.py
```

### Type Checking
```bash
mypy polymarket_ws_stream.py
```

## Architecture

The script uses:
- **asyncio** for asynchronous WebSocket handling
- **aiohttp** for WebSocket client implementation
- **backoff** for exponential retry logic
- **py_clob_client** for Polymarket API integration
- **signal** for graceful shutdown handling

## Security Notes

- Never commit private keys to version control
- Use environment variables or secure secret management in production
- Consider using dedicated wallet addresses for API access
- Monitor API key usage and rotate regularly