#pip install PyJWT

"""
Autenticación (JWT) y contexto del negocio activo.

Instalar:  pip install PyJWT

Variable de entorno OBLIGATORIA: VALEN_SECRET_KEY  (mínimo 32 caracteres).
Generar una:   python -c "import secrets; print(secrets.token_hex(32))"
En PowerShell: $env:VALEN_SECRET_KEY = "<la clave generada>"

Cómo funciona con varios negocios:
  * El token identifica al USUARIO y, opcionalmente, al negocio con el que está
    trabajando (campo "un" = id de su fila en usuario_negocio).
  * Rol y negocio NO se leen del token: en cada petición se vuelven a leer de
    la base de datos. Así, si un admin desvincula a alguien o le cambia el rol,
    el efecto es inmediato aunque su token siga vigente.

Tres niveles de acceso (dependencias para usar en los endpoints):
  contexto_usuario  -> cualquier usuario con token válido (aún sin negocio)
  contexto_negocio  -> usuario con un negocio elegido y vínculo activo
  solo_admin        -> lo anterior, y además con rol ADMIN en ese negocio
"""
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import SessionLocal
from models import Usuario, UsuarioNegocio

SECRET_KEY = os.getenv("VALEN_SECRET_KEY")

if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise RuntimeError(
        "Falta la variable de entorno VALEN_SECRET_KEY (mínimo 32 caracteres). "
        'Genera una con: python -c "import secrets; print(secrets.token_hex(32))" '
        'y en PowerShell defínela con: $env:VALEN_SECRET_KEY = "<la clave>"'
    )

ALGORITMO = "HS256"
DURACION_TOKEN_MINUTOS = 8 * 60  # 8 horas

# auto_error=False para responder nosotros con mensajes en español.
# HTTPBearer hace que en /docs el botón "Authorize" pida pegar el token.
_esquema_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Contexto:
    """Quién es el usuario que hace la petición y con qué negocio/rol."""
    usuario_id: int
    usuario_negocio_id: int | None = None
    negocio_id: int | None = None
    rol: str | None = None

    @property
    def es_admin(self) -> bool:
        return self.rol == "ADMIN"


def _no_autenticado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def crear_token(usuario_id: int, usuario_negocio_id: int | None = None) -> str:
    ahora = datetime.now(timezone.utc)

    carga = {
        "sub": str(usuario_id),          # PyJWT exige que "sub" sea texto
        "un": usuario_negocio_id,        # None = todavía sin negocio elegido
        "iat": ahora,
        "exp": ahora + timedelta(minutes=DURACION_TOKEN_MINUTOS),
    }

    return jwt.encode(carga, SECRET_KEY, algorithm=ALGORITMO)


def _leer_token(credenciales: HTTPAuthorizationCredentials | None) -> dict:
    if credenciales is None or not credenciales.credentials:
        raise _no_autenticado("Falta el token. Inicia sesión en POST /auth/login")

    try:
        return jwt.decode(credenciales.credentials, SECRET_KEY, algorithms=[ALGORITMO])
    except jwt.ExpiredSignatureError:
        raise _no_autenticado("La sesión expiró. Inicia sesión de nuevo")
    except jwt.InvalidTokenError:
        raise _no_autenticado("Token inválido")


def contexto_usuario(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_esquema_bearer),
) -> Contexto:
    """Token válido y usuario existente. El negocio es opcional."""
    datos = _leer_token(credenciales)

    try:
        usuario_id = int(datos["sub"])
    except (KeyError, TypeError, ValueError):
        raise _no_autenticado("Token inválido")

    usuario_negocio_id = datos.get("un")

    db = SessionLocal()

    try:
        if db.get(Usuario, usuario_id) is None:
            raise _no_autenticado("El usuario ya no existe")

        if usuario_negocio_id is None:
            return Contexto(usuario_id=usuario_id)

        vinculo = db.get(UsuarioNegocio, usuario_negocio_id)

        if vinculo is None or vinculo.usuario_id != usuario_id or not vinculo.activo:
            raise _no_autenticado(
                "Tu acceso a ese negocio ya no es válido. Inicia sesión de nuevo"
            )

        # Rol y negocio salen de la base de datos, no del token
        return Contexto(
            usuario_id=usuario_id,
            usuario_negocio_id=vinculo.id,
            negocio_id=vinculo.negocio_id,
            rol=vinculo.rol,
        )

    finally:
        db.close()


def contexto_negocio(ctx: Contexto = Depends(contexto_usuario)) -> Contexto:
    """Exige haber elegido un negocio."""
    if ctx.negocio_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Primero elige un negocio: POST /auth/negocio/{negocio_id} "
                "(o inicia sesión indicando negocio_id)"
            ),
        )

    return ctx


def solo_admin(ctx: Contexto = Depends(contexto_negocio)) -> Contexto:
    """Exige además rol ADMIN en el negocio elegido."""
    if not ctx.es_admin:
        raise HTTPException(
            status_code=403,
            detail="Esta acción es solo para administradores del negocio",
        )

    return ctx