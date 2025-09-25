class FailedToEstablishSessionException(Exception):
    """Exception raised when a session cannot be established after multiple attempts."""
    def __init__(self, source: str, dest: str):
        super().__init__(f"{source}: Failed to establish session with {dest}.")

class NoActiveSessionException(Exception):
    """Exception raised when there is no active session."""
    def __init__(self, source: str):
        super().__init__(f"{source}: No active session found.")

class PacketSendFailureException(Exception):
    """Raised when a packet cannot be sent after maximum retries."""
    def __init__(self, seq_num, source: str, message=None):
        if message is None:
            message = f"{source}: Failed to send packet {seq_num} after maximum retries."
        super().__init__(message)

class FinSessionFailureException(Exception):
    """Raised when FIN handshake fails after maximum retries."""
    def __init__(self, source: str, session_id: str, message=None):
        if message is None:
            message = f"{source}: Failed to close session with FIN (session_id={session_id}) after maximum retries."
        super().__init__(message)