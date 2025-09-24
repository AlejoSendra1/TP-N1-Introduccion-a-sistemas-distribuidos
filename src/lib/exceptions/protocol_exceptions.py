class FailedToEstablishSessionException(Exception):
    """Exception raised when a session cannot be established after multiple attempts."""
    def __init__(self, source: str, dest: str):
        super().__init__(f"{source}: Failed to establish session with {dest}.")

class NoActiveSessionException(Exception):
    """Exception raised when there is no active session."""
    def __init__(self, source: str):
        super().__init__(f"{source}: No active session found.")