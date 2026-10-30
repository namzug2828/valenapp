"""
Contraseñas: nunca se guardan en texto plano, solo su hash (argon2).

Instalar:  pip install argon2-cffi
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()

# Hash de relleno: el login lo verifica aunque el email no exista, para que
# "email inexistente" no responda más rápido que "contraseña incorrecta" y
# nadie pueda averiguar qué emails están registrados midiendo tiempos.
HASH_DE_RELLENO = _hasher.hash("contraseña-de-relleno")


def hashear_password(password: str) -> str:
    """Devuelve el hash que se guarda en usuario.password_hash."""
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    """
    True si la contraseña coincide con el hash guardado. Se usará en el login.
    Un hash con formato inválido (por ejemplo, usuarios viejos que quedaron con
    la contraseña en texto plano) devuelve False en vez de lanzar un error.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, ValueError):
        return False