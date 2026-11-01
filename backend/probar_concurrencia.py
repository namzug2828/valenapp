"""
probar_concurrencia.py - ¿pueden dos solicitudes simultáneas ocupar la misma franja?

Dispara muchas peticiones AL MISMO TIEMPO contra el servidor y comprueba que,
pase lo que pase con los tiempos, solo una gana cada franja y que ninguna
termina en error 500. Necesita el paso 1 aplicado (usa GET /citas con filtros).

Uso (con el servidor corriendo):
    python probar_concurrencia.py
    python probar_concurrencia.py --rondas 4 --url http://127.0.0.1:8000

Escenarios (cada uno se repite --rondas veces, con franjas distintas):
  A  8 clientes distintos piden la MISMA hora con el MISMO empleado
  B  1 cliente pide la MISMA hora con DOS empleados a la vez (no puede estar en dos sitios)
  C  dos citas existentes se REPROGRAMAN a la vez hacia la MISMA hora
  D  20 peticiones sobre 5 horas distintas: cada hora debe quedar con una sola cita
Al final comprueba que en todo el día no hay ninguna pareja de citas superpuestas
(por empleado ni por cliente).

Los datos llevan emails @prueba.test: se borran con limpiar_datos_de_prueba.sql.
Reutiliza las funciones de probar_api.py (debe estar en la misma carpeta).
"""
import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import probar_api as p

S = {}          # ids y token del escenario
CONTADOR = [0]


def hhmm(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def a_minutos(texto):
    h, m = texto.split(":")[:2]
    return int(h) * 60 + int(m)


def telefono_nuevo():
    CONTADOR[0] += 1
    return f"31{int(p.SUF) % 1000000:06d}{CONTADOR[0]:02d}"


# ---------------------------------------------------------------------------
# Preparación
# ---------------------------------------------------------------------------
def preparar():
    p.titulo("Preparación: negocio, 2 empleados, 1 servicio y 15 clientes")

    for clave in ("ana", "bruno"):
        S[f"{clave}_email"] = f"conc{clave}.{p.SUF}@prueba.test"
        cuerpo = p.probar(f"registrar a {clave}", p.llamar(
            "POST", "/usuarios", {"nombre": f"TEST Conc {clave}", "email": S[f"{clave}_email"], "password": p.CLAVE}))
        S[f"{clave}_id"] = p.id_de(cuerpo)

    cuerpo = p.probar("login de Ana", p.login(S["ana_email"]))
    tok_u = p.campo(cuerpo, "access_token")
    cuerpo = p.probar("crear negocio", p.llamar("POST", "/negocios", {"nombre": "TEST Concurrencia"}, tok_u))
    negocio = p.id_de(cuerpo)
    cuerpo = p.probar("elegir negocio", p.llamar("POST", f"/auth/negocio/{negocio}", token=tok_u))
    S["tok"] = p.campo(cuerpo, "access_token")

    if S["tok"] is None:
        return False

    T = S["tok"]
    cuerpo = p.probar("crear servicio Corte (30 min)", p.llamar(
        "POST", "/servicios", {"nombre": "TEST Corte", "duracion_minutos": 30, "precio": 25000}, T))
    S["srv"] = p.id_de(cuerpo)
    cuerpo = p.probar("vincular a Bruno", p.llamar("POST", "/usuarios-negocios", {"email": S["bruno_email"], "rol": "EMPLEADO"}, T))
    S["un_bruno"] = p.id_de(cuerpo)
    lista = p.llamar("GET", "/usuarios-negocio", token=T)[1]
    S["un_ana"] = next((v["id"] for v in lista if v["usuario_id"] == S["ana_id"]), None) if isinstance(lista, list) else None

    if None in (S["srv"], S["un_bruno"], S["un_ana"]):
        return False

    for clave in ("un_ana", "un_bruno"):
        p.probar(f"asignar Corte a {clave}", p.llamar(
            "POST", "/empleados-servicios", {"servicio_id": S["srv"], "usuario_negocio_id": S[clave]}, T))
        p.probar(f"horario lunes 09:00-18:00 de {clave}", p.llamar(
            "POST", "/horarios", {"usuario_negocio_id": S[clave], "dia_semana": 1, "hora_inicio": "09:00",
                                  "hora_fin": "18:00", "intervalo_minutos": 30}, T))

    S["clientes"] = []
    for i in range(15):
        cuerpo = p.llamar("POST", "/clientes", {"nombre": f"TEST Cliente {i + 1}", "telefono": telefono_nuevo()}, T)
        if cuerpo[0] != 200:
            p.verificar(f"crear cliente {i + 1}", False, f"(llegó {cuerpo})")
            return False
        S["clientes"].append(p.id_de(cuerpo[1]))
    p.verificar("15 clientes creados", len(S["clientes"]) == 15)
    return True


# ---------------------------------------------------------------------------
# Disparo simultáneo
# ---------------------------------------------------------------------------
def disparar(tareas):
    """Lanza todas las tareas a la vez (una barrera las libera juntas). Devuelve sus resultados."""
    barrera = threading.Barrier(len(tareas))

    def correr(tarea):
        barrera.wait()
        return tarea()

    with ThreadPoolExecutor(max_workers=len(tareas)) as pool:
        futuros = [pool.submit(correr, t) for t in tareas]
        return [f.result() for f in futuros]


def crear(cliente, empleado, hora):
    return lambda: p.llamar("POST", "/citas", p.cita_body(cliente, p.LUNES, hora, [S["srv"]], empleado), S["tok"])


def reprogramar(cita_id, hora):
    return lambda: p.llamar("PUT", f"/citas/{cita_id}", {"hora_inicio": hora}, S["tok"])


def evaluar(nombre, resultados, ganan, pierden):
    codigos = [r[0] for r in resultados]
    g, c = codigos.count(200), codigos.count(409)
    raros = [r for r in resultados if r[0] not in (200, 409)]
    p.verificar(
        f"{nombre}: {g} aceptada(s) y {c} rechazada(s) con 409 (esperado {ganan} y {pierden})",
        g == ganan and c == pierden and not raros,
        f"-> códigos {sorted(codigos)}" + (f"; primer caso raro: {raros[0]}" if raros else ""),
    )


def citas_del_dia(**filtros):
    consulta = "&".join(f"{k}={v}" for k, v in filtros.items())
    codigo, cuerpo = p.llamar("GET", f"/citas?desde={p.LUNES}&hasta={p.LUNES}" + (f"&{consulta}" if consulta else ""), token=S["tok"])
    return cuerpo if codigo == 200 and isinstance(cuerpo, list) else None


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------
def escenario_a(rondas):
    p.titulo(f"A. 8 clientes piden la misma hora con el mismo empleado ({rondas} rondas)")

    for r in range(rondas):
        hora = hhmm(9 * 60 + 30 * r)
        resultados = disparar([crear(c, S["un_bruno"], hora) for c in S["clientes"][:8]])
        evaluar(f"ronda {r + 1} ({hora})", resultados, 1, 7)
        citas = citas_del_dia(empleado_id=S["un_bruno"])
        a_esa_hora = [x for x in (citas or []) if x["hora_inicio"].startswith(hora) and x["estado"] != "CANCELADA"]
        p.verificar(f"ronda {r + 1}: en la base queda exactamente 1 cita a las {hora}", citas is not None and len(a_esa_hora) == 1,
                    f"(hay {len(a_esa_hora)})")


def escenario_b(rondas):
    p.titulo(f"B. Un cliente pide la misma hora con DOS empleados a la vez ({rondas} rondas)")
    cliente = S["clientes"][8]

    for r in range(rondas):
        hora = hhmm(13 * 60 + 30 * r)
        tareas = [crear(cliente, S["un_ana"], hora) for _ in range(3)] + [crear(cliente, S["un_bruno"], hora) for _ in range(3)]
        resultados = disparar(tareas)
        evaluar(f"ronda {r + 1} ({hora})", resultados, 1, 5)
        citas = citas_del_dia(cliente_id=cliente)
        a_esa_hora = [x for x in (citas or []) if x["hora_inicio"].startswith(hora) and x["estado"] != "CANCELADA"]
        p.verificar(f"ronda {r + 1}: el cliente queda con 1 sola cita a las {hora}", citas is not None and len(a_esa_hora) == 1,
                    f"(hay {len(a_esa_hora)})")


def escenario_c(rondas):
    p.titulo(f"C. Dos citas existentes se reprograman a la vez a la misma hora ({rondas} rondas)")
    y, z = S["clientes"][9], S["clientes"][10]

    for r in range(rondas):
        origen_y, origen_z, destino = hhmm(9 * 60 + 60 * r), hhmm(9 * 60 + 30 + 60 * r), hhmm(16 * 60 + 30 * r)
        cy = p.llamar("POST", "/citas", p.cita_body(y, p.LUNES, origen_y, [S["srv"]], S["un_ana"]), S["tok"])
        cz = p.llamar("POST", "/citas", p.cita_body(z, p.LUNES, origen_z, [S["srv"]], S["un_ana"]), S["tok"])
        id_y, id_z = p.id_de(cy[1]), p.id_de(cz[1])

        if None in (id_y, id_z):
            p.verificar(f"ronda {r + 1}: preparar las dos citas", False, f"(llegó {cy[0]} / {cz[0]}: {cy[1]} {cz[1]})")
            continue

        resultados = disparar([reprogramar(id_y, destino), reprogramar(id_z, destino)])
        evaluar(f"ronda {r + 1} (ambas a las {destino})", resultados, 1, 1)
        horas = sorted(
            (p.llamar("GET", f"/citas/{i}", token=S["tok"])[1] or {}).get("hora_inicio", "?")[:5] for i in (id_y, id_z)
        )
        p.verificar(f"ronda {r + 1}: una quedó en {destino} y la otra se quedó donde estaba",
                    horas == sorted([destino, origen_y if horas.count(origen_y) else origen_z]) and horas.count(destino) == 1,
                    f"(horas finales {horas})")


def escenario_d():
    p.titulo("D. 20 peticiones sobre 5 horas distintas: cada hora debe tener una sola cita")
    horas = [hhmm(15 * 60 + 30 * i) for i in range(5)]                  # 15:00 ... 17:00
    tareas = [crear(c, S["un_bruno"], h) for h in horas for c in S["clientes"][11:15]]
    resultados = disparar(tareas)
    evaluar("20 peticiones", resultados, 5, 15)
    citas = citas_del_dia(empleado_id=S["un_bruno"]) or []
    cuentas = {h: len([x for x in citas if x["hora_inicio"].startswith(h) and x["estado"] != "CANCELADA"]) for h in horas}
    p.verificar("cada una de las 5 horas quedó con exactamente 1 cita", all(v == 1 for v in cuentas.values()), f"(cuentas {cuentas})")


def invariante_global():
    p.titulo("Comprobación final: ninguna pareja de citas se superpone en todo el día")
    citas = citas_del_dia()

    if citas is None:
        p.verificar("leer las citas del día", False)
        return

    vivas = [c for c in citas if c["estado"] != "CANCELADA"]
    print(f"  ({len(vivas)} citas vivas en el día)")

    def solapes(clave):
        grupos, malos = {}, []
        for c in vivas:
            grupos.setdefault(c[clave], []).append((a_minutos(c["hora_inicio"]), a_minutos(c["hora_fin"]), c["id"]))
        for quien, lista in grupos.items():
            lista.sort()
            for (i0, f0, id0), (i1, f1, id1) in zip(lista, lista[1:]):
                if i1 < f0:
                    malos.append((quien, id0, id1))
        return malos

    por_empleado, por_cliente = solapes("usuario_negocio_id"), solapes("cliente_id")
    p.verificar("ningún empleado tiene dos citas superpuestas", not por_empleado, f"-> {por_empleado[:3]}")
    p.verificar("ningún cliente tiene dos citas superpuestas", not por_cliente, f"-> {por_cliente[:3]}")


def main():
    parser = argparse.ArgumentParser(description="Prueba de concurrencia de la API de Valen")
    parser.add_argument("--url", default=p.BASE)
    parser.add_argument("--rondas", type=int, default=3, help="repeticiones de cada escenario (1 a 4)")
    argumentos = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not 1 <= argumentos.rondas <= 4:
        print("--rondas debe estar entre 1 y 4 (el día de pruebas solo tiene espacio para eso)")
        return 2

    p.BASE = argumentos.url.rstrip("/")
    print(f"Concurrencia contra {p.BASE} ({argumentos.rondas} rondas; corrida {p.SUF}; lunes {p.LUNES})")

    try:
        codigo, _ = p.llamar("GET", "/")
    except OSError as error:
        print(f"No pude conectar con {p.BASE}: {error}\n¿Está corriendo uvicorn?")
        return 2

    if codigo != 200 or not preparar():
        print("\nNo se pudo preparar el escenario; revisa los [FALLA] de arriba.")
        return 1

    for escenario in (lambda: escenario_a(argumentos.rondas), lambda: escenario_b(argumentos.rondas),
                      lambda: escenario_c(argumentos.rondas), escenario_d, invariante_global):
        try:
            escenario()
        except Exception as error:
            p.fallas.append(f"escenario interrumpido: {error!r}")
            print(f"  [ERROR] escenario interrumpido: {error!r}")

    total = p.ok + len(p.fallas)
    print("\n" + "=" * 70)
    print(f"RESULTADO: {p.ok} de {total} comprobaciones correctas, {len(p.fallas)} fallaron")

    if p.fallas:
        print("\nFallaron:")
        for nombre in p.fallas:
            print(f"  - {nombre}")
        print("\nSi aparece un código 500, mira la terminal de uvicorn: ahí está el error real.")
    else:
        print("\nNo hubo ninguna doble reserva ni errores 500 bajo carga simultánea.")

    print("Para borrar estos datos: limpiar_datos_de_prueba.sql")
    return 1 if p.fallas else 0


if __name__ == "__main__":
    sys.exit(main())