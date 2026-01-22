import json
import pandas as pd
from collections import defaultdict, deque

# =====================================================
# CARGA
# =====================================================
def cargar_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def cargar_medicos(path):
    df = pd.read_csv(path)
    if "nombre" not in df.columns:
        raise ValueError("El CSV debe tener una columna 'nombre'")
    return df["nombre"].tolist()

# =====================================================
# VALIDACIÓN
# =====================================================
def validar(config, medicos):
    errores = []

    if config["tipo_turno"] not in (12, 24):
        errores.append("El tipo de turno debe ser 12 o 24 horas.")

    if config["tipo_turno"] == 24 and config["medicos_noche"] > config["medicos_dia"]:
        errores.append("En turnos de 24 h no puede haber más médicos en noche que en día.")

    if len(medicos) < max(config["medicos_dia"], config["medicos_noche"]):
        errores.append("Médicos insuficientes para cubrir los turnos requeridos.")

    if config["max_noches_consecutivas"] < 1:
        errores.append("El máximo de noches consecutivas debe ser ≥ 1.")

    return errores

# =====================================================
# GENERADOR
# =====================================================
def generar_turnos(config, medicos):
    errores = validar(config, medicos)
    if errores:
        raise RuntimeError("\n".join(errores))

    dias = config["dias_mes"]
    tipo = config["tipo_turno"]
    md = config["medicos_dia"]
    mn = config["medicos_noche"]
    max_noches = config["max_noches_consecutivas"]

    turnos = {m: {} for m in medicos}
    carga = defaultdict(int)
    noches_consecutivas = defaultdict(int)

    # Médicos que NO pueden programarse hoy por haber hecho noche ayer
    bloqueo_hoy = set()

    cola = deque(medicos)

    for dia in range(1, dias + 1):

        disponibles = [m for m in medicos if m not in bloqueo_hoy]

        if len(disponibles) < max(md, mn):
            raise RuntimeError(
                f"Día {dia}: no hay médicos suficientes disponibles "
                f"por descanso post-noche."
            )

        # =================================================
        # TURNOS DE 24 HORAS
        # =================================================
        if tipo == 24:

            diurnos = []
            cola_local = deque([m for m in cola if m in disponibles])

            while len(diurnos) < md:
                m = cola_local[0]
                cola_local.rotate(-1)
                if m not in diurnos:
                    diurnos.append(m)

            candidatos_noche = sorted(
                diurnos,
                key=lambda m: (carga[m], noches_consecutivas[m])
            )

            nocturnos = []
            for m in candidatos_noche:
                if len(nocturnos) >= mn:
                    break
                if noches_consecutivas[m] < max_noches:
                    nocturnos.append(m)

            if len(nocturnos) < mn:
                raise RuntimeError(
                    f"Día {dia}: no se pudo asignar noche sin violar reglas."
                )

            bloqueo_manana = set(nocturnos)

            for m in medicos:
                if m in nocturnos:
                    turnos[m][f"Día {dia}"] = "DN"
                    carga[m] += 24
                    noches_consecutivas[m] += 1
                elif m in diurnos:
                    turnos[m][f"Día {dia}"] = "D"
                    carga[m] += 12
                    noches_consecutivas[m] = 0
                else:
                    turnos[m][f"Día {dia}"] = ""
                    noches_consecutivas[m] = 0

        # =================================================
        # TURNOS DE 12 HORAS
        # =================================================
        else:

            diurnos = []
            cola_local = deque([m for m in cola if m in disponibles])

            while len(diurnos) < md:
                m = cola_local[0]
                cola_local.rotate(-1)
                if m not in diurnos:
                    diurnos.append(m)

            candidatos_noche = sorted(
                disponibles,
                key=lambda m: (noches_consecutivas[m], carga[m])
            )

            nocturnos = []
            for m in candidatos_noche:
                if m in diurnos:
                    continue
                if len(nocturnos) >= mn:
                    break
                if noches_consecutivas[m] < max_noches:
                    nocturnos.append(m)

            if len(nocturnos) < mn:
                raise RuntimeError(
                    f"Día {dia}: no se pudo asignar noche sin violar reglas."
                )

            bloqueo_manana = set(nocturnos)

            for m in medicos:
                if m in diurnos:
                    turnos[m][f"Día {dia}"] = "D"
                    carga[m] += 12
                    noches_consecutivas[m] = 0
                elif m in nocturnos:
                    turnos[m][f"Día {dia}"] = "N"
                    carga[m] += 12
                    noches_consecutivas[m] += 1
                else:
                    turnos[m][f"Día {dia}"] = ""
                    noches_consecutivas[m] = 0

        # Actualizar bloqueo para el día siguiente
        bloqueo_hoy = bloqueo_manana.copy()

        # Rotar cola global para equidad
        cola.rotate(-1)

    df = pd.DataFrame.from_dict(turnos, orient="index")
    df.insert(0, "Médico", df.index)
    df.reset_index(drop=True, inplace=True)

    return df, carga

# =====================================================
# EJECUCIÓN
# =====================================================
if __name__ == "__main__":
    try:
        config = cargar_config("config.json")
        medicos = cargar_medicos("medicos.csv")

        df, carga = generar_turnos(config, medicos)
        df.to_csv("cuadro_turnos.csv", index=False)

        print("Cuadro generado correctamente\n")
        print("Carga horaria total:")
        for m, h in sorted(carga.items(), key=lambda x: x[1]):
            print(f"{m}: {h} horas")

    except Exception as e:
        print("ERROR:")
        print(e)
