# radiokit

Aplicación para leer, editar y programar de forma segura walkies Baofeng, Radtel y similares.
Hecha en Python, solo con la biblioteca estándar: no necesita instalar nada (si `pyserial` está
instalado lo usa; si no, accede al puerto serie directamente con la API de Windows).

## Cable de programación

Para conectar la radio al PC hace falta un cable USB con conector Kenwood de 2 clavijas (3,5 mm + 2,5 mm):

👉 **[Cable de programación USB 2 pines para Baofeng](https://link.amazon/B00vVvpnN)** (Amazon)

Compatible con: Baofeng **UV-S Plus (tri)** (probado con radiokit), UV-5R, UV-5RA, UV-5RE, UV-5R EX, UV-5RX3, BF-888S, BF-88E, Quansheng UV-K5,
Retevis RT24, RT27, RT22, RT5R, RT622, RT3S, H777, RA79, GA-2S, y radios Kenwood y Wouxun con el mismo conector.
Funciona en Windows XP/7/8/10/11 (no en Mac).

Al conectarlo aparece como un puerto COM en Windows (p.ej. COM6); si no aparece, instala el controlador del chip
USB-serie del cable. Enciende la radio con el cable bien encajado hasta el fondo y el volumen a medio recorrido.

<sub>Enlace de afiliado: como afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los
requisitos aplicables. El precio para ti es el mismo.</sub>

## Uso

```
iniciar.cmd                                   (o: python -m radiokit serve)
```
Abre `http://127.0.0.1:8446` en el navegador:

1. Elige el puerto del cable (CH340 → p.ej. COM6) y pulsa **Leer radio**. Se guarda copia automática.
2. Edita canales (clic en una fila) y ajustes. Los cambios quedan en un **borrador** resaltado.
3. **Revisar y escribir**: muestra exactamente qué canales/ajustes/bloques cambian.
   Usa **Ensayo** para comprobar sin escribir; luego **Escribir**.

Modo demo sin hardware: `python -m radiokit serve --demo tests/data/uv-s-plus-reference.bin` (puerto `DEMO`).

`tests/data/uv-s-plus-reference.bin` es un volcado real de una Baofeng UV-S Plus (tri) con un plan de canales
útil en España: PMR446 en banda estrecha, SOS-Montaña (146.175 MHz, subtono 123 Hz), Canal 7-7 y canales
marítimos de solo escucha. Detalles y fuentes en [docs/CANALES_ESPANA.md](docs/CANALES_ESPANA.md).

Línea de comandos: `python -m radiokit ports | drivers | read --port COM6 | show <copia.bin>`.

## Seguridad al escribir

- Solo se escriben bloques modificados y solo en zonas permitidas por el driver
  (calibración, firmware, límites de banda: protegidos).
- Antes de escribir se lee la radio y se guarda copia `prewrite`; si la radio cambió en lo que
  se va a escribir, se cancela sin tocar nada.
- Después se relee la radio y se verifica bloque a bloque (copia `postwrite`).

## Estructura

```
radiokit/core/       transporte serie, imagen de memoria, modelo de canal, ajustes declarativos, servicio seguro
radiokit/protocols/  familias de protocolo de clonado
radiokit/drivers/    modelos concretos (mapa de memoria) + registro y autodetección
radiokit/testing/    emulador de radio para pruebas y modo demo
radiokit/web/        servidor local y interfaz
tests/               pruebas (python -m unittest -v tests.test_radiokit)
tools/               scripts originales (lectura/escritura PowerShell, plan de canales)
docs/                investigación, canales útiles en España, cómo añadir radios
```

## Modelos

| Modelo | Protocolo | Estado |
|---|---|---|
| Baofeng **UV-S Plus (tri)** / UV-S9X3 | Clonado Baofeng clásico | Verificado con hardware: lectura y escritura |
| Baofeng **UV-5R** | Clonado Baofeng clásico (mismo handshake; se distingue por firmware) | Lectura; escritura se habilita tras verificar con la radio |
| Baofeng **UV-13 Pro** (V1/V2) | Familia UV-17 (57600, páginas de flash con nivelación de desgaste) | Experimental, solo lectura |
| Quansheng **UV-K5** / UV-K5(8) / UV-K6 | Paquetes 38400 con XOR + CRC16 | Lectura de 200 canales, ajustes y menú oculto (F-LOCK, TX 200/350/500); escritura tras verificar, solo con firmware original |
| Radtel **RT-4D** (DMR) | Flash SPI 115200 | Copia de seguridad completa de la flash (4 MB); editor DMR pendiente |
| Baofeng BF-A58S / UV-82III | Clonado Baofeng clásico | Experimental, solo lectura |

Añadir más: [docs/ANADIR_RADIO.md](docs/ANADIR_RADIO.md).

## Licencia

GPLv3 (ver [LICENSE](LICENSE)). Los mapas de memoria proceden del proyecto [CHIRP](https://github.com/kk7ds/chirp)
(GPLv3), usado como referencia; el código de radiokit es una reimplementación propia. El protocolo del RT-4D
se documentó a partir de [rt4d-cps](https://github.com/jcalado/rt4d-cps) sin copiar su código.

**Aviso**: transmitir fuera de las bandas autorizadas o sin la licencia necesaria es ilegal. Los Baofeng no están
homologados para PMR446. En una emergencia llama primero al 112.
