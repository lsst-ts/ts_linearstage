from .mock_zaberLST import *
from .mock_igusDryveController import *

try:
    from .version import *
except ImportError:
    __version__ = "?"
