"""Shared helpers: API keys, HTTP, error mapping and source citations."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests
from dotenv import find_dotenv, load_dotenv

USER_AGENT = "kosis-g2b-mcp (+https://github.com/reseacher-J/kosis-g2b-mcp)"
TIMEOUT = 20


def load_env() -> None:
    """Load API keys from a .env file without overriding real environment variables.

    Search order: $KOSIS_G2B_ENV_FILE, the current working directory (upwards),
    then the project root next to ``src/`` (useful for a local clone).
    """
    explicit = os.getenv("KOSIS_G2B_ENV_FILE")
    if explicit:
        load_dotenv(explicit, override=False)
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)
    project_env = Path(__file__).resolve().parents[2] / ".env"
    if project_env.is_file():
        load_dotenv(project_env, override=False)


class ApiError(Exception):
    """An error that should be shown to the model as a readable message."""


def kosis_key() -> str:
    key = os.getenv("KOSIS_API_KEY", "").strip()
    if not key or key.startswith(("your_", "sample_")):
        raise ApiError(
            "KOSIS_API_KEY is not set. Get a free key at https://kosis.kr/openapi/ "
            "and put it in the environment or a .env file. (KOSIS_API_KEY가 없습니다)"
        )
    return key


def data_go_kr_key() -> str:
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key or key.startswith(("your_", "sample_")):
        raise ApiError(
            "DATA_GO_KR_KEY is not set. Get a service key at https://www.data.go.kr/ "
            "(either the Encoding or Decoding key works). (DATA_GO_KR_KEY가 없습니다)"
        )
    # data.go.kr issues an URL-encoded and a decoded key. requests encodes params
    # itself, so an encoded key would be double-encoded (%3D -> %253D) and
    # rejected as "SERVICE_KEY_IS_NOT_REGISTERED". Always pass the decoded form.
    return unquote(key)


def http_get(url: str, params: dict[str, Any]) -> requests.Response:
    try:
        return requests.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.Timeout as e:
        raise ApiError(f"Request timed out after {TIMEOUT}s: {url}") from e
    except requests.RequestException as e:
        raise ApiError(f"Network error calling {url}: {e}") from e


# data.go.kr gateway codes (공공데이터포털 공통 오류 코드)
DATA_GO_KR_ERRORS = {
    "01": "Application error at the provider (제공기관 서비스 오류)",
    "03": "No data for the request (데이터 없음)",
    "07": "Input range exceeded, e.g. the date range is too long (입력범위값 초과)",
    "10": "Invalid request parameter (잘못된 요청 파라미터)",
    "12": "This Open API service does not exist or was retired. Check the endpoint (해당 오픈API 서비스가 없거나 폐기됨)",
    "20": "Service access denied (서비스 접근 거부)",
    "22": "Daily request quota exceeded (일일 트래픽 초과)",
    "30": "Service key not registered for THIS service. Apply for it on data.go.kr "
          "(활용신청), or check that an Encoding key was not double-encoded (등록되지 않은 서비스키)",
    "31": "Service key expired (기한 만료된 서비스키)",
    "32": "Unregistered IP (등록되지 않은 IP)",
}


def data_go_kr_error(code: str | None, msg: str | None) -> ApiError:
    hint = DATA_GO_KR_ERRORS.get(str(code or ""), "")
    return ApiError(f"data.go.kr error {code}: {msg or ''} {('- ' + hint) if hint else ''}".strip())


def today() -> str:
    return date.today().isoformat()
