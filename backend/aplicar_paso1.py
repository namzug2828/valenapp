"""
aplicar_paso1.py - aplica a TU main.py y models.py los cambios del paso 1.

Uso (desde la carpeta del proyecto, donde están main.py y models.py):
    python aplicar_paso1.py

Qué hace:
  main.py    1) activa CORS (con los orígenes de la variable VALEN_ORIGENES_PERMITIDOS)
             2) conecta agenda.py (citas para el calendario y disponibilidad)
             3) quita de main.py los dos GET /citas viejos, que pasan a agenda.py
  models.py  agrega los 3 índices de la tabla cita (los mismos de la migración 0002)

Seguridad: antes de tocar nada guarda main.py.bak y models.py.bak, y si algo de
tus archivos no coincide con lo esperado se detiene SIN modificar nada.
Es seguro ejecutarlo dos veces: lo que ya está aplicado se salta.
"""
import re
import shutil
import sys
from pathlib import Path

BLOQUE_CORS = '''app = FastAPI()

# CORS: qué páginas web (orígenes) pueden llamar a esta API desde el navegador.
# En producción define VALEN_ORIGENES_PERMITIDOS con tus dominios, separados por coma:
#   $env:VALEN_ORIGENES_PERMITIDOS = "https://app.tudominio.com,https://reservas.tudominio.com"
ORIGENES_PERMITIDOS = [
    origen.strip()
    for origen in os.getenv(
        "VALEN_ORIGENES_PERMITIDOS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origen.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=False,  # el token viaja en la cabecera Authorization, no en cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Citas para el calendario y disponibilidad de empleados (ver agenda.py)
app.include_router(router_agenda)'''


class ErrorDeParche(Exception):
    pass


def exactamente_una(patron, texto, descripcion, flags=0):
    coincidencias = re.findall(patron, texto, flags)
    if len(coincidencias) != 1:
        raise ErrorDeParche(
            f"No encontré {descripcion} exactamente una vez (encontré {len(coincidencias)}). "
            "Tu archivo es distinto al esperado: no se modificó nada."
        )


def parchar_main(texto):
    if "router_agenda" in texto:
        return texto, ["main.py: ya estaba aplicado, se salta"]

    cambios = []

    # 1) imports
    exactamente_una(r"^import logging$", texto, "la línea 'import logging'", re.M)
    texto = re.sub(r"^import logging$", "import logging\nimport os", texto, count=1, flags=re.M)

    exactamente_una(r"^from fastapi\.responses import JSONResponse$", texto,
                    "la línea 'from fastapi.responses import JSONResponse'", re.M)
    texto = re.sub(
        r"^from fastapi\.responses import JSONResponse$",
        "from fastapi.middleware.cors import CORSMiddleware\nfrom fastapi.responses import JSONResponse",
        texto, count=1, flags=re.M,
    )

    exactamente_una(r"^import schemas$", texto, "la línea 'import schemas'", re.M)
    texto = re.sub(r"^import schemas$", "from agenda import router as router_agenda\nimport schemas",
                   texto, count=1, flags=re.M)
    cambios.append("main.py: imports de os, CORS y agenda")

    # 2) CORS + router justo después de crear la app
    exactamente_una(r"^app = FastAPI\(\)$", texto, "la línea 'app = FastAPI()'", re.M)
    texto = re.sub(r"^app = FastAPI\(\)$", lambda _: BLOQUE_CORS, texto, count=1, flags=re.M)
    cambios.append("main.py: CORS activado y router de agenda conectado")

    # 3) quitar los dos GET /citas viejos (ahora viven en agenda.py)
    patron = r'@app\.get\("/citas"\).*?(?=@app\.put\("/citas/\{cita_id\}"\))'
    exactamente_una(patron, texto, "el bloque GET /citas + GET /citas/{cita_id}", re.S)
    bloque = re.search(patron, texto, re.S).group(0)

    if bloque.count("@app.") != 2 or "def obtener_citas(" not in bloque or "def obtener_cita(" not in bloque:
        raise ErrorDeParche(
            "El bloque entre GET /citas y PUT /citas/{cita_id} no es solo esos dos endpoints. "
            "No se modificó nada: bórralos a mano (ver instrucciones) o pásame esa parte."
        )

    texto = re.sub(
        patron,
        "# GET /citas y GET /citas/{cita_id} viven ahora en agenda.py (respuesta completa para el calendario)\n\n\n",
        texto, count=1, flags=re.S,
    )
    cambios.append("main.py: GET /citas y GET /citas/{id} movidos a agenda.py")
    return texto, cambios


def parchar_models(texto):
    if "ix_cita_negocio_fecha" in texto:
        return texto, ["models.py: ya estaba aplicado, se salta"]

    exactamente_una(r"^    ForeignKey,\n    Integer,$", texto, "la importación 'ForeignKey, Integer'", re.M)
    texto = re.sub(r"^    ForeignKey,\n    Integer,$", "    ForeignKey,\n    Index,\n    Integer,", texto, count=1, flags=re.M)

    exactamente_una(r'CheckConstraint\("hora_inicio < hora_fin", name="chk_cita_horas"\),', texto,
                    "la restricción chk_cita_horas de la tabla cita")
    texto = texto.replace(
        'CheckConstraint("hora_inicio < hora_fin", name="chk_cita_horas"),',
        'CheckConstraint("hora_inicio < hora_fin", name="chk_cita_horas"),\n'
        '        Index("ix_cita_negocio_fecha", "negocio_id", "fecha"),\n'
        '        Index("ix_cita_empleado_fecha", "usuario_negocio_id", "fecha"),\n'
        '        Index("ix_cita_cliente_fecha", "cliente_id", "fecha"),',
        1,
    )
    return texto, ["models.py: índices de la tabla cita"]


def main():
    carpeta = Path(".")
    archivos = {"main.py": parchar_main, "models.py": parchar_models}
    nuevos, mensajes = {}, []

    for nombre, funcion in archivos.items():
        ruta = carpeta / nombre

        if not ruta.exists():
            print(f"No encuentro {nombre} aquí. Ejecuta el script desde la carpeta del proyecto.")
            return 1

        try:
            nuevos[nombre], cambios = funcion(ruta.read_text(encoding="utf-8"))
        except ErrorDeParche as error:
            print(f"\n[{nombre}] {error}")
            return 1

        mensajes += cambios

    for nombre, texto in nuevos.items():
        ruta = carpeta / nombre

        if ruta.read_text(encoding="utf-8") != texto:
            shutil.copyfile(ruta, carpeta / f"{nombre}.bak")
            ruta.write_text(texto, encoding="utf-8")

    print("Listo:")
    for mensaje in mensajes:
        print("  -", mensaje)
    print("Respaldos: main.py.bak y models.py.bak (bórralos cuando todo funcione).")
    return 0


if __name__ == "__main__":
    sys.exit(main())