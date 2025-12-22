"""
Manual Crypto Payment Integration - RELIABLE PRICES ONLY
NO COINGECKO - Uses Binance + CryptoCompare + Manual Override
"""

import logging
import requests
import time
import threading
from datetime import datetime
from database import Transaction, User

logger = logging.getLogger(__name__)

# Price cache with lock
_price_cache = {'prices': None, 'timestamp': 0}
_cache_lock = threading.Lock()
CACHE_DURATION = 180  # 3 minutes - prices locked for this duration

# ============================================
# YOUR CRYPTO WALLET ADDRESSES
# ============================================
CRYPTO_WALLETS = {
    'BTC': 'bc1pd99aer5naxcjkegcwfx9xtwe7kvwc88jasqcqxdqqf4xcjv93pvsgmyztz',
    'ETH': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'ETH_BASE': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'ETH_OPTIMISM': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'ETH_ARBITRUM': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'USDT_ERC20': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'USDT_BASE': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'USDT_OPTIMISM': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'USDT_ARBITRUM': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'USDT_BEP20': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'USDT_TRC20': 'TEkk8goGJ3538LfJkNSS59m16Dz4kXMzNU',
    'BNB': '0x4a998ce0877924feb7af749de60b644e1c39dad4',
    'TRX': 'TEkk8goGJ3538LfJkNSS59m16Dz4kXMzNU',
    'SOL': '96CRTrosdbXipD93zzNQh2jF4VtboyevQmN2SqyjHYVx',
}

NETWORK_NAMES = {
    'ETH': 'Ethereum (Mainnet)',
    'ETH_BASE': 'Ethereum (Base)',
    'ETH_OPTIMISM': 'Ethereum (Optimism)',
    'ETH_ARBITRUM': 'Ethereum (Arbitrum)',
    'USDT_ERC20': 'USDT (Ethereum)',
    'USDT_BASE': 'USDT (Base)',
    'USDT_OPTIMISM': 'USDT (Optimism)',
    'USDT_ARBITRUM': 'USDT (Arbitrum)',
    'USDT_TRC20': 'USDT (Tron)',
    'USDT_BEP20': 'USDT (BSC)',
}

# ============================================
# MANUAL PRICE OVERRIDE (ALWAYS UP TO DATE)
# Check: https://www.binance.com/en/markets/overview
# Update these daily or when you see wrong prices
# ============================================

def get_fallback_prices():
    """
    🎯 MANUAL PRICE OVERRIDE - EDIT WHEN NEEDED
    
    Update these prices daily from:
    https://www.binance.com/en/markets/overview
    
    Last updated: December 18, 2025 - 5:30 PM IST
    """
    return {
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ✏️ EDIT PRICES HERE (Check Binance daily)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        'BTC': 106300.0,    # Bitcoin
        'ETH': 3903.0,      # Ethereum ⬅️ UPDATE THIS
        'BNB': 703.0,       # BNB
        'SOL': 216.0,       # Solana
        'TRX': 0.2456,      # Tron
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Don't edit below (auto-copied from ETH)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        'ETH_BASE': 3903.0,
        'ETH_OPTIMISM': 3903.0,
        'ETH_ARBITRUM': 3903.0,
        'USDT_ERC20': 1.0,
        'USDT_BASE': 1.0,
        'USDT_OPTIMISM': 1.0,
        'USDT_ARBITRUM': 1.0,
        'USDT_TRC20': 1.0,
        'USDT_BEP20': 1.0,
    }

# ============================================
# RELIABLE PRICE FETCHING
# ============================================

def get_live_crypto_prices():
    """
    Fetch from RELIABLE sources only:
    1. Binance (no rate limits, most reliable)
    2. CryptoCompare (reliable backup)
    3. Manual fallback (you control)
    
    NEVER uses CoinGecko!
    """
    global _price_cache
    
    with _cache_lock:  # Prevent race conditions
        current_time = time.time()
        
        # Check cache - prices locked for 3 minutes
        if _price_cache['prices'] and (current_time - _price_cache['timestamp']) < CACHE_DURATION:
            cache_age = int(current_time - _price_cache['timestamp'])
            remaining = CACHE_DURATION - cache_age
            logger.info(f"📦 Using cached prices (locked for {remaining}s more)")
            return _price_cache['prices']
        
        logger.info("🔄 Fetching fresh prices (cache expired)...")
        
        # Try Binance first (MOST RELIABLE, NO RATE LIMITS!)
        prices = fetch_from_binance()
        if prices:
            _price_cache['prices'] = prices
            _price_cache['timestamp'] = current_time
            logger.info("✅ Binance prices - cached for 3 minutes")
            return prices
        
        logger.warning("⚠️ Binance failed, trying CryptoCompare...")
        
        # Try CryptoCompare (reliable backup)
        prices = fetch_from_cryptocompare()
        if prices:
            _price_cache['prices'] = prices
            _price_cache['timestamp'] = current_time
            logger.info("✅ CryptoCompare prices - cached for 3 minutes")
            return prices
        
        # Use expired cache if we have it
        if _price_cache['prices']:
            logger.warning("⚠️ All APIs failed, using expired cache")
            return _price_cache['prices']
        
        # Final fallback - your manual prices
        logger.error("❌ All APIs failed! Using manual fallback prices")
        logger.error("⚠️ Please update prices in get_fallback_prices()")
        fallback = get_fallback_prices()
        _price_cache['prices'] = fallback
        _price_cache['timestamp'] = current_time
        return fallback


def fetch_from_binance():
    """Fetch from Binance API (NO RATE LIMITS, SUPER RELIABLE)"""
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            logger.error(f"Binance API error: {response.status_code}")
            return None
        
        data = response.json()
        
        # Build price map
        price_map = {}
        for item in data:
            symbol = item['symbol']
            if symbol in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'TRXUSDT', 'SOLUSDT']:
                price_map[symbol] = float(item['price'])
        
        # Need at least BTC and ETH
        if 'BTCUSDT' not in price_map or 'ETHUSDT' not in price_map:
            logger.error("Binance missing required prices")
            return None
        
        eth_price = price_map['ETHUSDT']
        
        prices = {
            'BTC': price_map['BTCUSDT'],
            'ETH': eth_price,
            'ETH_BASE': eth_price,
            'ETH_OPTIMISM': eth_price,
            'ETH_ARBITRUM': eth_price,
            'USDT_ERC20': 1.0,
            'USDT_BASE': 1.0,
            'USDT_OPTIMISM': 1.0,
            'USDT_ARBITRUM': 1.0,
            'USDT_TRC20': 1.0,
            'USDT_BEP20': 1.0,
            'BNB': price_map.get('BNBUSDT', 703.0),
            'TRX': price_map.get('TRXUSDT', 0.2456),
            'SOL': price_map.get('SOLUSDT', 216.0),
        }
        
        logger.info(f"📊 Binance: BTC=${prices['BTC']:.0f} ETH=${prices['ETH']:.2f}")
        return prices
        
    except requests.exceptions.Timeout:
        logger.error("Binance API timeout")
        return None
    except Exception as e:
        logger.error(f"Binance error: {e}")
        return None


def fetch_from_cryptocompare():
    """Fetch from CryptoCompare (RELIABLE BACKUP)"""
    try:
        url = "https://min-api.cryptocompare.com/data/pricemulti"
        params = {
            'fsyms': 'BTC,ETH,BNB,TRX,SOL',
            'tsyms': 'USD'
        }
        
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code != 200:
            logger.error(f"CryptoCompare error: {response.status_code}")
            return None
        
        data = response.json()
        
        # Validate we have required data
        if 'BTC' not in data or 'ETH' not in data:
            logger.error("CryptoCompare missing required prices")
            return None
        
        if 'USD' not in data['BTC'] or 'USD' not in data['ETH']:
            logger.error("CryptoCompare invalid format")
            return None
        
        eth_price = data['ETH']['USD']
        
        prices = {
            'BTC': data['BTC']['USD'],
            'ETH': eth_price,
            'ETH_BASE': eth_price,
            'ETH_OPTIMISM': eth_price,
            'ETH_ARBITRUM': eth_price,
            'USDT_ERC20': 1.0,
            'USDT_BASE': 1.0,
            'USDT_OPTIMISM': 1.0,
            'USDT_ARBITRUM': 1.0,
            'USDT_TRC20': 1.0,
            'USDT_BEP20': 1.0,
            'BNB': data.get('BNB', {}).get('USD', 703.0),
            'TRX': data.get('TRX', {}).get('USD', 0.2456),
            'SOL': data.get('SOL', {}).get('USD', 216.0),
        }
        
        logger.info(f"📊 CryptoCompare: BTC=${prices['BTC']:.0f} ETH=${prices['ETH']:.2f}")
        return prices
        
    except requests.exceptions.Timeout:
        logger.error("CryptoCompare timeout")
        return None
    except Exception as e:
        logger.error(f"CryptoCompare error: {e}")
        return None


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_crypto_amount(usd_amount: float, crypto_type: str) -> float:
    """Convert USD to crypto amount"""
    prices = get_live_crypto_prices()
    rate = prices.get(crypto_type, 1.0)
    
    if rate <= 0:
        logger.error(f"Invalid rate for {crypto_type}: {rate}")
        return 0
    
    crypto_amount = usd_amount / rate
    
    # Round appropriately
    if crypto_type == 'BTC':
        return round(crypto_amount, 8)
    elif crypto_type in ['USDT_ERC20', 'USDT_TRC20', 'USDT_BEP20', 'USDT_BASE', 'USDT_OPTIMISM', 'USDT_ARBITRUM']:
        return round(crypto_amount, 2)
    elif crypto_type == 'TRX':
        return round(crypto_amount, 2)
    else:
        return round(crypto_amount, 6)


def get_crypto_display_name(crypto_type: str) -> str:
    """Get display name"""
    names = {
        'BTC': '₿ Bitcoin',
        'ETH': 'Ξ Ethereum (Mainnet)',
        'ETH_BASE': 'Ξ Ethereum (Base)',
        'ETH_OPTIMISM': 'Ξ Ethereum (Optimism)',
        'ETH_ARBITRUM': 'Ξ Ethereum (Arbitrum)',
        'USDT_ERC20': '💵 USDT (Ethereum)',
        'USDT_BASE': '💵 USDT (Base)',
        'USDT_OPTIMISM': '💵 USDT (Optimism)',
        'USDT_ARBITRUM': '💵 USDT (Arbitrum)',
        'USDT_TRC20': '💵 USDT (Tron)',
        'USDT_BEP20': '💵 USDT (BSC)',
        'BNB': '🔶 BNB',
        'TRX': '⚡ Tron',
        'SOL': '◎ Solana',
    }
    return names.get(crypto_type, crypto_type)


def create_crypto_deposit(user_id: int, amount_usd: float, crypto_type: str):
    """Create manual crypto deposit with enhanced tracking"""
    try:
        wallet_address = CRYPTO_WALLETS.get(crypto_type)
        
        if not wallet_address:
            logger.error(f"No wallet for {crypto_type}")
            return None
        
        crypto_amount = get_crypto_amount(amount_usd, crypto_type)
        
        if crypto_amount <= 0:
            logger.error(f"Invalid crypto amount: {crypto_amount}")
            return None
        
        import time
        payment_id = f"CRYPTO_{user_id}_{int(time.time())}"
        
        # Enhanced payment ID includes crypto type and amount for auto-verification
        enhanced_payment_id = f"{payment_id}|{crypto_type}|{crypto_amount}"
        
        transaction_id = Transaction.create(
            user_id=user_id,
            amount=amount_usd,
            payment_method='crypto_manual',
            payment_id=enhanced_payment_id
        )
        
        logger.info(f"✅ Deposit created: ${amount_usd} = {crypto_amount} {crypto_type}")
        
        return {
            'success': True,
            'transaction_id': str(transaction_id),
            'wallet_address': wallet_address,
            'crypto_type': crypto_type,
            'crypto_amount': crypto_amount,
            'amount_usd': amount_usd,
            'payment_id': payment_id,  # Return clean ID (without enhancement)
            'network_name': NETWORK_NAMES.get(crypto_type, get_crypto_display_name(crypto_type))
        }
        
    except Exception as e:
        logger.error(f"❌ Create deposit error: {e}")
        import traceback
        traceback.print_exc()
        return None


def verify_crypto_payment(transaction_id: str, tx_hash: str) -> bool:
    """Verify and credit crypto payment (manual admin verification)"""
    try:
        from bson.objectid import ObjectId
        
        transaction = Transaction.get_by_id(ObjectId(transaction_id))
        
        if not transaction:
            logger.error(f"Transaction not found: {transaction_id}")
            return False
        
        if transaction['status'] == 'completed':
            logger.info(f"Already completed: {transaction_id}")
            return True
        
        # Credit user
        success = User.update_balance(
            transaction['user_id'],
            transaction['amount'],
            operation='add'
        )
        
        if success:
            # Update transaction
            Transaction.update_status(
                ObjectId(transaction_id),
                'completed',
                charge_id=tx_hash
            )
            
            logger.info(f"✅ Manual verification: ${transaction['amount']} for user {transaction['user_id']}")
            return True
        
        logger.error(f"Failed to credit user: {transaction['user_id']}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Verify error: {e}")
        import traceback
        traceback.print_exc()
        return False