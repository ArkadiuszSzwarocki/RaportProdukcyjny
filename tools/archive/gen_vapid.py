"""One-time VAPID key generator for Web Push."""
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# Generate ECDH P-256 key pair
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

# Serialize private key as raw DER (PKCS8)
private_bytes = private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
private_b64 = base64.urlsafe_b64encode(private_bytes).decode().rstrip('=')

# Serialize public key as uncompressed point (65 bytes)
public_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint
)
public_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip('=')

print("=" * 60)
print("VAPID Keys Generated Successfully")
print("=" * 60)
print(f"\nVAPID_PRIVATE_KEY={private_b64}")
print(f"\nVAPID_PUBLIC_KEY={public_b64}")
print("\n" + "=" * 60)
print("Add the above lines to your .env file!")
print("=" * 60)
