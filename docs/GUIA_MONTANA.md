# Guía de uso del walkie en montaña

Guía práctica para salidas por el Pirineo, Andorra y Ordesa con las radios programadas con el plan de
[CANALES_ESPANA.md](CANALES_ESPANA.md) (Baofeng UV-S Plus / UV-5R, Quansheng UV-K5). Lo primero en una
emergencia sigue siendo **llamar al 112**; la radio es el complemento cuando no hay cobertura.

## 1. Antes de salir

- [ ] **Batería cargada** y, en invierno, una de repuesto o power bank. El frío reduce mucho la autonomía:
      lleva la radio dentro de la chaqueta y no en el exterior de la mochila.
- [ ] **Antena bien enroscada** y sin dañar.
- [ ] **Prueba entre radios** en el canal de grupo antes de empezar a caminar (voz, volumen, subtono).
- [ ] **Teclado bloqueado** (mantener `#` en las Baofeng): evita cambios de canal por roces en la mochila.
- [ ] **Volumen a dos tercios** y comprobado: la rueda de volumen no se bloquea y se mueve sola.
- [ ] **Plan de comunicaciones** (apartado 2) acordado y escrito en un papel o en el móvil de cada uno.
- [ ] **Ruta comunicada** a alguien que se queda en casa, y la app **My112** instalada (envía tu posición).
- [ ] Copia de la configuración de la radio hecha con radiokit (por si hay que restaurarla).

## 2. Plan de comunicaciones (método PACE)

Cuatro niveles, de más cómodo a más básico. Cada miembro del grupo debe saber cuándo pasar al siguiente.

| Nivel | Qué usar | Cuándo |
|---|---|---|
| **P** · Principal | Canal de grupo: un PMR (1-16) con un subtono propio poco habitual, igual en todas las radios del grupo | Uso normal |
| **A** · Alternativo | Otro PMR acordado de antemano | El principal está saturado o hay interferencias. Se acuerda una **palabra clave** para cambiar sin dar explicaciones: al oírla, todos pasan al alternativo |
| **C** · Contingencia | **112** por teléfono · **SOS-Montaña** (canal 20, Ordesa/Pirineo aragonés) · **Canal 7-7** (canal 21) | Accidente o persona perdida. Ver apartado 5 |
| **E** · Emergencia sin radio | Silbato, luz, señales al helicóptero (apartado 6) | Sin batería, sin cobertura o para que os localicen |

**Horarios de contacto**: si el grupo se separa o hay alguien esperando en el refugio, acordad ventanas
fijas (por ejemplo, 5 minutos a cada hora en punto) en lugar de llevar la radio siempre encendida. Ahorra
batería y da una regla clara: **si se pierden dos contactos seguidos, se activa el plan de contingencia**.

## 3. Cómo llega la señal en montaña

Estas radios funcionan **en línea de vista**: si una antena "ve" a la otra, hay comunicación; si hay una
montaña o una cresta en medio, normalmente no.

- **Gana altura**: subir a un collado o a una loma suele resolver más que cualquier antena o potencia.
  En un valle encajado, la señal no sale del valle.
- **VHF (146 MHz, SOS-Montaña) llega mejor que UHF (446 MHz, PMR)** en terreno accidentado y con bosque:
  rodea algo mejor el relieve y la vegetación le afecta menos. El PMR es de corto alcance (0,5 W y UHF).
- **El bosque húmedo y la vegetación densa** recortan mucho el alcance, más cuanto más alta la frecuencia.
- **El agua, la nieve y la roca desnuda** reflejan la señal y a veces la llevan más lejos de lo esperado.
- **Antena vertical**: con la radio tumbada o la antena horizontal se pierde mucha señal. Llévala en el
  tirante de la mochila, a la altura del pecho, y no la tapes con el cuerpo.
- **Relevo**: si dos grupos no se oyen, alguien en un punto intermedio con visión de ambos puede repetir
  los mensajes de viva voz.

## 4. Cómo hablar por radio

1. Escucha antes de transmitir: no pises a nadie.
2. Pulsa el PTT, **espera un segundo**, habla, **espera un segundo** y suelta (si no, se cortan el principio
   y el final).
3. Micrófono a 10-15 cm de la boca, protegido del viento. Frases cortas.
4. Llamada: "*[a quién]*, aquí *[quién]*" → respuesta → mensaje → "cambio". Al terminar: "corto".
5. No uses VOX en montaña: el viento abre la transmisión y bloquea el canal.
6. Potencia baja para hablar con el grupo cercano (ahorra batería); alta solo cuando haga falta alcance.

## 5. Emergencia: qué decir y dónde

**Orden**: 1) 112 por teléfono (o My112) → 2) SOS-Montaña (canal 20) si estás en la zona de los refugios
del Pirineo aragonés → 3) Canal 7-7 (canal 21) para pedir ayuda a grupos cercanos.

Mensaje de socorro, despacio y repitiéndolo si no hay respuesta:

> **SOCORRO, SOCORRO, SOCORRO**, aquí *[nombre/grupo]*.
> **Qué** ha pasado · **Dónde** estamos (lugar, coordenadas de la app, altitud) · **Cuántos** somos y
> **cuántos heridos** · **Estado** de los heridos · **Qué necesitamos** · **Tiempo** (visibilidad, viento).

- Si un refugio responde, **sigue sus instrucciones** y mantén la radio encendida en ese canal.
- Ahorra batería entre transmisiones: acordad con quien os atiende cada cuánto volver a llamar.
- En Cataluña: si llegas a un refugio con **código (REF-x-xxxx)** o a un **pal de cobertura 112**, da ese
  código al 112: os localizan al instante. Algunos refugios libres tienen **pulsador de emergencia** con
  conexión directa a Bombers.
- SOS-Montaña es una frecuencia de Protección Civil: sin licencia de radioaficionado, úsala **solo en
  emergencia real**. Nunca transmitas en los canales marítimos (22-29).

## 6. Señales sin radio

- **Señal internacional de socorro en montaña**: **6 señales por minuto** (pitidos, destellos o gritos),
  un minuto de pausa y repetir. La respuesta de quien te ha oído son **3 señales por minuto**.
- **Al helicóptero**: los **dos brazos en alto formando una Y** = *sí, necesitamos ayuda*; **un brazo arriba
  y otro abajo** formando una N = *no necesitamos ayuda*. No hagas gestos ambiguos como saludar.
- De día, algo de color vivo extendido en el suelo; de noche, la linterna o el frontal.

## 7. Ajustes recomendados de la radio

| Ajuste | Valor | Motivo |
|---|---|---|
| Bloqueo automático de teclado | Activado | Evita cambios de canal en la mochila |
| Tiempo máximo de transmisión (TOT) | 60 s | Corta transmisiones accidentales que bloquean el canal |
| VOX | Off | El viento la dispara |
| Squelch | 3-5 | Silencio sin ruido de fondo; en señal muy débil, usar MONI para abrirlo |
| Pantalla | Nombre del canal | Sabes de un vistazo dónde estás (SOSMONT, PMR 7-7...) |
| Doble escucha (TDR) | Canal de grupo + 7-7 | Escuchas a tu grupo y a otros grupos de montaña a la vez |
| Pitido Roger / LEDs | A tu gusto | Desactivarlos ahorra algo de batería |

Todos se cambian desde radiokit (pestaña **Ajustes**) o desde el menú de la radio.

## Referencias

- Plan de canales y fuentes: [CANALES_ESPANA.md](CANALES_ESPANA.md) (FAM, Montaña Segura, 112 Catalunya).
- *The Guerrilla's Guide to the Baofeng Radio* (libro de referencia, no incluido en el repositorio):
  ideas del plan PACE, horarios de contacto y propagación en el terreno, adaptadas aquí al uso civil en montaña.
