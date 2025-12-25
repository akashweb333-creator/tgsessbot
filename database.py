"""
MongoDB Database Module - COMPLETE FIXED VERSION
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import config
from bson.objectid import ObjectId

logger = logging.getLogger(__name__)

# MongoDB Client
client = None
db = None

def init_db():
    """Initialize MongoDB connection with pooling"""
    global client, db
    
    try:
        mongodb_url = config.MONGODB_URL
        
        logger.info(f"🔗 Connecting to MongoDB...")
        
        client = MongoClient(
            mongodb_url,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            maxPoolSize=50,  # ✅ ADD THIS
            minPoolSize=10,  # ✅ ADD THIS
            retryWrites=True,  # ✅ ADD THIS
            retryReads=True   # ✅ ADD THIS
        )
        
        # Test connection
        client.admin.command('ping')
        db = client.telegram_bot
        
        logger.info("✅ MongoDB connected successfully")
        create_indexes()
        create_default_settings()
        return True
        
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        raise Exception(f"Cannot connect to MongoDB: {e}")

def create_indexes():
    """Create database indexes"""
    try:
        db.users.create_index([("telegram_id", ASCENDING)], unique=True)
        db.sessions.create_index([("is_sold", ASCENDING)])
        db.sessions.create_index([("country", ASCENDING)])
        db.sessions.create_index([("uploader_id", ASCENDING)])
        db.transactions.create_index([("user_id", ASCENDING)])
        db.transactions.create_index([("status", ASCENDING)])
        db.transactions.create_index([("payment_id", ASCENDING)])
        db.purchases.create_index([("user_id", ASCENDING)])
        db.seller_applications.create_index([("telegram_id", ASCENDING)])
        db.seller_applications.create_index([("status", ASCENDING)])
        db.withdrawals.create_index([("user_id", ASCENDING)])
        db.withdrawals.create_index([("status", ASCENDING)])
        db.pending_uploads.create_index([("uploader_id", ASCENDING)])
        db.pending_uploads.create_index([("status", ASCENDING)])
        
        logger.info("✅ Indexes created")
    except Exception as e:
        logger.warning(f"⚠️ Index creation: {e}")

def create_default_settings():
    """Create default settings"""
    try:
        settings = db.settings.find_one({"_id": "system"})
        if not settings:
            db.settings.insert_one({
                "_id": "system",
                "min_deposit": 1.0,
                "inr_to_usd_rate": 0.012,
                "ton_manual_price": None,
                "updated_at": datetime.utcnow()
            })
            logger.info("✅ Default settings created")
    except Exception as e:
        logger.warning(f"⚠️ Settings: {e}")

def get_db():
    """Get MongoDB database with reconnection logic"""
    global db, client
    
    try:
        if db is None or client is None:
            init_db()
        
        # Test connection
        client.admin.command('ping')
        return db
        
    except Exception as e:
        logger.warning(f"DB connection lost, reconnecting: {e}")
        # Force reconnection
        client = None
        db = None
        init_db()
        return db

# ============================================
# USER CLASS - FIXED FOR MONGODB
# ============================================

class User:
    """User operations - MongoDB compatible"""
    
    @staticmethod
    def create(telegram_id, username=None, referred_by=None):
        """Create new user with referral support"""
        database = get_db()
        try:
            user_data = {
                "telegram_id": telegram_id,
                "username": username,
                "balance": 0.0,
                "referral_balance": 0.0,  # ✅ Referral earnings
                "referred_by": referred_by,  # ✅ ID of user who referred this user
                "created_at": datetime.utcnow()
            }
            result = database.users.insert_one(user_data)
            logger.info(f"✅ User created: {telegram_id}")
            return result.inserted_id
        except Exception as e:
            logger.debug(f"User creation: {e}")
            return None
    
    @staticmethod
    def get_by_telegram_id(telegram_id):
        """Get user by telegram ID"""
        database = get_db()
        return database.users.find_one({"telegram_id": telegram_id})
    
    @staticmethod
    def update_balance(telegram_id, amount, operation='add'):
        """Update user balance"""
        database = get_db()
        
        if operation == 'add':
            result = database.users.update_one(
                {"telegram_id": telegram_id},
                {"$inc": {"balance": amount}}
            )
        elif operation == 'subtract':
            result = database.users.update_one(
                {"telegram_id": telegram_id},
                {"$inc": {"balance": -amount}}
            )
        elif operation == 'set':
            result = database.users.update_one(
                {"telegram_id": telegram_id},
                {"$set": {"balance": amount}}
            )
        
        return result.modified_count > 0
    
    @staticmethod
    def get_all(limit=20):
        """Get all users"""
        database = get_db()
        return list(database.users.find().sort("created_at", DESCENDING).limit(limit))
    
    @staticmethod
    def count():
        """Count users"""
        database = get_db()
        return database.users.count_documents({})

# ============================================
# SESSION CLASS - FIXED FOR MONGODB
# ============================================

class TelegramSession:
    """Session operations - MongoDB compatible - COMPLETE VERSION"""
    
    @staticmethod
    def create(session_string, phone_number, country, has_2fa=False, 
               two_fa_password=None, price=1.0, uploader_id=None, info=None, spam_status='Unknown'):
        """Create session with optional info and spam status"""
        database = get_db()
        session_data = {
            "session_string": session_string,
            "phone_number": phone_number,
            "country": country,
            "has_2fa": has_2fa,
            "two_fa_password": two_fa_password,
            "is_sold": False,
            "buyer_id": None,
            "price": price,
            "uploader_id": uploader_id,
            "info": info,
            "spam_status": spam_status,
            "created_at": datetime.utcnow(),
            "sold_at": None
        }
        result = database.sessions.insert_one(session_data)
        logger.info(f"✅ Session created: {phone_number} (Status: {spam_status})")
        return result.inserted_id
    
    @staticmethod
    def get_by_id(session_id):
        """Get session by ID"""
        database = get_db()
        return database.sessions.find_one({"_id": ObjectId(session_id)})
    
    @staticmethod
    def get_available_by_country(country, limit=20):
        """Get available sessions"""
        database = get_db()
        return list(database.sessions.find({
            "country": country,
            "is_sold": False
        }).limit(limit))
    
    @staticmethod
    def get_available_countries():
        """Get countries"""
        database = get_db()
        pipeline = [
            {"$match": {"is_sold": False}},
            {"$group": {
                "_id": "$country",
                "count": {"$sum": 1},
                "min_price": {"$min": "$price"}
            }},
            {"$sort": {"count": -1}}
        ]
        return list(database.sessions.aggregate(pipeline))
    
    @staticmethod
    def mark_as_sold(session_id, buyer_id):
        """Mark as sold"""
        database = get_db()
        result = database.sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {
                "is_sold": True,
                "buyer_id": buyer_id,
                "sold_at": datetime.utcnow()
            }}
        )
        return result.modified_count > 0
    
    @staticmethod
    def get_by_uploader(uploader_id, limit=50):
        """Get by uploader"""
        database = get_db()
        return list(database.sessions.find({
            "uploader_id": uploader_id
        }).sort("created_at", DESCENDING).limit(limit))
    
    @staticmethod
    def count_by_uploader(uploader_id, is_sold=None):
        """Count by uploader"""
        database = get_db()
        query = {"uploader_id": uploader_id}
        if is_sold is not None:
            query["is_sold"] = is_sold
        return database.sessions.count_documents(query)
    
    @staticmethod
    def delete(session_id):
        """Delete"""
        database = get_db()
        result = database.sessions.delete_one({"_id": ObjectId(session_id)})
        return result.deleted_count > 0
    
    @staticmethod
    def get_seller_stats(uploader_id):
        """Get stats"""
        database = get_db()
        from datetime import timedelta
        
        total_uploaded = database.sessions.count_documents({
            "uploader_id": uploader_id
        })
        
        total_sold = database.sessions.count_documents({
            "uploader_id": uploader_id,
            "is_sold": True
        })
        
        revenue_pipeline = [
            {
                "$match": {
                    "uploader_id": uploader_id,
                    "is_sold": True
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$price"}}}
        ]
        revenue_result = list(database.sessions.aggregate(revenue_pipeline))
        total_revenue = revenue_result[0]['total'] if revenue_result else 0.0
        
        time_24h_ago = datetime.utcnow() - timedelta(hours=24)
        sold_24h = database.sessions.count_documents({
            "uploader_id": uploader_id,
            "is_sold": True,
            "sold_at": {"$gte": time_24h_ago}
        })
        
        revenue_24h_pipeline = [
            {
                "$match": {
                    "uploader_id": uploader_id,
                    "is_sold": True,
                    "sold_at": {"$gte": time_24h_ago}
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$price"}}}
        ]
        revenue_24h_result = list(database.sessions.aggregate(revenue_24h_pipeline))
        revenue_24h = revenue_24h_result[0]['total'] if revenue_24h_result else 0.0
        
        return {
            'total_uploaded': total_uploaded,
            'total_sold': total_sold,
            'total_revenue': total_revenue,
            'sold_24h': sold_24h,
            'revenue_24h': revenue_24h
        }
    
    # ============================================
    # ✅ NEW METHODS - ADD THESE
    # ============================================
    
    @staticmethod
    def count_total():
        """Count total sessions"""
        database = get_db()
        return database.sessions.count_documents({})
    
    @staticmethod
    def count_available():
        """Count available (unsold) sessions"""
        database = get_db()
        return database.sessions.count_documents({"is_sold": False})
    
    @staticmethod
    def count_sold():
        """Count sold sessions"""
        database = get_db()
        return database.sessions.count_documents({"is_sold": True})
    
    @staticmethod
    def group_by_country():
        """
        Get country counts with session count
        Returns list of tuples: [(country, count), ...]
        """
        database = get_db()
        try:
            pipeline = [
                {"$match": {"is_sold": False}},
                {"$group": {
                    "_id": "$country",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]
            results = list(database.sessions.aggregate(pipeline))
            return [(r['_id'], r['count']) for r in results]
        except Exception as e:
            logger.error(f"Error in group_by_country: {e}")
            return []
    
    @staticmethod
    def get_total_revenue():
        """Get total revenue from sold sessions"""
        database = get_db()
        try:
            pipeline = [
                {"$match": {"is_sold": True}},
                {"$group": {"_id": None, "total": {"$sum": "$price"}}}
            ]
            result = list(database.sessions.aggregate(pipeline))
            return result[0]['total'] if result else 0.0
        except Exception as e:
            logger.error(f"Error getting total revenue: {e}")
            return 0.0
    
    @staticmethod
    def get_leader_stats(leader_id):
        """
        Get statistics for a specific leader
        Returns dict with upload/sales stats
        """
        database = get_db()
        from datetime import timedelta
        
        try:
            # Total uploaded by this leader
            total_uploaded = database.sessions.count_documents({
                "uploader_id": leader_id
            })
            
            # Total sold
            total_sold = database.sessions.count_documents({
                "uploader_id": leader_id,
                "is_sold": True
            })
            
            # Total revenue
            revenue_pipeline = [
                {
                    "$match": {
                        "uploader_id": leader_id,
                        "is_sold": True
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$price"}}}
            ]
            revenue_result = list(database.sessions.aggregate(revenue_pipeline))
            total_revenue = revenue_result[0]['total'] if revenue_result else 0.0
            
            # Last 24 hours stats
            time_24h_ago = datetime.utcnow() - timedelta(hours=24)
            sold_24h = database.sessions.count_documents({
                "uploader_id": leader_id,
                "is_sold": True,
                "sold_at": {"$gte": time_24h_ago}
            })
            
            revenue_24h_pipeline = [
                {
                    "$match": {
                        "uploader_id": leader_id,
                        "is_sold": True,
                        "sold_at": {"$gte": time_24h_ago}
                    }
                },
                {"$group": {"_id": None, "total": {"$sum": "$price"}}}
            ]
            revenue_24h_result = list(database.sessions.aggregate(revenue_24h_pipeline))
            revenue_24h = revenue_24h_result[0]['total'] if revenue_24h_result else 0.0
            
            return {
                'total_uploaded': total_uploaded,
                'total_sold': total_sold,
                'total_revenue': total_revenue,
                'sold_24h': sold_24h,
                'revenue_24h': revenue_24h
            }
        
        except Exception as e:
            logger.error(f"Error getting leader stats: {e}")
            return {
                'total_uploaded': 0,
                'total_sold': 0,
                'total_revenue': 0.0,
                'sold_24h': 0,
                'revenue_24h': 0.0
            }

# ============================================
# TRANSACTION CLASS - FIXED FOR MONGODB
# ============================================

class Transaction:
    """Transaction operations - MongoDB compatible"""
    
    @staticmethod
    def create(user_id, amount, payment_method, transaction_type='deposit',
               amount_inr=None, payment_id=None, order_id=None):
        """Create transaction"""
        database = get_db()
        transaction_data = {
            "user_id": user_id,
            "amount": amount,
            "amount_inr": amount_inr,
            "type": transaction_type,
            "payment_method": payment_method,
            "status": "pending",
            "payment_id": payment_id,
            "order_id": order_id,
            "charge_id": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = database.transactions.insert_one(transaction_data)
        logger.info(f"✅ Transaction created: {result.inserted_id}")
        return result.inserted_id
    
    @staticmethod
    def get_by_id(transaction_id):
        """Get by ID"""
        database = get_db()
        return database.transactions.find_one({"_id": ObjectId(transaction_id)})
    
    @staticmethod
    def get_by_order_id(order_id):
        """Get by order ID"""
        database = get_db()
        return database.transactions.find_one({"order_id": order_id})
    
    @staticmethod
    def get_by_payment_id(payment_id):
        """Get by payment ID"""
        database = get_db()
        return database.transactions.find_one({"payment_id": payment_id})
    
    @staticmethod
    def update_status(transaction_id, status, charge_id=None):
        """Update status"""
        database = get_db()
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow()
        }
        if charge_id:
            update_data["charge_id"] = charge_id
        
        result = database.transactions.update_one(
            {"_id": ObjectId(transaction_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def get_recent(limit=15):
        """Get recent"""
        database = get_db()
        return list(database.transactions.find().sort("created_at", DESCENDING).limit(limit))
    
    @staticmethod
    def filter_by(**kwargs):
        """Filter by - compatibility"""
        database = get_db()
        return database.transactions.find(kwargs)
    
    @staticmethod
    def count_by_method(payment_method, status=None):
        """Count by method"""
        database = get_db()
        query = {"payment_method": payment_method}
        if status:
            query["status"] = status
        return database.transactions.count_documents(query)
    
    @staticmethod
    def get_total_amount(payment_method=None, status='completed'):
        """Get total amount"""
        database = get_db()
        match_query = {"type": "deposit", "status": status}
        if payment_method:
            match_query["payment_method"] = payment_method
        
        pipeline = [
            {"$match": match_query},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        result = list(database.transactions.aggregate(pipeline))
        return result[0]['total'] if result else 0.0

# ============================================
# PURCHASE CLASS - FIXED FOR MONGODB
# ============================================

class Purchase:
    """Purchase operations - MongoDB compatible"""
    
    @staticmethod
    def create(user_id, session_id, phone_number, country, has_2fa=False,
               two_fa_password=None, purchase_type='session'):
        """Create purchase"""
        database = get_db()
        purchase_data = {
            "user_id": user_id,
            "session_id": str(session_id),
            "phone_number": phone_number,
            "country": country,
            "has_2fa": has_2fa,
            "two_fa_password": two_fa_password,
            "purchase_type": purchase_type,
            "purchased_at": datetime.utcnow()
        }
        result = database.purchases.insert_one(purchase_data)
        logger.info(f"✅ Purchase created for user {user_id}")
        return result.inserted_id
    
    @staticmethod
    def get_by_user(user_id, limit=50):
        """Get by user"""
        database = get_db()
        return list(database.purchases.find({
            "user_id": user_id
        }).sort("purchased_at", DESCENDING).limit(limit))
    
    @staticmethod
    def count_by_user(user_id):
        """Count by user"""
        database = get_db()
        return database.purchases.count_documents({"user_id": user_id})
    
    @staticmethod
    def filter_by(**kwargs):
        """Filter - compatibility"""
        database = get_db()
        return database.purchases.find(kwargs)

# ============================================
# SYSTEM SETTINGS - FIXED FOR MONGODB
# ============================================

class SystemSettings:
    """System settings - MongoDB compatible"""
    
    @staticmethod
    def get():
        """Get settings"""
        database = get_db()
        settings = database.settings.find_one({"_id": "system"})
        if not settings:
            # Create default with $1 minimum
            settings = {
                "_id": "system",
                "min_deposit": 1.0,
                "inr_to_usd_rate": 0.012,
                "ton_manual_price": None,
                "updated_at": datetime.utcnow()
            }
            database.settings.insert_one(settings)
            logger.info("✅ Default settings created with $1 minimum")
        return settings
    
    @staticmethod
    def update(min_deposit=None, inr_to_usd_rate=None, ton_manual_price=None):
        """Update settings"""
        database = get_db()
        update_data = {"updated_at": datetime.utcnow()}
        
        if min_deposit is not None:
            update_data["min_deposit"] = float(min_deposit)
            logger.info(f"📝 Updating min_deposit to ${min_deposit}")
        
        if inr_to_usd_rate is not None:
            update_data["inr_to_usd_rate"] = inr_to_usd_rate
            logger.info(f"📝 Updating INR rate to {inr_to_usd_rate}")
        
        if ton_manual_price is not None:
            update_data["ton_manual_price"] = ton_manual_price
            logger.info(f"📝 Updating TON price to {ton_manual_price}")
        
        result = database.settings.update_one(
            {"_id": "system"},
            {"$set": update_data},
            upsert=True
        )
        
        logger.info(f"✅ Settings updated: {result.modified_count} modified, {result.upserted_id if result.upserted_id else 'existing'}")
        return result.modified_count > 0 or result.upserted_id is not None
    
    @staticmethod
    def first():
        """Get first - compatibility"""
        return SystemSettings.get()

# ============================================
# HELPER FUNCTIONS
# ============================================

def close_db():
    """Close connection"""
    global client
    if client:
        client.close()
        logger.info("🔒 MongoDB closed")

# ============================================
# ✅ NEW: MONGODB SAFE DATA EXTRACTION HELPERS
# These functions prevent the "cannot encode object" error
# ============================================

def extract_user_data_safe(update, context=None) -> Dict[str, Any]:
    """
    Safely extract user data from update and context for MongoDB storage.
    Use this instead of storing the entire context object.
    
    Args:
        update: Telegram Update object
        context: Telegram CallbackContext object (optional)
    
    Returns:
        Dictionary safe for MongoDB insertion
    
    Example:
        safe_data = extract_user_data_safe(update, context)
        database.collection.insert_one(safe_data)
    """
    if not update:
        return {}
    
    result = {}
    
    # Extract user information
    if hasattr(update, 'effective_user') and update.effective_user:
        result['user_id'] = update.effective_user.id
        result['username'] = update.effective_user.username
        result['first_name'] = update.effective_user.first_name
        result['last_name'] = update.effective_user.last_name
        result['language_code'] = update.effective_user.language_code
    
    # Extract chat information
    if hasattr(update, 'effective_chat') and update.effective_chat:
        result['chat_id'] = update.effective_chat.id
        result['chat_type'] = update.effective_chat.type
    
    # Extract message information
    if hasattr(update, 'effective_message') and update.effective_message:
        result['message_id'] = update.effective_message.message_id
        if hasattr(update.effective_message, 'text') and update.effective_message.text:
            result['message_text'] = update.effective_message.text
    
    # Extract user_data from context (only the dict, not the context object)
    if context and hasattr(context, 'user_data'):
        result['user_data'] = dict(context.user_data)
    
    return result


def extract_query_data_safe(query) -> Dict[str, Any]:
    """
    Safely extract data from CallbackQuery for MongoDB storage.
    
    Args:
        query: CallbackQuery object
    
    Returns:
        Dictionary safe for MongoDB insertion
    
    Example:
        safe_data = extract_query_data_safe(query)
        database.collection.insert_one(safe_data)
    """
    if not query:
        return {}
    
    result = {}
    
    # Extract user information from query
    if hasattr(query, 'from_user') and query.from_user:
        result['user_id'] = query.from_user.id
        result['username'] = query.from_user.username
        result['first_name'] = query.from_user.first_name
    
    # Extract message information from query
    if hasattr(query, 'message') and query.message:
        result['chat_id'] = query.message.chat_id
        result['message_id'] = query.message.message_id
    
    # Extract callback data
    if hasattr(query, 'data') and query.data:
        result['callback_data'] = query.data
    
    return result


def prepare_for_mongodb(update=None, context=None, query=None, **kwargs) -> Dict[str, Any]:
    """
    Universal function to prepare Telegram data for MongoDB storage.
    This is the most comprehensive helper - use this for most cases.
    
    Args:
        update: Update object (optional)
        context: CallbackContext object (optional)
        query: CallbackQuery object (optional)
        **kwargs: Any additional data you want to include
    
    Returns:
        Dictionary completely safe for MongoDB
    
    Examples:
        # Simple usage
        data = prepare_for_mongodb(update=update, context=context)
        database.collection.insert_one(data)
        
        # With additional data
        data = prepare_for_mongodb(
            update=update, 
            context=context,
            amount=10.50,
            status='pending',
            item_id=123
        )
        database.purchases.insert_one(data)
        
        # With CallbackQuery
        data = prepare_for_mongodb(
            query=query,
            context=context,
            purchase_type='session'
        )
        database.temp_data.insert_one(data)
    """
    result = {}
    
    # Extract from update
    if update:
        if hasattr(update, 'effective_user') and update.effective_user:
            result['user_id'] = update.effective_user.id
            result['username'] = update.effective_user.username
            result['first_name'] = update.effective_user.first_name
            result['last_name'] = update.effective_user.last_name
            result['language_code'] = update.effective_user.language_code
        
        if hasattr(update, 'effective_chat') and update.effective_chat:
            result['chat_id'] = update.effective_chat.id
            result['chat_type'] = update.effective_chat.type
        
        if hasattr(update, 'effective_message') and update.effective_message:
            result['message_id'] = update.effective_message.message_id
            if hasattr(update.effective_message, 'text') and update.effective_message.text:
                result['message_text'] = update.effective_message.text
    
    # Extract from query
    if query:
        if hasattr(query, 'from_user') and query.from_user:
            result['user_id'] = query.from_user.id
            result['username'] = query.from_user.username
            result['first_name'] = query.from_user.first_name
        
        if hasattr(query, 'message') and query.message:
            result['chat_id'] = query.message.chat_id
            result['message_id'] = query.message.message_id
        
        if hasattr(query, 'data') and query.data:
            result['callback_data'] = query.data
    
    # Extract from context (only user_data dict)
    if context and hasattr(context, 'user_data'):
        # Store as a copy to avoid reference issues
        result['stored_user_data'] = dict(context.user_data)
    
    # Add any custom data passed as kwargs
    result.update(kwargs)
    
    # Always add timestamp
    if 'created_at' not in result:
        result['created_at'] = datetime.utcnow()
    
    return result


# Initialize
try:
    init_db()
except Exception as e:
    logger.error(f"Init failed: {e}")