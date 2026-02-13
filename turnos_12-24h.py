import json
import pandas as pd
import random
from collections import defaultdict

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

def cargar_exclusiones(path):
    df = pd.read_csv(path)
    requeridas = {"nombre", "dia", "turno"}
    if not requeridas.issubset(df.columns):
        raise ValueError("exclusiones.csv debe tener columnas: nombre, dia, turno")

    excl = defaultdict(lambda: defaultdict(set))
    for _, r in df.iterrows():
        excl[r["nombre"]][int(r["dia"])].add(r["turno"].upper())
    return excl

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
        errores.append("Médicos insuficientes para cubrir los turnos.")

    if config["max_noches_consecutivas"] < 1:
        errores.append("El máximo de noches consecutivas debe ser ≥ 1.")

    return errores

# =====================================================
# UTILIDAD EXCLUSIONES
# =====================================================
def bloqueado(nombre, dia, turno, exclusiones):
    bloqueos = exclusiones.get(nombre, {}).get(dia, set())
    if "DN" in bloqueos:
        return True
    return turno in bloqueos

# =====================================================
# UTILIDAD INSERTAR FILAS CON HORAS
# =====================================================
def insertar_filas_horas(df):
    filas = []

    for _, row in df.iterrows():
        filas.append(row)

        horas = {"Médico": ""}
        for col, val in row.items():
            if col == "Médico":
                continue
            if val in ("D", "N"):
                horas[col] = 12
            elif val == "DN":
                horas[col] = 24
            else:
                horas[col] = ""

        filas.append(pd.Series(horas))

    return pd.DataFrame(filas).reset_index(drop=True)

# =====================================================
# GENERADOR
# =====================================================
def generar_turnos(config, medicos, exclusiones):
    incidencias = []
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
    hizo_noche_ayer = defaultdict(bool)

    turnos_dia = defaultdict(int)
    turnos_noche = defaultdict(int)

    for dia in range(1, dias + 1):

        # =================================================
        # TURNOS DE 24 HORAS
        # =================================================
        if tipo == 24:

            candidatos_dia = sorted(
                medicos,
                key=lambda m: (
                    turnos_dia[m],
                    carga[m],
                    random.random()
                )
            )

            diurnos = []
            for m in candidatos_dia:
                if len(diurnos) >= md:
                    break
                if (
                    not hizo_noche_ayer[m]
                    and not bloqueado(m, dia, "D", exclusiones)
                ):
                    diurnos.append(m)

            candidatos_noche = sorted(
                diurnos,
                key=lambda m: (
                    turnos_noche[m],
                    noches_consecutivas[m],
                    carga[m],
                    random.random()
                )
            )

            nocturnos = []
            for m in candidatos_noche:
                if len(nocturnos) >= mn:
                    break
                if (
                    noches_consecutivas[m] < max_noches
                    and not bloqueado(m, dia, "N", exclusiones)
                ):
                    nocturnos.append(m)

            if len(nocturnos) < mn:
                incidencias.append(
                    f"Día {dia}: no se pudo asignar {mn - len(nocturnos)} turno(s) de noche (24h)."
                )

            for m in medicos:
                if m in nocturnos:
                    turnos[m][f"Día {dia}"] = "DN"
                    carga[m] += 24
                    turnos_dia[m] += 1
                    turnos_noche[m] += 1
                    noches_consecutivas[m] += 1
                    hizo_noche_ayer[m] = True
                elif m in diurnos:
                    turnos[m][f"Día {dia}"] = "D"
                    carga[m] += 12
                    turnos_dia[m] += 1
                    noches_consecutivas[m] = 0
                    hizo_noche_ayer[m] = False
                else:
                    turnos[m][f"Día {dia}"] = ""
                    noches_consecutivas[m] = 0
                    hizo_noche_ayer[m] = False

        # =================================================
        # TURNOS DE 12 HORAS
        # =================================================
        else:

            candidatos_dia = sorted(
                medicos,
                key=lambda m: (
                    turnos_dia[m],
                    carga[m],
                    random.random()
                )
            )

            diurnos = []
            for m in candidatos_dia:
                if len(diurnos) >= md:
                    break
                if (
                    not hizo_noche_ayer[m]
                    and not bloqueado(m, dia, "D", exclusiones)
                ):
                    diurnos.append(m)

            candidatos_noche = sorted(
                medicos,
                key=lambda m: (
                    turnos_noche[m],
                    noches_consecutivas[m],
                    carga[m],
                    random.random()
                )
            )

            nocturnos = []
            for m in candidatos_noche:
                if len(nocturnos) >= mn:
                    break
                if (
                    m not in diurnos
                    and noches_consecutivas[m] < max_noches
                    and not bloqueado(m, dia, "N", exclusiones)
                ):
                    nocturnos.append(m)

            if len(nocturnos) < mn:
                incidencias.append(
                    f"Día {dia}: no se pudo asignar {mn - len(nocturnos)} turno(s) de noche (12h)."
                )

            for m in medicos:
                if m in nocturnos:
                    turnos[m][f"Día {dia}"] = "N"
                    carga[m] += 12
                    turnos_noche[m] += 1
                    noches_consecutivas[m] += 1
                    hizo_noche_ayer[m] = True
                elif m in diurnos:
                    turnos[m][f"Día {dia}"] = "D"
                    carga[m] += 12
                    turnos_dia[m] += 1
                    noches_consecutivas[m] = 0
                    hizo_noche_ayer[m] = False
                else:
                    turnos[m][f"Día {dia}"] = ""
                    noches_consecutivas[m] = 0
                    hizo_noche_ayer[m] = False

    df = pd.DataFrame.from_dict(turnos, orient="index")
    df.insert(0, "Médico", df.index)
    df.reset_index(drop=True, inplace=True)

    return df, carga, turnos_dia, turnos_noche, incidencias

# =====================================================
# EJECUCIÓN
# =====================================================
if __name__ == "__main__":
    try:
        config = cargar_config("config.json")

        if config.get("seed") is not None:
            random.seed(config["seed"])

        medicos = cargar_medicos("medicos.csv")
        exclusiones = cargar_exclusiones("exclusiones.csv")

        df, carga, td, tn, incidencias = generar_turnos(config, medicos, exclusiones)
        df = insertar_filas_horas(df)
        df.to_excel("cuadro_turnos.xlsx", index=False)

        print("Cuadro generado correctamente\n")
        print("Resumen de carga y turnos:")
        for m in sorted(medicos):
            print(
                f"{m}: Día={td[m]} | Noche={tn[m]} | Horas={carga[m]}"
            )

        if incidencias:
            print("\nINCIDENCIAS DETECTADAS:")
            for i in incidencias:
                print(f"- {i}")
        else:
            print("\nNo se detectaron incidencias en la asignación.")

    except Exception as e:
        print("ERROR:")
        print(e)
