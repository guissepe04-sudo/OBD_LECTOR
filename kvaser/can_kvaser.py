import argparse
import time

import serial
from canlib import canlib, Frame

CHANNEL = 0
BITRATE = canlib.Bitrate.BITRATE_250K

PORT = "/dev/ttyUSB0"
BAUDRATE = 115200

GEAR_CODES_INV = {"01": "P", "02": "R", "03": "N", "04": "D"}

PRIORITY = 6
PGN_CCVS = 0xFEF1  # velocidad (SPN 84, bytes 1-2 little-endian, /256 km/h)
PGN_ETC1 = 0xF005  # marcha (SPN 524 byte0, SPN 523 byte3, offset -125)
SA_CCVS = 0x11
SA_ETC1 = 0x03
# el carro (automatico) solo trae P/R/N/D, no un numero de marcha real;
# se mapea a un valor J1939 razonable ya que ETC1 espera un entero de marcha
GEAR_TO_J1939 = {"P": 0, "R": -1, "N": 0, "D": 1}


# --------------------------------------------------------------------------
# Envio de tramas J1939 (canlib)
# --------------------------------------------------------------------------

def enviar(ch, can_id, data, repeat=False, interval=0.05, etiqueta=""):
    frame = Frame(id_=can_id, data=list(data), flags=canlib.MessageFlag.EXT)
    tag = f" ({etiqueta})" if etiqueta else ""
    if not repeat:
        try:
            ch.write(frame)
            ch.writeSync(timeout=1000)
        except canlib.exceptions.CanOverflowError:
            pass
        print(f"Enviado {can_id:08X}: {' '.join(f'{b:02X}' for b in data)}{tag}")
        return
    print(f"Enviando {can_id:08X}: {' '.join(f'{b:02X}' for b in data)}{tag} cada {interval}s (Ctrl+C para cortar)")
    try:
        while True:
            try:
                ch.write(frame)
            except canlib.exceptions.CanOverflowError:
                pass
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------
# Codificacion J1939
# --------------------------------------------------------------------------

def j1939_id(pgn, sa, priority=PRIORITY):
    return (priority << 26) | (pgn << 8) | sa


def frame_speed_j1939(kmh):
    raw = round(kmh * 256)
    data = bytes([0xFF, raw & 0xFF, (raw >> 8) & 0xFF, 0xCC, 0xFF, 0xFF, 0x1F, 0xFF])
    return j1939_id(PGN_CCVS, SA_CCVS), data


def frame_gear_j1939(gear_num):
    g = gear_num + 125
    data = bytes([g, 0x00, 0x00, g, 0x20, 0x4E, 0x4E, 0x32])
    return j1939_id(PGN_ETC1, SA_ETC1), data


# --------------------------------------------------------------------------
# Parseo de logs del carro (formato: [timestamp] CAN_ID B0 B1 ... B7)
# --------------------------------------------------------------------------

def normalizar(linea):
    if "<" in linea:
        linea = linea[: linea.index("<")].strip()
    return linea


def parsear_linea(linea):
    partes = normalizar(linea).split()
    if not partes:
        return None

    ts = None
    if "." in partes[0] and partes[0].replace(".", "", 1).isdigit():
        ts = float(partes[0])
        partes = partes[1:]

    if len(partes) < 2:
        return None

    try:
        can_id = int(partes[0], 16)
        data = bytes(int(b, 16) for b in partes[1:])
    except ValueError:
        return None

    return ts, can_id, data


# --------------------------------------------------------------------------
# Subcomandos
# --------------------------------------------------------------------------

def cmd_speed(ch, args):
    can_id, data = frame_speed_j1939(args.valor)
    enviar(ch, can_id, data, args.repeat, args.interval)


def cmd_gear(ch, args):
    can_id, data = frame_gear_j1939(args.valor)
    enviar(ch, can_id, data, args.repeat, args.interval)


def cmd_replay(ch, args):
    realtime = args.realtime
    print(f"[REPLAY -> J1939] {args.log_file}  {'(tiempo real)' if realtime else '(rapido)'}")
    prev_ts = None
    enviados = 0
    try:
        with open(args.log_file, encoding="utf-8", errors="ignore") as f:
            for linea in f:
                resultado = parsear_linea(linea)
                if resultado is None:
                    continue
                ts, can_id, data = resultado

                if can_id == 0x28D and len(data) >= 3:
                    marcha = GEAR_CODES_INV.get(f"{data[2]:02X}")
                    if marcha is None:
                        continue
                    salida_id, salida_data = frame_gear_j1939(GEAR_TO_J1939[marcha])
                    etiqueta = f"marcha={marcha}"
                elif can_id == 0x271 and len(data) >= 4:
                    kmh = ((data[2] << 8) | data[3]) / 256.0
                    salida_id, salida_data = frame_speed_j1939(kmh)
                    etiqueta = f"velocidad={kmh:.1f} km/h"
                else:
                    continue

                if realtime and ts is not None:
                    if prev_ts is not None:
                        dt = ts - prev_ts
                        if 0 < dt < 0.5:
                            time.sleep(dt)
                    prev_ts = ts

                try:
                    ch.write(Frame(id_=salida_id, data=list(salida_data), flags=canlib.MessageFlag.EXT))
                except canlib.exceptions.CanOverflowError:
                    time.sleep(0.02)
                    continue

                enviados += 1
                bytes_str = " ".join(f"{b:02X}" for b in salida_data)
                print(f"{salida_id:08X}  {bytes_str}  ->  {etiqueta}")
    except KeyboardInterrupt:
        pass
    finally:
        print(f"Listo. {enviados} tramas enviadas.")


def cmd_bridge(ch, args):
    marcha = None
    velocidad = None

    print(f"[ELM327 -> Kvaser J1939] {PORT}")
    ser = serial.Serial(PORT, BAUDRATE, timeout=1)
    for cmd, espera in [("ATZ", 2), ("ATE0", 0.5), ("ATL0", 0.5), ("ATH1", 0.5), ("ATSP6", 0.5), ("0100", 0.5)]:
        ser.write((cmd + "\r").encode())
        time.sleep(espera)
        ser.read_all()
    ser.write(b"ATMA\r")

    try:
        while True:
            linea = ser.read_until(b"\r").decode(errors="ignore").strip()
            if not linea:
                continue
            if "BUFFER" in linea:
                ser.write(b"ATMA\r")
                continue

            partes = linea.split()
            if not partes:
                continue
            can_id = partes[0]

            if can_id == "28D" and len(partes) >= 4:
                nueva_marcha = GEAR_CODES_INV.get(partes[3])
                if nueva_marcha is not None and nueva_marcha != marcha:
                    marcha = nueva_marcha
                    j_id, j_data = frame_gear_j1939(GEAR_TO_J1939[marcha])
                    enviar(ch, j_id, j_data, etiqueta=f"marcha={marcha}")

            elif can_id == "271" and len(partes) >= 5:
                try:
                    raw = (int(partes[3], 16) << 8) | int(partes[4], 16)
                    nueva_velocidad = raw / 256.0
                except ValueError:
                    continue
                if nueva_velocidad != velocidad:
                    velocidad = nueva_velocidad
                    j_id, j_data = frame_speed_j1939(velocidad)
                    enviar(ch, j_id, j_data, etiqueta=f"velocidad={velocidad:.1f} km/h")
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--channel", type=int, default=CHANNEL)
    common.add_argument("--repeat", action="store_true", help="reenviar en loop en vez de una sola vez")
    common.add_argument("--interval", type=float, default=0.05, help="segundos entre reenvíos con --repeat")

    ap = argparse.ArgumentParser(description="Herramienta Kvaser: inyeccion J1939, replay de logs, y bridge desde ELM327")
    sub = ap.add_subparsers(dest="modo", required=True)

    sp = sub.add_parser("speed", help="CCVS (0xFEF1) - velocidad J1939", parents=[common])
    sp.add_argument("valor", type=float, help="km/h")
    sp.set_defaults(func=cmd_speed)

    sp = sub.add_parser("gear", help="ETC1 (0xF005) - marcha J1939", parents=[common])
    sp.add_argument("valor", type=int, help="-1=R, 0=N, 1,2,3...=marchas adelante")
    sp.set_defaults(func=cmd_gear)

    sp = sub.add_parser("replay", help="reproducir un log del carro (marcha/velocidad) recodificado como J1939", parents=[common])
    sp.add_argument("log_file")
    sp.add_argument("--realtime", action="store_true", help="respetar timing real del log")
    sp.set_defaults(func=cmd_replay)

    sp = sub.add_parser("bridge", help="leer ELM327 en vivo y reenviar marcha/velocidad como J1939", parents=[common])
    sp.set_defaults(func=cmd_bridge)

    args = ap.parse_args()

    with canlib.openChannel(channel=args.channel, bitrate=BITRATE) as ch:
        ch.busOn()
        try:
            args.func(ch, args)
        finally:
            ch.busOff()


if __name__ == "__main__":
    main()
