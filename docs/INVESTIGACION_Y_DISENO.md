# Baofeng UV-S Plus (tri) — Estado, mapa de memoria y diseño de la aplicación

_Fecha: 2026-11-12 · Radio en COM6 (cable CH340, VID 1A86 / PID 7523)_

## 1. Identificación de la radio

| Dato | Valor |
|---|---|
| Protocolo | Familia **UV-5R / WP970I**, handshake **UV-S9X3** (`50 BB FF 20 12 07 25`) |
| Ident devuelto | `AA 30 76 04 00 05 20 DD` |
| Firmware (0x1EF0) | `HN5RV011` |
| Código "6+encendido" (0x1ED0) | `151123H` (probablemente lote/fecha de fabricación) |
| Mensaje de encendido | `WELCOME` |
| Bandas TX habilitadas (0x1FC0) | VHF 136–174 · VHF2 200–260 · UHF 400–520 MHz |
| Memoria | 0x2000 bytes (8 KiB), 128 canales, sin "dropped byte" |
| Driver CHIRP equivalente | `UV-S9X3` (`baofeng_wp970i.py`, clase `UVS9X3`) |

## 2. Protocolo de clonado (9600 8N1)

1. PC → `50 BB FF 20 12 07 25` · radio → `06`
2. PC → `02` · radio → 8 bytes `AA .. .. .. .. .. .. DD` (ident)
3. PC → `06` · radio → `06` → **modo programación** (la radio deja de operar)
4. Lectura: PC → `53 AH AL 40` ("S" + dirección + tamaño) · radio → `06` + `58 AH AL 40` + 64 bytes · PC → `06`
5. Escritura (no usada aún): PC → `58 AH AL 10` + 16 bytes · radio → `06`. CHIRP solo escribe los rangos
   `0000–0DF0, 0E00–1800, 1EE0–1EF0, 1F60–1F70, 1F80–1F90, 1FC0–1FD0` → **nunca toca las tablas de calibración**.
6. Antes de leer la zona auxiliar hay que leer un bloque fuera de ella (0x1E80) o devuelve basura (firmwares nuevos).

**No existe control en tiempo real (CAT)** en esta familia: el puerto solo sirve para clonar memoria.
"Controlar" = leer/modificar/escribir la configuración. El control remoto en vivo solo es posible en
radios con firmware abierto (Quansheng/Baofeng UV-K5, Radtel RT-890 OEFW) o vía Bluetooth en algunos modelos nuevos.

## 3. Mapa de memoria (UV-S9X3)

| Rango | Contenido | Escritura segura |
|---|---|---|
| 0x0000–0x07FF | 128 canales × 16 B: RX/TX lbcd (10 Hz), tono RX/TX (ul16), S-code, potencia, ancho, BCL, scan, PTT-ID | ✅ |
| 0x0B00–0x0BEF | 15 códigos PTT-ID DTMF (5 dígitos) | ✅ |
| 0x0CAA–0x0CB2 | ANI (código, cuándo enviar, velocidad DTMF on/off) | ✅ |
| 0x0E20–0x0E4D | Ajustes generales (menú) — ver §4 | ✅ |
| 0x0E4A bits | `displayab`, `fmradio`, `alarm`, **`reset` (habilita menú RESET)**, **`menu` (habilita menús)** | ✅ ocultos |
| 0x0E4B bits | **`singleptt`**, **`vfomrlock` (bloquea paso a modo VFO)** | ✅ ocultos |
| 0x0E76–0x0E77 | Canal activo MR A / B | ✅ |
| 0x0F00–0x0F3F | VFO A y B (frecuencia, offset, tonos, paso, potencia, ancho) | ✅ |
| 0x0F4E | Preset radio FM | ✅ |
| 0x1000–0x17FF | Nombres de canal (7 caracteres) | ✅ |
| 0x1E00–0x1E7F | Copias/valores por defecto de VFO (fábrica) | ⚠️ no tocar |
| **0x1E80–0x1EBF** | **Calibración potencia TX VHF** (13 puntos × High/Mid/Low: `B0…`, `65…`, `4E–50`) | ⛔ servicio |
| 0x1ED0 | Mensaje "tecla 6 + encendido" (`151123H`) | ⚠️ |
| 0x1EE0 | Mensaje de encendido (2×7 car.) | ✅ |
| 0x1EF0 | Versión de firmware (identifica el modelo; no modificar) | ⛔ |
| **0x1F00–0x1F5F** | **Calibración potencia TX UHF/VHF2** (16 puntos × 3 niveles) | ⛔ servicio |
| **0x1F60–0x1F9F** | **Umbrales de squelch** SQL0–9 VHF/UHF (CHIRP los expone como "Service Settings") + VOX/curvas | ⚠️ servicio |
| 0x1FA0–0x1FBF | Calibración sin documentar (probable batería/VOX/desviación) | ⛔ |
| **0x1FC0–0x1FCE** | **Límites de banda TX** (enable + bbcd low/high, MHz) VHF/UHF/VHF2 | ⚠️ legal |

## 4. Ajustes de menú leídos (estado actual)

SQL 5 · STEP 5 kHz · SAVE 1:3 · VOX Off · ABR 5 · TDR (doble escucha) On · BEEP On · TOT 60 s ·
VOICE English · DTMF-ST DT+ANI · SC-REV TO · PTT-ID Off · PTT-LT 5 · MDF-A/B Frequency · BCL Off ·
AUTOLK Off · WT-LED Purple · RX-LED Blue · TX-LED Orange · AL-MOD Tone · TDR-AB Off · STE On ·
RP-STE 5 · RPT-RL Off · PONMSG Full · ROGER On · Modo Channel · KEYLOCK Off.

## 5. Funciones ocultas y de servicio

### En la radio (combinaciones al encender — familia UV-5R; verificar en esta unidad)
| Combinación | Efecto |
|---|---|
| Mantener **3** + encender | Muestra versión de firmware |
| Mantener **6** + encender | Muestra el texto de 0x1ED0 (`151123H`) |
| **PTT + MONI + VFO/MR** + encender | Modo "FACTORY": carga canales de prueba de fábrica (¡sobrescribe canales!) |
| **MENU** + encender (variantes UV-82) | Alterna VFO/MR cuando está bloqueado |
| PTT + BAND / PTT + A/B | Tono de apertura 1750 Hz (repetidores) |
| Menú RESET (VFO / ALL) | Reset; ALL borra canales |

### Por software (memoria)
- Habilitar/inhabilitar menús y RESET (`0x0E4A`), bloqueo VFO/MR y PTT único (`0x0E4B`).
- Límites de banda TX (`0x1FC0`): ampliar/restringir rangos. Fuera de las bandas autorizadas es ilegal transmitir.
- Umbrales de squelch por nivel (calibración RX).
- Tablas de potencia TX por frecuencia (calibración; un error puede dejar la radio sin potencia o dañar el PA).
- Mensajes de encendido, 15 códigos PTT-ID, ANI, presets FM.

## 6. Ecosistema de modelos y protocolos (base: drivers CHIRP actuales)

| Familia / driver | Modelos (ejemplos) | Baudios | Notas |
|---|---|---|---|
| `uv5r` | UV-5R, BF-F8HP, UV-82, UV-5RX3, UV-82X3, RT5R, TS-T9+ | 9600 | Handshake 7 B `50 BB FF…`, 0x1800 + aux |
| `baofeng_wp970i` | **UV-S9X3 (esta)**, BF-A58S, UV-82III, UV-9R, GT-3WP, 5RX | 9600 | Igual que arriba, mapa 0x2000 |
| `baofeng_uv17Pro` | UV-5RM, UV-17Pro(GPS), UV-21Pro, K5-Plus, K6, GM-5RH, BF-F8HP-PRO, UV-5G Plus, UV-25, UV-32 | 115200 | Magic ASCII `PROGRAMBFNORMALU`…, bloques cifrados |
| `baofeng_uv17` | UV-17, UV-13Pro | 57600 | `PASSSTA` |
| `mml_jc8810` | Radtel RT-470/470X/495/630, A36plus, UV-A37 | 57600 | `PROGRAMJC81U` |
| `radtel_rt490` | RT-490, 8800 Plus, AR-869 | 9600 | |
| `radtel_rt900` / `rt880g` | RT-900/910/920 (+BT), RT-880G | 57600/115200 | Algunas con programación Bluetooth |
| `uvk5*` | Quansheng / Baofeng UV-K5, UV-K1, Radtel RT-890 (OEFW aparte) | 38400 | XOR + CRC; firmware abierto (egzumer, F4HWN) |
| Digital: `baofeng_dm32uv` | Baofeng DM-32UV (DMR) | 115200 | En CHIRP solo canales analógicos/básico |
| Digital fuera de CHIRP | DM-1701 / RT-3S / MD-UV380, GD-77, AnyTone 868/878 | — | Codeplug DMR (contactos, TG, zonas, RX groups): **qdmr** (GPLv3) y **OpenGD77/OpenUV380** |

## 7. Arquitectura propuesta de la aplicación

```
app/
  core/
    transport.py      # Serial (pyserial) / Bluetooth / fichero; timeouts, log hex
    model.py          # Modelo neutral: Channel, Settings, Zone, Contact (DMR), Calibration
    codeplug.py       # Imagen binaria + metadatos + diff byte a byte
    safety.py         # Backup obligatorio, regiones protegidas, verificación post-escritura
  drivers/
    base.py           # Interfaz: probe() identify() download() upload(ranges) decode() encode()
    layouts/*.yaml    # Mapas de memoria declarativos (offset, tipo: lbcd/bbcd/ul16/bits/char)
    baofeng_wp970i.py # Primer driver (ya probado en lectura con bf_read.ps1)
    ...               # uv5r, uv17pro, jc8810, uvk5, dmr/*
  ui/                 # API local (FastAPI) + interfaz web, o app de escritorio (Tauri/Qt)
```

Principios:
1. **Autodetección**: probar handshakes de cada familia (solo lectura) hasta que uno responda.
2. **Mapas declarativos** (YAML) para añadir modelos sin escribir código; lógica de protocolo en Python por familia.
3. **Seguridad**: backup automático con hash antes de cualquier escritura; las regiones ⛔ solo se escriben en "modo servicio"
   explícito con confirmación doble; tras escribir, releer y comparar.
4. **Import/Export**: CSV de CHIRP, `.img` de CHIRP (ya generado), JSON propio.
5. **Licencia**: reutilizar código de CHIRP o qdmr obliga a GPLv3. Alternativa: usarlos solo como referencia y reimplementar
   (como en `tools/`), o integrarlos como dependencia y publicar la app como GPLv3.
6. **DMR** necesita un modelo de datos más rico (IDs, contactos, talkgroups, timeslot, color code, zonas).

### Fases
1. CLI: detección + backup + decode (hecho para UV-S9X3) → añadir escritura de canales con verificación.
2. Drivers de las familias `uv5r`, `uv17Pro`, `uvk5`.
3. Interfaz gráfica (tabla de canales, plantillas PMR446/emergencias, comparar radios).
4. Radtel JC8810/RT-900, programación Bluetooth.
5. DMR (DM-32UV, DM-1701) apoyándose en qdmr como referencia.

## 8. Observaciones sobre la configuración de fábrica

> La radio numera los canales **0–127** (así aparecen en pantalla y en este documento).

- **Subtonos PMR**: los walkies comerciales numeran los subtonos con la tabla de 38 tonos (subtono 4 = 77.0 Hz,
  subtono 12 = 100.0 Hz…). Para hablar con un PMR comercial en "canal-subtono" hay que usar esa tabla.
  Elegir un subtono poco habitual es una forma sencilla de no oír a otros usuarios en canales saturados.
- Los canales PMR venían en **Wide / High (5 W)**. PMR446 es banda estrecha (12,5 kHz, 0,5 W ERP): con **Narrow** el
  audio es compatible con los PMR comerciales. (Legalmente un Baofeng no está homologado para PMR446.)
- Canales **WX1–WX10** (162–163 MHz) son meteo NOAA de EE. UU.: inútiles en España y entran en el escaneo.
- **146.175 MHz** es la frecuencia SOS-Montaña del Pirineo aragonés, pero necesita subtono **123 Hz** (ver CANALES_ESPANA.md).
- Canales 0 (136.025) y 127 (470.625) sin nombre — probablemente restos de fábrica.
- La copia de referencia `tests/data/uv-s-plus-reference.bin` contiene el plan de canales de CANALES_ESPANA.md §5.
