import random
import time


def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0):
    """
    Sleep for random time to make automation less robotic.
    """
    time.sleep(random.uniform(min_seconds, max_seconds))


def small_pause():
    """
    Small human-like pause.
    """
    random_delay(0.5, 1.5)


def medium_pause():
    """
    Medium human-like pause.
    """
    random_delay(1.5, 3.0)