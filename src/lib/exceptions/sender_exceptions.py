class EmptyFileException(Exception):
    """Exception raised when a user tries to insert an empty file."""
    def __init__(self, message="The file is empty."):
        super().__init__(message)

class InvalidFileException(Exception):
    """Exception raised when the source file does not exist or cannot be read."""
    def __init__(self, message="The source file does not exist or cannot be read."):
        super().__init__(message)