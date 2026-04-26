"""
Tracking cleanup tasks for removing old location data.
"""
from datetime import datetime, timedelta
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_session_factory
from ..core.logging import get_logger
from ..models.technician_location_history import TechnicianLocationHistory

logger = get_logger(__name__)


async def cleanup_old_locations():
    """
    Clean up old location records from technician_location_history table.
    
    Removes location records older than 24 hours to optimize storage and query performance.
    Executes in batches of 1000 records to avoid long-running transactions.
    
    This task should be run periodically (e.g., every 6 hours) via APScheduler.
    """
    logger.info("🧹 Starting cleanup of old location records...")
    
    # Calculate cutoff time (24 hours ago)
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    
    async_session_maker = get_session_factory()
    async with async_session_maker() as session:
        try:
            # Count total records to delete
            count_query = select(func.count()).select_from(TechnicianLocationHistory).where(
                TechnicianLocationHistory.recorded_at < cutoff_time
            )
            total_count = await session.scalar(count_query)
            
            if total_count == 0:
                logger.info("✅ No old location records to clean up")
                return
            
            logger.info(f"📊 Found {total_count} old location records to delete")
            
            # Delete in batches of 1000 to avoid long-running transactions
            batch_size = 1000
            total_deleted = 0
            
            while True:
                # Get IDs of records to delete in this batch
                batch_query = (
                    select(TechnicianLocationHistory.id)
                    .where(TechnicianLocationHistory.recorded_at < cutoff_time)
                    .limit(batch_size)
                )
                result = await session.scalars(batch_query)
                batch_ids = list(result.all())
                
                if not batch_ids:
                    break
                
                # Delete batch
                delete_query = delete(TechnicianLocationHistory).where(
                    TechnicianLocationHistory.id.in_(batch_ids)
                )
                result = await session.execute(delete_query)
                await session.commit()
                
                deleted_count = result.rowcount
                total_deleted += deleted_count
                
                logger.info(
                    f"🗑️  Deleted batch of {deleted_count} records "
                    f"({total_deleted}/{total_count} total)"
                )
                
                # If we deleted fewer than batch_size, we're done
                if deleted_count < batch_size:
                    break
            
            logger.info(
                f"✅ Cleanup completed: Deleted {total_deleted} old location records "
                f"(older than {cutoff_time.isoformat()})"
            )
            
        except Exception as e:
            logger.error(f"❌ Error during location cleanup: {str(e)}", exc_info=True)
            await session.rollback()
            raise


async def get_cleanup_statistics():
    """
    Get statistics about location data storage.
    
    Returns:
        dict: Statistics including total records, old records, and storage estimates
    """
    async_session_maker = get_session_factory()
    async with async_session_maker() as session:
        try:
            # Total records
            total_query = select(func.count()).select_from(TechnicianLocationHistory)
            total_records = await session.scalar(total_query)
            
            # Old records (>24 hours)
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            old_query = select(func.count()).select_from(TechnicianLocationHistory).where(
                TechnicianLocationHistory.recorded_at < cutoff_time
            )
            old_records = await session.scalar(old_query)
            
            # Recent records (last 24 hours)
            recent_records = total_records - old_records
            
            # Oldest record
            oldest_query = (
                select(TechnicianLocationHistory.recorded_at)
                .order_by(TechnicianLocationHistory.recorded_at.asc())
                .limit(1)
            )
            oldest_record = await session.scalar(oldest_query)
            
            # Newest record
            newest_query = (
                select(TechnicianLocationHistory.recorded_at)
                .order_by(TechnicianLocationHistory.recorded_at.desc())
                .limit(1)
            )
            newest_record = await session.scalar(newest_query)
            
            return {
                "total_records": total_records,
                "recent_records": recent_records,
                "old_records": old_records,
                "oldest_record": oldest_record.isoformat() if oldest_record else None,
                "newest_record": newest_record.isoformat() if newest_record else None,
                "cleanup_threshold_hours": 24
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting cleanup statistics: {str(e)}", exc_info=True)
            return {
                "error": str(e)
            }
