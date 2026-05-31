#!/usr/bin/env python3
"""
SyamAdmin — Metrics Trends Aggregator
Queries the SQLite database to summarize 7-day average and peak resource utilization.
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta

def get_trends(db_path, days=7):
    if not os.path.exists(db_path):
        return f"Database not found at: {db_path}"

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Calculate time boundary
        time_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute("""
            SELECT metric_type, AVG(value), MAX(value)
            FROM metrics
            WHERE timestamp >= ?
            GROUP BY metric_type
        """, (time_limit,))
        
        rows = cur.fetchall()
        conn.close()
        
        if not rows:
            return "No historical metrics available yet."
            
        lines = [f"📊 Historical Metrics Summary (Last {days} days):"]
        for r in rows:
            m_type, avg_val, max_val = r
            unit = "%" if "percent" in m_type else ""
            lines.append(f"- {m_type}: Average {avg_val:.1f}{unit}, Peak {max_val:.1f}{unit}")
            
        return "\n".join(lines)
    except Exception as e:
        return f"Error collecting trends: {e}"

if __name__ == "__main__":
    db_path = os.environ.get("DB_PATH", "/var/lib/syamadmin/syamadmin.db")
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    print(get_trends(db_path))
