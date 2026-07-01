# OBD CAN Bus Monitor

Herramienta para leer el bus CAN nativo del carro via adaptador ELM327 (COM3, 115200 baud).
No usa la librería `python-obd` ni PIDs OBD-II estándar — todo es lectura pasiva ATMA de tramas CAN nativas.

## Archivos

| Archivo | Descripción |
|---|---|
| `can_marcha_velocidad.py` | Herramienta principal: decodifica marcha, velocidad y RPM en live y replay de log |
| `can_marcha.py` | Versión original, solo marcha |
| `can_pid.py` | Explorador de PIDs |
| `can_log.py` | Capturador de log al archivo |
| `obd_lector.py` | Lector via python-obd (referencia, NO usar) |
| `can_log_grande.txt` | Log de manejo completo (~17 min) |
| `CARRO PRENDIDO.txt` | Log con motor en ralentí |

## Uso

```bash
# Live — carro conectado en COM3
python can_marcha_velocidad.py

# Replay rápido de log (solo muestra cambios)
python can_marcha_velocidad.py can_log_grande.txt

# Replay en tiempo real
python can_marcha_velocidad.py can_log_grande.txt --realtime
```

## Configuración ELM327

```
ATZ        reset
ATE0       echo off
ATL0       linefeeds off
ATH1       headers on
ATSP6      protocolo ISO 15765-4 CAN 11-bit 500kbps
0100       iniciar comunicación
ATMA       monitor all (escucha pasiva)
```

Cuando aparece `BUFFER FULL` en la línea, se reenvía `ATMA\r` para recuperar el modo monitor.

## Tramas CAN identificadas

### Formato log: `timestamp CAN_ID B0 B1 B2 B3 B4 B5 B6 B7`
### Formato ATMA (serial): `CAN_ID B0 B1 B2 B3 B4 B5 B6 B7`

En código ATMA: `partes[0]=ID`, `partes[1]=B0`, `partes[2]=B1`, `partes[3]=B2`, `partes[4]=B3`...

### `28D` — Posición de palanca (marcha)
- Byte decodificado: `partes[3]` (B2)
- Códigos: `01`=P, `02`=R, `03`=N, `04`=D, `0F`=transición

### `271` — Velocidad
- Bytes: `partes[3]` (B2) y `partes[4]` (B3)
- Fórmula: `((B2 << 8) | B3) / 256.0` → km/h (fixed-point Q8.8: B2=entero, B3=fracción)

### `118` — RPM
- Bytes: `partes[3]` (B2) y `partes[4]` (B3)
- Fórmula: `((B2 << 8) | B3) / 2.0` → RPM
