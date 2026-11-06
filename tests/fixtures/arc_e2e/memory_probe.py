"""Optional read-only Linux process/cgroup telemetry; no dependencies or host access."""
from pathlib import Path

COUNTERS={
 '/sys/fs/cgroup/memory.current':'cgroup_v2_current_bytes',
 '/sys/fs/cgroup/memory.peak':'cgroup_v2_peak_bytes',
 '/sys/fs/cgroup/memory.max':'cgroup_v2_limit_bytes',
 '/sys/fs/cgroup/memory/memory.usage_in_bytes':'cgroup_v1_current_bytes',
 '/sys/fs/cgroup/memory/memory.max_usage_in_bytes':'cgroup_v1_peak_bytes',
 '/sys/fs/cgroup/memory/memory.limit_in_bytes':'cgroup_v1_limit_bytes'}

def snapshot(read=None):
    if read is None:read=lambda p:Path(p).read_text()
    out={}
    try:
        for line in read('/proc/self/status').splitlines():
            if line.startswith(('VmRSS:','VmHWM:')):
                key='rss_bytes' if line.startswith('VmRSS:') else 'rss_peak_bytes'
                out[key]=int(line.split()[1])*1024
    except (OSError,ValueError,IndexError):pass
    for path,key in COUNTERS.items():
        try:
            value=read(path).strip();out[key]=int(value) if value.isdigit() else value
        except OSError:pass
    return out
