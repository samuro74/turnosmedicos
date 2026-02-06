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

def cargar_tecnicos(path):
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
def validar(config, tecnicos):
    errores = []

    claves = (
        "dias_mes",
        "tecnicos_manana",
        "tecnicos_tarde",
        "tecnicos_noche",
        "max_noches_consecutivas"
    )

    for k in claves:
        if k not in config:
            errores.append(f"Falta la clave '{k}' en config.json")

    if errores:
        return errores

    for k in ("tecnicos_manana", "tecnicos_tarde", "tecnicos_noche"):
        if config[k] < 0:
            errores.append(f"{k} no puede ser negativo")

    if len(tecnicos) < max(
        config["tecnicos_manana"],
        config["tecnicos_tarde"],
        config["tecnicos_noche"]
    ):
        errores.append("Técnicos insuficientes para cubrir los turnos.")

    if config["max_noches_consecutivas"] < 1:
        errores.append("El máximo de noches consecutivas debe ser ≥ 1.")

    return errores

# =====================================================
# EXCLUSIONES
# =====================================================
def bloqueado(nombre, dia, turno, exclusiones):
    bloqueos = exclusiones.get(nombre, {}).get(dia, set())
    if "MTN" in bloqueos:
        return True
    return turno in bloqueos

# =====================================================
# INSERTAR FILAS DE HORAS
# =====================================================
def insertar_filas_horas(df):
    filas = []

    for _, row in df.iterrows():
        filas.append(row)

        horas = {"Técnico": ""}
        for col, val in row.items():
            if col == "Técnico":
                continue
            horas[col] = 8 if val in ("M", "T", "N") else ""

        filas.append(pd.Series(horas))

    return pd.DataFrame(filas).reset_index(drop=True)

# =====================================================
# GENERADOR DE TURNOS (8 HORAS)
# REGLA: NOCHE -> DESCANSO OBLIGATORIO AL DÍA SIGUIENTE
# =====================================================
def generar_turnos(config, tecnicos, exclusiones):
    incidencias = []
    errores = validar(config, tecnicos)
    if errores:
        raise RuntimeError("\n".join(errores))

    dias = config["dias_mes"]
    tm = config["tecnicos_manana"]
    tt = config["tecnicos_tarde"]
    tn = config["tecnicos_noche"]
    max_noches = config["max_noches_consecutivas"]

    turnos = {t: {} for t in tecnicos}

    carga = defaultdict(int)
    noches_consecutivas = defaultdict(int)
    hizo_noche_ayer = defaultdict(bool)

    turnos_m = defaultdict(int)
    turnos_t = defaultdict(int)
    turnos_n = defaultdict(int)

    for dia in range(1, dias + 1):

        # =========================
        # MAÑANA (no permitido si hizo noche ayer)
        # =========================
        candidatos_m = sorted(
            tecnicos,
            key=lambda t: (turnos_m[t], carga[t], random.random())
        )

        manana = []
        for t in candidatos_m:
            if len(manana) >= tm:
                break
            if (
                not hizo_noche_ayer[t]
                and not bloqueado(t, dia, "M", exclusiones)
            ):
                manana.append(t)

        # =========================
        # TARDE (no permitido si hizo noche ayer)
        # =========================
        candidatos_t = sorted(
            tecnicos,
            key=lambda t: (turnos_t[t], carga[t], random.random())
        )

        tarde = []
        for t in candidatos_t:
            if len(tarde) >= tt:
                break
            if (
                t not in manana
                and not hizo_noche_ayer[t]
                and not bloqueado(t, dia, "T", exclusiones)
            ):
                tarde.append(t)

        # =========================
        # NOCHE
        # =========================
        candidatos_n = sorted(
            tecnicos,
            key=lambda t: (
                turnos_n[t],
                noches_consecutivas[t],
                carga[t],
                random.random()
            )
        )

        noche = []
        for t in candidatos_n:
            if len(noche) >= tn:
                break
            if (
                t not in manana
                and t not in tarde
                and noches_consecutivas[t] < max_noches
                and not bloqueado(t, dia, "N", exclusiones)
            ):
                noche.append(t)

        if len(noche) < tn:
            incidencias.append(
                f"Día {dia}: faltaron {tn - len(noche)} turno(s) de noche."
            )

        # =========================
        # ASIGNACIÓN FINAL
        # =========================
        for t in tecnicos:
            if t in noche:
                turnos[t][f"Día {dia}"] = "N"
                carga[t] += 8
                turnos_n[t] += 1
                noches_consecutivas[t] += 1
                hizo_noche_ayer[t] = True

            elif t in tarde:
                turnos[t][f"Día {dia}"] = "T"
                carga[t] += 8
                turnos_t[t] += 1
                noches_consecutivas[t] = 0
                hizo_noche_ayer[t] = False

            elif t in manana:
                turnos[t][f"Día {dia}"] = "M"
                carga[t] += 8
                turnos_m[t] += 1
                noches_consecutivas[t] = 0
                hizo_noche_ayer[t] = False

            else:
                # Descanso (incluye descanso post-noche)
                turnos[t][f"Día {dia}"] = ""
                noches_consecutivas[t] = 0
                hizo_noche_ayer[t] = False

    df = pd.DataFrame.from_dict(turnos, orient="index")
    df.insert(0, "Técnico", df.index)
    df.reset_index(drop=True, inplace=True)

    return df, carga, turnos_m, turnos_t, turnos_n, incidencias

# =====================================================
# EJECUCIÓN
# =====================================================
if __name__ == "__main__":
    try:
        config = cargar_config("config_tecnico.json")

        if config.get("seed") is not None:
            random.seed(config["seed"])

        tecnicos = cargar_tecnicos("tecnicos.csv")
        exclusiones = cargar_exclusiones("exclusiones.csv")

        df, carga, tm, tt, tn, incidencias = generar_turnos(
            config, tecnicos, exclusiones
        )

        df = insertar_filas_horas(df)
        df.to_excel("cuadro_turnos_tecnicos.xlsx", index=False)

        print("Cuadro de turnos generado correctamente\n")
        print("Resumen de carga:")

        for t in sorted(tecnicos):
            print(
                f"{t}: Mañana={tm[t]} | Tarde={tt[t]} | Noche={tn[t]} | Horas={carga[t]}"
            )

        if incidencias:
            print("\nINCIDENCIAS DETECTADAS:")
            for i in incidencias:
                print(f"- {i}")
        else:
            print("\nNo se detectaron incidencias.")

    except Exception as e:
        print("ERROR:")
        print(e)
