"""
WhatsApp Number Handler - TemporaSMS API Integration (PRODUCTION)
Optimized for multiple concurrent users with caching and smart rate limiting
"""

import logging
import requests
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from database import get_db, User
from bson.objectid import ObjectId
import threading

logger = logging.getLogger(__name__)

# TemporaSMS API Configuration
TEMPORASMS_API_KEY = "36e990c4eed69c2d943bdf51f9743d64c236"
TEMPORASMS_BASE_URL = "https://api.temporasms.com/stubs/handler_api.php"

# WhatsApp service code
# IMPORTANT: Different operators use DIFFERENT service codes!
# Discovered via getServices endpoint
WHATSAPP_SERVICE_CODES = {
    '1': 'tss',   # Operator 1 → service code 'tss' 
    '11': 'tis',  # Operator 11 → service code 'tis'
    # Other operators return ERROR - may need balance or different codes
}
DEFAULT_WHATSAPP_SERVICE = 'tss'  # Fallback

# CRITICAL: Operators use DIFFERENT country IDs for the same country!
# Per TemporaSMS Support confirmation
OPERATOR_COUNTRY_MAP = {
    '1': '10',  # Operator 1 uses country ID 10 for Vietnam
    # Other operators may use different IDs - fetch dynamically
}

def get_country_id_for_operator(operator_id: str, default_country_id: str = '1') -> str:
    """Get the correct country ID for a specific operator"""
    return OPERATOR_COUNTRY_MAP.get(str(operator_id), default_country_id)

# Timeout settings
OTP_WAIT_TIMEOUT = 300  # 5 minutes in seconds
ORDER_CANCEL_TIMEOUT = 300  # Cancel and refund after 5 minutes
TOTAL_ORDER_TIMEOUT = 1200  # Total 20 minutes for the order

# ============================================
# PRODUCTION-READY RATE LIMITING
# ============================================
# Different delays for different operations
RATE_LIMITS = {
    'getBalance': 0.5,      # Balance checks are fast, can be more frequent
    'getNumber': 2.0,       # Purchasing numbers needs more delay
    'getStatus': 0.3,       # Status checks are frequent, need to be fast
    'setStatus': 1.0,       # Cancel/finish operations
    'getCountries': 5.0,    # Rarely called, can have long delay
    'getOperators': 5.0,    # Rarely called
}

# Track last call time per action type
API_LAST_CALL_TIMES = {}
API_LOCK = threading.Lock()

# ============================================
# CACHING FOR BALANCE CHECKS
# ============================================
BALANCE_CACHE = {
    'value': None,
    'timestamp': None,
    'ttl': 60  # Cache for 60 seconds
}

def format_phone_number(phone: str) -> str:
    """Ensure phone number has + prefix"""
    if not phone:
        return phone
    phone = str(phone).strip()
    if phone.startswith('+'):
        return phone
    return '+' + phone

def get_cached_balance():
    """Get cached balance if still valid"""
    if BALANCE_CACHE['timestamp']:
        age = time.time() - BALANCE_CACHE['timestamp']
        if age < BALANCE_CACHE['ttl']:
            logger.info(f"💾 Using cached balance: ${BALANCE_CACHE['value']} (age: {age:.1f}s)")
            return BALANCE_CACHE['value']
    return None

def cache_balance(balance: float):
    """Cache balance value"""
    BALANCE_CACHE['value'] = balance
    BALANCE_CACHE['timestamp'] = time.time()
    logger.info(f"💾 Cached balance: ${balance}")

def invalidate_balance_cache():
    """Invalidate cached balance after a purchase"""
    BALANCE_CACHE['value'] = None
    BALANCE_CACHE['timestamp'] = None
    logger.info(f"🗑️ Balance cache invalidated")


class TemporaSMSAPI:
    """TemporaSMS API client - PRODUCTION OPTIMIZED"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = TEMPORASMS_BASE_URL
    
    def _parse_response(self, text: str, action: str) -> Dict[str, Any]:
        """Parse TemporaSMS plain text response"""
        text = text.strip()
        
        # ============================================
        # ERROR RESPONSES
        # ============================================
        error_codes = {
            'NO_BALANCE': 'Provider has insufficient balance',
            'NO_NUMBERS': 'No numbers available for this service/country',
            'BAD_KEY': 'Invalid API key',
            'BAD_ACTION': 'Invalid API action',
            'BAD_SERVICE': 'Invalid service code',
            'BAD_OPERATOR': 'Invalid or unavailable operator',
            'WRONG_SERVICE': 'Service not available for this country',
            'NO_ACTIVATION': 'Order not found or already completed',
            'ERROR_SQL': 'Internal server error',
            'BANNED': 'Account is banned',
            'WRONG_ACTIVATION_ID': 'Invalid activation ID',
            'STATUS_CANCEL': 'Activation was cancelled',
            'WRONG_EXCEPTION_PHONE': 'Invalid phone exception',
            'TOO_MANY_REQUESTS': 'Rate limit exceeded',
        }
        
        if text in error_codes:
            return {'status': 'error', 'message': error_codes[text], 'error_code': text}
        
        if text.startswith('ERROR'):
            return {'status': 'error', 'message': text, 'error_code': text}
        
        # ============================================
        # SUCCESS RESPONSES
        # ============================================
        
        if action == 'getBalance':
            if text.startswith('ACCESS_BALANCE:'):
                try:
                    balance = float(text.split(':')[1])
                    cache_balance(balance)  # Cache it
                    return {'status': 'success', 'balance': balance}
                except (IndexError, ValueError):
                    return {'status': 'error', 'message': f'Invalid balance format: {text}'}
            else:
                return {'status': 'error', 'message': f'Unexpected balance response: {text}'}
        
        elif action == 'getCountries':
            if text and text not in error_codes:
                try:
                    import json
                    countries = json.loads(text)
                    return {'status': 'success', 'countries': countries}
                except:
                    return {'status': 'success', 'response': text}
            else:
                return {'status': 'error', 'message': text or 'Empty response'}
        
        elif action == 'getOperators':
            if text and text not in error_codes:
                try:
                    import json
                    operators = json.loads(text)
                    return {'status': 'success', 'operators': operators}
                except:
                    return {'status': 'success', 'response': text}
            else:
                return {'status': 'error', 'message': text or 'Empty response'}
        
        elif action == 'getNumber':
            if text.startswith('ACCESS_NUMBER:'):
                try:
                    parts = text.split(':')
                    if len(parts) >= 3:
                        return {
                            'status': 'success',
                            'id': parts[1],
                            'number': parts[2]
                        }
                    else:
                        return {'status': 'error', 'message': f'Invalid response format: {text}'}
                except Exception as e:
                    return {'status': 'error', 'message': f'Parse error: {text}'}
            else:
                return {'status': 'error', 'message': text, 'error_code': text}
        
        elif action == 'getStatus':
            if text.startswith('STATUS_'):
                parts = text.split(':')
                result = {'status': 'success', 'activation_status': parts[0]}
                if len(parts) > 1 and parts[1]:
                    result['code'] = parts[1]
                return result
            elif ':' in text:
                parts = text.split(':')
                result = {'status': 'success', 'activation_status': parts[0]}
                if len(parts) > 1 and parts[1]:
                    result['code'] = parts[1]
                return result
            elif text in error_codes:
                return {'status': 'error', 'message': error_codes[text], 'error_code': text}
            else:
                return {'status': 'success', 'activation_status': text}
        
        elif action == 'setStatus':
            if text.startswith('ACCESS_'):
                return {'status': 'success', 'message': text}
            elif text in error_codes:
                return {'status': 'error', 'message': error_codes[text], 'error_code': text}
            else:
                return {'status': 'error', 'message': text}
        
        logger.warning(f"Unknown response for '{action}': {text}")
        return {'status': 'success', 'response': text}
    
    def _make_request(self, action: str, **params) -> Dict[str, Any]:
        """Make API request with smart rate limiting"""
        with API_LOCK:  # Thread-safe rate limiting
            # Get rate limit for this action
            rate_limit = RATE_LIMITS.get(action, 1.0)
            
            # Check last call time for this action
            if action in API_LAST_CALL_TIMES:
                time_since_last = time.time() - API_LAST_CALL_TIMES[action]
                if time_since_last < rate_limit:
                    wait_time = rate_limit - time_since_last
                    logger.debug(f"⏱️ Rate limit ({action}): waiting {wait_time:.2f}s")
                    time.sleep(wait_time)
        
        try:
            params['api_key'] = self.api_key
            params['action'] = action
            
            logger.info(f"📡 TemporaSMS API Request: {action}")
            logger.debug(f"Parameters: {params}")
            
            # Retry logic for 429
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                response = requests.get(self.base_url, params=params, timeout=30)
                
                # Update last call time
                with API_LOCK:
                    API_LAST_CALL_TIMES[action] = time.time()
                
                logger.info(f"📥 Response [{response.status_code}]: {response.text}")
                
                # Handle 429
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Rate limit (429), retry {attempt + 1}/{max_retries} in {retry_delay}s")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        return {
                            'status': 'error',
                            'message': 'Too many requests. Please try again in a moment.',
                            'error_code': 'TOO_MANY_REQUESTS'
                        }
                
                # Other HTTP errors
                if response.status_code != 200:
                    return {
                        'status': 'error',
                        'message': f'HTTP {response.status_code}',
                        'error_code': f'HTTP_{response.status_code}'
                    }
                
                # Parse response
                result = self._parse_response(response.text, action)
                logger.info(f"✅ Parsed: {result}")
                
                return result
            
        except requests.exceptions.Timeout:
            return {'status': 'error', 'message': 'Request timeout'}
        except requests.exceptions.ConnectionError as e:
            return {'status': 'error', 'message': f'Connection error: {str(e)[:100]}'}
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)[:100]}
    
    def get_balance(self, use_cache: bool = True) -> Dict[str, Any]:
        """Get account balance with optional caching"""
        # Try cache first
        if use_cache:
            cached = get_cached_balance()
            if cached is not None:
                return {'status': 'success', 'balance': cached, 'cached': True}
        
        # Make actual API call
        return self._make_request('getBalance')
    
    def get_countries(self) -> Dict[str, Any]:
        """Get list of available countries"""
        return self._make_request('getCountries')
    
    def get_operators(self, country_id: str) -> Dict[str, Any]:
        """Get list of operators - use any valid service code"""
        # 'tss' works for getOperators even though we discovered different codes per operator
        return self._make_request('getOperators', country=country_id, service=DEFAULT_WHATSAPP_SERVICE)
    
    def get_number_status(self, order_id: str) -> Dict[str, Any]:
        """Get order status"""
        return self._make_request('getStatus', id=order_id)
    
    def get_number(self, country_id: str, operator: str = None) -> Dict[str, Any]:
        """
        Purchase WhatsApp number - ONLY uses Operator 1
        
        Configuration (confirmed by TemporaSMS support):
        - Operator: 1
        - Country: 10 (Vietnam)
        - Service: tss
        """
        # ONLY use Operator 1
        operator_id = '1'
        service_code = 'tss'
        correct_country_id = '10'
        
        logger.info(f"📱 Requesting WhatsApp number from Operator 1")
        logger.info(f"   Config: operator={operator_id}, service={service_code}, country={correct_country_id}")
        
        result = self._make_request(
            'getNumber',
            service=service_code,
            country=correct_country_id,
            operator=operator_id
        )
        
        # Check result
        if result.get('status') == 'success' and 'id' in result:
            logger.info(f"✅ SUCCESS! WhatsApp number obtained")
            return result
        
        # Handle errors
        error_code = result.get('error_code', '')
        error_message = result.get('message', 'Unknown error')
        
        if error_code == 'NO_BALANCE':
            logger.warning(f"💰 NO_BALANCE from provider")
            return {
                'status': 'error',
                'message': 'WhatsApp service temporarily unavailable. Provider balance issue. Try again later.',
                'error_code': 'NO_BALANCE'
            }
        elif error_code == 'NO_NUMBERS':
            logger.warning(f"📵 NO_NUMBERS available")
            return {
                'status': 'error',
                'message': 'No WhatsApp numbers available. Try again in a few minutes.',
                'error_code': 'NO_NUMBERS'
            }
        else:
            logger.error(f"❌ Error: {error_code} - {error_message}")
            return result
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel order (status 8)"""
        return self._make_request('setStatus', id=order_id, status='8')
    
    def finish_order(self, order_id: str) -> Dict[str, Any]:
        """Finish order (status 6)"""
        return self._make_request('setStatus', id=order_id, status='6')


# Initialize API client
temporasms = TemporaSMSAPI(TEMPORASMS_API_KEY)


async def get_whatsapp_countries() -> list:
    """Get available WhatsApp countries"""
    return [
        {
            'id': '1',
            'name': 'Vietnam',
            'code': 'VN',
            'available': True
        }
    ]


async def purchase_whatsapp_number(user_id: int, country_id: str, price: float) -> tuple:
    """
    Purchase WhatsApp number - PRODUCTION OPTIMIZED
    """
    database = get_db()
    
    try:
        # Check user balance
        user = User.get_by_telegram_id(user_id)
        if not user:
            return None, "❌ User not found"
        
        if user['balance'] < price:
            return None, f"❌ Insufficient balance! Need ${price:.2f}, you have ${user['balance']:.2f}"
        
        # Check provider balance (use cache to reduce API calls)
        balance_result = temporasms.get_balance(use_cache=False)
        if balance_result.get('status') == 'error':
            logger.error(f"❌ Balance check failed: {balance_result.get('message')}")
            return None, "⚠️ Service temporarily unavailable. Please contact support."
        
        api_balance = float(balance_result.get('balance', 0))
        cached = balance_result.get('cached', False)
        logger.info(f"💰 Provider Balance: ${api_balance} {'(cached)' if cached else ''}")
        
        if api_balance < 0.5:
            return None, "⚠️ Service temporarily unavailable. Admin is resolving the issue. Please contact @Akash_support_bot"
        
        # Purchase number (smart operator handling built-in)
        result = temporasms.get_number(country_id)
        
        if result.get('status') == 'error' or 'id' not in result or 'number' not in result:
            error_msg = result.get('message', 'Unknown error')
            error_code = result.get('error_code', '')
            
            # User-friendly error messages
            if 'NO_BALANCE' in error_code or 'balance' in error_msg.lower():
                return None, "⚠️ Service temporarily unavailable. Admin is resolving the issue. Please contact @Akash_support_bot"
            elif 'NO_NUMBERS' in error_code:
                return None, "❌ No numbers available right now. Please try again in a few minutes."
            elif 'NO_OPERATORS' in error_code or 'BAD_OPERATOR' in error_code:
                return None, "❌ WhatsApp service temporarily unavailable for this country. Please try again later."
            elif 'TOO_MANY_REQUESTS' in error_code:
                return None, "⚠️ Too many requests. Please wait 30 seconds and try again."
            else:
                return None, f"❌ Failed to get number: {error_msg}"
        
        order_id = result['id']
        raw_phone = result['number']
        phone_number = format_phone_number(raw_phone)  # ✅ Add this
        logger.info(f"📱 Formatted: '{raw_phone}' -> '{phone_number}'")
        
        # ✅ CRITICAL: Invalidate balance cache after purchase
        # This ensures next user sees updated balance, not cached old balance
        invalidate_balance_cache()
        logger.info(f"🗑️ Cache invalidated - balance will be re-checked for next user")
        
        # Deduct balance
        User.update_balance(user_id, price, operation='subtract')
        
        # Create order
        order_data = {
            'user_id': user_id,
            'order_id': order_id,
            'phone_number': phone_number,
            'country_id': country_id,
            'country_name': 'Vietnam',
            'service': 'whatsapp',
            'price': price,
            'status': 'waiting',
            'otp_code': None,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(seconds=ORDER_CANCEL_TIMEOUT),
            'refunded': False
        }
        
        database.whatsapp_orders.insert_one(order_data)
        logger.info(f"✅ WhatsApp number purchased: {phone_number} for user {user_id}")
        
        return order_data, None
        
    except Exception as e:
        logger.error(f"❌ Purchase error: {e}")
        import traceback
        traceback.print_exc()
        return None, f"❌ Error: {str(e)}"


async def cancel_and_refund_order(order_id: str, reason: str = "timeout") -> bool:
    """Cancel order and refund"""
    database = get_db()
    
    try:
        order = database.whatsapp_orders.find_one({'order_id': order_id})
        
        if not order:
            logger.error(f"❌ Order not found: {order_id}")
            return False
        
        if order.get('refunded', False):
            logger.warning(f"⚠️ Already refunded: {order_id}")
            return False
        
        user_id = order['user_id']
        price = order['price']
        
        # Cancel on API
        try:
            result = temporasms.cancel_order(order_id)
            logger.info(f"📡 Cancel result: {result}")
        except Exception as e:
            logger.warning(f"⚠️ Could not cancel on API: {e}")
        
        # Refund user
        success = User.update_balance(user_id, price, operation='add')
        
        if not success:
            logger.error(f"❌ Failed to refund user {user_id}")
            return False
        
        # ✅ Invalidate cache after refund
        invalidate_balance_cache()
        logger.info(f"🗑️ Cache invalidated after refund")
        
        # Update database
        database.whatsapp_orders.update_one(
            {'order_id': order_id},
            {
                '$set': {
                    'status': 'cancelled',
                    'refunded': True,
                    'refund_reason': reason,
                    'refunded_at': datetime.utcnow()
                }
            }
        )
        
        logger.info(f"✅ Refunded order {order_id}: ${price} to user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Refund error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def monitor_whatsapp_order(bot, user_id: int, order_id: str, message_id: int):
    """Monitor order for OTP"""
    database = get_db()
    start_time = datetime.utcnow()
    check_interval = 10
    
    try:
        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            
            # Timeout check
            if elapsed >= ORDER_CANCEL_TIMEOUT:
                logger.warning(f"⏰ Order {order_id} timed out")
                
                success = await cancel_and_refund_order(order_id, reason="timeout")
                
                order = database.whatsapp_orders.find_one({'order_id': order_id})
                
                if success:

                    phone = format_phone_number(order['phone_number'])
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=message_id,
                        text=(
                            "⏰ **Order Timeout**\n\n"
                            f"📱 Number: `{order['phone_number']}`\n\n"
                            "❌ No OTP received in 5 minutes\n"
                            f"💰 Refunded: ${order['price']}\n\n"
                            "💡 **Retry once if you didn't get it the first time**\n\n"
                            "Please try again or contact support."
                        ),
                        parse_mode='Markdown'
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=message_id,
                        text=(
                            "⚠️ **Service Error**\n\n"
                            "Could not process refund automatically.\n"
                            "Please contact @Akash_support_bot for manual refund."
                        ),
                        parse_mode='Markdown'
                    )
                
                break
            
            # Check status
            result = temporasms.get_number_status(order_id)
            
            # Check for OTP
            if result.get('code'):
                otp_code = result['code']
                
                database.whatsapp_orders.update_one(
                    {'order_id': order_id},
                    {
                        '$set': {
                            'status': 'completed',
                            'otp_code': otp_code,
                            'completed_at': datetime.utcnow()
                        }
                    }
                )
                
                order = database.whatsapp_orders.find_one({'order_id': order_id})
                phone = format_phone_number(order['phone_number'])

                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=(
                        "✅ **WhatsApp OTP Received!**\n\n"
                        f"📱 Number: `{order['phone_number']}`\n"
                        f"🔑 OTP Code: `{otp_code}`\n\n"
                        f"🌍 Country: {order['country_name']}\n\n"
                        "Use this OTP to verify your WhatsApp account!"
                    ),
                    parse_mode='Markdown'
                )
                
                temporasms.finish_order(order_id)
                
                logger.info(f"✅ OTP received for {order_id}: {otp_code}")
                break
            
            # Update status message every 30s
            if int(elapsed) % 30 == 0:
                time_left = ORDER_CANCEL_TIMEOUT - int(elapsed)
                minutes = time_left // 60
                seconds = time_left % 60
                
                order = database.whatsapp_orders.find_one({'order_id': order_id})
                phone = format_phone_number(order['phone_number'])
                
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=(
                        "⏳ **Waiting for WhatsApp OTP**\n\n"
                        f"📱 Number: `{order['phone_number']}`\n"
                        f"🌍 Country: {order['country_name']}\n\n"
                        f"⏰ Time left: {minutes}m {seconds}s\n\n"
                        "💡 OTP will arrive soon...\n"
                        "💰 Auto-refund if no OTP in 5 minutes"
                        "💡 **Retry once if you didn't get it the first time**"
                    ),
                    parse_mode='Markdown'
                )
            
            await asyncio.sleep(check_interval)
            
    except Exception as e:
        logger.error(f"❌ Monitor error: {e}")
        import traceback
        traceback.print_exc()


async def get_user_whatsapp_purchases(user_id: int, limit: int = 20) -> list:
    """Get user purchase history"""
    database = get_db()
    
    purchases = list(database.whatsapp_orders.find({
        'user_id': user_id,
        'status': 'completed'
    }).sort('created_at', -1).limit(limit))
    
    return purchases

async def admin_confirm_refund(order_id: str, db_order_id: ObjectId) -> tuple:
    """Admin manual refund"""
    database = get_db()
    
    try:
        order = database.whatsapp_orders.find_one({'_id': db_order_id})
        
        if not order:
            return False, "Order not found"
        
        if order.get('refunded', False):
            return False, "Already refunded"
        
        user_id = order['user_id']
        price = order['price']
        
        try:
            temporasms.cancel_order(order_id)
        except Exception as e:
            logger.warning(f"⚠️ Could not cancel on API: {e}")
        
        success = User.update_balance(user_id, price, operation='add')
        
        if not success:
            return False, "Failed to refund balance"
        
        # ✅ Invalidate cache after admin refund
        invalidate_balance_cache()
        
        database.whatsapp_orders.update_one(
            {'_id': db_order_id},
            {
                '$set': {
                    'status': 'refunded',
                    'refunded': True,
                    'refunded_at': datetime.utcnow(),
                    'refunded_by': 'admin'
                }
            }
        )
        
        logger.info(f"✅ Admin refunded {order_id}: ${price} to user {user_id}")
        return True, f"Refunded ${price} to user {user_id}"
        
    except Exception as e:
        logger.error(f"❌ Admin refund error: {e}")
        return False, f"Error: {str(e)}"


def get_all_whatsapp_settings() -> list:
    """Get WhatsApp settings"""
    database = get_db()
    
    try:
        settings = list(database.whatsapp_settings.find())
        
        if not settings:
            defaults = [
                {
                    'country_id': '1',
                    'country_name': 'Vietnam',
                    'price': 0.50,
                    'available': True,
                    'updated_at': datetime.utcnow()
                }
            ]
            
            database.whatsapp_settings.insert_many(defaults)
            settings = defaults
        
        return settings
        
    except Exception as e:
        logger.error(f"❌ Error loading settings: {e}")
        return []


def update_whatsapp_price(country_id: str, new_price: float) -> bool:
    """Update WhatsApp price"""
    database = get_db()
    
    try:
        if new_price <= 0:
            return False
        
        result = database.whatsapp_settings.update_one(
            {'country_id': country_id},
            {
                '$set': {
                    'price': new_price,
                    'updated_at': datetime.utcnow()
                }
            },
            upsert=True
        )
        
        return result.modified_count > 0 or result.upserted_id is not None
        
    except Exception as e:
        logger.error(f"❌ Price update error: {e}")
        return False

WHATSAPP_PRICES = {
    '1': 0.50
}

def get_whatsapp_price(country_id: str) -> float:
    """Get WhatsApp price"""
    database = get_db()
    
    try:
        price_doc = database.whatsapp_settings.find_one({'country_id': country_id})
        
        if price_doc:
            return price_doc['price']
        
        defaults = {
            '1': 0.50
        }
        
        default_price = defaults.get(country_id, 1.0)
        
        database.whatsapp_settings.insert_one({
            'country_id': country_id,
            'country_name': 'Vietnam' if country_id == '1' else f'Country {country_id}',
            'price': default_price,
            'updated_at': datetime.utcnow()
        })
        
        return default_price
        
    except Exception as e:
        logger.error(f"Error getting price: {e}")
        return 0.50