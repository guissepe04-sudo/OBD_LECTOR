"""
can_maple.py — Monitor CAN en tiempo real para Geely Maple EV

Uso:
  python can_maple.py                              # live (COM3)
  python can_maple.py can_log_cargando.txt         # replay rapido
  python can_maple.py can_log_cargando.txt --realtime  # replay tiempo real

Parametros decodificados:
  09D  B1          -> Marcha:    02=R  03=N  04=D
  122  B0+B1 /256  -> Velocidad: km/h (Q8.8 fixed-point)
  287  B1 *100/150 -> SOC:       % (escala 0-150)
  2C0  B0+B1 *0.5  -> Bateria:   V (voltaje HV)
  17B  B4+B5       -> Carga:     unidad raw (0 = no cargando)
  2A4  B4 =0x40    -> Freno mano: activo (senal principal, ~100ms)
  284  B0 =0x04    -> Freno mano: activo (senal alternativa, mas frecuente)
"""

import serial
import time
import sys

PORT     = "COM3"
BAUDRATE = 115200

GEAR_CODES = {"02": "R", "03": "N", "04": "D"}


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
    if "." in partes[0] and partes[0].replace(".", "", 1).isdigit():
        partes = partes[1:]
    return " ".join(partes)


class Estado:
    def __init__(self):
        self.marcha    = None
        self.velocidad = None
        self.soc       = None
        self.voltaje   = None
        self.carga_raw = None
        self.freno     = None
        self.freno_ts  = 0.0  # ultimo instante detectado freno activo (para latch)

    def campos(self):
        """Campos comparables para detectar cambios (excluye freno_ts)."""
        return (self.marcha, self.velocidad, self.soc,
                self.voltaje, self.carga_raw, self.freno)


def procesar(linea, estado):
    partes = linea.split()
    if not partes:
        return estado

    can_id = partes[0]

    # Marcha — 09D B1
    if can_id == "09D" and len(partes) >= 3:
        estado.marcha = GEAR_CODES.get(partes[2], f"?({partes[2]})")

    # Velocidad — 122 B0+B1 Q8.8 /256
    elif can_id == "122" and len(partes) >= 3:
        try:
            raw = (int(partes[1], 16) << 8) | int(partes[2], 16)
            estado.velocidad = raw / 256.0
        except (ValueError, IndexError):
            pass

    # SOC — 287 B1 escala 0-150
    elif can_id == "287" and len(partes) >= 3:
        try:
            estado.soc = int(partes[2], 16) * 100 / 150
        except (ValueError, IndexError):
            pass

    # Voltaje bateria HV — 2C0 B0+B1 *0.5
    elif can_id == "2C0" and len(partes) >= 3:
        try:
            raw = (int(partes[1], 16) << 8) | int(partes[2], 16)
            estado.voltaje = raw * 0.5
        except (ValueError, IndexError):
            pass

    # Corriente de carga — 17B B4+B5
    elif can_id == "17B" and len(partes) >= 7:
        try:
            raw = (int(partes[5], 16) << 8) | int(partes[6], 16)
            estado.carga_raw = raw
        except (ValueError, IndexError):
            pass

    # Freno de mano — 2A4 B4 (senal principal, activa ~100ms)
    elif can_id == "2A4" and len(partes) >= 6:
        try:
            b4 = int(partes[5], 16)
            if b4 == 0x40:
                estado.freno = True
                estado.freno_ts = time.time()
            else:
                estado.freno = False
        except (ValueError, IndexError):
            pass

    # Freno de mano — 284 B0 (senal alternativa, mas frecuente)
    elif can_id == "284" and len(partes) >= 2:
        try:
            b0 = int(partes[1], 16)
            if b0 == 0x04:
                estado.freno = True
                estado.freno_ts = time.time()
            elif estado.freno:
                estado.freno = False
        except (ValueError, IndexError):
            pass

    return estado


def mostrar(e, multilinea=False):
    mar  = e.marcha    if e.marcha    is not None else "?"
    vel  = f"{e.velocidad:.1f} km/h"  if e.velocidad is not None else "--.- km/h"
    soc  = f"{e.soc:.0f}%"            if e.soc       is not None else "--%"
    bat  = f"{e.voltaje:.0f} V"       if e.voltaje   is not None else "--- V"

    # Latch: mostrar ACTIVO hasta 2s despues de la ultima deteccion
    freno_activo = e.freno or (time.time() - e.freno_ts < 2.0)
    freno = "ACTIVO" if freno_activo else ("libre" if e.freno is not None else "?")

    if e.carga_raw is not None and e.carga_raw > 0:
        carga = f"CARGANDO ({e.carga_raw} raw)"
    elif e.carga_raw == 0:
        carga = "no"
    else:
        carga = "?"

    if multilinea:
        print(f"  Marcha    : {mar}")
        print(f"  Velocidad : {vel}")
        print(f"  SOC       : {soc}")
        print(f"  Bateria   : {bat}")
        print(f"  Carga     : {carga}")
        print(f"  Freno mano: {freno}")
    else:
        print(f"Marcha: {mar:<2}  |  Vel: {vel:<10}  |  SOC: {soc:<5}  |"
              f"  Bat: {bat:<7}  |  Carga: {carga:<20}  |  Freno: {freno}")


# ---------------------------------------------------------------------------

args     = sys.argv[1:]
log_file = None
realtime = "--realtime" in args
for a in args:
    if not a.startswith("--"):
        log_file = a

estado = Estado()

if log_file:
    print(f"[LOG] {log_file}  {'(tiempo real)' if realtime else '(rapido)'}")
    print("-" * 80)
    prev_ts = None
    with open(log_file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
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
            prev_campos = estado.campos()
            estado = procesar(linea, estado)
            if estado.campos() != prev_campos:
                mostrar(estado)

else:
    # Modo live — dashboard completo, actualizado cada 0.5s
    ser = serial.Serial(PORT, BAUDRATE, timeout=0.1)
    enviar(ser, "ATZ", espera=2)
    enviar(ser, "ATE0")
    enviar(ser, "ATL0")
    enviar(ser, "ATH1")
    enviar(ser, "ATSP6")
    # Sin 0100 — el Maple no responde PIDs OBD-II estandar
    ser.write(b"ATMA\r")

    ultimo_print = 0.0
    t_inicio = time.time()

    while True:
        linea = ser.read_until(b"\r").decode(errors="ignore").strip()
        if linea:
            if "BUFFER" in linea:
                ser.write(b"ATMA\r")
                continue
            linea_norm = normalizar(linea)
            if linea_norm:
                estado = procesar(linea_norm, estado)

        ahora = time.time()
        if ahora - ultimo_print >= 0.5:
            ultimo_print = ahora
            elapsed = ahora - t_inicio
            print("\033[H\033[2J", end="", flush=True)
            print(f"══ GEELY MAPLE CAN BUS ══════════════════════ t={elapsed:.0f}s  Ctrl+C para salir")
            mostrar(estado, multilinea=True)
