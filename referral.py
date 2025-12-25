"""
Referral System - COMPLETE FIXED VERSION
Replace your ENTIRE referral.py with this file
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler
)
import config
from database import get_db
from bson.objectid import ObjectId

logger = logging.getLogger(__name__)

# Conversation states
REFERRAL_WITHDRAWAL_AMOUNT, REFERRAL_WITHDRAWAL_ADDRESS = range(2)

# ✅ Bot username storage (set dynamically at startup)
_BOT_USERNAME = None

# Commission rates
LEVEL_1_COMMISSION = 0.03  # 3%
LEVEL_2_COMMISSION = 0.015  # 1.5%

def set_bot_username(username: str):
    """Store bot username (called from bot.py at startup)"""
    global _BOT_USERNAME
    _BOT_USERNAME = username
    logger.info(f"✅ Referral system: Bot username set to @{username}")

def get_bot_username() -> str:
    """Get stored bot username"""
    if not _BOT_USERNAME:
        logger.warning("⚠️ Bot username not set yet!")
        return "YourBot"  # Fallback
    return _BOT_USERNAME

# ============================================
# MAIN REFERRAL MENU - COMPLETELY FIXED
# ============================================

async def show_referral_menu(query_or_update, user_id=None):
    """
    Show referral menu - HANDLES BOTH Update AND CallbackQuery
    ✅ Works with any object type
    ✅ No more AttributeError
    """
    try:
        # ✅ CRITICAL FIX: Handle both Update and CallbackQuery objects
        if hasattr(query_or_update, 'callback_query'):
            # It's an Update object
            query = query_or_update.callback_query
            user_id = query.from_user.id
        else:
            # It's already a CallbackQuery object
            query = query_or_update
            if user_id is None:
                user_id = query.from_user.id
        
        logger.info(f"📊 Loading referral menu for user {user_id}")
        database = get_db()
        
        # Get bot username
        try:
            bot_username = get_bot_username()
            referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        except Exception as e:
            logger.error(f"Error generating referral link: {e}")
            referral_link = "❌ Error - contact support"
        
        # Get user data
        try:
            user = database.users.find_one({"telegram_id": user_id})
            if not user:
                try:
                    await query.edit_message_text(
                        "❌ User not found.\n\nPlease use /start to register."
                    )
                except:
                    pass
                return
            referral_balance = user.get('referral_balance', 0.0)
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            referral_balance = 0.0
        
        # Count Level 1 referrals
        try:
            level_1_count = database.users.count_documents({"referred_by": user_id})
        except Exception as e:
            logger.error(f"Error counting level 1 referrals: {e}")
            level_1_count = 0
        
        # Count Level 2 referrals
        try:
            level_1_users = list(database.users.find(
                {"referred_by": user_id}, 
                {"telegram_id": 1}
            ))
            level_1_ids = [u['telegram_id'] for u in level_1_users]
            level_2_count = database.users.count_documents({
                "referred_by": {"$in": level_1_ids}
            }) if level_1_ids else 0
        except Exception as e:
            logger.error(f"Error counting level 2 referrals: {e}")
            level_2_count = 0
        
        # Calculate total earnings
        try:
            total_earnings = database.referral_commissions.aggregate([
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ])
            earnings_list = list(total_earnings)
            total_earned = earnings_list[0]['total'] if earnings_list else 0.0
        except Exception as e:
            logger.error(f"Error calculating earnings: {e}")
            total_earned = 0.0
        
        # Calculate withdrawn amount
        try:
            withdrawn = database.referral_withdrawals.aggregate([
                {"$match": {"user_id": user_id, "status": "completed"}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ])
            withdrawn_list = list(withdrawn)
            total_withdrawn = withdrawn_list[0]['total'] if withdrawn_list else 0.0
        except Exception as e:
            logger.error(f"Error calculating withdrawals: {e}")
            total_withdrawn = 0.0
        
        # Build message (NO MARKDOWN to avoid encoding issues)
        message = (
            f"🎁 Referral Program\n\n"
            f"Your Referral Link:\n"
            f"{referral_link}\n\n"
            f"Commissions:\n"
            f"• Level 1 (Direct): 3%\n"
            f"• Level 2 (Sub-referrals): 1.5%\n\n"
            f"Your Stats:\n"
            f"👥 Level 1 Referrals: {level_1_count}\n"
            f"👥 Level 2 Referrals: {level_2_count}\n"
            f"💰 Total Earned: ${total_earned:.2f}\n"
            f"💸 Withdrawn: ${total_withdrawn:.2f}\n"
            f"💵 Available Balance: ${referral_balance:.2f}\n\n"
            f"Share your link and earn from every purchase!"
        )
        
        # Build keyboard
        keyboard = [
            [InlineKeyboardButton("📊 Referral Stats", callback_data='referral_stats')],
            [InlineKeyboardButton("💸 Withdraw Earnings", callback_data='referral_withdraw')],
            [InlineKeyboardButton("📜 Withdrawal History", callback_data='referral_history')],
            [InlineKeyboardButton("« Back", callback_data='back_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send message with error handling
        try:
            await query.edit_message_text(
                message, 
                reply_markup=reply_markup
            )
            logger.info(f"✅ Referral menu sent to user {user_id}")
        except Exception as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg or "message not modified" in error_msg:
                await query.answer("Referral menu is already displayed", show_alert=False)
                logger.info(f"ℹ️ Menu already displayed for user {user_id}")
            else:
                logger.error(f"Error sending referral menu: {e}")
                try:
                    await query.edit_message_text(
                        message,
                        reply_markup=reply_markup
                    )
                except:
                    await query.answer("Error loading referral menu. Please try /start again.", show_alert=True)
    
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR in show_referral_menu: {e}")
        import traceback
        traceback.print_exc()
        try:
            # Try to get query object if it exists
            if hasattr(query_or_update, 'callback_query'):
                await query_or_update.callback_query.answer("Critical error. Please contact support.", show_alert=True)
            elif hasattr(query_or_update, 'answer'):
                await query_or_update.answer("Critical error. Please contact support.", show_alert=True)
        except:
            pass


# ============================================
# REFERRAL STATS - FIXED VERSION
# ============================================

async def show_referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed referral statistics - WITH TELEGRAM ERROR HANDLING"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    try:
        database = get_db()
        
        # Get level 1 referrals
        try:
            level_1_users = list(database.users.find(
                {"referred_by": user_id},
                {"telegram_id": 1, "username": 1, "created_at": 1}
            ).limit(10))
        except Exception as e:
            logger.error(f"Error getting referrals: {e}")
            level_1_users = []
        
        # Get recent commissions
        try:
            recent_commissions = list(database.referral_commissions.find(
                {"user_id": user_id}
            ).sort("created_at", -1).limit(10))
        except Exception as e:
            logger.error(f"Error getting commissions: {e}")
            recent_commissions = []
        
        message = "📊 **Detailed Referral Stats**\n\n"
        
        if level_1_users:
            message += "**Recent Referrals:**\n"
            for user in level_1_users:
                username = user.get('username', 'No username')
                joined = user['created_at'].strftime('%Y-%m-%d')
                message += f"• @{username} (joined {joined})\n"
            message += "\n"
        else:
            message += "**No referrals yet.**\n\n"
        
        if recent_commissions:
            message += "**Recent Commissions:**\n"
            for comm in recent_commissions:
                level = comm.get('level', 1)
                amount = comm.get('amount', 0.0)
                date = comm['created_at'].strftime('%Y-%m-%d')
                message += f"• Level {level}: ${amount:.2f} ({date})\n"
        else:
            message += "**No commissions yet.** Start referring!"
        
        keyboard = [[InlineKeyboardButton("« Back", callback_data='referral_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ✅ CRITICAL: Handle Telegram "message not modified" error
        try:
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg or "message not modified" in error_msg:
                # Already showing same content
                await query.answer("Stats already displayed", show_alert=False)
            else:
                # Try without markdown
                try:
                    await query.edit_message_text(
                        message.replace('**', '').replace('`', ''),
                        reply_markup=reply_markup
                    )
                except:
                    await query.answer("Error loading stats", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in show_referral_stats: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            await query.edit_message_text(
                "❌ Error loading stats.\n\nPlease try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data='referral_menu')]])
            )
        except:
            await query.answer("Error loading stats", show_alert=True)


# ============================================
# REFERRAL HISTORY - FIXED VERSION
# ============================================

async def show_referral_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral withdrawal history - WITH TELEGRAM ERROR HANDLING"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    database = get_db()
    
    try:
        withdrawals = list(database.referral_withdrawals.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(10))
    except Exception as e:
        logger.error(f"Error getting withdrawals: {e}")
        withdrawals = []
    
    keyboard = [[InlineKeyboardButton("« Back", callback_data='referral_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if not withdrawals:
        message = (
            "📜 **Withdrawal History**\n\n"
            "No withdrawals yet."
        )
    else:
        message = "📜 **Withdrawal History**\n\n"
        
        for w in withdrawals:
            status_emoji = {
                'pending': '⏳',
                'completed': '✅',
                'rejected': '❌'
            }.get(w.get('status', 'pending'), '❓')
            
            message += f"{status_emoji} ${w.get('amount', 0):.2f} - {w.get('status', 'pending').title()}\n"
            message += f"   {w['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
            if w.get('address'):
                message += f"   {w['address'][:20]}...\n"
            message += "\n"
    
    # ✅ CRITICAL: Handle Telegram "message not modified" error
    try:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg or "message not modified" in error_msg:
            # Already showing same content
            await query.answer("History already displayed", show_alert=False)
        else:
            # Try without markdown
            try:
                await query.edit_message_text(
                    message.replace('**', '').replace('`', ''),
                    reply_markup=reply_markup
                )
            except:
                await query.answer("Error loading history", show_alert=True)


# ============================================
# REFERRAL COMMISSION PROCESSING
# ============================================

async def process_referral_commission(purchase_user_id: int, purchase_amount: float):
    """
    Process referral commissions when a purchase is made
    - Level 1 (direct referrer): 3%
    - Level 2 (referrer's referrer): 1.5%
    """
    try:
        database = get_db()
        
        # Get the user who made the purchase
        user = database.users.find_one({"telegram_id": purchase_user_id})
        if not user or not user.get('referred_by'):
            logger.info(f"No referrer for user {purchase_user_id}")
            return  # No referrer
        
        level_1_user_id = user['referred_by']
        
        # ========================================
        # LEVEL 1 COMMISSION (3%)
        # ========================================
        level_1_commission = purchase_amount * LEVEL_1_COMMISSION
        
        # Credit level 1 referrer
        database.users.update_one(
            {"telegram_id": level_1_user_id},
            {"$inc": {"referral_balance": level_1_commission}}
        )
        
        # Record commission
        database.referral_commissions.insert_one({
            "user_id": level_1_user_id,
            "from_user_id": purchase_user_id,
            "level": 1,
            "amount": level_1_commission,
            "purchase_amount": purchase_amount,
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"✅ Level 1 commission: ${level_1_commission:.2f} to user {level_1_user_id}")
        
        # ========================================
        # LEVEL 2 COMMISSION (1.5%)
        # ========================================
        level_1_user = database.users.find_one({"telegram_id": level_1_user_id})
        if level_1_user and level_1_user.get('referred_by'):
            level_2_user_id = level_1_user['referred_by']
            level_2_commission = purchase_amount * LEVEL_2_COMMISSION
            
            # Credit level 2 referrer
            database.users.update_one(
                {"telegram_id": level_2_user_id},
                {"$inc": {"referral_balance": level_2_commission}}
            )
            
            # Record commission
            database.referral_commissions.insert_one({
                "user_id": level_2_user_id,
                "from_user_id": purchase_user_id,
                "level": 2,
                "amount": level_2_commission,
                "purchase_amount": purchase_amount,
                "created_at": datetime.utcnow()
            })
            
            logger.info(f"✅ Level 2 commission: ${level_2_commission:.2f} to user {level_2_user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error processing referral commission: {e}")
        import traceback
        traceback.print_exc()


# ============================================
# WITHDRAWAL SYSTEM
# ============================================

async def referral_start_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start referral withdrawal process"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    database = get_db()
    
    user = database.users.find_one({"telegram_id": user_id})
    referral_balance = user.get('referral_balance', 0.0)
    
    if referral_balance < 1.0:
        keyboard = [[InlineKeyboardButton("« Back", callback_data='referral_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💰 **Referral Balance**\n\n"
            f"Available: ${referral_balance:.2f}\n\n"
            f"❌ Minimum withdrawal: $1.00\n\n"
            f"Keep referring to increase your balance!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Store only the balance amount
    context.user_data['referral_available_balance'] = referral_balance
    
    await query.edit_message_text(
        f"💸 **Referral Withdrawal**\n\n"
        f"💰 Available Balance: ${referral_balance:.2f}\n\n"
        f"How much do you want to withdraw?\n\n"
        f"Enter amount (Min: $1.00, Max: ${referral_balance:.2f}):\n\n"
        f"Send /cancel to abort.",
        parse_mode='Markdown'
    )
    
    return REFERRAL_WITHDRAWAL_AMOUNT

async def referral_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive withdrawal amount"""
    amount_text = update.message.text.strip()
    
    try:
        amount = float(amount_text)
        available = context.user_data.get('referral_available_balance', 0)
        
        if amount < 1.0:
            await update.message.reply_text(
                f"❌ Minimum withdrawal is $1.00\n\n"
                f"Available: ${available:.2f}\n"
                "Please enter a valid amount:"
            )
            return REFERRAL_WITHDRAWAL_AMOUNT
        
        if amount > available:
            await update.message.reply_text(
                f"❌ Insufficient balance!\n\n"
                f"Available: ${available:.2f}\n"
                f"You entered: ${amount:.2f}\n\n"
                "Please enter a valid amount:"
            )
            return REFERRAL_WITHDRAWAL_AMOUNT
        
        # Store only primitive data
        context.user_data['referral_withdrawal_amount'] = amount
        
        await update.message.reply_text(
            f"💰 Withdrawal Amount: ${amount:.2f}\n\n"
            "Now, send your USDT BEP20 address:\n\n"
            "(Make sure it's a valid BEP20 address)\n\n"
            "Send /cancel to abort."
        )
        
        return REFERRAL_WITHDRAWAL_ADDRESS
        
    except ValueError:
        available = context.user_data.get('referral_available_balance', 0)
        await update.message.reply_text(
            f"❌ Invalid amount!\n\n"
            f"Available: ${available:.2f}\n"
            "Please enter a number (e.g., 5.50):"
        )
        return REFERRAL_WITHDRAWAL_AMOUNT

async def referral_receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive USDT address and create withdrawal request"""
    address = update.message.text.strip()
    
    if len(address) < 20 or ' ' in address:
        await update.message.reply_text(
            "❌ Invalid address format.\n\n"
            "Please send a valid USDT BEP20 address:"
        )
        return REFERRAL_WITHDRAWAL_ADDRESS
    
    user = update.effective_user
    amount = context.user_data.get('referral_withdrawal_amount', 0)
    
    database = get_db()
    
    # Create withdrawal request with only serializable data
    withdrawal_data = {
        "user_id": user.id,
        "username": user.username or user.first_name,
        "amount": amount,
        "address": address,
        "type": "referral",
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    result = database.referral_withdrawals.insert_one(withdrawal_data)
    withdrawal_id = result.inserted_id
    
    # Confirm to user
    await update.message.reply_text(
        "✅ **Withdrawal Request Submitted**\n\n"
        f"💰 Amount: ${amount:.2f}\n"
        f"📍 Address: {address[:20]}...\n\n"
        "Admin will process your request soon.\n"
        "You'll be notified once completed!",
        parse_mode='Markdown'
    )
    
    # Notify admin
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Paid", callback_data=f'ref_withdraw_complete_{withdrawal_id}'),
                InlineKeyboardButton("❌ Reject", callback_data=f'ref_withdraw_reject_{withdrawal_id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            config.OWNER_ID,
            f"💸 **Referral Withdrawal Request**\n\n"
            f"👤 User: {user.first_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📝 {'@' + user.username if user.username else 'No username'}\n"
            f"💰 Amount: ${amount:.2f}\n"
            f"📍 USDT BEP20:\n{address}\n"
            f"📖 Type: Referral Earnings\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    # Clear context data
    context.user_data.clear()
    return ConversationHandler.END

async def referral_withdrawal_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel withdrawal"""
    context.user_data.clear()
    await update.message.reply_text("❌ Withdrawal cancelled.")
    return ConversationHandler.END


# ============================================
# ADMIN HANDLERS
# ============================================

async def admin_referral_withdrawal_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin marks referral withdrawal as completed"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != config.OWNER_ID:
        await query.answer("❌ Admin only", show_alert=True)
        return
    
    withdrawal_id = query.data.replace('ref_withdraw_complete_', '')
    database = get_db()
    
    withdrawal = database.referral_withdrawals.find_one({"_id": ObjectId(withdrawal_id)})
    if not withdrawal:
        await query.edit_message_text("❌ Withdrawal not found.")
        return
    
    # Deduct from user's referral balance
    database.users.update_one(
        {"telegram_id": withdrawal['user_id']},
        {"$inc": {"referral_balance": -withdrawal['amount']}}
    )
    
    # Mark as completed
    database.referral_withdrawals.update_one(
        {"_id": ObjectId(withdrawal_id)},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.utcnow(),
            "completed_by": query.from_user.id
        }}
    )
    
    await query.edit_message_text(
        f"✅ **Referral Withdrawal Completed**\n\n"
        f"👤 User ID: {withdrawal['user_id']}\n"
        f"💰 Amount: ${withdrawal['amount']:.2f}\n"
        f"📍 Address: {withdrawal['address'][:30]}...",
        parse_mode='Markdown'
    )
    
    # Notify user
    try:
        await context.bot.send_message(
            withdrawal['user_id'],
            f"✅ **Referral Withdrawal Completed!**\n\n"
            f"💰 ${withdrawal['amount']:.2f} sent to:\n"
            f"{withdrawal['address']}\n\n"
            "Thank you for promoting our service!",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")

async def admin_referral_withdrawal_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejects referral withdrawal"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != config.OWNER_ID:
        await query.answer("❌ Admin only", show_alert=True)
        return
    
    withdrawal_id = query.data.replace('ref_withdraw_reject_', '')
    database = get_db()
    
    withdrawal = database.referral_withdrawals.find_one({"_id": ObjectId(withdrawal_id)})
    if not withdrawal:
        await query.edit_message_text("❌ Withdrawal not found.")
        return
    
    database.referral_withdrawals.update_one(
        {"_id": ObjectId(withdrawal_id)},
        {"$set": {
            "status": "rejected",
            "rejected_at": datetime.utcnow(),
            "rejected_by": query.from_user.id
        }}
    )
    
    await query.edit_message_text(
        f"❌ **Referral Withdrawal Rejected**\n\n"
        f"👤 User ID: {withdrawal['user_id']}\n"
        f"💰 Amount: ${withdrawal['amount']:.2f}",
        parse_mode='Markdown'
    )
    
    # Notify user
    try:
        await context.bot.send_message(
            withdrawal['user_id'],
            "❌ **Referral Withdrawal Rejected**\n\n"
            "Your withdrawal request was not approved.\n"
            "Contact support for more information.\n\n"
            "@Akash_support_bot",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")

async def admin_referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show overall referral statistics"""
    if update.effective_user.id != config.OWNER_ID:
        await update.message.reply_text("❌ Admin only")
        return
    
    database = get_db()
    
    # Total users with referrals
    total_referrers = database.users.count_documents({"referred_by": {"$exists": True, "$ne": None}})
    
    # Total commissions paid
    total_commissions = database.referral_commissions.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ])
    comm_list = list(total_commissions)
    total_paid = comm_list[0]['total'] if comm_list else 0.0
    
    # Pending withdrawals
    pending = list(database.referral_withdrawals.find({"status": "pending"}))
    pending_amount = sum(w['amount'] for w in pending)
    
    # Top referrers
    top_referrers = database.referral_commissions.aggregate([
        {"$group": {"_id": "$user_id", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
        {"$limit": 5}
    ])
    
    message = (
        f"📊 **Referral System Stats**\n\n"
        f"👥 Total Referred Users: {total_referrers}\n"
        f"💰 Total Commissions Paid: ${total_paid:.2f}\n"
        f"⏳ Pending Withdrawals: {len(pending)} (${pending_amount:.2f})\n\n"
        f"**Top Referrers:**\n"
    )
    
    for idx, ref in enumerate(list(top_referrers), 1):
        user_id = ref['_id']
        total = ref['total']
        message += f"{idx}. User {user_id}: ${total:.2f}\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# ============================================
# SETUP HANDLERS
# ============================================

def setup_referral_handlers(application):
    """Setup referral system handlers"""
    logger.info("✅ Setting up referral handlers...")
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(show_referral_menu, pattern='^referral_menu$'))
    application.add_handler(CallbackQueryHandler(show_referral_stats, pattern='^referral_stats$'))
    application.add_handler(CallbackQueryHandler(show_referral_history, pattern='^referral_history$'))
    
    # Withdrawal conversation
    withdrawal_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(referral_start_withdrawal, pattern='^referral_withdraw$')
        ],
        states={
            REFERRAL_WITHDRAWAL_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, referral_receive_amount)
            ],
            REFERRAL_WITHDRAWAL_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, referral_receive_address)
            ]
        },
        fallbacks=[CommandHandler('cancel', referral_withdrawal_cancel)],
        allow_reentry=True
    )
    application.add_handler(withdrawal_conv)
    
    # Admin handlers
    application.add_handler(CallbackQueryHandler(admin_referral_withdrawal_complete, pattern='^ref_withdraw_complete_'))
    application.add_handler(CallbackQueryHandler(admin_referral_withdrawal_reject, pattern='^ref_withdraw_reject_'))
    application.add_handler(CommandHandler("referral_stats", admin_referral_stats))
    
    logger.info("✅ Referral handlers registered")