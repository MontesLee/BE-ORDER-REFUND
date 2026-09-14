"""Order after-sale refund service (golden answer).

Layering
--------
``models``          domain enums / value objects (no I/O)
``state_machine``   allowed status transitions (no I/O)
``repository``      SQLite connection, schema DDL, SQL statements
``service``         business rules + transaction boundaries
``refund_gateway``  third-party refund channel behind a swappable interface
``auth``            caller identity / role checks
``schemas``         request + response models
``main``            FastAPI application and HTTP error mapping
"""

__version__ = "1.0.0"
