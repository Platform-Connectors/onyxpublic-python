"""Tests for onyxpublic client."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from onyxpublic.client import (
    BearerTokenAuth,
    _load_tls_credentials,
    create_async_client,
)


@pytest.mark.parametrize(
    ("token", "expected_metadata"),
    [
        ("test-token", (("authorization", "Bearer test-token"),)),
        ("   ", (("authorization", "Bearer    "),)),
    ],
)
def test_bearer_token_auth_call(
    token: str, expected_metadata: tuple[tuple[str, str], ...]
) -> None:
    """BearerTokenAuth should forward token content unchanged into authorization metadata."""
    auth = BearerTokenAuth(token)
    context = MagicMock()
    callback = MagicMock()

    auth(context, callback)

    callback.assert_called_once_with(expected_metadata, None)


@pytest.mark.parametrize(
    ("cert_path", "read_data", "expected_root_certificates"),
    [
        (None, None, None),
        ("certs/ca.crt", b"fake-cert-content", b"fake-cert-content"),
    ],
)
def test_load_tls_credentials(
    cert_path: str | None,
    read_data: bytes | None,
    expected_root_certificates: bytes | None,
) -> None:
    """_load_tls_credentials should use system CAs or provided CA bytes based on cert_path."""
    if cert_path is None:
        with patch("grpc.ssl_channel_credentials") as mock_ssl:
            _load_tls_credentials(cert_path)
            mock_ssl.assert_called_once_with(
                root_certificates=expected_root_certificates
            )
        return

    with patch("builtins.open", mock_open(read_data=read_data)):
        with patch("grpc.ssl_channel_credentials") as mock_ssl:
            _load_tls_credentials(cert_path)
            mock_ssl.assert_called_once_with(
                root_certificates=expected_root_certificates
            )


def test_create_async_client_insecure():
    """Verify that create_async_client correctly initializes an insecure gRPC channel."""
    address = "127.0.0.1:8181"
    with patch("grpc.aio.insecure_channel") as mock_insecure:
        create_async_client(address, using_tls=False, bearer_token="secret-token")
        mock_insecure.assert_called_once_with(address)


def test_create_async_client_secure_with_token():
    """Verify that create_async_client initializes a secure channel with composite bearer token credentials."""
    address = "127.0.0.1:8181"
    token = "secret-token"
    with patch("grpc.ssl_channel_credentials"):
        with patch("grpc.metadata_call_credentials") as mock_meta:
            with patch("grpc.composite_channel_credentials") as mock_composite:
                with patch("grpc.aio.secure_channel") as mock_secure:
                    create_async_client(address, using_tls=True, bearer_token=token)

                    mock_meta.assert_called_once()
                    mock_composite.assert_called_once()
                    mock_secure.assert_called_once()
