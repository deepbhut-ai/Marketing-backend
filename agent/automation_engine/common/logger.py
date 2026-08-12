import sys
import io

DEBUG = False

# Force UTF-8 output to avoid cp1252 crashes on Windows with emoji.
# Wrap both sys.stdout and sys.__stdout__ so emoji never crashes.
if sys.platform == "win32":
    for _stream_attr in ("stdout", "__stdout__"):
        try:
            _stream = getattr(sys, _stream_attr)
            if _stream is not None and hasattr(_stream, "buffer"):
                setattr(sys, _stream_attr, io.TextIOWrapper(
                    _stream.buffer, encoding="utf-8", errors="replace"
                ))
        except Exception:
            pass


def clean_log(message):
    """
    User-visible clean terminal log.
    Always visible, even when automation output is hidden.
    """
    try:
        sys.__stdout__.write(str(message) + "\n")
        sys.__stdout__.flush()
    except Exception:
        pass


def debug_log(message):
    """
    Developer/debug log.
    Only visible when DEBUG = True.
    """
    if DEBUG:
        try:
            sys.__stdout__.write(str(message) + "\n")
            sys.__stdout__.flush()
        except Exception:
            pass