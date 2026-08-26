class XrplError(RuntimeError):
    """Base error presented by the XRPL command-line interface."""


class ConfigError(XrplError):
    """Invalid or incomplete project configuration."""


class DockerError(XrplError):
    """Failure while interacting with Docker."""


class ReconcileError(XrplError):
    """An existing chain cannot be safely reconciled with its declaration."""


class FundingError(XrplError):
    """A relayer funding transaction could not be completed."""


class HealthError(XrplError):
    """A chain did not become healthy within the expected time."""
