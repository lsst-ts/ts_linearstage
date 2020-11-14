from .csc import *

try:
    from .version import *
except ImportError:
    __version__ = "?"
