import re
from datetime import datetime, date, time
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    AfterValidator,
    StringConstraints,
    model_validator,
    ConfigDict,
)

# Horas en hora local "ingenua": si llega zona horaria ("10:00:00Z") se ignora
HoraLocal = Annotated[time, AfterValidator(lambda v: v.replace(tzinfo=None))]

OrigenCita = Literal["CLIENTE", "NEGOCIO", "EMPLEADO"]
RolNegocio = Literal["ADMIN", "EMPLEADO"]

# Siempre en minúsculas: el login y los vínculos comparan contra lower(email)
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=150,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


def _normalizar_telefono(valor: str) -> str:
    # '(300) 123-4567' -> '3001234567', para que no haya duplicados disfrazados
    limpio = re.sub(r"[\s\-().]", "", valor)
    if not re.fullmatch(r"\+?\d{7,15}", limpio):
        raise ValueError("Teléfono inválido: usa de 7 a 15 dígitos, con + opcional al inicio")
    return limpio


Telefono = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=30),
    AfterValidator(_normalizar_telefono),
]

# Nombres sin espacios sobrantes: "   " cuenta como vacío y se rechaza
Nombre100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Nombre150 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class _ConRangoDeHoras(BaseModel):
    # Base para todo lo que tenga hora_inicio / hora_fin
    hora_inicio: HoraLocal
    hora_fin: HoraLocal

    @model_validator(mode="after")
    def inicio_antes_que_fin(self):
        if self.hora_inicio >= self.hora_fin:
            raise ValueError("hora_inicio debe ser anterior a hora_fin")
        return self


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class LoginCrear(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)
    negocio_id: int | None = None  # solo si trabaja en varios negocios


# ---------------------------------------------------------------------------
# Negocio
# ---------------------------------------------------------------------------
class NegocioCrear(BaseModel):
    nombre: Nombre150
    telefono: Telefono | None = None
    direccion: str | None = Field(default=None, max_length=250)


class NegocioActualizar(BaseModel):
    nombre: Nombre150
    telefono: Telefono | None = None
    direccion: str | None = Field(default=None, max_length=250)


class NegocioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    telefono: str | None = None
    direccion: str | None = None
    fecha_creacion: datetime


# ---------------------------------------------------------------------------
# Usuario
# ---------------------------------------------------------------------------
class UsuarioCrear(BaseModel):
    nombre: Nombre100
    email: Email
    password: str = Field(min_length=8, max_length=128)  # se hashea antes de guardar


class UsuarioActualizar(BaseModel):
    nombre: Nombre100
    email: Email


class UsuarioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    email: str
    fecha_creacion: datetime


# ---------------------------------------------------------------------------
# UsuarioNegocio
# ---------------------------------------------------------------------------
class UsuarioNegocioCrear(BaseModel):
    # El negocio es el del admin que hace la petición (sale del token)
    email: Email
    rol: RolNegocio


class UsuarioNegocioActualizar(BaseModel):
    rol: RolNegocio


class UsuarioNegocioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    negocio_id: int
    rol: str
    activo: bool
    fecha_asociacion: datetime


# ---------------------------------------------------------------------------
# Cliente
# ---------------------------------------------------------------------------
class ClienteCrear(BaseModel):
    nombre: Nombre100
    telefono: Telefono


class ClienteActualizar(BaseModel):
    nombre: Nombre100
    telefono: Telefono


class ClienteRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    negocio_id: int
    nombre: str
    telefono: str
    fecha_creacion: datetime
    activo: bool


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------
class ServicioCrear(BaseModel):
    nombre: Nombre150
    descripcion: str | None = None
    duracion_minutos: int = Field(gt=0)
    precio: float = Field(ge=0)


class ServicioActualizar(BaseModel):
    nombre: Nombre150
    descripcion: str | None = None
    duracion_minutos: int = Field(gt=0)
    precio: float = Field(ge=0)


class ServicioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    negocio_id: int
    nombre: str
    descripcion: str | None = None
    duracion_minutos: int
    precio: float
    activo: bool
    fecha_creacion: datetime


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------
class ProductoCrear(BaseModel):
    nombre: Nombre150
    descripcion: str | None = None
    precio: float = Field(ge=0)
    stock: int | None = Field(default=None, ge=0)  # None = sin control de inventario


class ProductoActualizar(BaseModel):
    nombre: Nombre150
    descripcion: str | None = None
    precio: float = Field(ge=0)
    stock: int | None = Field(default=None, ge=0)


class ProductoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    negocio_id: int
    nombre: str
    descripcion: str | None = None
    precio: float
    stock: int | None = None
    activo: bool
    fecha_creacion: datetime


# ---------------------------------------------------------------------------
# Cita
# ---------------------------------------------------------------------------
class ServicioEnCita(BaseModel):
    servicio_id: int
    cantidad: int = Field(default=1, gt=0)


class CitaCrear(BaseModel):
    # hora_fin NO se envía: el servidor la calcula con la duración de los servicios.
    # El negocio sale del token. Sin usuario_negocio_id la cita queda para quien
    # la crea (un EMPLEADO solo puede agendar citas para sí mismo).
    cliente_id: int
    usuario_negocio_id: int | None = None
    fecha: date
    hora_inicio: HoraLocal
    servicios: list[ServicioEnCita] = Field(min_length=1)
    origen: OrigenCita = "CLIENTE"
    motivo: str | None = Field(default=None, max_length=255)
    observaciones: str | None = None

    @model_validator(mode="after")
    def sin_servicios_repetidos(self):
        ids = [s.servicio_id for s in self.servicios]
        if len(ids) != len(set(ids)):
            raise ValueError("No repitas un servicio: usa el campo 'cantidad'")
        return self


class CitaActualizar(BaseModel):
    # El estado NO se cambia aquí: usa los PATCH /citas/{id}/confirmar, /cancelar...
    # hora_fin tampoco: depende de los servicios de la cita.
    fecha: date | None = None
    hora_inicio: HoraLocal | None = None
    motivo: str | None = Field(default=None, max_length=255)
    observaciones: str | None = None


class CitaReasignar(BaseModel):
    usuario_negocio_id: int


class CitaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    negocio_id: int
    cliente_id: int
    usuario_negocio_id: int
    fecha: date
    hora_inicio: time
    hora_fin: time
    estado: str
    origen: str
    motivo: str | None = None
    observaciones: str | None = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime


# ---------------------------------------------------------------------------
# ServicioDeCita (tabla servicios_de_cita)
# ---------------------------------------------------------------------------
class ServicioDeCitaAgregar(BaseModel):
    # POST /citas/{cita_id}/servicios. Precio y duración los toma el servidor.
    servicio_id: int
    cantidad: int = Field(default=1, gt=0)


class ServicioDeCitaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cita_id: int
    servicio_id: int
    precio_unitario: float
    duracion_minutos: int
    cantidad: int


# ---------------------------------------------------------------------------
# ProductoDeCita (tabla productos_de_cita)
# ---------------------------------------------------------------------------
class ProductoDeCitaAgregar(BaseModel):
    # POST /citas/{cita_id}/productos. El precio lo toma el servidor.
    producto_id: int
    cantidad: int = Field(gt=0)


class ProductoDeCitaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cita_id: int
    producto_id: int
    cantidad: int
    precio_unitario: float


# ---------------------------------------------------------------------------
# EmpleadoServicio (tabla puente, sin id propio)
# ---------------------------------------------------------------------------
class EmpleadoServicioCrear(BaseModel):
    servicio_id: int
    usuario_negocio_id: int


class EmpleadoServicioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    servicio_id: int
    usuario_negocio_id: int


# ---------------------------------------------------------------------------
# Horario
# ---------------------------------------------------------------------------
class HorarioCrear(_ConRangoDeHoras):
    usuario_negocio_id: int
    dia_semana: int = Field(ge=1, le=7)  # 1 = lunes ... 7 = domingo
    intervalo_minutos: int = Field(default=30, gt=0)


class HorarioActualizar(_ConRangoDeHoras):
    dia_semana: int = Field(ge=1, le=7)
    intervalo_minutos: int = Field(gt=0)


class HorarioRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_negocio_id: int
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    intervalo_minutos: int
    activo: bool


# ---------------------------------------------------------------------------
# Pausa
# ---------------------------------------------------------------------------
class PausaCrear(_ConRangoDeHoras):
    horario_id: int
    motivo: str | None = Field(default=None, max_length=150)


class PausaActualizar(_ConRangoDeHoras):
    motivo: str | None = Field(default=None, max_length=150)


class PausaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    horario_id: int
    hora_inicio: time
    hora_fin: time
    motivo: str | None = None