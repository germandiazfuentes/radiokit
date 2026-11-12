# Cómo añadir una radio nueva a radiokit

radiokit separa **protocolo** (cómo se habla con la radio por el cable) de **driver**
(qué significa cada byte de su memoria). Añadir un modelo es uno de estos tres casos:

| Caso | Ejemplo | Qué hay que escribir |
|---|---|---|
| A. Mismo protocolo y mismo mapa que uno existente | BF-A58S, UV-9R, 5RX respecto al UV-S Plus | Una subclase de ~10 líneas |
| B. Mismo protocolo, mapa distinto | UV-5R, UV-82 (familia `uv5r`) | Un driver nuevo |
| C. Protocolo nuevo | UV-5RM / UV-17Pro, Radtel RT-470, UV-K5, DMR | Un módulo en `protocols/` + un driver |

## Reglas de seguridad (obligatorias)

1. `Protocol.identify()` **solo puede leer**. La autodetección lo ejecuta en cualquier radio conectada.
2. `WRITABLE` lista **solo** las zonas que se pueden escribir sin riesgo (canales, nombres, ajustes de menú).
   Calibración, firmware, límites de banda y zonas desconocidas **nunca** van en `WRITABLE`.
   El test `test_drivers_well_formed` falla si una zona escribible se solapa con una de tipo `service`.
3. `encode_channel()` modifica **solo los campos que cambian** y respeta los bits desconocidos.
   El test de ida y vuelta (`test_roundtrip_all_real_dumps`) lo comprueba con volcados reales.
4. Antes de dar un driver por bueno: lectura real → comprobar que el volcado se repite (mismo SHA256)
   → decodificar y comparar con lo que muestra la pantalla de la radio → escribir **un** cambio pequeño.

## Caso A: modelo hermano

```python
# radiokit/drivers/baofeng_wp970i.py
@register
class BaofengUV9R(WP970IFamily):
    ID = "baofeng.uv-9r"
    MODEL = "UV-9R"
    NAME_LEN = 7
    PROTOCOL_PARAMS = {"magic": MAGIC_WP970I}
    CHIRP_CLASS, CHIRP_MODEL = "UV9R", "UV-9R"
    NOTES = "Sin verificar con hardware real."
```

Si dos modelos responden al mismo handshake, se distinguen en `matches(info)` (por ejemplo, por
`info["firmware"]` o `info["ident"]`), y `PRIORITY` decide el preferido.

## Caso B: driver nuevo sobre un protocolo existente

Crear `radiokit/drivers/<fabricante>_<familia>.py` con una subclase de `RadioDriver`:

```python
@register
class MiRadio(RadioDriver):
    ID, VENDOR, MODEL = "fabricante.modelo", "Fabricante", "Modelo"
    PROTOCOL = BaofengCloneProtocol
    PROTOCOL_PARAMS = {"magic": bytes.fromhex("...")}
    MEM_SIZE = 0x1800
    WRITABLE = ((0x0000, 0x0800, "Canales"), ...)
    REGIONS = (...)                     # mapa documental, se ve en la pestaña "Memoria"
    SETTINGS = (Setting("squelch", "Squelch", "Basicos", 0x0E28, "list", ("Off", "1", ...)), ...)

    @classmethod
    def capabilities(cls): return Capabilities(channels=(0, 127), ...)
    @classmethod
    def decode_channel(cls, mem, n): ...
    @classmethod
    def encode_channel(cls, mem, ch): ...
```

Los **ajustes** son datos: cada `Setting` indica dirección, tipo (`list`, `int`, `bool`, `text`,
`freq_fm`), bit y anchura si es un campo de bits, y si es `advanced` (opciones ocultas).
La interfaz web los muestra automáticamente agrupados.

## Caso C: protocolo nuevo

Crear `radiokit/protocols/<nombre>.py` con una subclase de `Protocol`:

- `BAUDRATE`, `WRITE_BLOCK`
- `identify()` → `dict` con al menos `ident` y `firmware`, o `None` si la radio no responde
- `read_memory(size, progress)` → `bytearray`
- `write_block(addr, data)`
- `close()` si el protocolo necesita un comando de salida

Particularidades conocidas de otras familias (referencia: drivers de CHIRP):

| Familia | Baudios | Handshake | Notas |
|---|---|---|---|
| UV-5R clásico | 9600 | 7 bytes `50 BB FF …` | Mismo `BaofengCloneProtocol`, mapa 0x1800 + zona aux |
| UV-17Pro / UV-5RM / K5-Plus | 115200 | ASCII `PROGRAMBFNORMALU`, `PROGRAMCOLORPROU`… | Bloques cifrados con XOR, varias zonas de memoria |
| UV-17 / UV-13Pro | 57600 | `PASSSTA` | |
| Radtel RT-470/495, A36plus (JC8810) | 57600 | `PROGRAMJC81U` | |
| Quansheng / Baofeng UV-K5 | 38400 | Paquetes con CRC y ofuscación XOR | Firmware abierto: permite control en vivo |
| DMR (DM-32UV, DM-1701, RT-3S) | 115200 | Propio | Requiere ampliar el modelo: contactos, grupos, zonas, IDs |

Para el emulador de pruebas, añadir un `testing/fake_<protocolo>.py` que implemente la máquina de
estados de la radio; así se prueba la escritura sin hardware.

## Comprobación

```
python -m unittest -v tests.test_radiokit
python -m radiokit drivers
python -m radiokit read --port COM6
python -m radiokit show backups/radiokit/<driver>/<copia>.bin
```
