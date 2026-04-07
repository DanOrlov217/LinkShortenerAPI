import hashlib
import base64


def generate_short_url(url: str, length: int = 6) -> str:
    hash_object = hashlib.md5(url.encode())
    hash_bytes = hash_object.digest()
    base64_hash = base64.urlsafe_b64encode(hash_bytes).decode('ascii')
    alias = base64_hash.rstrip('=')[:length]
    return alias