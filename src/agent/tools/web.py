"""
Web tools for agent system.

Provides HTTP request capabilities with proper security constraints.
All tools follow FAANG principal engineer quality standards.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Annotated

from pydantic import Field


_SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}
_MAX_BODY_LENGTH = 10000
_ALLOWED_METHODS = {"GET", "POST"}


def create_http_request_tool() -> Callable[..., str]:
    """
    Create tool for making HTTP requests.

    Returns:
        Callable that performs HTTP requests and returns formatted responses.
    """

    def http_request(
        url: Annotated[str, Field(description="URL to request")],
        method: Annotated[
            str, Field(description="HTTP method (GET or POST)")
        ] = "GET",
        body: Annotated[
            str | None, Field(description="Request body (for POST)")
        ] = None,
        headers: Annotated[
            dict[str, str] | None,
            Field(description="Request headers (Authorization, Cookie, X-Api-Key blocked)"),
        ] = None,
        timeout: Annotated[
            int, Field(description="Request timeout in seconds", gt=0, le=60)
        ] = 30,
    ) -> str:
        """
        Make an HTTP request and return the response.

        Args:
            url: URL to request.
            method: HTTP method (only GET and POST allowed).
            body: Optional request body for POST requests.
            headers: Optional request headers (sensitive headers blocked).
            timeout: Request timeout in seconds (max 60).

        Returns:
            Formatted response with status, headers, and body, or error message.
        """
        # Validate method
        method_upper = method.upper()
        if method_upper not in _ALLOWED_METHODS:
            return f"❌ Error: Only GET and POST methods are allowed"

        # Validate headers for sensitive keys
        if headers:
            for key in headers:
                if key.lower() in _SENSITIVE_HEADERS:
                    return f"❌ Error: Sensitive headers (Authorization, Cookie, X-Api-Key) are not allowed"

        try:
            # Build request
            data = body.encode("utf-8") if body else None
            req = urllib.request.Request(url, data=data, method=method_upper)

            if headers:
                for key, value in headers.items():
                    req.add_header(key, value)

            # Execute request
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.status
                resp_headers = response.headers

                # Read body
                raw_body = response.read().decode("utf-8", errors="replace")

                # Truncate body if needed
                if len(raw_body) > _MAX_BODY_LENGTH:
                    raw_body = (
                        raw_body[:_MAX_BODY_LENGTH]
                        + f"\n\n[Body truncated at {_MAX_BODY_LENGTH:,} characters]"
                    )

                # Format selected headers
                header_lines: list[str] = []
                for h in ("content-type", "content-length"):
                    value = resp_headers.get(h)
                    if value:
                        header_lines.append(f"  {h}: {value}")

                headers_str = "\n".join(header_lines) if header_lines else "  (none)"

                return f"HTTP {status_code}\n\nHeaders:\n{headers_str}\n\nBody:\n{raw_body}"

        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
                if len(body_text) > _MAX_BODY_LENGTH:
                    body_text = body_text[:_MAX_BODY_LENGTH]
            except Exception:
                pass
            return f"HTTP {e.code}\n\nHeaders:\n  (error response)\n\nBody:\n{body_text}"
        except urllib.error.URLError as e:
            return f"❌ Error: {str(e.reason)}"
        except TimeoutError:
            return f"❌ Error: Request timed out after {timeout} seconds"
        except ValueError as e:
            return f"❌ Error: Invalid URL: {str(e)}"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    return http_request
