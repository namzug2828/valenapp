"""
Agenda para el calendario (lo que el front necesita para pintar y para agendar).

  GET /citas                 citas del negocio con cliente, empleado, servicios y totales,
                             filtrables por fechas, empleado, cliente y estado
  GET /citas/{cita_id}       la misma estructura para una sola cita
  GET /disponibilidad        horas libres de un empleado para uno o varios servicios en una fecha

La disponibilidad usa EXACTAMENTE las mismas reglas que al crear una cita
(reglas._buscar_hueco para horarios y pausas, y la misma definición de solape),
así que una hora que aquí aparece como libre se puede reservar. La única
diferencia posible es una carrera: otra persona la puede tomar justo antes.
Esa carrera la resuelve el bloqueo del empleado y las restricciones de la base
de datos al crear la cita.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

import reglas
from auth import Contexto, contexto_negocio
from database import SessionLocal
from models import Cita, Horario, ServicioDeCita, ProductoDeCita, UsuarioNegocio
from reglas import (
    _buscar_hueco,
    exigir_empleado_valido,
    exigir_servicio_para_empleado,
    obtener_del_negocio,
    se_superponen,
)

router = APIRouter()

EstadoCita = Literal["PENDIENTE", "CONFIRMADA", "CANCELADA", "COMPLETADA", "NO_ASISTIO"]

# Para que una consulta no pueda traerse media base de datos de un golpe
DIAS_MAXIMOS_POR_CONSULTA = 92
DIAS_POR_DEFECTO = 30


# ---------------------------------------------------------------------------
# Una sola forma de representar una cita (listado y detalle)
# ---------------------------------------------------------------------------
def cita_completa_a_dict(c) -> dict:
    """
    Mantiene todos los campos que ya tenía la API (ids, fecha, hora_inicio...)
    y agrega lo que el calendario necesita: nombres, servicios, productos,
    totales y fechas ISO (inicio/fin) listas para librerías de calendario.
    """
    inicio = datetime.combine(c.fecha, c.hora_inicio)
    fin = datetime.combine(c.fecha, c.hora_fin)

    total_servicios = sum(
        (s.precio_unitario * s.cantidad for s in c.servicios), Decimal(0)
    )
    total_productos = sum(
        (p.precio_unitario * p.cantidad for p in c.productos), Decimal(0)
    )

    empleado = c.usuario_negocio.usuario if c.usuario_negocio else None

    return {
        "id": c.id,
        "negocio_id": c.negocio_id,
        "cliente_id": c.cliente_id,
        "usuario_negocio_id": c.usuario_negocio_id,
        "fecha": c.fecha,
        "hora_inicio": c.hora_inicio,
        "hora_fin": c.hora_fin,
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "duracion_minutos": int((fin - inicio).total_seconds() // 60),
        "estado": c.estado,
        "origen": c.origen,
        "motivo": c.motivo,
        "observaciones": c.observaciones,
        "fecha_creacion": c.fecha_creacion,
        "fecha_actualizacion": c.fecha_actualizacion,
        "cliente": (
            {"id": c.cliente.id, "nombre": c.cliente.nombre, "telefono": c.cliente.telefono}
            if c.cliente else None
        ),
        "empleado": (
            {"id": c.usuario_negocio_id, "nombre": empleado.nombre}
            if empleado else None
        ),
        "servicios": [
            {
                "id": s.id,
                "servicio_id": s.servicio_id,
                "nombre": s.servicio.nombre if s.servicio else None,
                "duracion_minutos": s.duracion_minutos,
                "cantidad": s.cantidad,
                "precio_unitario": float(s.precio_unitario),
            }
            for s in c.servicios
        ],
        "productos": [
            {
                "id": p.id,
                "producto_id": p.producto_id,
                "nombre": p.producto.nombre if p.producto else None,
                "cantidad": p.cantidad,
                "precio_unitario": float(p.precio_unitario),
            }
            for p in c.productos
        ],
        "total_servicios": float(total_servicios),
        "total_productos": float(total_productos),
        "total": float(total_servicios + total_productos),
    }


@router.get("/citas")
def listar_citas(
    desde: date | None = None,
    hasta: date | None = None,
    empleado_id: int | None = None,
    cliente_id: int | None = None,
    estado: Annotated[list[EstadoCita] | None, Query()] = None,
    solo_mias: bool = False,
    ctx: Contexto = Depends(contexto_negocio),
):
    """
    Citas del negocio entre dos fechas (inclusive). Sin parámetros: desde hoy
    y los próximos 30 días. Máximo 92 días por consulta.
      ?desde=2026-11-01&hasta=2026-11-07
      ?empleado_id=5            (id de usuario_negocio)
      ?estado=PENDIENTE&estado=CONFIRMADA
      ?solo_mias=true           (la agenda de quien consulta)
    """
    desde = desde or date.today()
    hasta = hasta or desde + timedelta(days=DIAS_POR_DEFECTO)

    if hasta < desde:
        raise HTTPException(status_code=400, detail="'hasta' no puede ser anterior a 'desde'")

    if (hasta - desde).days > DIAS_MAXIMOS_POR_CONSULTA:
        raise HTTPException(
            status_code=400,
            detail=f"El rango máximo es de {DIAS_MAXIMOS_POR_CONSULTA} días por consulta",
        )

    db = SessionLocal()

    try:
        consulta = select(Cita).where(
            Cita.negocio_id == ctx.negocio_id,
            Cita.fecha >= desde,
            Cita.fecha <= hasta,
        )

        if empleado_id is not None:
            consulta = consulta.where(Cita.usuario_negocio_id == empleado_id)

        if solo_mias:
            consulta = consulta.where(Cita.usuario_negocio_id == ctx.usuario_negocio_id)

        if cliente_id is not None:
            consulta = consulta.where(Cita.cliente_id == cliente_id)

        if estado:
            consulta = consulta.where(Cita.estado.in_(estado))

        citas = db.execute(
            consulta
            .options(
                selectinload(Cita.servicios).selectinload(ServicioDeCita.servicio),
                selectinload(Cita.productos).selectinload(ProductoDeCita.producto),
                joinedload(Cita.cliente),
                joinedload(Cita.usuario_negocio).joinedload(UsuarioNegocio.usuario),
            )
            .order_by(Cita.fecha, Cita.hora_inicio, Cita.id)
        ).scalars().all()

        return [cita_completa_a_dict(c) for c in citas]

    finally:
        db.close()


@router.get("/citas/{cita_id}")
def obtener_cita(cita_id: int, ctx: Contexto = Depends(contexto_negocio)):
    db = SessionLocal()

    try:
        cita = obtener_del_negocio(db, Cita, cita_id, ctx, "Cita no encontrada")

        return cita_completa_a_dict(cita)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Disponibilidad
# ---------------------------------------------------------------------------
def _inicio_permitido(inicio: datetime, ahora: datetime, aplicar_antelacion: bool) -> bool:
    if inicio < ahora:                      # igual que validar_no_en_el_pasado
        return False

    if aplicar_antelacion and not reglas.MODO_PRUEBAS:
        if inicio < ahora + timedelta(minutes=reglas.ANTELACION_MINIMA_MINUTOS):
            return False
        if inicio > ahora + timedelta(days=reglas.ANTELACION_MAXIMA_DIAS):
            return False

    return True


def _franja_libre(horarios, pausas_por_horario, citas, inicio: time, fin: time) -> bool:
    horario, problema = _buscar_hueco(horarios, pausas_por_horario, inicio, fin)

    if problema is not None:
        return False

    return not any(
        se_superponen(inicio, fin, c.hora_inicio, c.hora_fin) for c in citas
    )


def calcular_huecos(db, usuario_negocio_id: int, fecha: date, duracion_minutos: int, *,
                    ahora: datetime | None = None,
                    aplicar_antelacion: bool = False) -> list[time]:
    """
    Horas de inicio posibles para una cita de `duracion_minutos` con ese
    empleado ese día. Candidatas: la hora de apertura de cada horario más
    múltiplos de su intervalo_minutos. Se descartan las que no caben en el
    horario, caen en una pausa, se cruzan con una cita no cancelada, o ya
    pasaron.

    aplicar_antelacion=True añade la antelación mínima y máxima de las citas
    pedidas por el CLIENTE (lo usará la página pública de reservas).
    """
    ahora = ahora or datetime.now()

    horarios = db.execute(
        select(Horario)
        .where(
            Horario.usuario_negocio_id == usuario_negocio_id,
            Horario.dia_semana == fecha.isoweekday(),
            Horario.activo == True,
        )
        .order_by(Horario.hora_inicio)
    ).scalars().all()

    if not horarios:
        return []

    pausas_por_horario = {h.id: h.pausas for h in horarios}

    citas = db.execute(
        select(Cita).where(
            Cita.usuario_negocio_id == usuario_negocio_id,
            Cita.fecha == fecha,
            Cita.estado != "CANCELADA",
        )
    ).scalars().all()

    duracion = timedelta(minutes=duracion_minutos)
    huecos = []

    for horario in horarios:
        paso = timedelta(minutes=horario.intervalo_minutos)
        fin_horario = datetime.combine(fecha, horario.hora_fin)
        inicio = datetime.combine(fecha, horario.hora_inicio)

        while inicio + duracion <= fin_horario:
            if (
                _inicio_permitido(inicio, ahora, aplicar_antelacion)
                and _franja_libre(
                    horarios, pausas_por_horario, citas,
                    inicio.time(), (inicio + duracion).time(),
                )
            ):
                huecos.append(inicio.time())

            inicio += paso

    return sorted(set(huecos))


@router.get("/disponibilidad")
def consultar_disponibilidad(
    empleado_id: int,
    fecha: date,
    servicio_id: Annotated[list[int], Query(min_length=1)],
    ctx: Contexto = Depends(contexto_negocio),
):
    """
    Horas libres de un empleado (id de usuario_negocio) para uno o varios
    servicios en una fecha:
      /disponibilidad?empleado_id=5&fecha=2026-11-02&servicio_id=3
      /disponibilidad?empleado_id=5&fecha=2026-11-02&servicio_id=3&servicio_id=4
    La duración es la suma de los servicios.
    """
    if len(set(servicio_id)) != len(servicio_id):
        raise HTTPException(status_code=400, detail="No repitas servicios en la consulta")

    db = SessionLocal()

    try:
        empleado = exigir_empleado_valido(db, empleado_id, ctx.negocio_id)

        servicios = [
            exigir_servicio_para_empleado(db, sid, empleado) for sid in servicio_id
        ]

        duracion = sum(s.duracion_minutos for s in servicios)
        huecos = calcular_huecos(db, empleado.id, fecha, duracion)

        return {
            "fecha": fecha,
            "empleado_id": empleado.id,
            "servicios": [s.id for s in servicios],
            "duracion_minutos": duracion,
            "huecos": [
                {
                    "inicio": h.strftime("%H:%M"),
                    "fin": (datetime.combine(fecha, h) + timedelta(minutes=duracion)).strftime("%H:%M"),
                }
                for h in huecos
            ],
        }

    finally:
        db.close()