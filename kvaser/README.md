# Kvaser J1939 Injector

Herramienta para inyectar tramas J1939 (CAN 29-bit extendido, 250kbps) en un bus vía el
adaptador Kvaser U100, usando la librería oficial de Kvaser (`canlib`/`pycanlib`), no
`python-can`.

## Archivos

| Archivo | Descripción |
|---|---|
| `can_kvaser.py` | Herramienta única: inyección directa, replay de log, y bridge desde ELM327 |
| `can_log_grande.txt` | Log de ejemplo (formato del carro, 11-bit) para probar `replay` |

## Requisitos

- Driver propietario de Kvaser instalado (`mhydra`/`kvcommon` vía dkms, del repo
  [astuff/kvaser-linuxcan](https://github.com/astuff/kvaser-linuxcan)) — **no** el driver
  `kvaser_usb` de SocketCAN, son mutuamente excluyentes.
- Dependencias Python: `pip install -r requirements.txt` (`canlib` no está en PyPI, ver
  el propio `requirements.txt` para instalarlo manualmente).
- El U100 conectado por USB, canal 0.

## Uso

```bash
# Inyectar velocidad/marcha J1939 directo, en loop cada 0.5s
python3 can_kvaser.py speed 100 --repeat --interval 0.5
python3 can_kvaser.py gear 2 --repeat --interval 0.5      # -1=R, 0=N, 1,2,3...=marchas

# Una sola trama
python3 can_kvaser.py speed 80
python3 can_kvaser.py gear -1

# Reproducir un log del carro (formato 11-bit) recodificado como J1939
python3 can_kvaser.py replay can_log_grande.txt
python3 can_kvaser.py replay can_log_grande.txt --realtime   # respeta el timing real

# Puente en vivo: ELM327 (carro real) -> decodifica -> J1939 -> Kvaser
python3 can_kvaser.py bridge
```

`--channel` (default `0`) y `--repeat`/`--interval` son comunes a todos los subcomandos.

## Codificación J1939

ID de 29 bits: `(priority << 26) | (pgn << 8) | source_address`, priority=6.

### Velocidad — PGN `0xFEF1` (CCVS, SPN 84), SA `0x11`
- Bytes: `FF <lo> <hi> CC FF FF 1F FF`
- `<lo>`/`<hi>` = velocidad×256 en little-endian (bytes 1-2)
- Ejemplo: 100 km/h → `FF 00 64 CC FF FF 1F FF` → ID `0x18FEF111`

### Marcha — PGN `0xF005` (ETC1, SPN 523/524), SA `0x03`
- Bytes: `<g> 00 00 <g> 20 4E 4E 32`
- `<g>` = marcha + 125 (125=neutral, <125=reversa, >125=marchas adelante), repetido en byte 0 y 3
- Ejemplo: 2da marcha → byte=127 (`0x7F`) → `7F 00 00 7F 20 4E 4E 32` → ID `0x18F00503`

El carro (automático) solo reporta `P/R/N/D`, no un número de marcha real — `replay` y
`bridge` mapean `P/N→0, R→-1, D→1` (ver `GEAR_TO_J1939` en el código).

## Fuente de datos para `replay`/`bridge`

El carro emite estas tramas nativas (11-bit) vía ELM327 en modo monitor pasivo (`ATMA`),
formato `CAN_ID B0 B1 B2 B3 B4 B5 B6 B7`:
- `28D` → marcha, byte `B2` (`01`=P, `02`=R, `03`=N, `04`=D)
- `271` → velocidad, `((B2 << 8) | B3) / 256.0` km/h

`bridge` abre `/dev/ttyUSB0` a 115200 baud y configura el ELM327 con:
```
ATZ        reset
ATE0       echo off
ATL0       linefeeds off
ATH1       headers on
ATSP6      protocolo ISO 15765-4 CAN 11-bit 500kbps
0100       iniciar comunicación
ATMA       monitor all (escucha pasiva)
```
