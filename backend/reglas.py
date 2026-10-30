"""
Reglas de negocio y validaciones reutilizables.

Códigos HTTP que se usan aquí:
  400 -> la petición es inválida (referencias que no corresponden, fecha pasada...)
  404 -> el recurso no existe
  409 -> choca con el estado actual (solapes, fuera de horario, transición no
         permitida, stock insuficiente, duplicados, citas futuras afectadas...)

Convención de días: dia_semana 1 = lunes ... 7 = domingo (date.isoweekday()).
Dos rangos que solo se "tocan" (09:00-10:00 y 10:00-11:00) NO se superponen.
"""
import os
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from models import (
    Cita,
    Cliente,
    EmpleadoServicio,
    Horario,
    Pausa,
    Producto,
    Servicio,
    ServicioDeCita,
    Usuario,
    UsuarioNegocio,
)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
# Con la variable de entorno VALEN_MODO_PRUEBAS=1 se relajan las reglas de
# tiempo (antelación mínima/máxima y "la cita ya empezó") para poder probar el
# flujo completo sin esperar horas. En producción NO la definas.
MODO_PRUEBAS = os.getenv("VALEN_MODO_PRUEBAS") == "1"

# Solo aplican a citas pedidas por el CLIENTE (origen "CLIENTE"). El negocio o
# el empleado pueden agendar sobre la marcha. Más adelante conviene moverlas a
# columnas de la tabla negocio para que cada negocio elija las suyas.
ANTELACION_MINIMA_MINUTOS = 60
ANTELACION_MAXIMA_DIAS = 60

# ---------------------------------------------------------------------------
# Estados de la cita
# ---------------------------------------------------------------------------
# Para cambiar las reglas de estados solo hay que editar esta tabla.
TRANSICIONES_CITA = {
    "PENDIENTE": {"CONFIRMADA", "CANCELADA"},
    "CONFIRMADA": {"COMPLETADA", "NO_ASISTIO", "CANCELADA"},
    "COMPLETADA": set(),   # estados finales: forman parte del historial
    "CANCELADA": set(),
    "NO_ASISTIO": set(),
}

# Citas que todavía "cuentan": ocupan agenda y pueden quedar afectadas.
ESTADOS_ACTIVOS = ("PENDIENTE", "CONFIRMADA")

# Solo en estos estados se puede cambiar fecha/hora, servicios o productos.
ESTADOS_EDITABLES = {"PENDIENTE", "CONFIRMADA"}

# Solo estas citas se pueden borrar del todo (las demás se cancelan).
ESTADOS_ELIMINABLES = {"PENDIENTE", "CANCELADA"}


# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------
def formato_hora(hora: time) -> str:
    return hora.strftime("%H:%M")


def se_superponen(inicio_a: time, fin_a: time, inicio_b: time, fin_b: time) -> bool:
    return inicio_a < fin_b and inicio_b < fin_a


def obtener_o_404(db, modelo, id_, mensaje: str, bloquear: bool = False):
    """
    Busca por clave primaria o lanza 404.
    Con bloquear=True hace SELECT ... FOR UPDATE: otra petición que quiera
    bloquear la misma fila espera a que esta termine. Se usa para que dos
    peticiones simultáneas no puedan crear citas que se pisen.
    """
    opciones = {"with_for_update": True} if bloquear else {}
    objeto = db.get(modelo, id_, **opciones)

    if objeto is None:
        raise HTTPException(status_code=404, detail=mensaje)

    return objeto


# ---------------------------------------------------------------------------
# Duplicados (409 en vez de error 500 de la base de datos)
# ---------------------------------------------------------------------------
def exigir_email_libre(db, email: str, excluir_usuario_id: int | None = None):
    """El email no lo usa otro usuario (sin distinguir mayúsculas)."""
    consulta = select(Usuario).where(func.lower(Usuario.email) == email.lower())

    if excluir_usuario_id is not None:
        consulta = consulta.where(Usuario.id != excluir_usuario_id)

    if db.execute(consulta).scalars().first() is not None:
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese email")


def exigir_telefono_libre(db, negocio_id: int, telefono: str,
                          excluir_cliente_id: int | None = None):
    """No hay otro cliente (activo o no) con ese teléfono en el mismo negocio."""
    consulta = select(Cliente).where(
        Cliente.negocio_id == negocio_id,
        Cliente.telefono == telefono,
    )

    if excluir_cliente_id is not None:
        consulta = consulta.where(Cliente.id != excluir_cliente_id)

    existente = db.execute(consulta).scalars().first()

    if existente is not None:
        pista = (
            f" Está inactivo: reactívalo con PATCH /clientes/{existente.id}/activar"
            if not existente.activo else ""
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Ya existe un cliente con ese teléfono en este negocio: "
                f"#{existente.id} {existente.nombre}.{pista}"
            ),
        )


def exigir_asociacion_libre(db, usuario_id: int, negocio_id: int):
    """El usuario no está ya vinculado (activo o no) a ese negocio."""
    existente = db.execute(
        select(UsuarioNegocio).where(
            UsuarioNegocio.usuario_id == usuario_id,
            UsuarioNegocio.negocio_id == negocio_id,
        )
    ).scalars().first()

    if existente is not None:
        pista = (
            f" Está inactiva: reactívala con PATCH /usuarios-negocio/{existente.id}/activar"
            if not existente.activo else ""
        )
        raise HTTPException(
            status_code=409,
            detail=f"Ese usuario ya está vinculado a este negocio.{pista}",
        )


# ---------------------------------------------------------------------------
# Empleados, clientes, servicios, productos
# ---------------------------------------------------------------------------
def exigir_empleado_valido(db, usuario_negocio_id: int, negocio_id: int | None = None,
                           bloquear: bool = False):
    """El empleado (usuario_negocio) existe, está activo y es del negocio indicado."""
    empleado = obtener_o_404(
        db, UsuarioNegocio, usuario_negocio_id, "Empleado no encontrado", bloquear
    )

    if not empleado.activo:
        raise HTTPException(status_code=400, detail="El empleado está inactivo")

    if negocio_id is not None and empleado.negocio_id != negocio_id:
        raise HTTPException(
            status_code=400,
            detail="El empleado no pertenece al mismo negocio",
        )

    return empleado


def exigir_cliente_valido(db, cliente_id: int, negocio_id: int):
    cliente = obtener_o_404(db, Cliente, cliente_id, "Cliente no encontrado")

    if not cliente.activo:
        raise HTTPException(status_code=400, detail="El cliente está inactivo")

    if cliente.negocio_id != negocio_id:
        raise HTTPException(
            status_code=400,
            detail="El cliente no pertenece a este negocio",
        )

    return cliente


def exigir_servicio_para_empleado(db, servicio_id: int, empleado):
    """
    El servicio existe, está activo, es del mismo negocio que el empleado
    y el empleado lo tiene asignado.
    """
    servicio = obtener_o_404(
        db, Servicio, servicio_id, f"Servicio {servicio_id} no encontrado"
    )

    if not servicio.activo:
        raise HTTPException(
            status_code=400,
            detail=f"El servicio '{servicio.nombre}' está inactivo",
        )

    if servicio.negocio_id != empleado.negocio_id:
        raise HTTPException(
            status_code=400,
            detail=f"El servicio '{servicio.nombre}' no pertenece al mismo negocio",
        )

    if db.get(EmpleadoServicio, (servicio.id, empleado.id)) is None:
        raise HTTPException(
            status_code=400,
            detail=f"El empleado no tiene asignado el servicio '{servicio.nombre}'",
        )

    return servicio


def exigir_empleado_atiende_servicios(db, empleado, servicios_de_cita):
    """
    Para reasignar una cita: el nuevo empleado tiene asignados todos los
    servicios de la cita. (No se exige que sigan activos: la cita ya estaba
    reservada con ellos.)
    """
    faltantes = []

    for linea in servicios_de_cita:
        if db.get(EmpleadoServicio, (linea.servicio_id, empleado.id)) is None:
            servicio = db.get(Servicio, linea.servicio_id)
            faltantes.append(servicio.nombre if servicio else f"#{linea.servicio_id}")

    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"El empleado no tiene asignado: {', '.join(faltantes)}",
        )


def exigir_producto_para_cita(db, producto_id: int, cantidad: int, negocio_id: int):
    """El producto existe, está activo, es del negocio y hay existencias."""
    producto = obtener_o_404(db, Producto, producto_id, "Producto no encontrado")

    if not producto.activo:
        raise HTTPException(
            status_code=400,
            detail=f"El producto '{producto.nombre}' está inactivo",
        )

    if producto.negocio_id != negocio_id:
        raise HTTPException(
            status_code=400,
            detail=f"El producto '{producto.nombre}' no pertenece a este negocio",
        )

    # stock NULL = producto sin control de inventario
    if producto.stock is not None and cantidad > producto.stock:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Stock insuficiente de '{producto.nombre}' "
                f"(disponible: {producto.stock}, pedido: {cantidad})"
            ),
        )

    return producto


# ---------------------------------------------------------------------------
# Horarios y pausas
# ---------------------------------------------------------------------------
def validar_solape_horarios(db, usuario_negocio_id: int, dia_semana: int,
                            hora_inicio: time, hora_fin: time,
                            excluir_horario_id: int | None = None):
    """Un empleado no puede tener dos horarios activos que se pisen el mismo día."""
    consulta = select(Horario).where(
        Horario.usuario_negocio_id == usuario_negocio_id,
        Horario.dia_semana == dia_semana,
        Horario.activo == True,
    )

    if excluir_horario_id is not None:
        consulta = consulta.where(Horario.id != excluir_horario_id)

    for otro in db.execute(consulta).scalars().all():
        if se_superponen(hora_inicio, hora_fin, otro.hora_inicio, otro.hora_fin):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Se superpone con otro horario del mismo día "
                    f"({formato_hora(otro.hora_inicio)}-{formato_hora(otro.hora_fin)})"
                ),
            )


def validar_pausa(db, horario, hora_inicio: time, hora_fin: time,
                  excluir_pausa_id: int | None = None):
    """La pausa cabe dentro de su horario y no pisa otras pausas del mismo horario."""
    if hora_inicio < horario.hora_inicio or hora_fin > horario.hora_fin:
        raise HTTPException(
            status_code=409,
            detail=(
                "La pausa debe estar dentro del horario "
                f"({formato_hora(horario.hora_inicio)}-{formato_hora(horario.hora_fin)})"
            ),
        )

    consulta = select(Pausa).where(Pausa.horario_id == horario.id)

    if excluir_pausa_id is not None:
        consulta = consulta.where(Pausa.id != excluir_pausa_id)

    for otra in db.execute(consulta).scalars().all():
        if se_superponen(hora_inicio, hora_fin, otra.hora_inicio, otra.hora_fin):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Se superpone con otra pausa del mismo horario "
                    f"({formato_hora(otra.hora_inicio)}-{formato_hora(otra.hora_fin)})"
                ),
            )


def validar_pausas_dentro_de_horario(horario, nuevo_inicio: time, nuevo_fin: time):
    """Al cambiar un horario, sus pausas existentes deben seguir cabiendo."""
    for pausa in horario.pausas:
        if pausa.hora_inicio < nuevo_inicio or pausa.hora_fin > nuevo_fin:
            raise HTTPException(
                status_code=409,
                detail=(
                    "No se puede cambiar el horario: la pausa "
                    f"{formato_hora(pausa.hora_inicio)}-{formato_hora(pausa.hora_fin)} "
                    "quedaría fuera. Ajusta o elimina la pausa primero"
                ),
            )


# ---------------------------------------------------------------------------
# Citas futuras afectadas por cambios en la agenda o en las personas
# ---------------------------------------------------------------------------
def _condicion_futura():
    """Citas que aún no terminaron (hoy más tarde, o días posteriores)."""
    ahora = datetime.now()
    return or_(
        Cita.fecha > ahora.date(),
        and_(Cita.fecha == ahora.date(), Cita.hora_fin > ahora.time()),
    )


def citas_futuras_activas(db, *, usuario_negocio_id: int | None = None,
                          cliente_id: int | None = None,
                          servicio_id: int | None = None):
    """Citas PENDIENTE/CONFIRMADA que aún no terminaron, filtradas opcionalmente."""
    consulta = select(Cita).where(
        Cita.estado.in_(ESTADOS_ACTIVOS),
        _condicion_futura(),
    )

    if usuario_negocio_id is not None:
        consulta = consulta.where(Cita.usuario_negocio_id == usuario_negocio_id)

    if cliente_id is not None:
        consulta = consulta.where(Cita.cliente_id == cliente_id)

    if servicio_id is not None:
        consulta = consulta.join(
            ServicioDeCita, ServicioDeCita.cita_id == Cita.id
        ).where(ServicioDeCita.servicio_id == servicio_id)

    return db.execute(
        consulta.order_by(Cita.fecha, Cita.hora_inicio)
    ).scalars().all()


def _detalle_citas_afectadas(accion: str, citas) -> str:
    resumen = ", ".join(
        f"#{c.id} ({c.fecha:%d/%m} {formato_hora(c.hora_inicio)})" for c in citas[:5]
    )
    extra = f" y {len(citas) - 5} más" if len(citas) > 5 else ""
    return (
        f"No se puede {accion}: hay {len(citas)} cita(s) futura(s) pendiente(s) "
        f"o confirmada(s) afectada(s): {resumen}{extra}. "
        "Cancélalas o reasígnalas primero"
    )


def exigir_sin_citas_futuras(db, accion: str, **filtros):
    """
    Bloquea acciones (desactivar un empleado, servicio o cliente, quitar una
    asignación...) mientras existan citas futuras que dependan de ello.
    filtros: usuario_negocio_id=..., cliente_id=..., servicio_id=...
    """
    citas = citas_futuras_activas(db, **filtros)

    if citas:
        raise HTTPException(status_code=409, detail=_detalle_citas_afectadas(accion, citas))


def exigir_agenda_cubre_citas_futuras(db, usuario_negocio_id: int, accion: str):
    """
    Se llama DESPUÉS de aplicar en la sesión un cambio de horario o de pausa
    (sin hacer commit). Comprueba que todas las citas futuras del empleado
    siguen cabiendo en su agenda. Si alguna quedaría huérfana lanza 409 y,
    como no hubo commit, el cambio se descarta solo.
    """
    db.flush()  # para que las consultas de abajo vean el cambio que se está probando

    citas = citas_futuras_activas(db, usuario_negocio_id=usuario_negocio_id)

    if not citas:
        return

    horarios = db.execute(
        select(Horario).where(
            Horario.usuario_negocio_id == usuario_negocio_id,
            Horario.activo == True,
        )
    ).scalars().all()

    pausas_por_horario = {}

    if horarios:
        pausas = db.execute(
            select(Pausa).where(Pausa.horario_id.in_([h.id for h in horarios]))
        ).scalars().all()

        for pausa in pausas:
            pausas_por_horario.setdefault(pausa.horario_id, []).append(pausa)

    huerfanas = []

    for cita in citas:
        del_dia = [h for h in horarios if h.dia_semana == cita.fecha.isoweekday()]
        _, problema = _buscar_hueco(
            del_dia, pausas_por_horario, cita.hora_inicio, cita.hora_fin
        )

        if problema is not None:
            huerfanas.append(cita)

    if huerfanas:
        raise HTTPException(status_code=409, detail=_detalle_citas_afectadas(accion, huerfanas))


# ---------------------------------------------------------------------------
# Citas: tiempos y disponibilidad
# ---------------------------------------------------------------------------
def duracion_servicios_minutos(servicios_de_cita) -> int:
    return sum(s.duracion_minutos * s.cantidad for s in servicios_de_cita)


def duracion_de_cita_minutos(cita) -> int:
    """Duración según sus servicios; si no tuviera (datos viejos), según sus horas."""
    total = duracion_servicios_minutos(cita.servicios)

    if total > 0:
        return total

    inicio = datetime.combine(cita.fecha, cita.hora_inicio)
    fin = datetime.combine(cita.fecha, cita.hora_fin)
    return int((fin - inicio).total_seconds() // 60)


def calcular_hora_fin(fecha: date, hora_inicio: time, duracion_minutos: int) -> time:
    fin = datetime.combine(fecha, hora_inicio) + timedelta(minutes=duracion_minutos)

    if fin.date() != fecha:
        raise HTTPException(
            status_code=400,
            detail="La cita terminaría después de medianoche",
        )

    return fin.time()


def validar_no_en_el_pasado(fecha: date, hora_inicio: time):
    if datetime.combine(fecha, hora_inicio) < datetime.now():
        raise HTTPException(
            status_code=400,
            detail="No se puede agendar una cita en el pasado",
        )


def validar_antelacion(fecha: date, hora_inicio: time, origen: str):
    """
    Antelación mínima y máxima. Solo para citas pedidas por el CLIENTE:
    el negocio o el empleado pueden agendar sobre la marcha.
    """
    if MODO_PRUEBAS or origen != "CLIENTE":
        return

    inicio = datetime.combine(fecha, hora_inicio)
    ahora = datetime.now()

    if inicio < ahora + timedelta(minutes=ANTELACION_MINIMA_MINUTOS):
        raise HTTPException(
            status_code=400,
            detail=(
                "Las citas deben agendarse con al menos "
                f"{ANTELACION_MINIMA_MINUTOS} minutos de anticipación"
            ),
        )

    if inicio > ahora + timedelta(days=ANTELACION_MAXIMA_DIAS):
        raise HTTPException(
            status_code=400,
            detail=(
                "No se puede agendar con más de "
                f"{ANTELACION_MAXIMA_DIAS} días de anticipación"
            ),
        )


def _buscar_hueco(horarios_del_dia, pausas_por_horario, hora_inicio: time, hora_fin: time):
    """
    Devuelve (horario, None) si [inicio, fin) cabe completo en UNO de los
    horarios del día sin tocar ninguna de sus pausas; si no, (None, mensaje).
    """
    if not horarios_del_dia:
        return None, "El empleado no trabaja ese día"

    ordenados = sorted(horarios_del_dia, key=lambda h: h.hora_inicio)

    horario = next(
        (h for h in ordenados if h.hora_inicio <= hora_inicio and hora_fin <= h.hora_fin),
        None,
    )

    if horario is None:
        rangos = ", ".join(
            f"{formato_hora(h.hora_inicio)}-{formato_hora(h.hora_fin)}" for h in ordenados
        )
        return None, f"La cita queda fuera del horario del empleado ese día ({rangos})"

    for pausa in pausas_por_horario.get(horario.id, []):
        if se_superponen(hora_inicio, hora_fin, pausa.hora_inicio, pausa.hora_fin):
            motivo = f" - {pausa.motivo}" if pausa.motivo else ""
            return None, (
                "La cita coincide con una pausa del empleado "
                f"({formato_hora(pausa.hora_inicio)}-{formato_hora(pausa.hora_fin)}{motivo})"
            )

    return horario, None


def validar_inicio_alineado(horario, hora_inicio: time):
    """
    La cita debe empezar en un "turno" del horario: la hora de apertura más un
    múltiplo de intervalo_minutos (09:00, 09:30, 10:00... con intervalo 30).
    """
    paso = horario.intervalo_minutos * 60
    base = datetime.combine(date.min, horario.hora_inicio)
    segundos = int((datetime.combine(date.min, hora_inicio) - base).total_seconds())

    if segundos % paso != 0:
        siguiente = base + timedelta(seconds=(segundos // paso + 1) * paso)
        raise HTTPException(
            status_code=409,
            detail=(
                "La cita debe empezar en un turno válido: este horario abre a las "
                f"{formato_hora(horario.hora_inicio)} y agenda cada "
                f"{horario.intervalo_minutos} min. "
                f"El siguiente turno es a las {formato_hora(siguiente.time())}"
            ),
        )


def validar_disponibilidad(db, usuario_negocio_id: int, fecha: date,
                           hora_inicio: time, hora_fin: time,
                           excluir_cita_id: int | None = None,
                           comprobar_alineacion: bool = True):
    """
    El empleado puede atender en [hora_inicio, hora_fin) ese día:
      1. trabaja ese día de la semana (tiene horario activo),
      2. el rango cabe completo dentro de UNO de sus horarios,
      3. no pisa ninguna pausa de ese horario,
      4. el inicio cae en un turno del horario (si comprobar_alineacion),
      5. no se cruza con otra cita suya (las CANCELADAS no bloquean).
    comprobar_alineacion=False se usa cuando la hora de inicio no cambia
    (reasignar a otro empleado, alargar una cita al agregar un servicio).
    """
    horarios = db.execute(
        select(Horario)
        .where(
            Horario.usuario_negocio_id == usuario_negocio_id,
            Horario.dia_semana == fecha.isoweekday(),
            Horario.activo == True,
        )
        .order_by(Horario.hora_inicio)
    ).scalars().all()

    horario, problema = _buscar_hueco(
        horarios, {h.id: h.pausas for h in horarios}, hora_inicio, hora_fin
    )

    if problema is not None:
        raise HTTPException(status_code=409, detail=problema)

    if comprobar_alineacion:
        validar_inicio_alineado(horario, hora_inicio)

    consulta = select(Cita).where(
        Cita.usuario_negocio_id == usuario_negocio_id,
        Cita.fecha == fecha,
        Cita.estado != "CANCELADA",
        Cita.hora_inicio < hora_fin,
        Cita.hora_fin > hora_inicio,
    )

    if excluir_cita_id is not None:
        consulta = consulta.where(Cita.id != excluir_cita_id)

    choque = db.execute(consulta).scalars().first()

    if choque is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "El empleado ya tiene una cita de "
                f"{formato_hora(choque.hora_inicio)} a {formato_hora(choque.hora_fin)} ese día"
            ),
        )


def validar_cliente_sin_solape(db, cliente_id: int, fecha: date,
                               hora_inicio: time, hora_fin: time,
                               excluir_cita_id: int | None = None):
    """El cliente no puede estar en dos citas a la vez (aunque sea con empleados distintos)."""
    consulta = select(Cita).where(
        Cita.cliente_id == cliente_id,
        Cita.fecha == fecha,
        Cita.estado != "CANCELADA",
        Cita.hora_inicio < hora_fin,
        Cita.hora_fin > hora_inicio,
    )

    if excluir_cita_id is not None:
        consulta = consulta.where(Cita.id != excluir_cita_id)

    choque = db.execute(consulta).scalars().first()

    if choque is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "El cliente ya tiene una cita de "
                f"{formato_hora(choque.hora_inicio)} a {formato_hora(choque.hora_fin)} ese día"
            ),
        )


# ---------------------------------------------------------------------------
# Citas: estados y existencias
# ---------------------------------------------------------------------------
def exigir_cita_editable(cita):
    if cita.estado not in ESTADOS_EDITABLES:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede modificar una cita en estado {cita.estado}",
        )


def validar_transicion(cita, nuevo_estado: str):
    permitidos = TRANSICIONES_CITA.get(cita.estado, set())

    if nuevo_estado not in permitidos:
        opciones = ", ".join(sorted(permitidos)) or "ninguno (es un estado final)"
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede pasar de {cita.estado} a {nuevo_estado}. "
                f"Cambios permitidos: {opciones}"
            ),
        )


def exigir_cita_iniciada(cita, nuevo_estado: str):
    """COMPLETADA y NO_ASISTIO solo tienen sentido cuando la cita ya empezó."""
    if MODO_PRUEBAS:
        return

    if datetime.combine(cita.fecha, cita.hora_inicio) > datetime.now():
        raise HTTPException(
            status_code=409,
            detail=(
                f"No se puede marcar como {nuevo_estado} una cita que aún no ha empezado "
                f"({cita.fecha:%d/%m/%Y} {formato_hora(cita.hora_inicio)})"
            ),
        )


def descontar_stock_de_cita(db, cita):
    """
    Se llama al COMPLETAR la cita: descuenta del inventario los productos
    vendidos. Si algún producto ya no tiene existencias suficientes lanza 409
    y no se guarda nada (la transacción completa se revierte).
    """
    for item in cita.productos:
        producto = db.get(Producto, item.producto_id, with_for_update=True)

        if producto.stock is None:
            continue

        if producto.stock < item.cantidad:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Stock insuficiente de '{producto.nombre}' para completar la cita "
                    f"(disponible: {producto.stock}, en la cita: {item.cantidad})"
                ),
            )

        producto.stock -= item.cantidad


# ---------------------------------------------------------------------------
# Acceso: aislamiento entre negocios y permisos por rol
# ctx es el Contexto de auth.py (negocio_id, usuario_negocio_id, es_admin).
# ---------------------------------------------------------------------------
def obtener_del_negocio(db, modelo, id_, ctx, mensaje: str, bloquear: bool = False):
    """
    Como obtener_o_404, pero además el registro debe ser del negocio del
    usuario. Si pertenece a otro negocio se responde 404 (el mismo mensaje que
    si no existiera), para no revelar que ese id existe en otro negocio.
    Solo para modelos que tienen negocio_id (Servicio, Cliente, Producto,
    Cita, UsuarioNegocio).
    """
    objeto = obtener_o_404(db, modelo, id_, mensaje, bloquear)

    if objeto.negocio_id != ctx.negocio_id:
        raise HTTPException(status_code=404, detail=mensaje)

    return objeto


def obtener_horario_del_negocio(db, horario_id: int, ctx, bloquear: bool = False):
    """El horario existe y es de un empleado del negocio del usuario."""
    mensaje = "Horario no encontrado"
    horario = obtener_o_404(db, Horario, horario_id, mensaje, bloquear)
    dueno = db.get(UsuarioNegocio, horario.usuario_negocio_id)

    if dueno is None or dueno.negocio_id != ctx.negocio_id:
        raise HTTPException(status_code=404, detail=mensaje)

    return horario


def obtener_pausa_del_negocio(db, pausa_id: int, ctx):
    """La pausa existe y su horario es de un empleado del negocio del usuario."""
    mensaje = "Pausa no encontrada"
    pausa = obtener_o_404(db, Pausa, pausa_id, mensaje)

    try:
        obtener_horario_del_negocio(db, pausa.horario_id, ctx)
    except HTTPException:
        raise HTTPException(status_code=404, detail=mensaje)

    return pausa


def exigir_puede_operar_cita(ctx, cita):
    """
    El ADMIN opera cualquier cita del negocio. El EMPLEADO solo las que tiene
    asignadas. Para dar más libertad a los empleados, cambia solo esta función.
    """
    if ctx.es_admin:
        return

    if cita.usuario_negocio_id != ctx.usuario_negocio_id:
        raise HTTPException(
            status_code=403,
            detail="Como empleado solo puedes modificar tus propias citas",
        )


def exigir_queda_otro_admin(db, negocio_id: int, excluir_usuario_negocio_id: int):
    """Un negocio siempre conserva al menos un administrador activo."""
    otro = db.execute(
        select(UsuarioNegocio).where(
            UsuarioNegocio.negocio_id == negocio_id,
            UsuarioNegocio.rol == "ADMIN",
            UsuarioNegocio.activo == True,
            UsuarioNegocio.id != excluir_usuario_negocio_id,
        )
    ).scalars().first()

    if otro is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "El negocio debe conservar al menos un administrador activo. "
                "Nombra a otro administrador primero"
            ),
        )