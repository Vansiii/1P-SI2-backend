"""
Diagnostics API endpoints for monitoring database connections and system health.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session, get_engine
from ...shared.dependencies.auth import get_current_user
from ...models.user import User

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/db-connections")
async def get_database_connections(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get information about active database connections.
    
    Requires admin authentication.
    
    Returns:
        - Pool statistics
        - Active connections from PostgreSQL
        - Connection details
    """
    # Verificar que sea administrador
    if current_user.user_type != "administrator":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access diagnostics"
        )
    
    # Get pool statistics
    pool = get_engine().pool
    pool_stats = {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total_connections": pool.size() + pool.overflow(),
    }
    
    # Query PostgreSQL for active connections
    query = text("""
        SELECT 
            pid,
            usename,
            application_name,
            client_addr,
            state,
            state_change,
            query_start,
            wait_event_type,
            wait_event,
            backend_start,
            EXTRACT(EPOCH FROM (NOW() - query_start)) as query_duration_seconds,
            EXTRACT(EPOCH FROM (NOW() - state_change)) as state_duration_seconds,
            LEFT(query, 100) as query_preview
        FROM pg_stat_activity
        WHERE datname = current_database()
        AND pid != pg_backend_pid()
        ORDER BY state_change DESC
    """)
    
    result = await session.execute(query)
    connections = []
    
    for row in result:
        connections.append({
            "pid": row.pid,
            "user": row.usename,
            "application": row.application_name,
            "client_ip": str(row.client_addr) if row.client_addr else "local",
            "state": row.state,
            "state_change": row.state_change.isoformat() if row.state_change else None,
            "query_start": row.query_start.isoformat() if row.query_start else None,
            "wait_event_type": row.wait_event_type,
            "wait_event": row.wait_event,
            "backend_start": row.backend_start.isoformat() if row.backend_start else None,
            "query_duration_seconds": float(row.query_duration_seconds) if row.query_duration_seconds else None,
            "state_duration_seconds": float(row.state_duration_seconds) if row.state_duration_seconds else None,
            "query_preview": row.query_preview,
        })
    
    # Count connections by state
    state_counts = {}
    for conn in connections:
        state = conn["state"]
        state_counts[state] = state_counts.get(state, 0) + 1
    
    # Identify potential issues
    issues = []
    
    # Check for idle connections
    idle_count = state_counts.get("idle", 0)
    if idle_count > 10:
        issues.append(f"High number of idle connections: {idle_count}")
    
    # Check for long-running queries
    long_running = [c for c in connections if c["query_duration_seconds"] and c["query_duration_seconds"] > 30]
    if long_running:
        issues.append(f"Long-running queries detected: {len(long_running)}")
    
    # Check for idle in transaction
    idle_in_transaction = [c for c in connections if c["state"] == "idle in transaction"]
    if idle_in_transaction:
        issues.append(f"Idle in transaction connections: {len(idle_in_transaction)} (potential connection leak)")
    
    return {
        "pool_statistics": pool_stats,
        "active_connections": connections,
        "connection_count": len(connections),
        "state_summary": state_counts,
        "issues": issues,
        "recommendations": _get_recommendations(pool_stats, state_counts, issues)
    }


@router.get("/db-pool-status")
async def get_pool_status(
    current_user: User = Depends(get_current_user)
):
    """
    Get quick pool status without querying the database.
    
    Requires admin authentication.
    """
    # Verificar que sea administrador
    if current_user.user_type != "administrator":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access diagnostics"
        )
    
    pool = get_engine().pool
    
    checked_out = pool.checkedout()
    total_capacity = pool.size() + pool.overflow()
    usage_percentage = (checked_out / total_capacity * 100) if total_capacity > 0 else 0
    
    status = "healthy"
    if usage_percentage > 80:
        status = "warning"
    if usage_percentage > 95:
        status = "critical"
    
    return {
        "status": status,
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": checked_out,
        "overflow": pool.overflow(),
        "total_capacity": total_capacity,
        "usage_percentage": round(usage_percentage, 2),
        "available": total_capacity - checked_out
    }


@router.post("/db-kill-idle-connections")
async def kill_idle_connections(
    min_idle_seconds: int = 300,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Kill idle database connections that have been idle for more than specified seconds.
    
    Use with caution! This will terminate connections.
    
    Args:
        min_idle_seconds: Minimum idle time in seconds before killing (default: 300 = 5 minutes)
    
    Requires admin authentication.
    """
    # Verificar que sea administrador
    if current_user.user_type != "administrator":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can kill connections"
        )
    
    # Find idle connections
    query = text("""
        SELECT 
            pid,
            usename,
            application_name,
            state,
            EXTRACT(EPOCH FROM (NOW() - state_change)) as idle_seconds
        FROM pg_stat_activity
        WHERE datname = current_database()
        AND state = 'idle'
        AND pid != pg_backend_pid()
        AND EXTRACT(EPOCH FROM (NOW() - state_change)) > :min_idle_seconds
    """)
    
    result = await session.execute(query, {"min_idle_seconds": min_idle_seconds})
    idle_connections = list(result)
    
    killed_count = 0
    killed_pids = []
    
    for row in idle_connections:
        try:
            kill_query = text("SELECT pg_terminate_backend(:pid)")
            await session.execute(kill_query, {"pid": row.pid})
            killed_count += 1
            killed_pids.append({
                "pid": row.pid,
                "user": row.usename,
                "application": row.application_name,
                "idle_seconds": float(row.idle_seconds)
            })
        except Exception as e:
            logger.error(f"Failed to kill connection {row.pid}: {e}")
    
    await session.commit()
    
    return {
        "killed_count": killed_count,
        "killed_connections": killed_pids,
        "message": f"Killed {killed_count} idle connections"
    }


def _get_recommendations(pool_stats: dict, state_counts: dict, issues: list) -> list:
    """Generate recommendations based on diagnostics."""
    recommendations = []
    
    # Check pool usage
    usage = pool_stats["checked_out"] / pool_stats["total_connections"] if pool_stats["total_connections"] > 0 else 0
    
    if usage > 0.8:
        recommendations.append("Pool usage is high (>80%). Consider increasing DB_POOL_SIZE and DB_MAX_OVERFLOW.")
    
    # Check for idle in transaction
    if state_counts.get("idle in transaction", 0) > 0:
        recommendations.append(
            "Idle in transaction connections detected. This indicates connection leaks. "
            "Ensure all database sessions are properly closed with try/finally or context managers."
        )
    
    # Check for too many idle connections
    if state_counts.get("idle", 0) > 10:
        recommendations.append(
            "High number of idle connections. Consider reducing pool_size or implementing "
            "connection recycling with pool_recycle parameter."
        )
    
    if not recommendations:
        recommendations.append("No issues detected. Connection pool is healthy.")
    
    return recommendations
