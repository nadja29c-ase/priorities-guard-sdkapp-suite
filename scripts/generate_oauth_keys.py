#!/usr/bin/env python3
"""
Generate RSA-2048 key pair for OAuth provider.

Usage:
    python scripts/generate_oauth_keys.py

Outputs environment variables to copy into .env file.
"""

import base64
import secrets
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def generate_oauth_keys():
    """Generate RSA-2048 key pair and output as base64-encoded environment variables."""
    print("Generating RSA-2048 key pair for OAuth provider...")
    print()

    # Generate RSA-2048 key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()

    # Serialize private key to PEM format (no encryption)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key to PEM format
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Base64 encode for safe environment variable storage
    private_b64 = base64.b64encode(private_pem).decode('ascii')
    public_b64 = base64.b64encode(public_pem).decode('ascii')

    # Generate kid with current year-month
    current_ym = datetime.now().strftime("%Y-%m")
    kid = f"focused-{current_ym}"

    print("=" * 80)
    print("OAuth RSA Keys Generated Successfully")
    print("=" * 80)
    print()
    print("Copy the following lines to your .env file:")
    print()
    print("# OAuth Provider Settings")
    print(f"OAUTH_RSA_PRIVATE_KEY={private_b64}")
    print(f"OAUTH_RSA_PUBLIC_KEY={public_b64}")
    print(f"OAUTH_JWT_KID={kid}")
    print(f"OAUTH_ISSUER=https://www.priority-guard.com")
    print()

    # Generate internal API secret for MCP -> backend communication
    internal_secret = secrets.token_urlsafe(32)
    print("# Internal API Secret (MCP server -> backend authentication)")
    print(f"INTERNAL_API_SECRET={internal_secret}")
    print()

    print("=" * 80)
    print("IMPORTANT:")
    print("- Keep OAUTH_RSA_PRIVATE_KEY and INTERNAL_API_SECRET secret")
    print("- INTERNAL_API_SECRET must be the same in backend and MCP server")
    print("- Never commit .env to version control")
    print("- For dev environment, override OAUTH_ISSUER to http://localhost:8000")
    print("=" * 80)


if __name__ == "__main__":
    generate_oauth_keys()
