"""
Statistics Service
"""
from typing import List, Dict
from datetime import datetime, timedelta
from database.supabase_client import get_supabase

class StatsService:
    def __init__(self):
        self.supabase = get_supabase()
    
    async def get_overall_stats(self) -> Dict:
        """Get overall statistics"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        # Total violations
        total_result = self.supabase.table("violations") \
            .select("id", count="exact") \
            .execute()
        total_count = total_result.count if hasattr(total_result, 'count') else len(total_result.data)
        
        # Today
        today_result = self.supabase.table("violations") \
            .select("id", count="exact") \
            .gte("timestamp", today_start.isoformat()) \
            .execute()
        today_count = today_result.count if hasattr(today_result, 'count') else len(today_result.data)
        
        # Week
        week_result = self.supabase.table("violations") \
            .select("id", count="exact") \
            .gte("timestamp", week_start.isoformat()) \
            .execute()
        week_count = week_result.count if hasattr(week_result, 'count') else len(week_result.data)
        
        # Month
        month_result = self.supabase.table("violations") \
            .select("id", count="exact") \
            .gte("timestamp", month_start.isoformat()) \
            .execute()
        month_count = month_result.count if hasattr(month_result, 'count') else len(month_result.data)
        
        return {
            "total_violations": total_count,
            "today_violations": today_count,
            "week_violations": week_count,
            "month_violations": month_count
        }
    
    async def get_stats_by_camera(self) -> List[Dict]:
        """Get violations grouped by camera"""
        # This would be better with a GROUP BY query, but Supabase client doesn't support it directly
        # You'd need to use RPC or do aggregation in Python
        result = self.supabase.table("violations") \
            .select("camera_id") \
            .execute()
        
        # Count violations per camera
        camera_counts = {}
        for row in result.data:
            cam_id = row['camera_id']
            camera_counts[cam_id] = camera_counts.get(cam_id, 0) + 1
        
        return [
            {"camera_id": cam_id, "count": count}
            for cam_id, count in camera_counts.items()
        ]
    
    async def get_stats_by_hour(self, days: int = 7) -> List[Dict]:
        """Get violations by hour"""
        start_date = datetime.now() - timedelta(days=days)
        
        result = self.supabase.table("violations") \
            .select("timestamp") \
            .gte("timestamp", start_date.isoformat()) \
            .execute()
        
        # Group by hour
        hour_counts = {}
        for row in result.data:
            ts = datetime.fromisoformat(row['timestamp'])
            hour = ts.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        
        return [
            {"hour": hour, "count": count}
            for hour, count in sorted(hour_counts.items())
        ]
