"""Contract error shape: {"error": {"code": ..., "message": ...}} and the handlers that emit it."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def body(self) -> dict[str, object]:
        return {"error": {"code": self.code, "message": self.message}}


class BadAudio(ApiError):
    status_code = 400
    code = "bad_audio"


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class BadRequest(ApiError):
    status_code = 422
    code = "bad_request"


class RateLimited(ApiError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after_ms: int) -> None:
        super().__init__(message)
        self.retry_after_ms = retry_after_ms

    def body(self) -> dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retry_after_ms": self.retry_after_ms,
            }
        }


class UpstreamError(ApiError):
    status_code = 502
    code = "upstream_error"


async def _api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(status_code=exc.status_code, content=exc.body())


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = sorted({str(err["loc"][-1]) for err in exc.errors() if err.get("loc")})
    message = f"Missing or invalid field: {', '.join(fields)}." if fields else "Invalid request."
    return JSONResponse(status_code=422, content=BadRequest(message).body())


def install_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
