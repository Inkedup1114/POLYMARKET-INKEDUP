Complete Polymarket Technical Documentation: Scanner & Trader Development Guide
This comprehensive guide provides all the technical information needed to build a market scanner and automated trader for Polymarket. We'll start with the foundational concepts and build up to advanced implementation details.
Table of Contents

System Architecture Overview
Authentication System
API Endpoints and Structure
Order Management and Trading
Market Data and Scanning
Real-time Data (WebSocket)
Rate Limits and Performance
SDKs and Client Libraries
Fee Structure
Error Handling and Status Codes
Security and Compliance
Implementation Examples

System Architecture Overview
Polymarket uses a hybrid-decentralized architecture called CLOB (Central Limit Order Book), which combines the speed of centralized order matching with the security of decentralized settlement.
Core Components
Off-chain Components:

Order matching and management
Market data aggregation
WebSocket real-time feeds
API services

On-chain Components:

Order settlement via smart contracts
Fund custody (non-custodial)
Token transfers (USDC and outcome tokens)
Order cancellation backup

Network Details

Blockchain: Polygon (Chain ID: 137)
Collateral: USDC
Token Standard: ERC1155 (Conditional Tokens Framework)
Exchange Contract: Audited by Chainsecurity

Authentication System
Polymarket implements a two-level authentication system that balances security with usability for automated systems.
L1 Authentication (Private Key)
Used for the most sensitive operations that require cryptographic proof of ownership.
Required For:

Placing orders (signing order messages)
Creating/revoking API keys
Account management operations

Headers Required:
POLY_ADDRESS: Your Polygon wallet address
POLY_SIGNATURE: EIP-712 signature
POLY_TIMESTAMP: Current UNIX timestamp
POLY_NONCE: Nonce value (default: 0)
EIP-712 Signature Structure:
javascriptdomain = {
  "name": "ClobAuthDomain",
  "version": "1", 
  "chainId": 137  // Polygon Chain ID
}

types = {
  "ClobAuth": [
    {"name": "address", "type": "address"},
    {"name": "timestamp", "type": "string"},
    {"name": "nonce", "type": "uint256"},
    {"name": "message", "type": "string"}
  ]
}

value = {
  "address": signingAddress,
  "timestamp": ts,
  "nonce": nonce,
  "message": "This message attests that I control the given wallet"
}
L2 Authentication (API Key)
Used for routine API operations after initial setup.
Headers Required:
POLY_ADDRESS: Your Polygon wallet address
POLY_SIGNATURE: HMAC signature for the request
POLY_TIMESTAMP: Current UNIX timestamp  
POLY_API_KEY: Your API key UUID
POLY_PASSPHRASE: Your API key passphrase
API Key Components:

Key: UUID identifying the credentials
Secret: Used to generate HMAC signatures (never sent)
Passphrase: Sent with requests for encryption/decryption

Authentication Endpoints
Create API Key:
POST /auth/api-key
Content-Type: application/json
Headers: L1 Authentication

Response:
{
  "apiKey": "xxxxxxxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxx",
  "secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=", 
  "passphrase": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
Derive Existing API Key:
GET /auth/derive-api-key
Headers: L1 Authentication
Get All API Keys:
GET /auth/api-keys
Headers: L1 Authentication
Delete API Key:
DELETE /auth/api-key
Headers: L2 Authentication
API Endpoints and Structure
Polymarket provides three main API services, each serving different purposes for your scanner and trader.
Primary Endpoints
CLOB API (Trading & Orders):
https://clob.polymarket.com/

Order placement and management
Trade execution and history
Account information
Order book data

Gamma Markets API (Market Discovery):
https://gamma-api.polymarket.com/

Market metadata and discovery
Enhanced filtering capabilities
Market categorization
Volume and liquidity data

Data API (User Data):
https://data-api.polymarket.com/

User positions and holdings
On-chain activity history
Portfolio analytics

WebSocket API (Real-time Data):
wss://ws-subscriptions-clob.polymarket.com/ws/

Real-time order book updates
Trade notifications
User-specific event streams

Order Management and Trading
Understanding order types and lifecycle is crucial for building an effective trader.
Order Types
GTC (Good-Till-Cancelled):

Remains active until filled or manually cancelled
Perfect for limit order strategies
Most common order type for automated trading

GTD (Good-Till-Date):

Active until specified expiration timestamp
Useful for time-bound strategies
Minimum 1-minute security threshold

FOK (Fill-Or-Kill):

Executes immediately and completely or cancels
Ideal for market orders and arbitrage
No partial fills allowed

FAK (Fill-And-Kill) - New:

Executes immediately for available quantity
Remaining unfilled portion is cancelled
Allows partial fills unlike FOK

Order Structure
Every order requires these core parameters:
pythonOrderArgs(
    price=0.50,        # Price in USDC (0.01 to 0.99)
    size=100.0,        # Quantity of shares
    side=BUY,          # BUY or SELL
    token_id="token_id" # Market token identifier
)
Order Placement Process
Single Order:
python# Create and sign order
order_args = OrderArgs(price=0.50, size=100.0, side=BUY, token_id="token_id")
signed_order = client.create_order(order_args)

# Post order
response = client.post_order(signed_order, OrderType.GTC)
Batch Orders (up to 5):
pythonorders = [
    PostOrdersArgs(order=client.create_order(order_args_1), type=OrderType.GTC),
    PostOrdersArgs(order=client.create_order(order_args_2), type=OrderType.GTC)
]
response = client.post_orders(orders)
Order Status Tracking
Orders progress through various states:
Placement Status:

PLACED - Successfully placed in order book
DELAYED - Experiencing processing delay
FAILED - Order placement failed

Execution Status:

MATCHED - Order matched with counterparty
MINED - Transaction submitted to blockchain
CONFIRMED - Transaction confirmed on-chain
RETRYING - Retrying after failure
FAILED - Final failure state

Order Management Operations
Get Single Order:
GET /order/{order_id}
Headers: L2 Authentication
Get Active Orders:
GET /orders
Headers: L2 Authentication
Query params: market, next_cursor
Cancel Orders:
DELETE /order  # Cancel single order
DELETE /orders # Cancel multiple orders
Headers: L2 Authentication
Market Data and Scanning
Building an effective scanner requires understanding both market discovery and data retrieval patterns.
Market Discovery (Gamma API)
Get All Markets:
GET /markets
Query Parameters:
- limit: Results per page (default: 20, max: 100)
- offset: Pagination offset
- active: Filter by active status
- closed: Include closed markets
- tag: Filter by category tags
- order: Sort order (volume, liquidity, newest)
Market Response Structure:
json{
  "slug": "market-slug",
  "condition_id": "condition_identifier", 
  "question_id": "question_identifier",
  "tokens": [
    {
      "token_id": "token_identifier",
      "outcome": "Yes", 
      "price": "0.52",
      "winner": false
    }
  ],
  "volume": "1234567.89",
  "liquidity": "98765.43",
  "end_date_iso": "2024-12-31T23:59:59Z",
  "description": "Market description",
  "tags": ["Politics", "Election"]
}
CLOB Market Data
Get Markets (CLOB):
GET /markets
Query Parameters:
- next_cursor: Pagination cursor
- active: Filter active markets only
Get Simplified Markets:
GET /simplified-markets
Returns streamlined market data optimized for scanning
Price and Order Book Data
Get Current Price:
GET /price?token_id={token_id}&side={BUY|SELL}

Response:
{
  "price": "0.52",
  "size": "100.0"
}
Get Order Book:
GET /book?token_id={token_id}

Response:
{
  "bids": [["0.51", "100"], ["0.50", "200"]],
  "asks": [["0.53", "150"], ["0.54", "300"]]
}
Get Multiple Prices:
GET /prices
Body: ["token_id_1", "token_id_2", ...]
Get Midpoint Prices:
GET /midpoint?token_id={token_id}
Get Spread Data:
GET /spread?token_id={token_id}
Historical Data
Price History:
GET /prices-history?market={market}&interval={interval}&fidelity={fidelity}

Parameters:
- interval: 1m, 5m, 1h, 6h, 1d, 1w, max
- fidelity: Data point density
- market: Market identifier
Trade History:
GET /trades?market={market}&limit={limit}&cursor={cursor}
Headers: L2 Authentication (for detailed data)
Real-time Data (WebSocket)
WebSocket connections provide sub-second latency for critical trading data.
Connection Setup
Base URL:
wss://ws-subscriptions-clob.polymarket.com/ws/
Channel Types:

market - Public market data (no auth required)
user - Private user data (requires authentication)

Market Channel (Public)
Subscribe to order book updates and market data:
javascriptconst ws = new WebSocket('wss://ws-subscriptions-clob.polymarket.com/ws/market');

// Subscribe to specific tokens
ws.send(JSON.stringify({
  "type": "market",
  "assets_ids": ["token_id_1", "token_id_2"],
  "initial_book_state": true  // Optional: get initial order book
}));
Market Data Messages:

Order book snapshots and updates
Price changes
Trade executions
Market status changes

User Channel (Authenticated)
Subscribe to personal trading updates:
javascriptconst ws = new WebSocket('wss://ws-subscriptions-clob.polymarket.com/ws/user');

// Authentication message
ws.send(JSON.stringify({
  "type": "user",
  "markets": ["market_id_1", "market_id_2"],
  "auth": {
    "api_key": "your_api_key",
    "signature": "hmac_signature",
    "timestamp": "current_timestamp",
    "passphrase": "your_passphrase"
  }
}));
User Data Messages:

Order status updates
Trade confirmations
Balance changes
Position updates

WebSocket Client Example
pythonfrom websocket import WebSocketApp
import json

class PolymarketWebSocket:
    def __init__(self, channel_type, token_ids, auth=None):
        self.channel_type = channel_type
        self.token_ids = token_ids
        self.auth = auth
        
        url = f"wss://ws-subscriptions-clob.polymarket.com/ws/{channel_type}"
        self.ws = WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
    
    def on_open(self, ws):
        if self.channel_type == "market":
            ws.send(json.dumps({
                "type": "market",
                "assets_ids": self.token_ids,
                "initial_book_state": True
            }))
        elif self.channel_type == "user" and self.auth:
            ws.send(json.dumps({
                "type": "user", 
                "markets": self.token_ids,
                "auth": self.auth
            }))
    
    def on_message(self, ws, message):
        data = json.loads(message)
        # Process market updates for your scanner/trader
        self.handle_update(data)
    
    def handle_update(self, data):
        # Implement your update handling logic
        pass
Rate Limits and Performance
Understanding rate limits is crucial for building robust automated systems.
Rate Limit Structure
Order Operations (Most Important for Trading):

Burst Limit: 500 requests per 10 seconds
Sustained Limit: 3000 requests per 10 minutes
Behavior: Throttling (delays) rather than rejection

Market Data Operations:

General Book Requests: 50 per 10 seconds
Price Endpoints: 100 per 10 seconds
Market Discovery: 100 per 10 seconds

User Data Operations:

Account Information: 50 per 10 seconds
Trade History: 100 per 10 seconds

Rate Limit Best Practices
For Scanners:

Cache market data locally and update periodically
Use WebSocket for real-time updates instead of polling
Batch multiple token price requests
Implement exponential backoff for failed requests

For Traders:

Queue orders and implement intelligent batching
Monitor rate limit headers in responses
Use WebSocket for order status updates
Implement circuit breakers for rate limit protection

SDKs and Client Libraries
Polymarket provides official SDKs that handle authentication, rate limiting, and error handling.
Python SDK (py-clob-client)
Installation:
bashpip install py-clob-client
Basic Setup:
pythonfrom py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

# Initialize client
host = "https://clob.polymarket.com"
chain_id = 137
private_key = "your_private_key"

# Different initialization options based on wallet type:

# 1. Email/Magic Link account
client = ClobClient(
    host, 
    key=private_key, 
    chain_id=chain_id, 
    signature_type=1, 
    funder=POLYMARKET_PROXY_ADDRESS
)

# 2. Browser wallet (MetaMask, Coinbase)  
client = ClobClient(
    host,
    key=private_key,
    chain_id=chain_id,
    signature_type=2, 
    funder=POLYMARKET_PROXY_ADDRESS
)

# 3. Direct EOA trading
client = ClobClient(host, key=private_key, chain_id=chain_id)
Key Client Methods:
python# Authentication
client.set_api_creds(client.create_or_derive_api_creds())

# Market data
markets = client.get_markets()
prices = client.get_prices(["token_id_1", "token_id_2"])
book = client.get_book("token_id")

# Trading
order = client.create_order(OrderArgs(...))
response = client.post_order(order, OrderType.GTC)
orders = client.get_orders()
client.cancel_order("order_id")

# Account data
balances = client.get_balances()
trades = client.get_trades()
TypeScript/JavaScript SDK
Installation:
bashnpm install @polymarket/clob-client
Basic Usage:
typescriptimport { ClobClient } from '@polymarket/clob-client';

const client = new ClobClient(
  'https://clob.polymarket.com',
  chainId,
  privateKey,
  signatureType
);
Go SDK
Available for high-performance applications requiring maximum speed and efficiency.
Fee Structure
Current Fee Schedule:

Maker Fees: 0 basis points (0%)
Taker Fees: 0 basis points (0%)
Network Fees: ~$0.08 MATIC for deposits on Polygon

Fee Calculation (When Applied):
Fees are calculated symmetrically in output assets to maintain market integrity:
Selling outcome tokens for collateral:
feeQuote = baseRate × min(price, 1-price) × size
Buying outcome tokens with collateral:
feeBase = baseRate × min(price, 1-price) × (size/price)
Error Handling and Status Codes
Common Order Errors
Validation Errors:

INVALID_ORDER_MIN_TICK_SIZE - Price doesn't meet minimum tick size
INVALID_ORDER_MIN_SIZE - Order size below minimum
INVALID_ORDER_NOT_ENOUGH_BALANCE - Insufficient funds

System Errors:

INSERT_ORDER_ERROR - Database insertion failed
EXECUTION_ERROR - Order execution failed
ORDER_DELAYED - Processing delay
FOK_ORDER_NOT_FILLED_ERROR - FOK order couldn't be filled completely

Error Response Format
json{
  "success": false,
  "errorMsg": "INVALID_ORDER_NOT_ENOUGH_BALANCE",
  "status": "FAILED"
}
Retry Logic
Implement exponential backoff for transient errors:
pythonimport time
import random

def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait_time)
Security and Compliance
Geographic Restrictions
Important: US persons are completely prohibited from using Polymarket, including:

Platform access
API usage
Automated trading
VPN circumvention

Compliance Monitoring
The platform actively monitors for compliance:
GET /auth/ban-status/cert-required
Users may be required to provide residence verification within 14 days if flagged.
Security Best Practices
Private Key Management:

Never hardcode private keys
Use environment variables or secure key management
Implement key rotation where possible
Use hardware wallets for production systems

API Security:

Implement request signing verification
Use HTTPS for all communications
Validate all incoming data
Implement proper session management

Implementation Examples
Basic Market Scanner
pythonimport time
from py_clob_client.client import ClobClient

class PolymarketScanner:
    def __init__(self):
        self.client = ClobClient("https://clob.polymarket.com")
        
    def scan_markets(self):
        """Scan all active markets for opportunities"""
        markets = self.client.get_simplified_markets()
        
        opportunities = []
        for market in markets:
            if self.is_opportunity(market):
                opportunities.append(market)
                
        return opportunities
    
    def is_opportunity(self, market):
        """Define your opportunity detection logic"""
        # Example: Look for markets with high volume and tight spreads
        if market.get('volume', 0) > 10000:
            for token in market.get('tokens', []):
                book = self.client.get_book(token['token_id'])
                spread = self.calculate_spread(book)
                if spread < 0.02:  # 2% spread
                    return True
        return False
    
    def calculate_spread(self, book):
        """Calculate bid-ask spread"""
        if book['bids'] and book['asks']:
            best_bid = float(book['bids'][0][0])
            best_ask = float(book['asks'][0][0])
            return best_ask - best_bid
        return float('inf')
Automated Trader Example
pythonclass PolymarketTrader:
    def __init__(self, private_key):
        self.client = ClobClient(
            "https://clob.polymarket.com",
            key=private_key,
            chain_id=137
        )
        self.client.set_api_creds(self.client.create_or_derive_api_creds())
        
    def place_arbitrage_order(self, token_id, target_price, size):
        """Place an arbitrage order"""
        try:
            # Check current best price
            book = self.client.get_book(token_id)
            
            if self.should_place_order(book, target_price):
                order_args = OrderArgs(
                    price=target_price,
                    size=size,
                    side=BUY,
                    token_id=token_id
                )
                
                signed_order = self.client.create_order(order_args)
                response = self.client.post_order(signed_order, OrderType.GTC)
                
                return response
                
        except Exception as e:
            print(f"Order placement failed: {e}")
            return None
    
    def should_place_order(self, book, target_price):
        """Determine if order should be placed based on current book"""
        if book['asks']:
            best_ask = float(book['asks'][0][0])
            return target_price < best_ask
        return False
        
    def monitor_positions(self):
        """Monitor active positions and orders"""
        orders = self.client.get_orders()
        for order in orders:
            # Implement position monitoring logic
            self.evaluate_order(order)
WebSocket Real-time Scanner
pythonimport json
from websocket import WebSocketApp

class RealtimeScanner:
    def __init__(self, token_ids):
        self.token_ids = token_ids
        self.order_books = {}
        self.opportunities = []
        
    def start_scanning(self):
        """Start real-time market scanning"""
        url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        
        self.ws = WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        self.ws.run_forever()
    
    def on_open(self, ws):
        # Subscribe to market updates
        ws.send(json.dumps({
            "type": "market",
            "assets_ids": self.token_ids,
            "initial_book_state": True
        }))
    
    def on_message(self, ws, message):
        data = json.loads(message)
        
        # Update local order book
        if 'asset_id' in data:
            self.order_books[data['asset_id']] = data
            
            # Check for opportunities
            if self.detect_opportunity(data):
                self.handle_opportunity(data)
    
    def detect_opportunity(self, book_data):
        """Implement your opportunity detection logic"""
        # Example: Detect price movements above threshold
        if 'price_change' in book_data:
            return abs(book_data['price_change']) > 0.05
        return False
    
    def handle_opportunity(self, opportunity):
        """Handle detected opportunity"""
        print(f"Opportunity detected: {opportunity}")
        # Implement your opportunity handling logic
