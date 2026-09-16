"""
keep_alive.py
-------------
Servidor Flask minimo para que servicios como UptimeRobot puedan hacer
ping al bot y evitar que hostings tipo Render lo duerman por inactividad.
"""

import os
import logging
from threading import Thread

from flask import Flask

# Silenciamos los logs de Flask/werkzeug para no ensuciar la consola del bot
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask("keep_alive")


@app.route("/")
def home():
    return "The bot is alive and running.", 200


@app.route("/status")
def status():
    return {"status": "online"}, 200


def run():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    """Levanta el servidor Flask en un hilo aparte para no bloquear el bot."""
    t = Thread(target=run)
    t.daemon = True
    t.start()
