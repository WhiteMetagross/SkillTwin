class MediaIntelligenceError(RuntimeError):
    """Base class for operational media intelligence failures."""


class RuntimeConfigurationError(MediaIntelligenceError):
    """Raised when required production configuration or binaries are missing."""


class MediaValidationError(MediaIntelligenceError, ValueError):
    """Raised when supplied media violates an input or processing boundary."""


class AudioInspectionError(MediaIntelligenceError):
    """Raised when audio presence or speech cannot be determined truthfully."""


class ObservationProviderError(MediaIntelligenceError):
    """Raised when the production visual observer fails or returns invalid output."""


class StorageError(MediaIntelligenceError):
    """Base class for storage provider failures."""


class StorageNotFoundError(StorageError, FileNotFoundError):
    """Raised when a requested storage object does not exist."""


class StorageAccessDeniedError(StorageError, PermissionError):
    """Raised when the storage provider rejects access."""


class StorageTransientError(StorageError):
    """Raised for throttling and retryable storage provider failures."""


class StorageLimitError(StorageError, ValueError):
    """Raised when an object or staging operation exceeds configured bounds."""


class TranscriptionError(MediaIntelligenceError):
    """Base class for Amazon Transcribe lifecycle failures."""


class TranscriptionJobNotFoundError(TranscriptionError):
    """Raised only when Amazon Transcribe confirms that a job is absent."""


class TranscriptionAccessDeniedError(TranscriptionError, PermissionError):
    """Raised when Amazon Transcribe rejects access."""


class TranscriptionTransientError(TranscriptionError):
    """Raised for throttling and retryable Amazon Transcribe failures."""


class TranscriptionPendingError(TranscriptionError):
    """Raised when a transcription has not reached a terminal state."""


class TranscriptionTimeoutError(TranscriptionPendingError, TimeoutError):
    """Raised when bounded polling expires before a terminal state."""


class TranscriptionFailedError(TranscriptionError):
    """Raised when Amazon Transcribe reports FAILED."""


class TranscriptParseError(TranscriptionError, ValueError):
    """Raised when a completed provider artifact is absent or malformed."""
