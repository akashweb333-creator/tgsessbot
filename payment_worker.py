"""
TON Payment Verification Worker
Runs in background to check for incoming TON payments
"""

import logging
import asyncio
from datetime import datetime, timedelta
from database import get_db, Transaction, User
from payment_ton import get_ton_payment

logger = logging.getLogger(__name__)

class TONPaymentWorker:
    """Background worker to verify TON payments"""
    
    def __init__(self, bot_instance):
        """
        Initialize worker
        
        Args:
            bot_instance: Telegram bot instance for sending notifications
        """
        self.bot = bot_instance
        self.running = False
        self.check_interval = 30  # Check every 30 seconds
    
    async def start(self):
        """Start the payment verification worker"""
        self.running = True
        logger.info("TON Payment Worker started")
        
        while self.running:
            try:
                await self.check_pending_payments()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in TON payment worker: {e}")
                await asyncio.sleep(self.check_interval)
    
    def stop(self):
        """Stop the worker"""
        self.running = False
        logger.info("TON Payment Worker stopped")
    
    async def check_pending_payments(self):
        """Check all pending TON payments"""
        db = get_db()
        try:
            # Get all pending TON transactions from last 24 hours
            time_limit = datetime.utcnow() - timedelta(hours=24)
            
            pending_transactions = db.query(Transaction).filter(
                Transaction.status == 'pending',
                Transaction.payment_method == 'ton',
                Transaction.created_at >= time_limit
            ).all()
            
            if not pending_transactions:
                return
            
            logger.info(f"Checking {len(pending_transactions)} pending TON payments")
            
            ton_handler = get_ton_payment()
            
            for transaction in pending_transactions:
                try:
                    # Verify and credit payment
                    success = await ton_handler.verify_and_credit_payment(transaction.id)
                    
                    if success:
                        # Send notification to user
                        await self.notify_user(transaction.user_id, transaction.amount)
                        logger.info(
                            f"Payment verified and user notified: "
                            f"User {transaction.user_id}, Amount ${transaction.amount}"
                        )
                    
                    # Small delay between checks
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(
                        f"Error checking transaction {transaction.id}: {e}"
                    )
                    continue
                    
        except Exception as e:
            logger.error(f"Error checking pending payments: {e}")
        finally:
            db.close()
    
    async def notify_user(self, user_id: int, amount: float):
        """
        Send notification to user about successful payment
        
        Args:
            user_id: Telegram user ID
            amount: Amount credited in USD
        """
        try:
            # Get user's current balance
            db = get_db()
            try:
                user = db.query(User).filter_by(telegram_id=user_id).first()
                if user:
                    current_balance = user.balance
                else:
                    current_balance = amount
            finally:
                db.close()
            
            message = (
                "✅ Payment Received!\n\n"
                f"💰 Amount: ${amount:.2f} USD\n"
                f"💳 New Balance: ${current_balance:.2f} USD\n\n"
                "Thank you for your payment! "
                "Your balance has been credited automatically."
            )
            
            await self.bot.send_message(
                chat_id=user_id,
                text=message
            )
            
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")

# Global worker instance
payment_worker = None

def init_payment_worker(bot_instance):
    """Initialize global payment worker"""
    global payment_worker
    payment_worker = TONPaymentWorker(bot_instance)
    logger.info("TON Payment Worker initialized")
    return payment_worker

def get_payment_worker():
    """Get global payment worker"""
    return payment_worker

async def start_payment_worker():
    """Start the payment verification worker"""
    if payment_worker:
        await payment_worker.start()
    else:
        logger.error("Payment worker not initialized")