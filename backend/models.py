from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Negocio(Base):
    __tablename__ = "negocio"

    id = Column(BigInteger, primary_key=True)
    nombre = Column(String(150), nullable=False)
    telefono = Column(String(30), nullable=True)
    direccion = Column(String(250), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

    servicios = relationship("Servicio", back_populates="negocio")
    clientes = relationship("Cliente", back_populates="negocio")
    productos = relationship("Producto", back_populates="negocio")
    citas = relationship("Cita", back_populates="negocio")
    usuarios_negocio = relationship("UsuarioNegocio", back_populates="negocio")


class Usuario(Base):
    __tablename__ = "usuario"

    id = Column(BigInteger, primary_key=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.now)

    negocios = relationship("UsuarioNegocio", back_populates="usuario")


class UsuarioNegocio(Base):
    __tablename__ = "usuario_negocio"

    __table_args__ = (
        CheckConstraint(
            "rol IN ('ADMIN', 'EMPLEADO')",
            name="chk_usuario_negocio_rol"
        ),
    )

    id = Column(BigInteger, primary_key=True)
    usuario_id = Column(BigInteger, ForeignKey("usuario.id"), nullable=False)
    negocio_id = Column(BigInteger, ForeignKey("negocio.id"), nullable=False)
    rol = Column(String(20), nullable=False)

    activo = Column(Boolean, nullable=False, default=True)

    fecha_asociacion = Column(DateTime, default=datetime.now)

    usuario = relationship("Usuario", back_populates="negocios")
    negocio = relationship("Negocio", back_populates="usuarios_negocio")
    citas = relationship("Cita", back_populates="usuario_negocio")
    horarios = relationship("Horario", back_populates="usuario_negocio")
    servicios_asignados = relationship(
        "EmpleadoServicio",
        back_populates="usuario_negocio"
    )


class Cliente(Base):
    __tablename__ = "cliente"
    __table_args__ = (
        # UNIQUE (negocio_id, telefono)
    )

    id = Column(BigInteger, primary_key=True)
    negocio_id = Column(BigInteger, ForeignKey("negocio.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    telefono = Column(String(30), nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.now)
    activo = Column(Boolean, nullable=False, default=True)

    negocio = relationship("Negocio", back_populates="clientes")
    citas = relationship("Cita", back_populates="cliente")


class Servicio(Base):
    __tablename__ = "servicio"
    __table_args__ = (
        CheckConstraint("duracion_minutos > 0", name="chk_servicio_duracion"),
        CheckConstraint("precio >= 0", name="chk_servicio_precio"),
    )

    id = Column(BigInteger, primary_key=True)
    negocio_id = Column(BigInteger, ForeignKey("negocio.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    duracion_minutos = Column(Integer, nullable=False)
    precio = Column(Numeric(12, 2), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

    negocio = relationship("Negocio", back_populates="servicios")
    empleados = relationship("EmpleadoServicio", back_populates="servicio")
    citas_asociadas = relationship("ServicioDeCita", back_populates="servicio")


class Producto(Base):
    __tablename__ = "producto"
    __table_args__ = (
        CheckConstraint("precio >= 0", name="chk_producto_precio"),
        CheckConstraint("stock IS NULL OR stock >= 0", name="chk_producto_stock"),
    )

    id = Column(BigInteger, primary_key=True)
    negocio_id = Column(BigInteger, ForeignKey("negocio.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    precio = Column(Numeric(12, 2), nullable=False)
    stock = Column(Integer, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime, default=datetime.now)

    negocio = relationship("Negocio", back_populates="productos")
    citas_asociadas = relationship("ProductoDeCita", back_populates="producto")


class Cita(Base):
    __tablename__ = "cita"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('PENDIENTE', 'CONFIRMADA', 'CANCELADA', 'COMPLETADA', 'NO_ASISTIO')",
            name="chk_cita_estado",
        ),
        CheckConstraint(
            "origen IN ('CLIENTE', 'NEGOCIO', 'EMPLEADO')", name="chk_cita_origen"
        ),
        CheckConstraint("hora_inicio < hora_fin", name="chk_cita_horas"),
    )

    id = Column(BigInteger, primary_key=True)
    negocio_id = Column(BigInteger, ForeignKey("negocio.id"), nullable=False)
    cliente_id = Column(BigInteger, ForeignKey("cliente.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    estado = Column(String(20), nullable=False, default="PENDIENTE")
    origen = Column(String(20), nullable=False, default="CLIENTE")
    motivo = Column(String(255), nullable=True)
    observaciones = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now)
    fecha_actualizacion = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    usuario_negocio_id = Column(BigInteger, ForeignKey("usuario_negocio.id"), nullable=False)

    negocio = relationship("Negocio", back_populates="citas")
    cliente = relationship("Cliente", back_populates="citas")
    usuario_negocio = relationship("UsuarioNegocio", back_populates="citas")
    servicios = relationship(
        "ServicioDeCita", back_populates="cita", cascade="all, delete-orphan"
    )
    productos = relationship(
        "ProductoDeCita", back_populates="cita", cascade="all, delete-orphan"
    )


class ServicioDeCita(Base):
    __tablename__ = "servicios_de_cita"

    __table_args__ = (
        CheckConstraint(
            "duracion_minutos > 0",
            name="chk_servicios_cita_duracion"
        ),
        CheckConstraint(
            "precio_unitario >= 0",
            name="chk_servicios_cita_precio"
        ),
        CheckConstraint(
            "cantidad > 0",
            name="chk_servicios_cita_cantidad"
        ),
    )

    id = Column(BigInteger, primary_key=True)

    cita_id = Column(
        BigInteger,
        ForeignKey("cita.id", ondelete="CASCADE"),
        nullable=False
    )

    servicio_id = Column(
        BigInteger,
        ForeignKey("servicio.id"),
        nullable=False
    )

    precio_unitario = Column(Numeric(12, 2), nullable=False)
    duracion_minutos = Column(Integer, nullable=False)
    cantidad = Column(Integer, nullable=False)

    cita = relationship("Cita", back_populates="servicios")
    servicio = relationship("Servicio", back_populates="citas_asociadas")


class ProductoDeCita(Base):
    __tablename__ = "productos_de_cita"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="chk_productos_cita_cantidad"),
        CheckConstraint("precio_unitario >= 0", name="chk_productos_cita_precio"),
    )

    id = Column(BigInteger, primary_key=True)
    cita_id = Column(BigInteger, ForeignKey("cita.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(BigInteger, ForeignKey("producto.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(12, 2), nullable=False)

    cita = relationship("Cita", back_populates="productos")
    producto = relationship("Producto", back_populates="citas_asociadas")


class EmpleadoServicio(Base):
    """
    OJO: en el dump esta tabla NO tiene primary key propia, solo las dos FKs
    (servicio_id, usuario_negocio_id). SQLAlchemy exige al menos una PK para
    mapear la clase, así que aquí se declara una clave primaria compuesta con
    esas mismas columnas. Esto es válido siempre que la combinación sea única
    en la práctica; si quieres que quede reflejado también en la base de
    datos, te conviene agregar la constraint real con una migración:
        ALTER TABLE empleado_servicio
            ADD CONSTRAINT empleado_servicio_pkey PRIMARY KEY (servicio_id, usuario_negocio_id);
    """

    __tablename__ = "empleado_servicio"

    servicio_id = Column(
        BigInteger, ForeignKey("servicio.id", ondelete="CASCADE"), primary_key=True
    )
    usuario_negocio_id = Column(
        BigInteger, ForeignKey("usuario_negocio.id"), primary_key=True
    )

    servicio = relationship("Servicio", back_populates="empleados")
    usuario_negocio = relationship("UsuarioNegocio", back_populates="servicios_asignados")


class Horario(Base):
    __tablename__ = "horario"
    __table_args__ = (
        CheckConstraint("dia_semana >= 1 AND dia_semana <= 7", name="chk_horario_dia"),
        CheckConstraint("hora_inicio < hora_fin", name="chk_horario_horas"),
        CheckConstraint("intervalo_minutos > 0", name="chk_horario_intervalo"),
    )

    id = Column(BigInteger, primary_key=True)
    dia_semana = Column(SmallInteger, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    intervalo_minutos = Column(Integer, nullable=False, default=30)
    activo = Column(Boolean, nullable=False, default=True)
    usuario_negocio_id = Column(BigInteger, ForeignKey("usuario_negocio.id"), nullable=False)

    usuario_negocio = relationship("UsuarioNegocio", back_populates="horarios")
    pausas = relationship("Pausa", back_populates="horario", cascade="all, delete-orphan")


class Pausa(Base):
    __tablename__ = "pausa"
    __table_args__ = (
        CheckConstraint("hora_inicio < hora_fin", name="chk_pausa_horas"),
    )

    id = Column(BigInteger, primary_key=True)
    horario_id = Column(BigInteger, ForeignKey("horario.id", ondelete="CASCADE"), nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)
    motivo = Column(String(150), nullable=True)

    horario = relationship("Horario", back_populates="pausas")