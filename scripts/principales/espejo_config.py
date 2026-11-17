"""Ajustes de la misión con espejo (config/mission_espejo.json), con qué hace cada uno.

Cada campo de MirrorConfig es una clave del JSON. El valor de aquí es el de por defecto; el
JSON lo pisa. En el laboratorio se cambian en el JSON (o con `python lab.py` -> c), no aquí.
Los ajustes de cada dron (config/mision_dron<N>.json, p. ej. la integral inicial del PID) se
aplican encima con ajustes_dron (`--dron N`).

También se usan: config/mission_tags.json (MissionConfig en mission_tags.py: acciones de cada
tag, tamaño del tag, detección) y config/flight.json (FlightConfig en first_flight.py:
seguridad, despegue, flip).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, fields
from pathlib import Path

from first_flight import ROOT


@dataclass
class MirrorConfig:
    espejo: str = "v"  # cómo se voltea la imagen (ver test_tags.py --espejo)
    quieto: bool = False  # True: no avanza, espera a que haya un tag debajo
    cruise_alt_cm: float = 100.0  # más alto = ve más piso debajo (a 100 cm, vista a −10.3°: ~20 cm adelante, ~60 atrás, ±52 de lado)
    advance_fb: int = 15  # rc 15 ≈ 16–20 cm/s (calibración real)
    advance_timeout_s: float = 12.0  # sin ver tag debajo por esto: fin (sin vista al frente)
    advance_lr: int = 0  # rc lateral fijo al avanzar sin tag, para compensar si el dron se va de un lado
    # (se va a la derecha: negativo, p. ej. -10)
    alinear_bordes: bool = False  # True: girar para alinearse con los bordes del tag (supone tags derechos)
    ignorar_inicio: bool = True  # ignorar el tag que se ve mientras despega (el de inicio)
    inicio_alt_cm: float = 70.0  # ...solo el visto abajo de esta altura, aún sobre el punto de despegue
    quieto_timeout_s: float = 20.0
    center_kp: float = 0.6
    center_kd: float = 1.0  # rc por cm/s: frena según qué tan rápido se acerca (real 9-nov: oscilaba ±15–20 cm)
    center_min: int = 10
    center_max: int = 15
    center_dead: float = 5.0  # mando calculado menor que esto: no mandar nada (el Tello frena solo)
    center_tol_cm: float = 6.0
    center_vel_tol: float = 4.0  # cm/s: para ejecutar, además de cerca, casi quieto
    centrar_max_s: float = 8.0  # si no se estabiliza encima en este tiempo, ejecuta igual (el punto es por el tag)
    rot_kp: float = 1.0
    rot_tol_deg: float = 4.0
    window: int = 7  # mediana de N frames
    # sostener la posición con el piso visto por el espejo (11-nov: los dos Tellos se iban solos
    # a la derecha, 4–12 cm/s, y el primer tag quedaba en la orilla de la vista o fuera)
    sostener_piso: bool = True  # quieto y subiendo: volver al punto de despegue; avanzando: sostener la línea
    piso_calidad: float = 0.1  # calidad mínima de la correlación de fase para creerle
    piso_kp: float = 0.5  # rc por cm de distancia a donde debería estar
    piso_kd: float = 0.8  # rc por cm/s que se está yendo
    piso_ki: float = 0.15  # rc por cm·s: junta el empuje que hace falta contra una deriva constante
    # (sin esto, con el Tello 7 se quedaba ~26 cm corrido: el PD solo empuja si hay error)
    piso_i_max: float = 15.0  # tope de lo juntado, en rc (que no se pase de largo)
    # integral al despegar, en rc (lado, adelante): + si el dron se va solo a la derecha / adelante.
    # Va en config/mision_dron<N>.json de cada dron. OJO: si el dron ya no deriva, empuja de más al
    # principio hasta que la integral se corrige sola (unos segundos)
    piso_i_inicial: tuple = (0.0, 0.0)
    # ejecutando un tag (giros, pausa): sostenerse sobre él con su posición (11-nov: en un giro de
    # 90° se corría 26–42 cm), y que el tramo nuevo pase por el tag y no por donde quedó el dron
    sostener_tag: bool = True
    # rc máximo para quedarse sobre el tag mientras lo ejecuta. Con 20 (por si al girar no le
    # alcanzaba contra los ~12 cm/s que se corre) fue peor en las pistas al azar: 76 % de los puntos
    # contra 86 % con 15 (16-nov)
    sostener_tag_max: int = 15
    # el tag recién ejecutado se sigue cuadro por cuadro: un tag con su número a menos de esto de
    # donde debe estar (su última posición, corrida con lo que avanzó el dron) es el mismo y se
    # ignora; en otra parte es OTRO tag y se ejecuta. Antes se ignoraba por número y se perdían los
    # tags repetidos y los que se vuelven a visitar tras un 180° (pistas al azar, 12-nov)
    mismo_tag_cm: float = 35.0  # la mitad de la separación mínima entre tags (70 cm)
    # un tag ya ejecutado antes (no el último) solo cuenta si está en la línea del tramo: adelante y a
    # menos de esto de lado (al regresar tras un 180° está enfrente; uno viejo a un lado no se toma)
    pasillo_cm: float = 40.0
    piso_min: int = 10
    piso_max: int = 20
    piso_dead: float = 4.0  # mando menor que esto: nada
    # seguro, por si en el dron real la medida sale al revés y la corrección empuja hacia afuera:
    # apagarla si, corrigiendo, se aleja piso_alejandose_cm en 1.5 s (al revés, deriva y corrección
    # suman >30 cm/s) o si se pasa de piso_limite_cm. No cuenta lo que se fue al despegar: ahí el
    # Tello ignora el rc (el Tello 7 se va >80 cm)
    piso_alejandose_cm: float = 35.0
    piso_limite_cm: float = 150.0
    buscar_s: float = 4.0  # tag perdido al centrarse: buscarlo donde debe estar esto, luego seguir avanzando
    vista_adelante_deg: float = 0.0  # inclinación del espejo: medirla con test_tags.py --espejo
    vista_lado_deg: float = 0.0

    @classmethod
    def load(cls, path: Path) -> MirrorConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


def ajustes_dron(ecfg: "MirrorConfig", dron: str | None) -> list[str]:
    """Aplica config/mision_dron<N>.json (lo que cambia en la misión con ese dron, p. ej. la
    integral inicial). Devuelve lo que cambió."""
    if not dron:
        return []
    path = ROOT / "config" / f"mision_dron{dron}.json"
    if not path.exists():
        raise SystemExit(f"no existe {path.relative_to(ROOT)}")
    data = {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}
    unknown = set(data) - {f.name for f in fields(MirrorConfig)}
    if unknown:
        raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
    for k, v in data.items():
        setattr(ecfg, k, tuple(v) if isinstance(v, list) else v)
    return [f"{k}={v}" for k, v in data.items()]
