"""
Copyright © 2026 Sintela Ltd. All rights reserved.
gRPC client utilities for connecting to Onyx systems.
"""

import grpc


class BearerTokenAuth(grpc.AuthMetadataPlugin):
    """gRPC metadata plugin for bearer token authentication."""

    def __init__(self, token: str):
        self.token = token

    def __call__(self, context, callback):
        metadata = (("authorization", f"Bearer {self.token}"),)
        callback(metadata, None)


def _load_tls_credentials(
    server_cert_path: str | None = None,
) -> grpc.ChannelCredentials:
    """
    Load TLS credentials for a gRPC client.

    Args:
        server_cert_path: Optional path to server CA certificate

    Returns:
        gRPC channel credentials
    """
    # Load server CA certificate if provided
    root_certificates = None
    if server_cert_path:
        with open(server_cert_path, "rb") as f:
            root_certificates = f.read()

    # Create credentials
    # If server_cert_path is provided, use it as root certificate
    # Otherwise, use system CAs (None)
    credentials = grpc.ssl_channel_credentials(
        root_certificates=root_certificates,  # Use provided CA or system CAs
    )

    return credentials


def create_async_client(
    address: str,
    using_tls: bool = True,
    server_cert_path: str | None = None,
    bearer_token: str | None = None,
) -> grpc.aio.Channel:
    """
    Create a new async gRPC client channel.

    Args:
        address: Address including port number to connect to (e.g., "127.0.0.1:8181")
        using_tls: True to use TLS
        server_cert_path: Optional path to server CA certificate
        bearer_token: Optional bearer token for authentication.

    Supported TLS auth modes:
        - TLS with server CA only
        - TLS with server CA + bearer token (no client cert/key required)

    Returns:
        Async gRPC channel
    """
    if using_tls:
        credentials = _load_tls_credentials(
            server_cert_path=server_cert_path,
        )

        if bearer_token:
            call_credentials = grpc.metadata_call_credentials(
                BearerTokenAuth(bearer_token)
            )
            credentials = grpc.composite_channel_credentials(
                credentials, call_credentials
            )

        return grpc.aio.secure_channel(address, credentials)
    return grpc.aio.insecure_channel(address)
