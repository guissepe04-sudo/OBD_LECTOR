import serial
import time

PORT = "COM3"
BAUDRATE = 115200

def enviar(ser, cmd, espera=0.5):
    ser.write((cmd + "\r").encode())
    time.sleep(espera)
    return ser.read_all().decode(errors="ignore").strip()

ser = serial.Serial(PORT, BAUDRATE, timeout=1)

enviar(ser, "ATZ", espera=2)
enviar(ser, "ATE0")
enviar(ser, "ATL0")
enviar(ser, "ATH1")
enviar(ser, "ATSP6")
enviar(ser, "0100")

ser.write(b"ATMA\r")  # no leer respuesta, ir directo al loop

print("--- frames CAN ---")
while True:
    linea = ser.read_until(b"\r").decode(errors="ignore").strip()
    if linea == "BUFFER FULL":
        ser.write(b"ATMA\r")
    elif linea:
        print(linea)
