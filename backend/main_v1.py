#.\venv\Scripts\Activate.ps1
#uvicorn main:app --reload
from datetime import datetime

from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from database import engine, SessionLocal
from models import (
    Servicio,
    Cliente,
    Usuario,
    UsuarioNegocio,
    Negocio,
    Producto,
    EmpleadoServicio,
    Horario,
    Pausa,
    Cita,
    ServicioDeCita,
    ProductoDeCita,
)
import schemas

app = FastAPI()


@app.get("/")
def inicio():
    return {"mensaje": "Bienvenido a Valen"}


@app.get("/prueba-db")
def prueba_db():
    with engine.connect() as conexion:
        resultado = conexion.exec_driver_sql("SELECT 1")
        return {"resultado": resultado.scalar()}


@app.get("/servicios")
def obtener_servicios():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Servicio).where(Servicio.activo == True)
        )
        servicios = resultado.fetchall()

        return [
            {
                "id": servicio.id,
                "negocio_id": servicio.negocio_id,
                "nombre": servicio.nombre,
                "descripcion": servicio.descripcion,
                "duracion_minutos": servicio.duracion_minutos,
                "precio": float(servicio.precio),
                "activo": servicio.activo
            }
            for servicio in servicios
        ]

@app.get("/servicios/admin")
def obtener_todos_los_servicios():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(Servicio))
        servicios = resultado.fetchall()

        return [
            {
                "id": servicio.id,
                "negocio_id": servicio.negocio_id,
                "nombre": servicio.nombre,
                "descripcion": servicio.descripcion,
                "duracion_minutos": servicio.duracion_minutos,
                "precio": float(servicio.precio),
                "activo": servicio.activo
            }
            for servicio in servicios
        ]


@app.get("/servicios/{servicio_id}")
def obtener_servicio(servicio_id: int):
    db = SessionLocal()

    try:
        servicio = db.get(Servicio, servicio_id)

        if servicio is None:
            return {"mensaje": "Servicio no encontrado"}

        return {
            "id": servicio.id,
            "negocio_id": servicio.negocio_id,
            "nombre": servicio.nombre,
            "descripcion": servicio.descripcion,
            "duracion_minutos": servicio.duracion_minutos,
            "precio": float(servicio.precio),
            "activo": servicio.activo
        }

    finally:
        db.close()


@app.post("/servicios")
def crear_servicio(servicio: schemas.ServicioCrear):
    db = SessionLocal()

    try:
        nuevo_servicio = Servicio(
            negocio_id=servicio.negocio_id,
            nombre=servicio.nombre,
            descripcion=servicio.descripcion,
            duracion_minutos=servicio.duracion_minutos,
            precio=servicio.precio,
            activo=True
        )

        db.add(nuevo_servicio)
        db.commit()
        db.refresh(nuevo_servicio)

        return {
            "mensaje": "Servicio creado correctamente",
            "id": nuevo_servicio.id
        }

    finally:
        db.close()

@app.put("/servicios/{servicio_id}")
def actualizar_servicio(
    servicio_id: int,
    datos: schemas.ServicioActualizar
):
    db = SessionLocal()

    try:
        servicio = db.get(Servicio, servicio_id)

        if servicio is None:
            return {"mensaje": "Servicio no encontrado"}

        servicio.nombre = datos.nombre
        servicio.descripcion = datos.descripcion
        servicio.duracion_minutos = datos.duracion_minutos
        servicio.precio = datos.precio
        

        db.commit()
        db.refresh(servicio)

        return {
            "mensaje": "Servicio actualizado correctamente",
            "id": servicio.id
        }

    finally:
        db.close()

@app.delete("/servicios/{servicio_id}")
def eliminar_servicio(servicio_id: int):
    db = SessionLocal()

    try:
        servicio = db.get(Servicio, servicio_id)

        if servicio is None:
            return {"mensaje": "Servicio no encontrado"}

        servicio.activo = False

        db.commit()

        return {
            "mensaje": "Servicio eliminado correctamente",
            "id": servicio.id
        }

    finally:
        db.close()


@app.patch("/servicios/{servicio_id}/activar")
def activar_servicio(servicio_id: int):
    db = SessionLocal()

    try:
        servicio = db.get(Servicio, servicio_id)

        if servicio is None:
            return {"mensaje": "Servicio no encontrado"}

        servicio.activo = True

        db.commit()

        return {
            "mensaje": "Servicio activado correctamente",
            "id": servicio.id
        }

    finally:
        db.close()


@app.get("/clientes")
def obtener_clientes():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Cliente).where(Cliente.activo == True)
        )
        clientes = resultado.fetchall()

        return [
            {
                "id": cliente.id,
                "negocio_id": cliente.negocio_id,
                "nombre": cliente.nombre,
                "telefono": cliente.telefono,
                "fecha_creacion": cliente.fecha_creacion,
                "activo": cliente.activo
            }
            for cliente in clientes
        ]


@app.get("/clientes/admin")
def obtener_todos_los_clientes():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(Cliente))
        clientes = resultado.fetchall()

        return [
            {
                "id": cliente.id,
                "negocio_id": cliente.negocio_id,
                "nombre": cliente.nombre,
                "telefono": cliente.telefono,
                "fecha_creacion": cliente.fecha_creacion,
                "activo": cliente.activo
            }
            for cliente in clientes
        ]

@app.get("/clientes/{cliente_id}")
def obtener_cliente(cliente_id: int):
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Cliente).where(Cliente.id == cliente_id)
        )

        cliente = resultado.fetchone()

        if cliente is None:
            return {"mensaje": "Cliente no encontrado"}

        return {
            "id": cliente.id,
            "negocio_id": cliente.negocio_id,
            "nombre": cliente.nombre,
            "telefono": cliente.telefono,
            "fecha_creacion": cliente.fecha_creacion,
            "activo": cliente.activo
        }


@app.post("/clientes")
def crear_cliente(cliente: schemas.ClienteCrear):
    db = SessionLocal()

    try:
        nuevo_cliente = Cliente(
            negocio_id=cliente.negocio_id,
            nombre=cliente.nombre,
            telefono=cliente.telefono
        )

        db.add(nuevo_cliente)
        db.commit()
        db.refresh(nuevo_cliente)

        return {
            "mensaje": "Cliente creado correctamente",
            "id": nuevo_cliente.id
        }

    finally:
        db.close()

@app.put("/clientes/{cliente_id}")
def actualizar_cliente(
    cliente_id: int,
    cliente: schemas.ClienteActualizar
):
    db = SessionLocal()

    try:
        cliente_actual = db.get(Cliente, cliente_id)

        if cliente_actual is None:
            return {"mensaje": "Cliente no encontrado"}

        cliente_actual.nombre = cliente.nombre
        cliente_actual.telefono = cliente.telefono

        db.commit()
        db.refresh(cliente_actual)

        return {
            "mensaje": "Cliente actualizado correctamente",
            "id": cliente_actual.id
        }

    finally:
        db.close()

@app.delete("/clientes/{cliente_id}")
def eliminar_cliente(cliente_id: int):
    db = SessionLocal()

    try:
        cliente = db.get(Cliente, cliente_id)

        if cliente is None:
            return {"mensaje": "Cliente no encontrado"}

        cliente.activo = False

        db.commit()

        return {
            "mensaje": "Cliente eliminado correctamente",
            "id": cliente.id
        }

    finally:
        db.close()

@app.patch("/clientes/{cliente_id}/activar")
def activar_cliente(cliente_id: int):
    db = SessionLocal()

    try:
        cliente = db.get(Cliente, cliente_id)

        if cliente is None:
            return {"mensaje": "Cliente no encontrado"}

        cliente.activo = True

        db.commit()

        return {
            "mensaje": "Cliente activado correctamente",
            "id": cliente.id
        }

    finally:
        db.close()



@app.post("/usuarios")
def crear_usuario(usuario: schemas.UsuarioCrear):
    db = SessionLocal()

    try:
        nuevo_usuario = Usuario(
            nombre=usuario.nombre,
            email=usuario.email,
            password_hash=usuario.password
        )

        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)

        return {
            "mensaje": "Usuario creado correctamente",
            "id": nuevo_usuario.id
        }

    finally:
        db.close()


@app.get("/usuarios")
def obtener_usuarios():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Usuario)
        )

        usuarios = resultado.fetchall()

        return [
            {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "email": usuario.email,
                "fecha_creacion": usuario.fecha_creacion
            }
            for usuario in usuarios
        ]


@app.get("/usuarios/{usuario_id}")
def obtener_usuario(usuario_id: int):
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Usuario).where(Usuario.id == usuario_id)
        )

        usuario = resultado.fetchone()

        if usuario is None:
            return {
                "mensaje": "Usuario no encontrado"
            }

        return {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "email": usuario.email,
            "fecha_creacion": usuario.fecha_creacion
        }

@app.put("/usuarios/{usuario_id}")
def actualizar_usuario(
    usuario_id: int,
    usuario: schemas.UsuarioActualizar
):
    db = SessionLocal()

    try:
        usuario_actual = db.get(Usuario, usuario_id)

        if usuario_actual is None:
            return {
                "mensaje": "Usuario no encontrado"
            }

        usuario_actual.nombre = usuario.nombre
        usuario_actual.email = usuario.email

        db.commit()
        db.refresh(usuario_actual)

        return {
            "mensaje": "Usuario actualizado correctamente",
            "id": usuario_actual.id
        }

    finally:
        db.close()




@app.post("/usuarios-negocios")
def crear_usuario_negocio(
    usuario_negocio: schemas.UsuarioNegocioCrear
):
    db = SessionLocal()

    try:
        nueva_asociacion = UsuarioNegocio(
            usuario_id=usuario_negocio.usuario_id,
            negocio_id=usuario_negocio.negocio_id,
            rol=usuario_negocio.rol
        )

        db.add(nueva_asociacion)
        db.commit()
        db.refresh(nueva_asociacion)

        return {
            "mensaje": "Usuario asociado al negocio correctamente",
            "id": nueva_asociacion.id
        }

    finally:
        db.close()

@app.get("/usuarios-negocio")
def obtener_usuarios_negocio():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(UsuarioNegocio).where(UsuarioNegocio.activo == True)
        )

        asociaciones = resultado.fetchall()

        return [
            {
                "id": asociacion.id,
                "usuario_id": asociacion.usuario_id,
                "negocio_id": asociacion.negocio_id,
                "rol": asociacion.rol,
                "activo": asociacion.activo,
                "fecha_asociacion": asociacion.fecha_asociacion
            }
            for asociacion in asociaciones
        ]



@app.get("/usuarios-negocio/admin")
def obtener_usuarios_negocio_admin():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(UsuarioNegocio)
        )

        asociaciones = resultado.fetchall()

        return [
            {
                "id": asociacion.id,
                "usuario_id": asociacion.usuario_id,
                "negocio_id": asociacion.negocio_id,
                "rol": asociacion.rol,
                "activo": asociacion.activo,
                "fecha_asociacion": asociacion.fecha_asociacion
            }
            for asociacion in asociaciones
        ]



@app.get("/usuarios-negocio/{usuario_negocio_id}")
def obtener_usuario_negocio(usuario_negocio_id: int):
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(UsuarioNegocio).where(
                UsuarioNegocio.id == usuario_negocio_id
            )
        )

        asociacion = resultado.fetchone()

        if asociacion is None:
            return {
                "mensaje": "Asociación no encontrada"
            }

        return {
            "id": asociacion.id,
            "usuario_id": asociacion.usuario_id,
            "negocio_id": asociacion.negocio_id,
            "rol": asociacion.rol,
            "fecha_asociacion": asociacion.fecha_asociacion
        }

@app.put("/usuarios-negocio/{usuario_negocio_id}")
def actualizar_usuario_negocio(
    usuario_negocio_id: int,
    datos: schemas.UsuarioNegocioActualizar
):
    db = SessionLocal()

    try:
        asociacion = db.get(
            UsuarioNegocio,
            usuario_negocio_id
        )

        if asociacion is None:
            return {
                "mensaje": "Asociación no encontrada"
            }

        asociacion.rol = datos.rol

        db.commit()
        db.refresh(asociacion)

        return {
            "mensaje": "Rol actualizado correctamente",
            "id": asociacion.id
        }

    finally:
        db.close()


@app.delete("/usuarios-negocio/{usuario_negocio_id}")
def eliminar_usuario_negocio(usuario_negocio_id: int):

    db = SessionLocal()

    usuario_negocio = db.get(UsuarioNegocio, usuario_negocio_id)

    if usuario_negocio is None:
        db.close()
        return {"mensaje": "La asociación no existe"}

    usuario_negocio.activo = False

    db.commit()
    db.close()

    return {"mensaje": "Usuario desvinculado del negocio"}

@app.patch("/usuarios-negocio/{usuario_negocio_id}/activar")
def activar_usuario_negocio(usuario_negocio_id: int):

    db = SessionLocal()

    usuario_negocio = db.get(UsuarioNegocio, usuario_negocio_id)

    if usuario_negocio is None:
        db.close()
        raise HTTPException(
            status_code=404,
            detail="La asociación usuario-negocio no existe"
        )

    usuario_negocio.activo = True

    db.commit()
    db.refresh(usuario_negocio)
    db.close()

    return {
        "mensaje": "Usuario vinculado nuevamente al negocio",
        "id": usuario_negocio.id
    }


# ---------------------------------------------------------------------------
# Negocio
# ---------------------------------------------------------------------------
@app.post("/negocios")
def crear_negocio(negocio: schemas.NegocioCrear):
    db = SessionLocal()

    try:
        nuevo_negocio = Negocio(
            nombre=negocio.nombre,
            telefono=negocio.telefono,
            direccion=negocio.direccion
        )

        db.add(nuevo_negocio)
        db.commit()
        db.refresh(nuevo_negocio)

        return {
            "mensaje": "Negocio creado correctamente",
            "id": nuevo_negocio.id
        }

    finally:
        db.close()


@app.get("/negocios")
def obtener_negocios():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(Negocio))
        negocios = resultado.fetchall()

        return [
            {
                "id": negocio.id,
                "nombre": negocio.nombre,
                "telefono": negocio.telefono,
                "direccion": negocio.direccion,
                "fecha_creacion": negocio.fecha_creacion
            }
            for negocio in negocios
        ]


@app.get("/negocios/{negocio_id}")
def obtener_negocio(negocio_id: int):
    db = SessionLocal()

    try:
        negocio = db.get(Negocio, negocio_id)

        if negocio is None:
            return {"mensaje": "Negocio no encontrado"}

        return {
            "id": negocio.id,
            "nombre": negocio.nombre,
            "telefono": negocio.telefono,
            "direccion": negocio.direccion,
            "fecha_creacion": negocio.fecha_creacion
        }

    finally:
        db.close()


@app.put("/negocios/{negocio_id}")
def actualizar_negocio(negocio_id: int, datos: schemas.NegocioActualizar):
    db = SessionLocal()

    try:
        negocio = db.get(Negocio, negocio_id)

        if negocio is None:
            return {"mensaje": "Negocio no encontrado"}

        negocio.nombre = datos.nombre
        negocio.telefono = datos.telefono
        negocio.direccion = datos.direccion

        db.commit()
        db.refresh(negocio)

        return {
            "mensaje": "Negocio actualizado correctamente",
            "id": negocio.id
        }

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Producto
# ---------------------------------------------------------------------------
@app.post("/productos")
def crear_producto(producto: schemas.ProductoCrear):
    db = SessionLocal()

    try:
        nuevo_producto = Producto(
            negocio_id=producto.negocio_id,
            nombre=producto.nombre,
            descripcion=producto.descripcion,
            precio=producto.precio,
            stock=producto.stock,
            activo=True
        )

        db.add(nuevo_producto)
        db.commit()
        db.refresh(nuevo_producto)

        return {
            "mensaje": "Producto creado correctamente",
            "id": nuevo_producto.id
        }

    finally:
        db.close()


@app.get("/productos")
def obtener_productos():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Producto).where(Producto.activo == True)
        )
        productos = resultado.fetchall()

        return [
            {
                "id": producto.id,
                "negocio_id": producto.negocio_id,
                "nombre": producto.nombre,
                "descripcion": producto.descripcion,
                "precio": float(producto.precio),
                "stock": producto.stock,
                "activo": producto.activo
            }
            for producto in productos
        ]


@app.get("/productos/admin")
def obtener_todos_los_productos():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(Producto))
        productos = resultado.fetchall()

        return [
            {
                "id": producto.id,
                "negocio_id": producto.negocio_id,
                "nombre": producto.nombre,
                "descripcion": producto.descripcion,
                "precio": float(producto.precio),
                "stock": producto.stock,
                "activo": producto.activo
            }
            for producto in productos
        ]


@app.get("/productos/{producto_id}")
def obtener_producto(producto_id: int):
    db = SessionLocal()

    try:
        producto = db.get(Producto, producto_id)

        if producto is None:
            return {"mensaje": "Producto no encontrado"}

        return {
            "id": producto.id,
            "negocio_id": producto.negocio_id,
            "nombre": producto.nombre,
            "descripcion": producto.descripcion,
            "precio": float(producto.precio),
            "stock": producto.stock,
            "activo": producto.activo
        }

    finally:
        db.close()


@app.put("/productos/{producto_id}")
def actualizar_producto(producto_id: int, datos: schemas.ProductoActualizar):
    db = SessionLocal()

    try:
        producto = db.get(Producto, producto_id)

        if producto is None:
            return {"mensaje": "Producto no encontrado"}

        producto.nombre = datos.nombre
        producto.descripcion = datos.descripcion
        producto.precio = datos.precio
        producto.stock = datos.stock

        db.commit()
        db.refresh(producto)

        return {
            "mensaje": "Producto actualizado correctamente",
            "id": producto.id
        }

    finally:
        db.close()


@app.delete("/productos/{producto_id}")
def eliminar_producto(producto_id: int):
    db = SessionLocal()

    try:
        producto = db.get(Producto, producto_id)

        if producto is None:
            return {"mensaje": "Producto no encontrado"}

        producto.activo = False

        db.commit()

        return {
            "mensaje": "Producto eliminado correctamente",
            "id": producto.id
        }

    finally:
        db.close()


@app.patch("/productos/{producto_id}/activar")
def activar_producto(producto_id: int):
    db = SessionLocal()

    try:
        producto = db.get(Producto, producto_id)

        if producto is None:
            return {"mensaje": "Producto no encontrado"}

        producto.activo = True

        db.commit()

        return {
            "mensaje": "Producto activado correctamente",
            "id": producto.id
        }

    finally:
        db.close()


# ---------------------------------------------------------------------------
# EmpleadoServicio (tabla puente, sin id propio -> clave compuesta)
# ---------------------------------------------------------------------------
@app.post("/empleados-servicios")
def asignar_empleado_a_servicio(datos: schemas.EmpleadoServicioCrear):
    db = SessionLocal()

    try:
        existente = db.get(
            EmpleadoServicio,
            (datos.servicio_id, datos.usuario_negocio_id)
        )

        if existente is not None:
            return {"mensaje": "Ese empleado ya está asignado a ese servicio"}

        nueva_asignacion = EmpleadoServicio(
            servicio_id=datos.servicio_id,
            usuario_negocio_id=datos.usuario_negocio_id
        )

        db.add(nueva_asignacion)
        db.commit()

        return {
            "mensaje": "Empleado asignado al servicio correctamente",
            "servicio_id": nueva_asignacion.servicio_id,
            "usuario_negocio_id": nueva_asignacion.usuario_negocio_id
        }

    finally:
        db.close()


@app.get("/empleados-servicios")
def obtener_empleados_servicios():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(EmpleadoServicio))
        asignaciones = resultado.fetchall()

        return [
            {
                "servicio_id": asignacion.servicio_id,
                "usuario_negocio_id": asignacion.usuario_negocio_id
            }
            for asignacion in asignaciones
        ]


@app.delete("/empleados-servicios/{servicio_id}/{usuario_negocio_id}")
def quitar_empleado_de_servicio(servicio_id: int, usuario_negocio_id: int):
    db = SessionLocal()

    try:
        asignacion = db.get(
            EmpleadoServicio,
            (servicio_id, usuario_negocio_id)
        )

        if asignacion is None:
            return {"mensaje": "Esa asignación no existe"}

        db.delete(asignacion)
        db.commit()

        return {"mensaje": "Empleado desvinculado del servicio"}

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Horario
# ---------------------------------------------------------------------------
@app.post("/horarios")
def crear_horario(horario: schemas.HorarioCrear):
    db = SessionLocal()

    try:
        nuevo_horario = Horario(
            usuario_negocio_id=horario.usuario_negocio_id,
            dia_semana=horario.dia_semana,
            hora_inicio=horario.hora_inicio,
            hora_fin=horario.hora_fin,
            intervalo_minutos=horario.intervalo_minutos,
            activo=True
        )

        db.add(nuevo_horario)
        db.commit()
        db.refresh(nuevo_horario)

        return {
            "mensaje": "Horario creado correctamente",
            "id": nuevo_horario.id
        }

    finally:
        db.close()


@app.get("/horarios")
def obtener_horarios():
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(Horario).where(Horario.activo == True)
        )
        horarios = resultado.fetchall()

        return [
            {
                "id": horario.id,
                "usuario_negocio_id": horario.usuario_negocio_id,
                "dia_semana": horario.dia_semana,
                "hora_inicio": horario.hora_inicio,
                "hora_fin": horario.hora_fin,
                "intervalo_minutos": horario.intervalo_minutos,
                "activo": horario.activo
            }
            for horario in horarios
        ]


@app.get("/horarios/{horario_id}")
def obtener_horario(horario_id: int):
    db = SessionLocal()

    try:
        horario = db.get(Horario, horario_id)

        if horario is None:
            return {"mensaje": "Horario no encontrado"}

        return {
            "id": horario.id,
            "usuario_negocio_id": horario.usuario_negocio_id,
            "dia_semana": horario.dia_semana,
            "hora_inicio": horario.hora_inicio,
            "hora_fin": horario.hora_fin,
            "intervalo_minutos": horario.intervalo_minutos,
            "activo": horario.activo
        }

    finally:
        db.close()


@app.put("/horarios/{horario_id}")
def actualizar_horario(horario_id: int, datos: schemas.HorarioActualizar):
    db = SessionLocal()

    try:
        horario = db.get(Horario, horario_id)

        if horario is None:
            return {"mensaje": "Horario no encontrado"}

        horario.dia_semana = datos.dia_semana
        horario.hora_inicio = datos.hora_inicio
        horario.hora_fin = datos.hora_fin
        horario.intervalo_minutos = datos.intervalo_minutos

        db.commit()
        db.refresh(horario)

        return {
            "mensaje": "Horario actualizado correctamente",
            "id": horario.id
        }

    finally:
        db.close()


@app.delete("/horarios/{horario_id}")
def eliminar_horario(horario_id: int):
    db = SessionLocal()

    try:
        horario = db.get(Horario, horario_id)

        if horario is None:
            return {"mensaje": "Horario no encontrado"}

        horario.activo = False

        db.commit()

        return {
            "mensaje": "Horario eliminado correctamente",
            "id": horario.id
        }

    finally:
        db.close()


@app.patch("/horarios/{horario_id}/activar")
def activar_horario(horario_id: int):
    db = SessionLocal()

    try:
        horario = db.get(Horario, horario_id)

        if horario is None:
            return {"mensaje": "Horario no encontrado"}

        horario.activo = True

        db.commit()

        return {
            "mensaje": "Horario activado correctamente",
            "id": horario.id
        }

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pausa (no tiene columna "activo": eliminación es definitiva)
# ---------------------------------------------------------------------------
@app.post("/pausas")
def crear_pausa(pausa: schemas.PausaCrear):
    db = SessionLocal()

    try:
        nueva_pausa = Pausa(
            horario_id=pausa.horario_id,
            hora_inicio=pausa.hora_inicio,
            hora_fin=pausa.hora_fin,
            motivo=pausa.motivo
        )

        db.add(nueva_pausa)
        db.commit()
        db.refresh(nueva_pausa)

        return {
            "mensaje": "Pausa creada correctamente",
            "id": nueva_pausa.id
        }

    finally:
        db.close()


@app.get("/pausas")
def obtener_pausas():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(Pausa))
        pausas = resultado.fetchall()

        return [
            {
                "id": pausa.id,
                "horario_id": pausa.horario_id,
                "hora_inicio": pausa.hora_inicio,
                "hora_fin": pausa.hora_fin,
                "motivo": pausa.motivo
            }
            for pausa in pausas
        ]


@app.get("/pausas/{pausa_id}")
def obtener_pausa(pausa_id: int):
    db = SessionLocal()

    try:
        pausa = db.get(Pausa, pausa_id)

        if pausa is None:
            return {"mensaje": "Pausa no encontrada"}

        return {
            "id": pausa.id,
            "horario_id": pausa.horario_id,
            "hora_inicio": pausa.hora_inicio,
            "hora_fin": pausa.hora_fin,
            "motivo": pausa.motivo
        }

    finally:
        db.close()


@app.put("/pausas/{pausa_id}")
def actualizar_pausa(pausa_id: int, datos: schemas.PausaActualizar):
    db = SessionLocal()

    try:
        pausa = db.get(Pausa, pausa_id)

        if pausa is None:
            return {"mensaje": "Pausa no encontrada"}

        pausa.hora_inicio = datos.hora_inicio
        pausa.hora_fin = datos.hora_fin
        pausa.motivo = datos.motivo

        db.commit()
        db.refresh(pausa)

        return {
            "mensaje": "Pausa actualizada correctamente",
            "id": pausa.id
        }

    finally:
        db.close()


@app.delete("/pausas/{pausa_id}")
def eliminar_pausa(pausa_id: int):
    db = SessionLocal()

    try:
        pausa = db.get(Pausa, pausa_id)

        if pausa is None:
            return {"mensaje": "Pausa no encontrada"}

        db.delete(pausa)
        db.commit()

        return {"mensaje": "Pausa eliminada correctamente"}

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cita
# ---------------------------------------------------------------------------
@app.post("/citas")
def crear_cita(cita: schemas.CitaCrear):
    db = SessionLocal()

    try:
        nueva_cita = Cita(
            negocio_id=cita.negocio_id,
            cliente_id=cita.cliente_id,
            usuario_negocio_id=cita.usuario_negocio_id,
            fecha=cita.fecha,
            hora_inicio=cita.hora_inicio,
            hora_fin=cita.hora_fin,
            origen=cita.origen,
            motivo=cita.motivo,
            observaciones=cita.observaciones,
            estado="PENDIENTE"
        )

        db.add(nueva_cita)
        db.commit()
        db.refresh(nueva_cita)

        return {
            "mensaje": "Cita creada correctamente",
            "id": nueva_cita.id
        }

    finally:
        db.close()


@app.get("/citas")
def obtener_citas():
    with engine.connect() as conexion:
        resultado = conexion.execute(select(Cita))
        citas = resultado.fetchall()

        return [
            {
                "id": cita.id,
                "negocio_id": cita.negocio_id,
                "cliente_id": cita.cliente_id,
                "usuario_negocio_id": cita.usuario_negocio_id,
                "fecha": cita.fecha,
                "hora_inicio": cita.hora_inicio,
                "hora_fin": cita.hora_fin,
                "estado": cita.estado,
                "origen": cita.origen,
                "motivo": cita.motivo,
                "observaciones": cita.observaciones,
                "fecha_creacion": cita.fecha_creacion,
                "fecha_actualizacion": cita.fecha_actualizacion
            }
            for cita in citas
        ]


@app.get("/citas/{cita_id}")
def obtener_cita(cita_id: int):
    db = SessionLocal()

    try:
        cita = db.get(Cita, cita_id)

        if cita is None:
            return {"mensaje": "Cita no encontrada"}

        return {
            "id": cita.id,
            "negocio_id": cita.negocio_id,
            "cliente_id": cita.cliente_id,
            "usuario_negocio_id": cita.usuario_negocio_id,
            "fecha": cita.fecha,
            "hora_inicio": cita.hora_inicio,
            "hora_fin": cita.hora_fin,
            "estado": cita.estado,
            "origen": cita.origen,
            "motivo": cita.motivo,
            "observaciones": cita.observaciones,
            "fecha_creacion": cita.fecha_creacion,
            "fecha_actualizacion": cita.fecha_actualizacion
        }

    finally:
        db.close()


@app.put("/citas/{cita_id}")
def actualizar_cita(cita_id: int, datos: schemas.CitaActualizar):
    db = SessionLocal()

    try:
        cita = db.get(Cita, cita_id)

        if cita is None:
            return {"mensaje": "Cita no encontrada"}

        if datos.fecha is not None:
            cita.fecha = datos.fecha
        if datos.hora_inicio is not None:
            cita.hora_inicio = datos.hora_inicio
        if datos.hora_fin is not None:
            cita.hora_fin = datos.hora_fin
        if datos.estado is not None:
            cita.estado = datos.estado
        if datos.motivo is not None:
            cita.motivo = datos.motivo
        if datos.observaciones is not None:
            cita.observaciones = datos.observaciones

        cita.fecha_actualizacion = datetime.now()

        db.commit()
        db.refresh(cita)

        return {
            "mensaje": "Cita actualizada correctamente",
            "id": cita.id
        }

    finally:
        db.close()


@app.delete("/citas/{cita_id}")
def eliminar_cita(cita_id: int):
    db = SessionLocal()

    try:
        cita = db.get(Cita, cita_id)

        if cita is None:
            return {"mensaje": "Cita no encontrada"}

        # Borrado definitivo: servicios_de_cita y productos_de_cita
        # tienen ON DELETE CASCADE, así que se limpian solos.
        db.delete(cita)
        db.commit()

        return {"mensaje": "Cita eliminada correctamente"}

    finally:
        db.close()


def _cambiar_estado_cita(cita_id: int, nuevo_estado: str):
    db = SessionLocal()

    try:
        cita = db.get(Cita, cita_id)

        if cita is None:
            return {"mensaje": "Cita no encontrada"}

        cita.estado = nuevo_estado
        cita.fecha_actualizacion = datetime.now()

        db.commit()
        db.refresh(cita)

        return {
            "mensaje": f"Cita marcada como {nuevo_estado}",
            "id": cita.id
        }

    finally:
        db.close()


@app.patch("/citas/{cita_id}/confirmar")
def confirmar_cita(cita_id: int):
    return _cambiar_estado_cita(cita_id, "CONFIRMADA")


@app.patch("/citas/{cita_id}/cancelar")
def cancelar_cita(cita_id: int):
    return _cambiar_estado_cita(cita_id, "CANCELADA")


@app.patch("/citas/{cita_id}/completar")
def completar_cita(cita_id: int):
    return _cambiar_estado_cita(cita_id, "COMPLETADA")


@app.patch("/citas/{cita_id}/no-asistio")
def marcar_no_asistio(cita_id: int):
    return _cambiar_estado_cita(cita_id, "NO_ASISTIO")


# ---------------------------------------------------------------------------
# Servicios de una cita
# ---------------------------------------------------------------------------
@app.post("/citas/{cita_id}/servicios")
def agregar_servicio_a_cita(cita_id: int, datos: schemas.ServicioDeCitaAgregar):
    db = SessionLocal()

    try:
        cita = db.get(Cita, cita_id)

        if cita is None:
            return {"mensaje": "Cita no encontrada"}

        nuevo_servicio_cita = ServicioDeCita(
            cita_id=cita_id,
            servicio_id=datos.servicio_id,
            precio_unitario=datos.precio_unitario,
            duracion_minutos=datos.duracion_minutos,
            cantidad=datos.cantidad
        )

        db.add(nuevo_servicio_cita)
        db.commit()
        db.refresh(nuevo_servicio_cita)

        return {
            "mensaje": "Servicio agregado a la cita correctamente",
            "id": nuevo_servicio_cita.id
        }

    finally:
        db.close()


@app.get("/citas/{cita_id}/servicios")
def obtener_servicios_de_cita(cita_id: int):
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(ServicioDeCita).where(ServicioDeCita.cita_id == cita_id)
        )
        servicios = resultado.fetchall()

        return [
            {
                "id": servicio.id,
                "cita_id": servicio.cita_id,
                "servicio_id": servicio.servicio_id,
                "precio_unitario": float(servicio.precio_unitario),
                "duracion_minutos": servicio.duracion_minutos,
                "cantidad": servicio.cantidad
            }
            for servicio in servicios
        ]


@app.delete("/citas/{cita_id}/servicios/{servicio_id}")
def quitar_servicio_de_cita(cita_id: int, servicio_id: int):
    db = SessionLocal()

    try:
        servicio_cita = db.execute(
            select(ServicioDeCita).where(
                ServicioDeCita.cita_id == cita_id,
                ServicioDeCita.servicio_id == servicio_id
            )
        ).scalar_one_or_none()

        if servicio_cita is None:
            return {"mensaje": "Ese servicio no está asociado a esta cita"}

        db.delete(servicio_cita)
        db.commit()

        return {"mensaje": "Servicio quitado de la cita correctamente"}

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Productos de una cita
# ---------------------------------------------------------------------------
@app.post("/citas/{cita_id}/productos")
def agregar_producto_a_cita(cita_id: int, datos: schemas.ProductoDeCitaAgregar):
    db = SessionLocal()

    try:
        cita = db.get(Cita, cita_id)

        if cita is None:
            return {"mensaje": "Cita no encontrada"}

        nuevo_producto_cita = ProductoDeCita(
            cita_id=cita_id,
            producto_id=datos.producto_id,
            cantidad=datos.cantidad,
            precio_unitario=datos.precio_unitario
        )

        db.add(nuevo_producto_cita)
        db.commit()
        db.refresh(nuevo_producto_cita)

        return {
            "mensaje": "Producto agregado a la cita correctamente",
            "id": nuevo_producto_cita.id
        }

    finally:
        db.close()


@app.get("/citas/{cita_id}/productos")
def obtener_productos_de_cita(cita_id: int):
    with engine.connect() as conexion:
        resultado = conexion.execute(
            select(ProductoDeCita).where(ProductoDeCita.cita_id == cita_id)
        )
        productos = resultado.fetchall()

        return [
            {
                "id": producto.id,
                "cita_id": producto.cita_id,
                "producto_id": producto.producto_id,
                "cantidad": producto.cantidad,
                "precio_unitario": float(producto.precio_unitario)
            }
            for producto in productos
        ]


@app.delete("/citas/{cita_id}/productos/{producto_id}")
def quitar_producto_de_cita(cita_id: int, producto_id: int):
    db = SessionLocal()

    try:
        producto_cita = db.execute(
            select(ProductoDeCita).where(
                ProductoDeCita.cita_id == cita_id,
                ProductoDeCita.producto_id == producto_id
            )
        ).scalar_one_or_none()

        if producto_cita is None:
            return {"mensaje": "Ese producto no está asociado a esta cita"}

        db.delete(producto_cita)
        db.commit()

        return {"mensaje": "Producto quitado de la cita correctamente"}

    finally:
        db.close()