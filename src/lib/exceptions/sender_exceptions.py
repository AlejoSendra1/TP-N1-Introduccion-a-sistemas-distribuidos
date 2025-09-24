class EmptyFileException(Exception):
    """Exception raised when a user tries to insert an empty file."""
    def __init__(self, message="El archivo está vacío."):
        super().__init__(message)

class InvalidFileException(Exception):
    """Exception raised when the source file does not exist or cannot be read."""
    def __init__(self, message="El archivo fuente no existe o no se puede leer."):
        super().__init__(message)