"""radiokit - lectura, edicion y programacion segura de walkies (Baofeng, Radtel y similares).

Capas:
  core.transport  -> acceso al puerto serie (Win32 nativo / pyserial) o emulador
  protocols.*     -> familias de protocolo de clonado (handshake, lectura/escritura de bloques)
  drivers.*       -> un modelo concreto: mapa de memoria, canales, ajustes, zonas protegidas
  core.service    -> operaciones seguras: detectar, leer, escribir con copia y verificacion
  web             -> interfaz web local
"""
__version__ = "0.1.0"
