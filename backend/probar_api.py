"""
probar_api.py  -  Prueba de punta a punta de la API de Valen.

Crea sus propios datos de prueba (por la API) y comprueba reglas, permisos y
aislamiento entre negocios. No necesita instalar nada: usa solo la librería estándar.

Uso (con el servidor ya corriendo en otra terminal):
    python probar_api.py
    python probar_api.py --url http://127.0.0.1:8000
    python probar_api.py --modo-pruebas     # SOLO si arrancaste uvicorn con VALEN_MODO_PRUEBAS=1

Todos los datos llevan emails @prueba.test y nombres "TEST ...": se borran con
limpiar_datos_de_prueba.sql. Cada ejecución crea datos nuevos, así que se puede repetir.
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from urllib import error as urlerr
from urllib import request as urlreq

BASE = "http://127.0.0.1:8000"
CLAVE = "Clave12345"
SUF = str(int(time.time()))
MODO_PRUEBAS = False
ORIGEN_PERMITIDO = "http://localhost:5173"   # uno de los de VALEN_ORIGENES_PERMITIDOS

E = {}            # estado compartido: ids y tokens que se van creando
ok = 0
fallas = []
saltados = []


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def llamar(metodo, ruta, cuerpo=None, token=None):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urlreq.Request(BASE + ruta, data=datos, method=metodo)
    peticion.add_header("Content-Type", "application/json")

    if token:
        peticion.add_header("Authorization", f"Bearer {token}")

    try:
        with urlreq.urlopen(peticion, timeout=30) as respuesta:
            texto, codigo = respuesta.read().decode("utf-8"), respuesta.status
    except urlerr.HTTPError as error:
        texto, codigo = error.read().decode("utf-8"), error.code

    try:
        return codigo, (json.loads(texto) if texto else None)
    except ValueError:
        return codigo, texto


def titulo(texto):
    print(f"\n=== {texto} ===")


def probar(nombre, respuesta, esperado=200, contiene=None):
    """Compara el código HTTP (y opcionalmente un texto) y devuelve el cuerpo."""
    global ok
    codigo, cuerpo = respuesta
    texto = json.dumps(cuerpo, ensure_ascii=False)
    aceptados = esperado if isinstance(esperado, (tuple, list)) else (esperado,)
    bien = codigo in aceptados and (contiene is None or contiene.lower() in texto.lower())

    if bien:
        ok += 1
        print(f"  [OK]    {nombre}")
    else:
        extra = f" con '{contiene}'" if contiene else ""
        fallas.append(nombre)
        print(f"  [FALLA] {nombre}")
        print(f"          esperaba {'/'.join(map(str, aceptados))}{extra}; llegó {codigo}: {texto[:350]}")

    return cuerpo


def verificar(nombre, condicion, detalle=""):
    global ok

    if condicion:
        ok += 1
        print(f"  [OK]    {nombre}")
    else:
        fallas.append(nombre)
        print(f"  [FALLA] {nombre}  {detalle}")


def requiere(*claves):
    faltan = [c for c in claves if E.get(c) is None]

    if faltan:
        saltados.append(f"{', '.join(faltan)}")
        print(f"  [SALTADO] falta {', '.join(faltan)} (falló un paso anterior)")
        return False

    return True


def id_de(cuerpo):
    return cuerpo.get("id") if isinstance(cuerpo, dict) else None


def campo(cuerpo, nombre):
    return cuerpo.get(nombre) if isinstance(cuerpo, dict) else None


def login(email, negocio_id=None):
    cuerpo = {"email": email, "password": CLAVE}

    if negocio_id is not None:
        cuerpo["negocio_id"] = negocio_id

    return llamar("POST", "/auth/login", cuerpo)


def proximo_dia(dia_semana, minimo_dias):
    """Primer día con ese weekday (0=lunes ... 6=domingo) que esté al menos N días adelante."""
    dia = date.today() + timedelta(days=minimo_dias)

    while dia.weekday() != dia_semana:
        dia += timedelta(days=1)

    return dia


LUNES = proximo_dia(0, 3)
DOMINGO = proximo_dia(6, 1)


def cita_body(cliente, fecha, hora, servicios, empleado=None, **extra):
    cuerpo = {
        "cliente_id": cliente,
        "fecha": fecha.isoformat(),
        "hora_inicio": hora,
        "servicios": [{"servicio_id": s} if isinstance(s, int) else s for s in servicios],
    }

    if empleado is not None:
        cuerpo["usuario_negocio_id"] = empleado

    cuerpo.update(extra)
    return cuerpo


# ---------------------------------------------------------------------------
# 1. Registro, login y sesiones
# ---------------------------------------------------------------------------
def s1_registro_y_login():
    titulo("1. Registro, login y sesiones")

    for clave, nombre in (("ana", "TEST Ana"), ("bruno", "TEST Bruno"),
                          ("carla", "TEST Carla"), ("dani", "TEST Dani")):
        E[f"{clave}_email"] = f"{clave}.{SUF}@prueba.test"
        cuerpo = probar(
            f"registrar a {clave}",
            llamar("POST", "/usuarios", {"nombre": nombre, "email": E[f"{clave}_email"], "password": CLAVE}),
        )
        E[f"{clave}_id"] = id_de(cuerpo)

    probar("email repetido -> 409",
           llamar("POST", "/usuarios", {"nombre": "X", "email": E["ana_email"], "password": CLAVE}), 409, "email")
    probar("email repetido en MAYÚSCULAS -> 409 (no distingue mayúsculas)",
           llamar("POST", "/usuarios", {"nombre": "X", "email": E["ana_email"].upper(), "password": CLAVE}), 409)
    probar("email sin formato -> 422",
           llamar("POST", "/usuarios", {"nombre": "X", "email": "sin-arroba", "password": CLAVE}), 422)
    probar("contraseña de 3 caracteres -> 422",
           llamar("POST", "/usuarios", {"nombre": "X", "email": f"x.{SUF}@prueba.test", "password": "123"}), 422)

    probar("login con contraseña incorrecta -> 401",
           login_con(E["ana_email"], "incorrecta"), 401, "incorrectos")
    probar("login con email inexistente -> 401 (mismo mensaje, no revela si existe)",
           login_con(f"nadie.{SUF}@prueba.test", CLAVE), 401, "incorrectos")

    cuerpo = probar("login de Ana (aún sin ningún negocio)", login(E["ana_email"]), 200, "ningún negocio")
    E["tok_ana_u"] = campo(cuerpo, "access_token")
    verificar("...el token viene sin negocio", campo(cuerpo, "negocio_id") is None)

    probar("sin token -> 401", llamar("GET", "/servicios"), 401, "token")
    probar("token falso -> 401", llamar("GET", "/servicios", token="abc.def.ghi"), 401, "inválido")

    if requiere("tok_ana_u"):
        probar("token sin negocio elegido -> 403", llamar("GET", "/servicios", token=E["tok_ana_u"]), 403, "elige un negocio")
        probar("GET /auth/me con token sin negocio", llamar("GET", "/auth/me", token=E["tok_ana_u"]), 200, E["ana_email"])


def login_con(email, password):
    return llamar("POST", "/auth/login", {"email": email, "password": password})


# ---------------------------------------------------------------------------
# 2. Negocio y catálogo (Ana)
# ---------------------------------------------------------------------------
def s2_negocio_y_catalogo():
    titulo("2. Negocio, servicios y productos (Ana)")

    if not requiere("tok_ana_u"):
        return

    probar("negocio sin nombre -> 422",
           llamar("POST", "/negocios", {"nombre": ""}, E["tok_ana_u"]), 422)
    probar("negocio con teléfono inválido -> 422",
           llamar("POST", "/negocios", {"nombre": "TEST X", "telefono": "abc"}, E["tok_ana_u"]), 422)

    cuerpo = probar("Ana crea 'TEST Salón Bella' y queda como ADMIN",
                    llamar("POST", "/negocios", {"nombre": "TEST Salón Bella", "telefono": "(601) 555-0101",
                                                 "direccion": "Calle 1 # 2-3"}, E["tok_ana_u"]), 200, "ADMIN")
    E["negocio_a"] = id_de(cuerpo)

    if not requiere("negocio_a"):
        return

    cuerpo = probar("Ana elige su negocio (token nuevo)",
                    llamar("POST", f"/auth/negocio/{E['negocio_a']}", token=E["tok_ana_u"]), 200)
    E["tok_ana"] = campo(cuerpo, "access_token")

    if not requiere("tok_ana"):
        return

    T = E["tok_ana"]
    cuerpo = probar("GET /auth/me muestra negocio y rol", llamar("GET", "/auth/me", token=T), 200, "ADMIN")
    verificar("...negocio_id coincide", campo(cuerpo, "negocio_id") == E["negocio_a"])

    cuerpo = probar("GET /negocios/{id}: el teléfono se guardó normalizado",
                    llamar("GET", f"/negocios/{E['negocio_a']}", token=T), 200, "6015550101")
    probar("PUT /negocios/{id}", llamar("PUT", f"/negocios/{E['negocio_a']}",
                                        {"nombre": "TEST Salón Bella", "telefono": "6015550101",
                                         "direccion": "Calle 1 # 2-3"}, T))

    # --- servicios
    for clave, nombre, minutos, precio in (("corte", "TEST Corte", 30, 25000),
                                           ("tinte", "TEST Tinte", 90, 120000),
                                           ("manicure", "TEST Manicure", 45, 40000)):
        cuerpo = probar(f"crear servicio {nombre}",
                        llamar("POST", "/servicios", {"nombre": nombre, "duracion_minutos": minutos, "precio": precio}, T))
        E[f"srv_{clave}"] = id_de(cuerpo)

    probar("servicio con duración 0 -> 422",
           llamar("POST", "/servicios", {"nombre": "X", "duracion_minutos": 0, "precio": 10}, T), 422)
    probar("servicio con precio negativo -> 422",
           llamar("POST", "/servicios", {"nombre": "X", "duracion_minutos": 30, "precio": -5}, T), 422)
    probar("servicio sin nombre -> 422",
           llamar("POST", "/servicios", {"nombre": "   ", "duracion_minutos": 30, "precio": 5}, T), 422)
    cuerpo = probar("GET /servicios", llamar("GET", "/servicios", token=T))
    verificar("...hay 3 servicios", isinstance(cuerpo, list) and len(cuerpo) == 3, f"(hay {len(cuerpo) if isinstance(cuerpo, list) else '?'})")

    # --- productos
    cuerpo = probar("crear producto Shampoo (stock 5)",
                    llamar("POST", "/productos", {"nombre": "TEST Shampoo", "precio": 30000, "stock": 5}, T))
    E["prod_shampoo"] = id_de(cuerpo)
    cuerpo = probar("crear producto Cera (sin control de stock)",
                    llamar("POST", "/productos", {"nombre": "TEST Cera", "precio": 15000}, T))
    E["prod_cera"] = id_de(cuerpo)
    probar("producto con stock negativo -> 422",
           llamar("POST", "/productos", {"nombre": "X", "precio": 1, "stock": -1}, T), 422)
    probar("GET /productos/admin", llamar("GET", "/productos/admin", token=T))


# ---------------------------------------------------------------------------
# 3. Equipo, permisos por rol y asignaciones
# ---------------------------------------------------------------------------
def s3_equipo_y_permisos():
    titulo("3. Equipo, permisos por rol y asignaciones")

    if not requiere("tok_ana", "bruno_email", "srv_corte", "srv_tinte", "srv_manicure"):
        return

    T = E["tok_ana"]

    cuerpo = probar("Ana vincula a Bruno por email como EMPLEADO",
                    llamar("POST", "/usuarios-negocios", {"email": E["bruno_email"], "rol": "EMPLEADO"}, T))
    E["un_bruno"] = id_de(cuerpo)
    probar("vincular otra vez -> 409",
           llamar("POST", "/usuarios-negocios", {"email": E["bruno_email"], "rol": "EMPLEADO"}, T), 409, "vinculado")
    probar("email que no existe -> 404",
           llamar("POST", "/usuarios-negocios", {"email": f"nadie.{SUF}@prueba.test", "rol": "EMPLEADO"}, T), 404, "No existe")
    probar("rol inválido -> 422",
           llamar("POST", "/usuarios-negocios", {"email": E["carla_email"], "rol": "JEFE"}, T), 422)

    lista = probar("GET /usuarios-negocio (admin)", llamar("GET", "/usuarios-negocio", token=T))
    if isinstance(lista, list):
        E["un_ana"] = next((v["id"] for v in lista if v["usuario_id"] == E["ana_id"]), None)

    cuerpo = probar("Bruno inicia sesión: queda en el único negocio que tiene", login(E["bruno_email"]), 200, "EMPLEADO")
    E["tok_bruno"] = campo(cuerpo, "access_token")
    verificar("...negocio elegido automáticamente", campo(cuerpo, "negocio_id") == E["negocio_a"])

    if not requiere("tok_bruno", "un_bruno", "un_ana"):
        return

    B = E["tok_bruno"]

    # --- lo que un EMPLEADO NO puede hacer
    probar("EMPLEADO no crea servicios -> 403",
           llamar("POST", "/servicios", {"nombre": "X", "duracion_minutos": 30, "precio": 1}, B), 403, "administradores")
    probar("EMPLEADO no crea productos -> 403",
           llamar("POST", "/productos", {"nombre": "X", "precio": 1}, B), 403)
    probar("EMPLEADO no ve /servicios/admin -> 403", llamar("GET", "/servicios/admin", token=B), 403)
    probar("EMPLEADO no ve /usuarios-negocio -> 403", llamar("GET", "/usuarios-negocio", token=B), 403)
    probar("EMPLEADO no ve /usuarios -> 403", llamar("GET", "/usuarios", token=B), 403)
    probar("EMPLEADO no vincula personas -> 403",
           llamar("POST", "/usuarios-negocios", {"email": E["carla_email"], "rol": "EMPLEADO"}, B), 403)
    probar("EMPLEADO no cambia el negocio -> 403",
           llamar("PUT", f"/negocios/{E['negocio_a']}", {"nombre": "Hackeado"}, B), 403)
    probar("EMPLEADO no crea horarios -> 403",
           llamar("POST", "/horarios", {"usuario_negocio_id": E["un_bruno"], "dia_semana": 2,
                                        "hora_inicio": "09:00", "hora_fin": "10:00"}, B), 403)

    # --- lo que un EMPLEADO SÍ puede
    probar("EMPLEADO lee servicios", llamar("GET", "/servicios", token=B))
    probar("EMPLEADO lee productos", llamar("GET", "/productos", token=B))
    cuerpo = probar("EMPLEADO crea clientes",
                    llamar("POST", "/clientes", {"nombre": "TEST Extra", "telefono": "3001112222"}, B))
    E["cli_extra"] = id_de(cuerpo)

    # --- asignaciones empleado-servicio (Ana)
    for etiqueta, servicio, empleado in (("Bruno hace Corte", "corte", "un_bruno"), ("Bruno hace Tinte", "tinte", "un_bruno"),
                                         ("Ana hace Corte", "corte", "un_ana"), ("Ana hace Manicure", "manicure", "un_ana")):
        probar(f"asignar: {etiqueta}",
               llamar("POST", "/empleados-servicios", {"servicio_id": E[f"srv_{servicio}"], "usuario_negocio_id": E[empleado]}, T))

    probar("asignación repetida -> 409",
           llamar("POST", "/empleados-servicios", {"servicio_id": E["srv_corte"], "usuario_negocio_id": E["un_bruno"]}, T), 409)
    probar("servicio inexistente -> 404",
           llamar("POST", "/empleados-servicios", {"servicio_id": 999999999, "usuario_negocio_id": E["un_bruno"]}, T), 404)
    probar("EMPLEADO no asigna -> 403",
           llamar("POST", "/empleados-servicios", {"servicio_id": E["srv_manicure"], "usuario_negocio_id": E["un_bruno"]}, B), 403)
    cuerpo = probar("EMPLEADO lee las asignaciones", llamar("GET", "/empleados-servicios", token=B))
    verificar("...hay 4", isinstance(cuerpo, list) and len(cuerpo) == 4)


# ---------------------------------------------------------------------------
# 4. Horarios y pausas
# ---------------------------------------------------------------------------
def s4_horarios_y_pausas():
    titulo("4. Horarios y pausas")

    if not requiere("tok_ana", "tok_bruno", "un_bruno", "un_ana"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]

    def horario(un, dia, ini, fin, intervalo=30):
        return {"usuario_negocio_id": un, "dia_semana": dia, "hora_inicio": ini, "hora_fin": fin, "intervalo_minutos": intervalo}

    cuerpo = probar("horario de Bruno: lunes 09:00-18:00", llamar("POST", "/horarios", horario(E["un_bruno"], 1, "09:00", "18:00"), T))
    E["h_bruno"] = id_de(cuerpo)
    cuerpo = probar("horario de Ana: lunes 09:00-17:00", llamar("POST", "/horarios", horario(E["un_ana"], 1, "09:00", "17:00"), T))
    E["h_ana"] = id_de(cuerpo)

    probar("horario que se pisa (17:00-19:00) -> 409",
           llamar("POST", "/horarios", horario(E["un_bruno"], 1, "17:00", "19:00"), T), 409, "superpone")
    probar("sábado 09-12 y luego 12-14 (pegados) -> permitido",
           llamar("POST", "/horarios", horario(E["un_bruno"], 6, "09:00", "12:00"), T))
    probar("...el pegado 12:00-14:00",
           llamar("POST", "/horarios", horario(E["un_bruno"], 6, "12:00", "14:00"), T))
    probar("...pero 11:00-13:00 pisa a los dos -> 409",
           llamar("POST", "/horarios", horario(E["un_bruno"], 6, "11:00", "13:00"), T), 409, "superpone")
    probar("día 8 -> 422", llamar("POST", "/horarios", horario(E["un_bruno"], 8, "09:00", "10:00"), T), 422)
    probar("inicio después del fin -> 422", llamar("POST", "/horarios", horario(E["un_bruno"], 3, "18:00", "09:00"), T), 422)
    probar("intervalo 0 -> 422", llamar("POST", "/horarios", horario(E["un_bruno"], 3, "09:00", "10:00", 0), T), 422)
    probar("empleado inexistente -> 404", llamar("POST", "/horarios", horario(999999999, 3, "09:00", "10:00"), T), 404)

    probar("EMPLEADO lee horarios", llamar("GET", "/horarios", token=B))
    if requiere("h_bruno"):
        probar("EMPLEADO lee un horario", llamar("GET", f"/horarios/{E['h_bruno']}", token=B))

        # --- pausas
        def pausa(ini, fin, motivo=None):
            return {"horario_id": E["h_bruno"], "hora_inicio": ini, "hora_fin": fin, "motivo": motivo}

        cuerpo = probar("pausa de almuerzo 12:00-13:00", llamar("POST", "/pausas", pausa("12:00", "13:00", "Almuerzo"), T))
        E["pausa_alm"] = id_de(cuerpo)
        probar("pausa que se pisa (12:30-13:30) -> 409", llamar("POST", "/pausas", pausa("12:30", "13:30"), T), 409, "superpone")
        probar("pausa fuera del horario (08:00-08:30) -> 409", llamar("POST", "/pausas", pausa("08:00", "08:30"), T), 409, "dentro del horario")
        cuerpo = probar("pausa pegada 13:00-14:00 -> permitida", llamar("POST", "/pausas", pausa("13:00", "14:00"), T))
        if id_de(cuerpo):
            probar("...y se elimina", llamar("DELETE", f"/pausas/{id_de(cuerpo)}", token=T))
        probar("EMPLEADO no crea pausas -> 403", llamar("POST", "/pausas", pausa("15:00", "15:30"), B), 403)
        probar("EMPLEADO lee pausas", llamar("GET", "/pausas", token=B))


# ---------------------------------------------------------------------------
# 5. Clientes
# ---------------------------------------------------------------------------
def s5_clientes():
    titulo("5. Clientes")

    if not requiere("tok_ana", "tok_bruno"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]

    cuerpo = probar("crear a Laura con teléfono '(300) 123-4567'",
                    llamar("POST", "/clientes", {"nombre": "TEST Laura", "telefono": "(300) 123-4567"}, T))
    E["cli_laura"] = id_de(cuerpo)

    if requiere("cli_laura"):
        cuerpo = probar("el teléfono quedó normalizado", llamar("GET", f"/clientes/{E['cli_laura']}", token=T), 200, "3001234567")

    probar("mismo teléfono escrito distinto ('300 123 4567') -> 409",
           llamar("POST", "/clientes", {"nombre": "TEST Otra", "telefono": "300 123 4567"}, T), 409, "teléfono")
    probar("teléfono 'abc' -> 422", llamar("POST", "/clientes", {"nombre": "X", "telefono": "abc"}, T), 422)
    probar("teléfono muy corto -> 422", llamar("POST", "/clientes", {"nombre": "X", "telefono": "123"}, T), 422)

    for clave, nombre, telefono in (("marcos", "TEST Marcos", "3109998877"), ("sofia", "TEST Sofia", "3205551234"),
                                    ("pedro", "TEST Pedro", "3151112233"), ("sincitas", "TEST SinCitas", "3004445566")):
        cuerpo = probar(f"crear a {nombre}", llamar("POST", "/clientes", {"nombre": nombre, "telefono": telefono}, T))
        E[f"cli_{clave}"] = id_de(cuerpo)

    if requiere("cli_marcos"):
        probar("cambiar el teléfono de Marcos por el de Laura -> 409",
               llamar("PUT", f"/clientes/{E['cli_marcos']}", {"nombre": "TEST Marcos", "telefono": "3001234567"}, T), 409)
        probar("EMPLEADO puede editar clientes (con su propio teléfono)",
               llamar("PUT", f"/clientes/{E['cli_marcos']}", {"nombre": "TEST Marcos", "telefono": "3109998877"}, B))


# ---------------------------------------------------------------------------
# 6. Citas: reglas de agenda
# ---------------------------------------------------------------------------
def s6_citas_reglas_de_agenda():
    titulo(f"6. Citas: reglas de agenda (lunes {LUNES}, domingo {DOMINGO})")

    if not requiere("tok_ana", "tok_bruno", "un_bruno", "un_ana", "srv_corte", "srv_tinte", "srv_manicure",
                    "cli_laura", "cli_marcos", "cli_sofia", "cli_pedro", "cli_extra", "h_bruno", "pausa_alm"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]
    corte, tinte, manicure = E["srv_corte"], E["srv_tinte"], E["srv_manicure"]
    bruno, ana = E["un_bruno"], E["un_ana"]

    cuerpo = probar("Laura con Bruno: Corte a las 10:00",
                    llamar("POST", "/citas", cita_body(E["cli_laura"], LUNES, "10:00", [corte], bruno), B), 200, "10:30")
    E["cita_laura"] = id_de(cuerpo)
    verificar("...el servidor calculó hora_fin 10:30 y total 25000", campo(cuerpo, "hora_fin") == "10:30" and campo(cuerpo, "total_servicios") == 25000.0)

    probar("empieza a las 10:10 (fuera de la cuadrícula de 30 min) -> 409",
           llamar("POST", "/citas", cita_body(E["cli_sofia"], LUNES, "10:10", [corte], bruno), B), 409, "turno válido")
    probar("Bruno ya tiene cita a las 10:00 -> 409",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "10:00", [corte], bruno), B), 409, "El empleado ya tiene")
    probar("Laura ya tiene cita a las 10:00 (con otro empleado) -> 409",
           llamar("POST", "/citas", cita_body(E["cli_laura"], LUNES, "10:00", [corte], ana), T), 409, "El cliente ya tiene")
    probar("a las 12:00 cae en el almuerzo -> 409",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "12:00", [corte], bruno), B), 409, "pausa")
    probar("a las 08:00 es antes del horario -> 409",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "08:00", [corte], bruno), B), 409, "fuera del horario")
    probar("en domingo Bruno no trabaja -> 409",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], DOMINGO, "10:00", [corte], bruno), B), 409, "no trabaja")
    probar("Bruno no hace Manicure -> 400",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "15:00", [manicure], bruno), B), 400, "no tiene asignado")
    probar("fecha pasada -> 400",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], date.today() - timedelta(days=1), "10:00", [corte], bruno), B), 400, "pasado")
    probar("servicio repetido en la misma cita -> 422",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "15:00", [corte, corte], bruno), B), 422, "repitas")
    probar("cita sin servicios -> 422",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "15:00", [], bruno), B), 422)
    probar("servicio con cantidad 0 -> 422",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "15:00", [{"servicio_id": corte, "cantidad": 0}], bruno), B), 422)
    probar("EMPLEADO no agenda citas para otro empleado -> 403",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "15:00", [corte], ana), B), 403, "para ti")

    if not MODO_PRUEBAS:
        cerca = datetime.now() + timedelta(minutes=30)
        probar("CLIENTE con solo 30 min de antelación -> 400",
               llamar("POST", "/citas", {"cliente_id": E["cli_marcos"], "fecha": cerca.date().isoformat(),
                                         "hora_inicio": cerca.strftime("%H:%M:%S"), "servicios": [{"servicio_id": corte}],
                                         "usuario_negocio_id": bruno}, B), 400, "al menos 60 minutos")
        probar("CLIENTE con 90 días de antelación -> 400",
               llamar("POST", "/citas", cita_body(E["cli_marcos"], date.today() + timedelta(days=90), "10:00", [corte], bruno), B),
               400, "más de 60 días")
    else:
        print("  [--]    (modo pruebas: se omiten las reglas de antelación)")

    cuerpo = probar("Sofia con Bruno: Corte a las 11:00",
                    llamar("POST", "/citas", cita_body(E["cli_sofia"], LUNES, "11:00", [corte], bruno), B))
    E["cita_sofia"] = id_de(cuerpo)

    cuerpo = probar("Marcos con Bruno: Corte + Tinte a las 14:00",
                    llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "14:00", [corte, tinte], bruno), B), 200, "16:00")
    E["cita_marcos_largo"] = id_de(cuerpo)
    verificar("...dura 120 min (hora_fin 16:00) y suma 145000", campo(cuerpo, "hora_fin") == "16:00" and campo(cuerpo, "total_servicios") == 145000.0)

    cuerpo = probar("Extra con Bruno a las 16:30 (sin indicar empleado: queda para quien la crea)",
                    llamar("POST", "/citas", cita_body(E["cli_extra"], LUNES, "16:30", [corte]), B))
    E["cita_extra"] = id_de(cuerpo)
    if requiere("cita_extra"):
        cuerpo = probar("...se asignó a Bruno", llamar("GET", f"/citas/{E['cita_extra']}", token=B))
        verificar("...usuario_negocio_id es el de Bruno", campo(cuerpo, "usuario_negocio_id") == bruno)

    cuerpo = probar("Pedro con Ana (ADMIN) a las 09:00, sin indicar empleado",
                    llamar("POST", "/citas", cita_body(E["cli_pedro"], LUNES, "09:00", [corte]), T))
    E["cita_pedro"] = id_de(cuerpo)

    cuerpo = probar("GET /citas (EMPLEADO ve las del negocio)", llamar("GET", "/citas", token=B))
    verificar("...hay 5 citas", isinstance(cuerpo, list) and len(cuerpo) == 5, f"(hay {len(cuerpo) if isinstance(cuerpo, list) else '?'})")


# ---------------------------------------------------------------------------
# 7. Servicios y productos dentro de una cita
# ---------------------------------------------------------------------------
def s7_servicios_y_productos_de_cita():
    titulo("7. Servicios y productos dentro de una cita")

    if not requiere("tok_ana", "tok_bruno", "cita_laura", "cita_sofia", "cita_marcos_largo", "cita_pedro",
                    "srv_corte", "srv_tinte", "prod_shampoo", "prod_cera"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]
    corte, tinte = E["srv_corte"], E["srv_tinte"]
    laura, sofia, marcos, pedro = E["cita_laura"], E["cita_sofia"], E["cita_marcos_largo"], E["cita_pedro"]
    shampoo, cera = E["prod_shampoo"], E["prod_cera"]

    probar("alargar la cita de Laura con Tinte choca con la de Sofia (11:00) -> 409",
           llamar("POST", f"/citas/{laura}/servicios", {"servicio_id": tinte}, B), 409, "El empleado ya tiene")
    cuerpo = probar("quitar Tinte a la cita larga de Marcos: baja a 14:30",
                    llamar("DELETE", f"/citas/{marcos}/servicios/{tinte}", token=B), 200, "14:30")
    cuerpo = probar("volver a agregarle Tinte: sube a 16:00 (sí hay hueco)",
                    llamar("POST", f"/citas/{marcos}/servicios", {"servicio_id": tinte}, B), 200, "16:00")
    probar("agregar un servicio que ya está -> 409",
           llamar("POST", f"/citas/{marcos}/servicios", {"servicio_id": corte}, B), 409, "ya está")
    probar("quitar un servicio que no es de la cita -> 404",
           llamar("DELETE", f"/citas/{marcos}/servicios/999999999", token=B), 404)
    probar("no se puede dejar una cita sin servicios -> 409",
           llamar("DELETE", f"/citas/{pedro}/servicios/{corte}", token=T), 409, "al menos un servicio")
    cuerpo = probar("GET servicios de la cita", llamar("GET", f"/citas/{marcos}/servicios", token=B))
    verificar("...tiene 2 servicios con el precio copiado", isinstance(cuerpo, list) and len(cuerpo) == 2
              and {s["precio_unitario"] for s in cuerpo} == {25000.0, 120000.0})

    # --- productos
    probar("agregar Shampoo x2 a la cita de Laura", llamar("POST", f"/citas/{laura}/productos", {"producto_id": shampoo, "cantidad": 2}, B))
    probar("agregar el mismo producto otra vez -> 409",
           llamar("POST", f"/citas/{laura}/productos", {"producto_id": shampoo, "cantidad": 1}, B), 409, "ya está")
    probar("Cera x999 (sin control de stock) -> permitido",
           llamar("POST", f"/citas/{laura}/productos", {"producto_id": cera, "cantidad": 999}, B))
    probar("cantidad 0 -> 422", llamar("POST", f"/citas/{sofia}/productos", {"producto_id": shampoo, "cantidad": 0}, B), 422)
    probar("Shampoo x6 con stock 5 -> 409",
           llamar("POST", f"/citas/{sofia}/productos", {"producto_id": shampoo, "cantidad": 6}, B), 409, "Stock insuficiente")
    probar("producto inexistente -> 404",
           llamar("POST", f"/citas/{sofia}/productos", {"producto_id": 999999999, "cantidad": 1}, B), 404)
    probar("Shampoo x1 a Sofia", llamar("POST", f"/citas/{sofia}/productos", {"producto_id": shampoo, "cantidad": 1}, B))
    probar("...y se quita", llamar("DELETE", f"/citas/{sofia}/productos/{shampoo}", token=B))
    probar("quitar un producto que no está -> 404", llamar("DELETE", f"/citas/{sofia}/productos/{shampoo}", token=B), 404)
    cuerpo = probar("GET productos de la cita de Laura", llamar("GET", f"/citas/{laura}/productos", token=B))
    verificar("...2 productos, Shampoo a precio del servidor (30000)",
              isinstance(cuerpo, list) and len(cuerpo) == 2 and any(p["precio_unitario"] == 30000.0 for p in cuerpo))

    # --- permisos sobre la cita de otra persona
    probar("EMPLEADO no agrega productos a la cita de Ana -> 403",
           llamar("POST", f"/citas/{pedro}/productos", {"producto_id": shampoo, "cantidad": 1}, B), 403, "propias citas")
    probar("ADMIN sí agrega Shampoo x2 a la cita de Pedro",
           llamar("POST", f"/citas/{pedro}/productos", {"producto_id": shampoo, "cantidad": 2}, T))


# ---------------------------------------------------------------------------
# 8. Estados, reprogramar y eliminar
# ---------------------------------------------------------------------------
def s8_estados():
    titulo("8. Estados, reprogramar y eliminar citas")

    if not requiere("tok_ana", "tok_bruno", "cita_laura", "cita_sofia", "cita_pedro", "cli_marcos", "un_bruno", "srv_corte", "prod_shampoo"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]
    laura, sofia, pedro = E["cita_laura"], E["cita_sofia"], E["cita_pedro"]

    probar("PENDIENTE -> COMPLETADA directo -> 409",
           llamar("PATCH", f"/citas/{laura}/completar", token=B), 409, "No se puede pasar de PENDIENTE a COMPLETADA")
    probar("Bruno confirma su cita", llamar("PATCH", f"/citas/{laura}/confirmar", token=B))
    probar("confirmar otra vez -> 409", llamar("PATCH", f"/citas/{laura}/confirmar", token=B), 409)
    probar("una cita CONFIRMADA no se elimina -> 409 (se cancela)",
           llamar("DELETE", f"/citas/{laura}", token=T), 409, "historial")

    probar("Bruno cancela la cita de Sofia", llamar("PATCH", f"/citas/{sofia}/cancelar", token=B))
    probar("una cita CANCELADA no se puede confirmar -> 409",
           llamar("PATCH", f"/citas/{sofia}/confirmar", token=B), 409, "estado final")
    probar("...ni modificar", llamar("PUT", f"/citas/{sofia}", {"motivo": "x"}, B), 409, "No se puede modificar")

    # El hueco de la cita cancelada queda libre
    cuerpo = probar("la cita CANCELADA libera el hueco: Marcos puede tomar las 11:00",
                    llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "11:00", [E["srv_corte"]], E["un_bruno"]), B))
    E["cita_marcos_corto"] = id_de(cuerpo)

    if requiere("cita_marcos_corto"):
        corto = E["cita_marcos_corto"]
        cuerpo = probar("reprogramar a las 11:30", llamar("PUT", f"/citas/{corto}", {"hora_inicio": "11:30"}, B))
        cuerpo = probar("...se movió también la hora de fin", llamar("GET", f"/citas/{corto}", token=B))
        verificar("...11:30 a 12:00", campo(cuerpo, "hora_inicio") == "11:30:00" and campo(cuerpo, "hora_fin") == "12:00:00")
        probar("reprogramar a las 10:00 (choca con Laura) -> 409",
               llamar("PUT", f"/citas/{corto}", {"hora_inicio": "10:00"}, B), 409, "El empleado ya tiene")
        probar("reprogramar a las 11:10 (fuera de cuadrícula) -> 409",
               llamar("PUT", f"/citas/{corto}", {"hora_inicio": "11:10"}, B), 409, "turno válido")
        probar("reprogramar a una fecha pasada -> 400",
               llamar("PUT", f"/citas/{corto}", {"fecha": (date.today() - timedelta(days=2)).isoformat()}, B), 400, "pasado")
        probar("poner motivo", llamar("PUT", f"/citas/{corto}", {"motivo": "Primera vez"}, B))
        probar("borrar el motivo enviando null", llamar("PUT", f"/citas/{corto}", {"motivo": None}, B))
        probar("EMPLEADO no elimina citas -> 403", llamar("DELETE", f"/citas/{corto}", token=B), 403)

    probar("ADMIN elimina una cita CANCELADA", llamar("DELETE", f"/citas/{sofia}", token=T))
    probar("...ya no existe -> 404", llamar("GET", f"/citas/{sofia}", token=T), 404)

    # --- completar con descuento de stock (cita de Pedro, con Ana)
    probar("Ana confirma la cita de Pedro", llamar("PATCH", f"/citas/{pedro}/confirmar", token=T))
    if not MODO_PRUEBAS:
        probar("completar una cita que aún no empezó -> 409",
               llamar("PATCH", f"/citas/{pedro}/completar", token=T), 409, "aún no ha empezado")
        probar("marcar no-asistió antes de la hora -> 409",
               llamar("PATCH", f"/citas/{pedro}/no-asistio", token=T), 409, "aún no ha empezado")
        print("  [--]    (para probar el descuento de stock reinicia el servidor con VALEN_MODO_PRUEBAS=1 y corre con --modo-pruebas)")
    else:
        probar("completar la cita de Pedro (modo pruebas)", llamar("PATCH", f"/citas/{pedro}/completar", token=T))
        cuerpo = probar("el stock del Shampoo bajó de 5 a 3", llamar("GET", f"/productos/{E['prod_shampoo']}", token=T))
        verificar("...stock 3", campo(cuerpo, "stock") == 3, f"(stock {campo(cuerpo, 'stock')})")
        probar("una cita COMPLETADA no se modifica -> 409", llamar("PUT", f"/citas/{pedro}", {"motivo": "x"}, T), 409, "No se puede modificar")
        probar("...ni se elimina -> 409", llamar("DELETE", f"/citas/{pedro}", token=T), 409, "historial")
        probar("...ni se vuelve a completar -> 409", llamar("PATCH", f"/citas/{pedro}/completar", token=T), 409)


# ---------------------------------------------------------------------------
# 9. Reasignar citas
# ---------------------------------------------------------------------------
def s9_reasignar():
    titulo("9. Reasignar citas a otro empleado")

    if not requiere("tok_ana", "tok_bruno", "cita_marcos_largo", "cita_marcos_corto", "un_ana", "un_bruno"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]

    probar("Ana no hace Tinte: no se le puede reasignar la cita larga -> 400",
           llamar("PATCH", f"/citas/{E['cita_marcos_largo']}/reasignar", {"usuario_negocio_id": E["un_ana"]}, T), 400, "no tiene asignado")
    probar("reasignar al mismo empleado -> 400",
           llamar("PATCH", f"/citas/{E['cita_marcos_corto']}/reasignar", {"usuario_negocio_id": E["un_bruno"]}, T), 400, "ya está asignada")
    probar("EMPLEADO no reasigna -> 403",
           llamar("PATCH", f"/citas/{E['cita_marcos_corto']}/reasignar", {"usuario_negocio_id": E["un_ana"]}, B), 403)
    probar("empleado inexistente -> 404",
           llamar("PATCH", f"/citas/{E['cita_marcos_corto']}/reasignar", {"usuario_negocio_id": 999999999}, T), 404)
    probar("la cita corta (solo Corte) sí pasa a Ana",
           llamar("PATCH", f"/citas/{E['cita_marcos_corto']}/reasignar", {"usuario_negocio_id": E["un_ana"]}, T))
    probar("Bruno ya no puede cancelar esa cita (ahora es de Ana) -> 403",
           llamar("PATCH", f"/citas/{E['cita_marcos_corto']}/cancelar", token=B), 403, "propias citas")


# ---------------------------------------------------------------------------
# 10. Citas futuras: no se puede dejar a nadie "colgado"
# ---------------------------------------------------------------------------
def s10_citas_futuras():
    titulo("10. Cambios bloqueados cuando hay citas futuras")

    if not requiere("tok_ana", "h_bruno", "un_bruno", "srv_corte", "srv_tinte", "srv_manicure", "cli_laura", "cli_sincitas", "un_ana"):
        return

    T = E["tok_ana"]
    h = E["h_bruno"]

    def horario(fin):
        return {"dia_semana": 1, "hora_inicio": "09:00", "hora_fin": fin, "intervalo_minutos": 30}

    probar("acortar el horario a 09-15 dejaría sin cabida la cita de las 14:00-16:00 -> 409",
           llamar("PUT", f"/horarios/{h}", horario("15:00"), T), 409, "cita(s) futura(s)")
    probar("acortar a 09-17 sí es posible (todas las citas siguen cabiendo)", llamar("PUT", f"/horarios/{h}", horario("17:00"), T))
    probar("...y se restaura a 09-18", llamar("PUT", f"/horarios/{h}", horario("18:00"), T))
    probar("acortar a 09-11:45 dejaría la pausa de almuerzo fuera -> 409",
           llamar("PUT", f"/horarios/{h}", horario("11:45"), T), 409, "pausa")
    probar("desactivar el horario con citas ese día -> 409", llamar("DELETE", f"/horarios/{h}", token=T), 409, "cita(s) futura(s)")
    probar("una pausa que tapa la cita de las 10:00 -> 409",
           llamar("POST", "/pausas", {"horario_id": h, "hora_inicio": "10:00", "hora_fin": "10:30"}, T), 409, "cita(s) futura(s)")
    cuerpo = probar("una pausa 17:30-18:00 (sin citas) sí se puede",
                    llamar("POST", "/pausas", {"horario_id": h, "hora_inicio": "17:30", "hora_fin": "18:00"}, T))
    if id_de(cuerpo):
        probar("...y se elimina", llamar("DELETE", f"/pausas/{id_de(cuerpo)}", token=T))
    if requiere("pausa_alm"):
        probar("mover el almuerzo a 10:00-11:00 taparía a Laura -> 409",
               llamar("PUT", f"/pausas/{E['pausa_alm']}", {"hora_inicio": "10:00", "hora_fin": "11:00"}, T), 409, "cita(s) futura(s)")

    probar("desvincular a Bruno con citas futuras -> 409",
           llamar("DELETE", f"/usuarios-negocio/{E['un_bruno']}", token=T), 409, "cita(s) futura(s)")
    probar("quitarle Corte a Bruno con citas de Corte -> 409",
           llamar("DELETE", f"/empleados-servicios/{E['srv_corte']}/{E['un_bruno']}", token=T), 409, "cita(s) futura(s)")
    probar("desactivar el servicio Tinte (en una cita) -> 409",
           llamar("DELETE", f"/servicios/{E['srv_tinte']}", token=T), 409, "cita(s) futura(s)")
    probar("desactivar a Laura (tiene cita) -> 409",
           llamar("DELETE", f"/clientes/{E['cli_laura']}", token=T), 409, "cita(s) futura(s)")

    # --- el camino contrario: sin citas, sí se puede
    probar("desactivar Manicure (sin citas) -> permitido", llamar("DELETE", f"/servicios/{E['srv_manicure']}", token=T))
    cuerpo = probar("...ya no aparece en /servicios", llamar("GET", "/servicios", token=T))
    verificar("...quedan 2 activos", isinstance(cuerpo, list) and E["srv_manicure"] not in [s["id"] for s in cuerpo])
    probar("no se puede agendar un servicio inactivo -> 400",
           llamar("POST", "/citas", cita_body(E["cli_sincitas"], LUNES, "13:00", [E["srv_manicure"]], E["un_ana"]), T), 400, "inactivo")
    probar("reactivar Manicure", llamar("PATCH", f"/servicios/{E['srv_manicure']}/activar", token=T))

    probar("desactivar a un cliente sin citas -> permitido", llamar("DELETE", f"/clientes/{E['cli_sincitas']}", token=T))
    probar("un cliente inactivo no puede agendar -> 400",
           llamar("POST", "/citas", cita_body(E["cli_sincitas"], LUNES, "13:00", [E["srv_corte"]], E["un_ana"]), T), 400, "inactivo")
    probar("reactivar al cliente", llamar("PATCH", f"/clientes/{E['cli_sincitas']}/activar", token=T))


# ---------------------------------------------------------------------------
# 11. Aislamiento entre negocios
# ---------------------------------------------------------------------------
def s11_aislamiento():
    titulo("11. Aislamiento: Carla (otro negocio) no ve nada de Ana")

    if not requiere("carla_email", "cita_laura", "cli_laura", "srv_corte", "prod_shampoo", "h_bruno", "un_bruno", "negocio_a", "ana_id"):
        return

    cuerpo = probar("Carla inicia sesión (aún sin negocio)", login(E["carla_email"]), 200, "ningún negocio")
    tok_u = campo(cuerpo, "access_token")
    cuerpo = probar("Carla crea 'TEST Barbería'",
                    llamar("POST", "/negocios", {"nombre": "TEST Barbería"}, tok_u), 200, "ADMIN")
    E["negocio_b"] = id_de(cuerpo)

    if not requiere("negocio_b"):
        return

    cuerpo = probar("Carla elige su negocio", llamar("POST", f"/auth/negocio/{E['negocio_b']}", token=tok_u))
    E["tok_carla_b"] = campo(cuerpo, "access_token")

    if not requiere("tok_carla_b"):
        return

    C = E["tok_carla_b"]
    cuerpo = probar("Carla crea un servicio propio", llamar("POST", "/servicios", {"nombre": "TEST Corte B", "duracion_minutos": 20, "precio": 10000}, C))
    E["srv_b"] = id_de(cuerpo)
    cuerpo = probar("Carla crea un cliente propio", llamar("POST", "/clientes", {"nombre": "TEST ClienteB", "telefono": "3007778899"}, C))
    E["cli_b"] = id_de(cuerpo)

    # Los listados no mezclan negocios
    ids_de_ana = {"servicios": {E["srv_corte"]}, "clientes": {E["cli_laura"]}, "citas": {E["cita_laura"]}, "productos": {E["prod_shampoo"]}}
    for recurso in ("servicios", "servicios/admin", "clientes", "clientes/admin", "citas", "productos", "productos/admin",
                    "horarios", "pausas", "empleados-servicios", "usuarios-negocio"):
        cuerpo = llamar("GET", f"/{recurso}", token=C)
        lista = cuerpo[1] if isinstance(cuerpo[1], list) else []
        ajenos = [x for x in lista if isinstance(x, dict) and x.get("negocio_id") == E["negocio_a"]]
        ajenos += [x for x in lista if isinstance(x, dict) and x.get("usuario_negocio_id") in (E["un_bruno"], E["un_ana"])]
        verificar(f"GET /{recurso}: no aparece nada del negocio de Ana", cuerpo[0] in (200, 403) and not ajenos, f"(llegó {cuerpo[0]}, {len(ajenos)} ajenos)")

    # Pedir recursos ajenos por id -> 404 (como si no existieran)
    ajenos = (
        ("GET", f"/servicios/{E['srv_corte']}"), ("PUT", f"/servicios/{E['srv_corte']}"), ("DELETE", f"/servicios/{E['srv_corte']}"),
        ("PATCH", f"/servicios/{E['srv_corte']}/activar"),
        ("GET", f"/clientes/{E['cli_laura']}"), ("PUT", f"/clientes/{E['cli_laura']}"), ("DELETE", f"/clientes/{E['cli_laura']}"),
        ("GET", f"/productos/{E['prod_shampoo']}"), ("DELETE", f"/productos/{E['prod_shampoo']}"),
        ("GET", f"/citas/{E['cita_laura']}"), ("PUT", f"/citas/{E['cita_laura']}"), ("DELETE", f"/citas/{E['cita_laura']}"),
        ("PATCH", f"/citas/{E['cita_laura']}/cancelar"), ("PATCH", f"/citas/{E['cita_laura']}/completar"),
        ("GET", f"/citas/{E['cita_laura']}/servicios"), ("GET", f"/citas/{E['cita_laura']}/productos"),
        ("POST", f"/citas/{E['cita_laura']}/productos"), ("POST", f"/citas/{E['cita_laura']}/servicios"),
        ("GET", f"/horarios/{E['h_bruno']}"), ("PUT", f"/horarios/{E['h_bruno']}"), ("DELETE", f"/horarios/{E['h_bruno']}"),
        ("PATCH", f"/horarios/{E['h_bruno']}/activar"),
        ("GET", f"/usuarios-negocio/{E['un_bruno']}"), ("DELETE", f"/usuarios-negocio/{E['un_bruno']}"),
        ("GET", f"/negocios/{E['negocio_a']}"), ("PUT", f"/negocios/{E['negocio_a']}"),
    )
    cuerpos_validos = {
        "PUT": {"nombre": "Hackeado", "duracion_minutos": 30, "precio": 1, "activo": True, "telefono": "3001234567",
                "dia_semana": 1, "hora_inicio": "09:00", "hora_fin": "10:00", "intervalo_minutos": 30, "motivo": "x"},
        "POST": {"producto_id": 1, "servicio_id": 1, "cantidad": 1},
    }
    for metodo, ruta in ajenos:
        probar(f"{metodo} {ruta} -> 404", llamar(metodo, ruta, cuerpos_validos.get(metodo), C), 404)

    probar("crear una cita en B con un cliente de A -> 400",
           llamar("POST", "/citas", cita_body(E["cli_laura"], LUNES, "10:00", [E["srv_b"]]), C), 400, "no pertenece")
    probar("asignar un servicio de A desde B -> 404",
           llamar("POST", "/empleados-servicios", {"servicio_id": E["srv_corte"], "usuario_negocio_id": 1}, C), 404)
    probar("Carla (admin de B) no ve a Ana (que no es de su negocio) -> 404",
           llamar("GET", f"/usuarios/{E['ana_id']}", token=C), 404)
    probar("...y Ana tampoco ve el servicio de B -> 404",
           llamar("GET", f"/servicios/{E['srv_b']}", token=E["tok_ana"]), 404)
    probar("...ni el cliente de B -> 404",
           llamar("GET", f"/clientes/{E['cli_b']}", token=E["tok_ana"]), 404)


# ---------------------------------------------------------------------------
# 12. Una persona en varios negocios
# ---------------------------------------------------------------------------
def s12_varios_negocios():
    titulo("12. Una misma persona en varios negocios (Carla)")

    if not requiere("tok_ana", "tok_carla_b", "negocio_a", "negocio_b", "carla_email", "cita_marcos_corto"):
        return

    T, C = E["tok_ana"], E["tok_carla_b"]

    cuerpo = probar("Ana vincula a Carla (que es admin de otro negocio) como EMPLEADO",
                    llamar("POST", "/usuarios-negocios", {"email": E["carla_email"], "rol": "EMPLEADO"}, T))
    E["un_carla_a"] = id_de(cuerpo)

    cuerpo = probar("login de Carla sin indicar negocio: pide elegir", login(E["carla_email"]), 200, "varios negocios")
    verificar("...no eligió ninguno", campo(cuerpo, "negocio_id") is None)
    verificar("...y lista sus 2 negocios", len(campo(cuerpo, "negocios") or []) == 2)

    cuerpo = probar("login indicando el negocio de Ana: entra como EMPLEADO", login(E["carla_email"], E["negocio_a"]), 200, "EMPLEADO")
    E["tok_carla_a"] = campo(cuerpo, "access_token")
    cuerpo = probar("login indicando su barbería: entra como ADMIN", login(E["carla_email"], E["negocio_b"]), 200, "ADMIN")
    probar("login indicando un negocio ajeno -> 403", login(E["carla_email"], 999999999), 403, "No perteneces")

    cuerpo = probar("cambiar de negocio sin contraseña (POST /auth/negocio/{id})",
                    llamar("POST", f"/auth/negocio/{E['negocio_a']}", token=C), 200, "EMPLEADO")
    probar("cambiar a un negocio ajeno -> 403", llamar("POST", "/auth/negocio/999999999", token=C), 403)

    if requiere("tok_carla_a"):
        K = E["tok_carla_a"]
        cuerpo = probar("GET /auth/me con el token del negocio de Ana", llamar("GET", "/auth/me", token=K), 200)
        verificar("...rol EMPLEADO en ese negocio", campo(cuerpo, "rol") == "EMPLEADO" and campo(cuerpo, "negocio_id") == E["negocio_a"])
        probar("en el negocio de Ana, Carla (EMPLEADO) no crea servicios -> 403",
               llamar("POST", "/servicios", {"nombre": "X", "duracion_minutos": 30, "precio": 1}, K), 403)
        probar("en su barbería, Carla (ADMIN) sí crea servicios",
               llamar("POST", "/servicios", {"nombre": "TEST Barba B", "duracion_minutos": 30, "precio": 1}, C))

    probar("reasignar una cita a Carla, que no tiene el servicio asignado -> 400",
           llamar("PATCH", f"/citas/{E['cita_marcos_corto']}/reasignar", {"usuario_negocio_id": E["un_carla_a"]}, T), 400, "no tiene asignado")


# ---------------------------------------------------------------------------
# 13. Perfiles y usuarios
# ---------------------------------------------------------------------------
def s13_perfiles():
    titulo("13. Perfiles de usuario")

    if not requiere("tok_ana", "tok_bruno", "ana_id", "bruno_id", "dani_id", "bruno_email", "dani_email"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]

    cuerpo = probar("Ana lista las personas de su negocio", llamar("GET", "/usuarios", token=T))
    emails = [u.get("email") for u in cuerpo] if isinstance(cuerpo, list) else []
    verificar("...están Ana, Bruno y Carla (y no Dani)", E["ana_email"] in emails and E["bruno_email"] in emails
              and E["carla_email"] in emails and E["dani_email"] not in emails)
    verificar("...sin exponer contraseñas", "password" not in json.dumps(cuerpo) and "hash" not in json.dumps(cuerpo))
    probar("Ana ve a Bruno (es de su negocio)", llamar("GET", f"/usuarios/{E['bruno_id']}", token=T))
    probar("Ana no ve a Dani (no es de su negocio) -> 404", llamar("GET", f"/usuarios/{E['dani_id']}", token=T), 404)
    probar("Bruno (EMPLEADO) no ve a Ana -> 404", llamar("GET", f"/usuarios/{E['ana_id']}", token=B), 404)
    probar("cada quien ve su propio perfil", llamar("GET", f"/usuarios/{E['bruno_id']}", token=B))
    probar("Ana no edita el perfil de Bruno -> 403",
           llamar("PUT", f"/usuarios/{E['bruno_id']}", {"nombre": "Hackeado", "email": E["bruno_email"]}, T), 403)
    probar("Ana edita el suyo",
           llamar("PUT", f"/usuarios/{E['ana_id']}", {"nombre": "TEST Ana Maria", "email": E["ana_email"]}, T))
    probar("...pero no puede quedarse con el email de Bruno -> 409",
           llamar("PUT", f"/usuarios/{E['ana_id']}", {"nombre": "TEST Ana", "email": E["bruno_email"]}, T), 409)

    cuerpo = probar("Dani (sin negocio) inicia sesión", login(E["dani_email"]), 200, "ningún negocio")
    tok_d = campo(cuerpo, "access_token")
    probar("...no tiene negocios", llamar("GET", "/negocios", token=tok_d), 200)
    probar("...y no puede usar rutas de negocio -> 403", llamar("GET", "/servicios", token=tok_d), 403)


# ---------------------------------------------------------------------------
# 14. Roles en vivo y último administrador
# ---------------------------------------------------------------------------
def s14_roles_en_vivo():
    titulo("14. Cambios de rol al instante y último administrador")

    if not requiere("tok_ana", "tok_bruno", "un_ana", "un_bruno", "tok_carla_a", "tok_carla_b", "un_carla_a"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]

    probar("Ana es la única admin: no puede desvincularse -> 409",
           llamar("DELETE", f"/usuarios-negocio/{E['un_ana']}", token=T), 409, "al menos un administrador")
    probar("...ni bajarse a EMPLEADO -> 409",
           llamar("PUT", f"/usuarios-negocio/{E['un_ana']}", {"rol": "EMPLEADO"}, T), 409, "al menos un administrador")

    probar("Ana asciende a Bruno a ADMIN", llamar("PUT", f"/usuarios-negocio/{E['un_bruno']}", {"rol": "ADMIN"}, T))
    probar("Bruno (con el MISMO token de antes) ya actúa como ADMIN: el rol se lee en vivo",
           llamar("POST", "/servicios", {"nombre": "TEST Servicio de Bruno", "duracion_minutos": 30, "precio": 1}, B))
    probar("ahora que hay otro admin, Ana puede bajarse a EMPLEADO",
           llamar("PUT", f"/usuarios-negocio/{E['un_ana']}", {"rol": "EMPLEADO"}, T))
    probar("Ana ya no es admin (con su token de siempre) -> 403",
           llamar("POST", "/servicios", {"nombre": "X", "duracion_minutos": 30, "precio": 1}, T), 403)
    probar("Bruno es el único admin: no puede desvincularse -> 409",
           llamar("DELETE", f"/usuarios-negocio/{E['un_bruno']}", token=B), 409, "al menos un administrador")
    probar("Bruno no desvincula a Ana: tiene citas futuras -> 409",
           llamar("DELETE", f"/usuarios-negocio/{E['un_ana']}", token=B), 409, "cita(s) futura(s)")

    # --- desvincular a alguien corta su acceso al instante
    probar("Bruno desvincula a Carla (sin citas) -> permitido",
           llamar("DELETE", f"/usuarios-negocio/{E['un_carla_a']}", token=B))
    probar("el token de Carla para ese negocio deja de servir al instante -> 401",
           llamar("GET", "/servicios", token=E["tok_carla_a"]), 401, "ya no es válido")
    probar("...pero su token de la barbería sigue funcionando",
           llamar("GET", "/servicios", token=E["tok_carla_b"]), 200)
    probar("Bruno la vuelve a vincular", llamar("PATCH", f"/usuarios-negocio/{E['un_carla_a']}/activar", token=B))
    probar("...y su token vuelve a funcionar",
           llamar("GET", "/servicios", token=E["tok_carla_a"]), 200)

    # --- se deja todo como al principio
    probar("(restaurar) Bruno devuelve el rol ADMIN a Ana", llamar("PUT", f"/usuarios-negocio/{E['un_ana']}", {"rol": "ADMIN"}, B))
    probar("(restaurar) Ana vuelve a dejar a Bruno como EMPLEADO", llamar("PUT", f"/usuarios-negocio/{E['un_bruno']}", {"rol": "EMPLEADO"}, T))


# ---------------------------------------------------------------------------
# 15. Calendario: CORS, citas completas, filtros y disponibilidad
# ---------------------------------------------------------------------------
def preflight(origen):
    """Simula lo que hace el navegador antes de llamar a la API desde otra página (OPTIONS)."""
    peticion = urlreq.Request(BASE + "/citas", method="OPTIONS")
    peticion.add_header("Origin", origen)
    peticion.add_header("Access-Control-Request-Method", "GET")
    peticion.add_header("Access-Control-Request-Headers", "authorization")

    try:
        with urlreq.urlopen(peticion, timeout=30) as respuesta:
            return respuesta.status, {k.lower(): v for k, v in respuesta.headers.items()}
    except urlerr.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}


def s15_calendario():
    titulo("15. Calendario: CORS, citas completas, filtros y disponibilidad")

    codigo, cab = preflight(ORIGEN_PERMITIDO)
    verificar(f"CORS: {ORIGEN_PERMITIDO} puede llamar a la API desde el navegador",
              codigo == 200 and cab.get("access-control-allow-origin") == ORIGEN_PERMITIDO,
              f"(llegó {codigo}, allow-origin={cab.get('access-control-allow-origin')}; ¿definiste VALEN_ORIGENES_PERMITIDOS distinto? usa --origen-permitido)")
    codigo, cab = preflight("https://sitio-malicioso.example")
    verificar("CORS: un origen no autorizado NO recibe permiso", "access-control-allow-origin" not in cab,
              f"(llegó {codigo}, allow-origin={cab.get('access-control-allow-origin')})")

    if not requiere("tok_ana", "tok_bruno", "un_bruno", "un_ana", "srv_corte", "srv_tinte", "srv_manicure", "cli_laura",
                    "cli_sincitas", "cita_laura", "cita_marcos_largo", "cita_marcos_corto"):
        return

    T, B = E["tok_ana"], E["tok_bruno"]
    L = LUNES.isoformat()

    # --- citas completas para el calendario
    cuerpo = probar("GET /citas del lunes", llamar("GET", f"/citas?desde={L}&hasta={L}", token=B))
    verificar("...son 5 citas", isinstance(cuerpo, list) and len(cuerpo) == 5, f"(hay {len(cuerpo) if isinstance(cuerpo, list) else '?'})")
    laura = next((c for c in cuerpo if c.get("id") == E["cita_laura"]), None) if isinstance(cuerpo, list) else None
    if laura:
        verificar("...trae cliente, empleado y servicios con nombre",
                  laura["cliente"]["nombre"] == "TEST Laura" and laura["empleado"]["nombre"] == "TEST Bruno"
                  and [s["nombre"] for s in laura["servicios"]] == ["TEST Corte"])
        verificar("...trae fechas ISO para el calendario",
                  laura["inicio"] == f"{L}T10:00:00" and laura["fin"] == f"{L}T10:30:00" and laura["duracion_minutos"] == 30)
        verificar("...trae totales (servicios 25000 + productos 15045000 = 15070000)",
                  (laura["total_servicios"], laura["total_productos"], laura["total"]) == (25000.0, 15045000.0, 15070000.0),
                  f"(total {laura['total']})")
        verificar("...y conserva los campos de siempre", all(k in laura for k in ("cliente_id", "usuario_negocio_id", "hora_inicio", "hora_fin", "estado")))
    else:
        verificar("...incluye la cita de Laura", False)

    cuerpo = probar("GET /citas/{id} devuelve la misma estructura", llamar("GET", f"/citas/{E['cita_laura']}", token=B))
    verificar("...con cliente y servicios", isinstance(cuerpo, dict) and cuerpo.get("cliente", {}).get("nombre") == "TEST Laura" and len(cuerpo.get("servicios", [])) == 1)

    # --- filtros
    def cuantas(ruta, token=T):
        c = llamar("GET", ruta, token=token)
        return c[0], (len(c[1]) if isinstance(c[1], list) else None)

    verificar("filtro por empleado: Bruno tiene 3 citas", cuantas(f"/citas?desde={L}&hasta={L}&empleado_id={E['un_bruno']}") == (200, 3))
    verificar("filtro por empleado: Ana tiene 2 (la suya y la reasignada)", cuantas(f"/citas?desde={L}&hasta={L}&empleado_id={E['un_ana']}") == (200, 2))
    verificar("solo_mias: Bruno ve sus 3", cuantas(f"/citas?desde={L}&hasta={L}&solo_mias=true", B) == (200, 3))
    verificar("solo_mias: Ana ve sus 2", cuantas(f"/citas?desde={L}&hasta={L}&solo_mias=true", T) == (200, 2))
    verificar("filtro por cliente: Laura tiene 1", cuantas(f"/citas?desde={L}&hasta={L}&cliente_id={E['cli_laura']}") == (200, 1))
    verificar("filtro por estado CANCELADA: ninguna", cuantas(f"/citas?desde={L}&hasta={L}&estado=CANCELADA") == (200, 0))
    verificar("filtro por varios estados a la vez", cuantas(f"/citas?desde={L}&hasta={L}&estado=PENDIENTE&estado=CONFIRMADA&estado=COMPLETADA")[1] == 5)
    verificar("el día siguiente no tiene citas", cuantas(f"/citas?desde={(LUNES + timedelta(days=1)).isoformat()}&hasta={(LUNES + timedelta(days=1)).isoformat()}") == (200, 0))
    probar("estado inventado -> 422", llamar("GET", f"/citas?estado=XYZ", token=T), 422)
    probar("'hasta' antes que 'desde' -> 400", llamar("GET", f"/citas?desde={L}&hasta={(LUNES - timedelta(days=1)).isoformat()}", token=T), 400)
    probar("más de 92 días en una consulta -> 400", llamar("GET", f"/citas?desde={L}&hasta={(LUNES + timedelta(days=93)).isoformat()}", token=T), 400, "92")
    probar("sin token -> 401", llamar("GET", f"/citas?desde={L}&hasta={L}"), 401)
    verificar("sin parámetros funciona (hoy y los próximos 30 días)", cuantas("/citas")[0] == 200)

    # --- disponibilidad
    def huecos(servicios, empleado=None, fecha=LUNES, token=B):
        consulta = "".join(f"&servicio_id={s}" for s in servicios)
        codigo, c = llamar("GET", f"/disponibilidad?empleado_id={empleado or E['un_bruno']}&fecha={fecha.isoformat()}{consulta}", token=token)
        return codigo, ([h["inicio"] for h in c["huecos"]] if isinstance(c, dict) and "huecos" in c else c)

    esperado_corte = ["09:00", "09:30", "10:30", "11:00", "11:30", "13:00", "13:30", "16:00", "17:00", "17:30"]
    codigo, lista = huecos([E["srv_corte"]])
    verificar("disponibilidad de Bruno el lunes para un Corte (descuenta cita de Laura, almuerzo y citas de la tarde)",
              codigo == 200 and lista == esperado_corte, f"(llegó {codigo}: {lista})")
    cuerpo = llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha={L}&servicio_id={E['srv_corte']}", token=B)[1]
    verificar("...cada hueco trae su hora de fin", isinstance(cuerpo, dict) and cuerpo["huecos"][0] == {"inicio": "09:00", "fin": "09:30"} and cuerpo["duracion_minutos"] == 30)
    codigo, lista = huecos([E["srv_tinte"]])
    verificar("para un Tinte de 90 min solo cabe a las 10:30", (codigo, lista) == (200, ["10:30"]), f"(llegó {codigo}: {lista})")
    codigo, lista = huecos([E["srv_corte"], E["srv_tinte"]])
    verificar("Corte + Tinte (120 min): no hay hueco", (codigo, lista) == (200, []), f"(llegó {codigo}: {lista})")
    verificar("en domingo Bruno no trabaja: lista vacía", huecos([E["srv_corte"]], fecha=DOMINGO) == (200, []))
    verificar("una fecha pasada: lista vacía", huecos([E["srv_corte"]], fecha=date.today() - timedelta(days=3)) == (200, []))
    probar("Bruno no hace Manicure -> 400", llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha={L}&servicio_id={E['srv_manicure']}", token=B), 400, "no tiene asignado")
    probar("servicio repetido -> 400", llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha={L}&servicio_id={E['srv_corte']}&servicio_id={E['srv_corte']}", token=B), 400)
    probar("empleado inexistente -> 404", llamar("GET", f"/disponibilidad?empleado_id=999999999&fecha={L}&servicio_id={E['srv_corte']}", token=B), 404)
    probar("sin indicar servicio -> 422", llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha={L}", token=B), 422)
    probar("fecha inválida -> 422", llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha=2026-13-45&servicio_id={E['srv_corte']}", token=B), 422)
    probar("sin token -> 401", llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha={L}&servicio_id={E['srv_corte']}"), 401)
    if E.get("tok_carla_b"):
        probar("un empleado de otro negocio no se puede consultar -> 400",
               llamar("GET", f"/disponibilidad?empleado_id={E['un_bruno']}&fecha={L}&servicio_id={E['srv_corte']}", token=E["tok_carla_b"]), 400)

    # --- lo que se ofrece como libre se puede reservar, y deja de ofrecerse
    probar("reservar la primera hora ofrecida (09:00)",
           llamar("POST", "/citas", cita_body(E["cli_sincitas"], LUNES, "09:00", [E["srv_corte"]]), B))
    codigo, lista = huecos([E["srv_corte"]])
    verificar("...y esa hora ya no aparece como libre", codigo == 200 and "09:00" not in lista and lista == esperado_corte[1:], f"(llegó {lista})")
    probar("una hora que NO se ofrece (10:00) se rechaza al reservar",
           llamar("POST", "/citas", cita_body(E["cli_marcos"], LUNES, "10:00", [E["srv_corte"]]), B), 409)


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
SECCIONES = (s1_registro_y_login, s2_negocio_y_catalogo, s3_equipo_y_permisos, s4_horarios_y_pausas, s5_clientes,
             s6_citas_reglas_de_agenda, s7_servicios_y_productos_de_cita, s8_estados, s9_reasignar, s10_citas_futuras,
             s11_aislamiento, s12_varios_negocios, s13_perfiles, s14_roles_en_vivo, s15_calendario)


def main():
    global BASE, MODO_PRUEBAS, ORIGEN_PERMITIDO

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Prueba de punta a punta de la API de Valen")
    parser.add_argument("--url", default=BASE, help="dirección del servidor (por defecto %(default)s)")
    parser.add_argument("--modo-pruebas", action="store_true",
                        help="usa esto solo si arrancaste el servidor con VALEN_MODO_PRUEBAS=1")
    parser.add_argument("--origen-permitido", default=ORIGEN_PERMITIDO,
                        help="un origen que SÍ esté en VALEN_ORIGENES_PERMITIDOS (por defecto %(default)s)")
    argumentos = parser.parse_args()
    BASE, MODO_PRUEBAS = argumentos.url.rstrip("/"), argumentos.modo_pruebas
    ORIGEN_PERMITIDO = argumentos.origen_permitido

    print(f"Probando {BASE}  (modo pruebas: {'sí' if MODO_PRUEBAS else 'no'}; identificador de esta corrida: {SUF})")

    try:
        codigo, _ = llamar("GET", "/")
    except (urlerr.URLError, OSError) as error:
        print(f"\nNo pude conectar con {BASE}: {error}\n¿Está corriendo uvicorn? (uvicorn main:app --reload)")
        return 2

    if codigo != 200:
        print(f"\nEl servidor respondió {codigo} en '/'. Revisa la terminal de uvicorn.")
        return 2

    for seccion in SECCIONES:
        try:
            seccion()
        except Exception as error:  # una sección rota no debe tumbar a las demás
            fallas.append(f"{seccion.__name__} se interrumpió: {error!r}")
            print(f"  [ERROR] {seccion.__name__} se interrumpió: {error!r}")

    total = ok + len(fallas)
    print("\n" + "=" * 70)
    print(f"RESULTADO: {ok} de {total} comprobaciones correctas, {len(fallas)} fallaron"
          + (f", {len(saltados)} saltadas" if saltados else ""))

    if fallas:
        print("\nFallaron:")
        for nombre in fallas:
            print(f"  - {nombre}")
        print("\nCopia la salida completa (sobre todo las líneas [FALLA] con 'esperaba ... llegó ...') y compártela.")

    print("\nDatos para seguir probando a mano en /docs (contraseña de todos: " + CLAVE + "):")
    for clave in ("ana", "bruno", "carla", "dani"):
        print(f"  {clave:6} {E.get(clave + '_email')}")
    print(f"  Negocio de Ana (id {E.get('negocio_a')}): Ana ADMIN, Bruno EMPLEADO, Carla EMPLEADO")
    print(f"  Negocio de Carla (id {E.get('negocio_b')}): Carla ADMIN")
    print(f"  Citas de prueba el lunes {LUNES}. Para borrar todo: limpiar_datos_de_prueba.sql")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())