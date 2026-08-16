"""Generate VAPID keys once, then save them as host environment variables."""

import base64
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat
from py_vapid import Vapid


def main():
    vapid = Vapid()
    vapid.generate_keys()
    public_key = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    private_key = vapid.private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    print("VAPID_PUBLIC_KEY=" + base64.urlsafe_b64encode(public_key).decode().rstrip("="))
    print("VAPID_PRIVATE_KEY=" + base64.urlsafe_b64encode(private_key).decode().rstrip("="))


if __name__ == "__main__":
    main()
