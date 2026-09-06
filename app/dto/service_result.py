from typing import Any, Optional, Dict, List
from dataclasses import dataclass

@dataclass
class ServiceResult:
    """
    Standardized Data Transfer Object (DTO) for Service Layer responses.
    Guarantees consistent contracts across all services (WMS, MES, ERP).
    Provides factory methods, dictionary conversion, and tuple-unpacking for 100% backwards compatibility.
    """
    success: bool
    message: str = ""
    data: Optional[Any] = None
    error_code: Optional[str] = None
    errors: Optional[List[str]] = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "Operacja zakończona sukcesem.") -> 'ServiceResult':
        """Factory for successful service results."""
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, message: str = "Wystąpił błąd operacji.", error_code: Optional[str] = None, data: Any = None, errors: Optional[List[str]] = None) -> 'ServiceResult':
        """Factory for failed service results."""
        return cls(success=False, message=message, error_code=error_code, data=data, errors=errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to clean dictionary for Flask jsonify responses."""
        res = {
            "success": self.success,
            "message": self.message,
            "data": self.data
        }
        if self.error_code:
            res["error_code"] = self.error_code
        if self.errors:
            res["errors"] = self.errors
        return res

    def __iter__(self):
        """Enable tuple unpacking: success, msg, data = result (backwards compatibility)."""
        yield self.success
        yield self.message
        yield self.data

    def __bool__(self) -> bool:
        """Allow evaluating result directly in if-statements: if result: ..."""
        return self.success
