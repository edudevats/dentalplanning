"""Instrumentación opt-in de tiempos de respuesta.

Se activa con la variable de entorno PROFILE_REQUESTS=1 (o true/yes). Apagada
(por defecto) no registra ningún listener ni añade overhead. Encendida, por cada
request escribe una línea en el log:

    [PERF] GET /api/v1/reportes/trimestral?year=2026 -> 200 | 842.1 ms wall | 49 queries | 791.3 ms sql

Pensada para medir antes/después en PythonAnywhere: activar la variable, pegarle
al endpoint lento y comparar `ms wall` / `ms sql` antes y después de aplicar la
migración de índices.

Opcional: PROFILE_SLOW_MS=200 para loguear solo requests por encima de N ms.
"""
import os
import time
import logging

from flask import g, request, has_request_context
from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger("perf")


def _enabled():
    return str(os.getenv("PROFILE_REQUESTS", "")).lower() in ("1", "true", "yes")


def init_profiling(app):
    if not _enabled():
        return

    slow_ms = float(os.getenv("PROFILE_SLOW_MS", "0"))

    # ── Conteo y tiempo de cada query SQL, acumulado en el contexto del request ──
    @event.listens_for(Engine, "before_cursor_execute")
    def _before_cursor(conn, cursor, statement, parameters, context, executemany):
        context._perf_start = time.perf_counter()

    @event.listens_for(Engine, "after_cursor_execute")
    def _after_cursor(conn, cursor, statement, parameters, context, executemany):
        if not has_request_context():
            return
        dur = time.perf_counter() - getattr(context, "_perf_start", time.perf_counter())
        g._perf_q_count = getattr(g, "_perf_q_count", 0) + 1
        g._perf_q_time = getattr(g, "_perf_q_time", 0.0) + dur

    # ── Tiempo total (wall) del request ──
    @app.before_request
    def _start_timer():
        g._perf_wall_start = time.perf_counter()

    @app.after_request
    def _log_perf(response):
        start = getattr(g, "_perf_wall_start", None)
        if start is None:
            return response
        wall_ms = (time.perf_counter() - start) * 1000.0
        q_count = getattr(g, "_perf_q_count", 0)
        q_time_ms = getattr(g, "_perf_q_time", 0.0) * 1000.0
        if wall_ms >= slow_ms:
            logger.warning(
                "[PERF] %s %s -> %s | %.1f ms wall | %d queries | %.1f ms sql",
                request.method,
                request.full_path.rstrip("?"),
                response.status_code,
                wall_ms,
                q_count,
                q_time_ms,
            )
        return response

    app.logger.info("PROFILE_REQUESTS activo: registrando tiempos por request")
