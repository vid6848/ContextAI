"""Print a VAPID key pair for Web Push, ready to paste into your host's secrets.

    python -m scripts.generate_vapid_keys

Set them as VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY so browser push subscriptions keep working across
redeploys (otherwise the server generates new keys on each fresh container and old subscriptions break).
"""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def main() -> None:
    vapid = Vapid01()
    vapid.generate_keys()
    public = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    private_pem = vapid.private_pem().decode().strip().replace("\n", "\\n")
    print(f"VAPID_PUBLIC_KEY={base64.urlsafe_b64encode(public).rstrip(b'=').decode()}")
    print(f"VAPID_PRIVATE_KEY={private_pem}")


if __name__ == "__main__":
    main()
