import serial
import time

PORT = "COM3"
BAUDRATE = 115200
LOG = "can_log.txt"

def enviar(ser, cmd, espera=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(espera)
    ser.read_all()

ser = serial.Serial(PORT, BAUDRATE, timeout=1)
enviar(ser, "ATZ", espera=2)
enviar(ser, "ATE0")
enviar(ser, "ATL0")
enviar(ser, "ATH1")
enviar(ser, "ATSP6")
enviar(ser, "0100")
ser.write(b"ATMA\r")

print(f"Guardando en {LOG} ... Ctrl+C para detener")
with open(LOG, "w") as f:
    while True:
        linea = ser.read_until(b"\r").decode(errors="ignore").strip()
        if "BUFFER" in linea:
            ser.write(b"ATMA\r")
        elif linea and not linea.startswith(">"):
            entrada = f"{time.time():.3f} {linea}\n"
            f.write(entrada)
            print(entrada, end="")
