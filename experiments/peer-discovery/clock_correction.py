import json
import time
from pathlib import Path

import psutil


directory = Path('/var/lib/peer-operator')
sample_before = time.time_ns()
boot_clock_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
sample_after = time.time_ns()
epoch_boot_ns = (sample_before + sample_after) // 2 - boot_clock_ns
record = {'sample_before_ns': sample_before, 'sample_after_ns': sample_after, 'boot_clock_ns': boot_clock_ns,
    'psutil_boot_epoch': psutil.boot_time(), 'measured_boot_epoch_ns': epoch_boot_ns,
    'psutil_epoch_correction_seconds': epoch_boot_ns / 1e9 - psutil.boot_time()}
(directory / 'boot-clock-correction.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record))
