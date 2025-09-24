class FailedToEstablishSessionException(Exception):
    """Exception raised when a session cannot be established after multiple attempts."""
    def __init__(self, dest: str):
        super().__init__(f"Failed to establish session with {dest}.")