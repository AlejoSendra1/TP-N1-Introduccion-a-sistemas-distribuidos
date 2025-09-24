class ShutdownRequestException(Exception):
    """Exception raised when a shutdown request is received."""

    def __init__(self, message="A shutdown request was received."):
        super().__init__(message)