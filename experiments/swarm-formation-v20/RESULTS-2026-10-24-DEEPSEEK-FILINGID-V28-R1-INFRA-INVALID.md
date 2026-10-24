# DeepSeek filing-identity v28 R1: infrastructure-invalid

The campaign ended before any model request. It was launched concurrently with
the paired GLM campaign and could not acquire the collector's global inference
lock:

`BlockingIOError: [Errno 35] Resource temporarily unavailable`

No behavioral conclusion can be drawn from this attempt. Its files are
retained as infrastructure evidence. The campaign was not overwritten or
silently resumed; DeepSeek R2 used a fresh output directory and ran alone.
