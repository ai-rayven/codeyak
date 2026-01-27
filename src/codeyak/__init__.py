"""CodeYak - AI-powered code review tool."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("codeyak")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"
