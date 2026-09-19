import uuid

from sqlalchemy import BINARY
from sqlalchemy.types import TypeDecorator

# Python 3.14 added uuid7. Fall back to uuid4 so the code still runs
# on older interpreters, just with a less index-friendly ID.
try:
    from uuid import uuid7 as _generate
except ImportError:  # pragma: no cover
    from uuid import uuid4 as _generate


def new_uuid() -> uuid.UUID:
    """Default for Request.id. Passed as a function, never called here."""
    return _generate()


class UUIDBinary(TypeDecorator):
    """Stores uuid.UUID as BINARY(16). Python never sees the bytes."""

    impl = BINARY(16)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Python -> database."""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value.bytes
        return uuid.UUID(str(value)).bytes

    def process_result_value(self, value, dialect):
        """Database -> Python."""
        if value is None:
            return None
        return uuid.UUID(bytes=value)