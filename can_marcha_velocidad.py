import serial
import time
import sys

PORT = "COM3"
BAUDRATE = 115200

GEAR_CODES = {"01": "P", "02": "R", "03": "N", "04": "D"}

def enviar(ser, cmd, espera=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(espera)
    ser.read_all()

def normalizar(linea):
    if "<" in linea:
        linea = linea[:linea.index("<")].strip()
    partes = linea.split()
    if not partes:
        return ""
    # Si el primer token es timestamp decimal (log), descartarlo
    if "." in partes[0] and partes[0].replace(".", "", 1).isdigit():
        partes = partes[1:]
    return " ".join(partes)

def procesar(linea, marcha, velocidad, rpm):
    partes = linea.split()
    if not partes:
        return marcha, velocidad, rpm

    can_id = partes[0]

    if can_id == "28D" and len(partes) >= 4:
        codigo = partes[3]
        marcha = GEAR_CODES.get(codigo, f"?({codigo})")

    elif can_id == "271" and len(partes) >= 5:
        try:
            raw = (int(partes[3], 16) << 8) | int(partes[4], 16)
            velocidad = raw / 256.0
        except ValueError:
            pass

    elif can_id == "118" and len(partes) >= 5:
        try:
            raw = (int(partes[3], 16) << 8) | int(partes[4], 16)
            rpm = raw / 2.0
        except ValueError:
            pass

    return marcha, velocidad, rpm

def mostrar(marcha, velocidad, rpm):
    mar_str = marcha if marcha is not None else "?"
    vel_str = f"{velocidad:.1f} km/h" if velocidad is not None else "-- km/h"
    rpm_str = f"{rpm:.0f} RPM" if rpm is not None else "-- RPM"
    print(f"Palanca: {mar_str}  |  Velocidad: {vel_str}  |  RPM: {rpm_str}")

# ---------------------------------------------------------------------------

marcha = None
velocidad = None
rpm = None

if len(sys.argv) > 1:
    # Modo replay: python can_marcha_velocidad.py archivo.txt [--realtime]
    log_file = sys.argv[1]
    realtime = "--realtime" in sys.argv
    print(f"[LOG] {log_file}  {'(tiempo real)' if realtime else '(rapido)'}")
    print("-" * 60)

    prev_ts = None
    with open(log_file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Simular timing real si se pide
            if realtime:
                partes_raw = line.split()
                if partes_raw and "." in partes_raw[0] and partes_raw[0].replace(".", "", 1).isdigit():
                    ts = float(partes_raw[0])
                    if prev_ts is not None:
                        dt = ts - prev_ts
                        if 0 < dt < 0.5:
                            time.sleep(dt)
                    prev_ts = ts

            linea = normalizar(line)
            if not linea:
                continue

            estado_prev = (marcha, velocidad, rpm)
            marcha, velocidad, rpm = procesar(linea, marcha, velocidad, rpm)
            if (marcha, velocidad, rpm) != estado_prev:
                mostrar(marcha, velocidad, rpm)

else:
    # Modo live: puerto serial ATMA
    ser = serial.Serial(PORT, BAUDRATE, timeout=1)
    enviar(ser, "ATZ", espera=2)
    enviar(ser, "ATE0")
    enviar(ser, "ATL0")
    enviar(ser, "ATH1")
    enviar(ser, "ATSP6")
    enviar(ser, "0100")
    ser.write(b"ATMA\r")

    while True:
        linea = ser.read_until(b"\r").decode(errors="ignore").strip()
        if not linea:
            continue

        if "BUFFER" in linea:
            ser.write(b"ATMA\r")
            continue

        marcha, velocidad, rpm = procesar(linea, marcha, velocidad, rpm)
        mostrar(marcha, velocidad, rpm)
