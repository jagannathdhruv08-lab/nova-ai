# ==========================================
# NOVA SYSTEM HEALTH MONITOR — CPU, RAM, Disk, Battery
# ==========================================
import time
from datetime import datetime


def get_system_health():
    """Get real-time system health metrics using psutil."""
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")

        # Battery (may not exist on desktops)
        battery_info = None
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_info = {
                    "percent": battery.percent,
                    "plugged": battery.power_plugged,
                }
        except Exception:
            pass

        health = {
            "cpu_percent": cpu_percent,
            "ram_percent": ram.percent,
            "ram_used_gb": round(ram.used / (1024 ** 3), 1),
            "ram_total_gb": round(ram.total / (1024 ** 3), 1),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024 ** 3), 1),
            "disk_total_gb": round(disk.total / (1024 ** 3), 1),
            "boot_time": boot_time,
            "battery": battery_info,
        }

        # Build a friendly status message
        status_flags = []
        if cpu_percent > 80:
            status_flags.append("🔥 CPU high")
        if ram.percent > 85:
            status_flags.append("🧠 RAM high")
        if disk.percent > 90:
            status_flags.append("💾 Disk almost full")
        if battery_info and battery_info["percent"] < 20 and not battery_info["plugged"]:
            status_flags.append("🔋 Battery low!")

        if status_flags:
            message = "⚠️ " + " • ".join(status_flags)
        else:
            message = f"✅ System healthy • CPU {cpu_percent}% • RAM {ram.percent}% • Disk {disk.percent}%"

        return {
            "success": True,
            "feature": "system_health",
            "metrics": health,
            "message": message,
            "checked_at": time.strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "system_health",
            "error": str(e),
            "message": f"System health check failed: {str(e)}",
        }


def get_top_processes(n=5):
    """Get top N processes by CPU usage."""
    try:
        import psutil
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                pinfo = proc.info
                if pinfo["cpu_percent"] is not None and pinfo["cpu_percent"] > 0:
                    processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
        top = processes[:n]
        return {
            "success": True,
            "feature": "system_health",
            "top_processes": [
                {
                    "name": p["name"],
                    "pid": p["pid"],
                    "cpu": round(p["cpu_percent"], 1),
                    "memory": round(p["memory_percent"] or 0, 1),
                }
                for p in top
            ],
            "message": f"Top {len(top)} CPU processes",
        }
    except Exception as e:
        return {
            "success": False,
            "feature": "system_health",
            "error": str(e),
            "message": f"Failed to list processes: {str(e)}",
        }


__version__ = "1.0.0"
__all__ = ["get_system_health", "get_top_processes"]
