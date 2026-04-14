"""Tests for onyxpublic client."""

from unittest.mock import MagicMock, mock_open, patch

from onyxpublic.client import (
    BearerTokenAuth,
    _load_tls_credentials,
    create_async_client,
)


def test_bearer_token_auth_call():
    """Verify that BearerTokenAuth correctly formats and returns the authorization metadata."""
    token = "test-token"
    auth = BearerTokenAuth(token)
    context = MagicMock()
    callback = MagicMock()

    auth(context, callback)

    expected_metadata = (("authorization", f"Bearer {token}"),)
    callback.assert_called_once_with(expected_metadata, None)


def test_load_tls_credentials_no_path():
    """Verify that _load_tls_credentials uses default system CAs when no path is provided."""
    with patch("grpc.ssl_channel_credentials") as mock_ssl:
        _load_tls_credentials()
        mock_ssl.assert_called_once_with(root_certificates=None)


def test_load_tls_credentials_with_path():
    """Verify that _load_tls_credentials reads and uses the provided server CA certificate file."""
    cert_path = "certs/ca.crt"
    cert_content = b"fake-cert-content"

    with patch("builtins.open", mock_open(read_data=cert_content)):
        with patch("grpc.ssl_channel_credentials") as mock_ssl:
            _load_tls_credentials(cert_path)
            mock_ssl.assert_called_once_with(root_certificates=cert_content)


def test_create_async_client_insecure():
    """Verify that create_async_client correctly initializes an insecure gRPC channel."""
    address = "127.0.0.1:8181"
    with patch("grpc.aio.insecure_channel") as mock_insecure:
        create_async_client(address, using_tls=False)
        mock_insecure.assert_called_once_with(address)


def test_create_async_client_secure_no_token():
    """Verify that create_async_client initializes a secure channel without extra credentials."""
    address = "127.0.0.1:8181"
    with patch("grpc.ssl_channel_credentials") as mock_ssl:
        with patch("grpc.aio.secure_channel") as mock_secure:
            create_async_client(address, using_tls=True)
            mock_secure.assert_called_once()
            args, _ = mock_secure.call_args
            assert args[0] == address


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
