from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt

from .config import load_effective_config
from .db import set_metadata
from .events import EventProcessor
from .network_monitor import NetworkMonitor, remember_ircddb_user_from_line

logging.basicConfig(level=os.getenv("PP5CI_HOTSPOT_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("pp5ci-hotspot-collector")


class Collector:
    def __init__(self) -> None:
        cfg = load_effective_config()
        self.host = os.getenv("PP5CI_HOTSPOT_MQTT_HOST", str(cfg["mqtt_host"]))
        self.port = int(os.getenv("PP5CI_HOTSPOT_MQTT_PORT", str(cfg["mqtt_port"])))
        self.topic = os.getenv("PP5CI_HOTSPOT_MQTT_TOPIC", f"{cfg['mqtt_name']}/json")
        self.processor = EventProcessor()
        self.network_monitor = NetworkMonitor()
        self.stop_event = threading.Event()
        self.journal_process: subprocess.Popen[str] | None = None
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="pp5ci-hotspot-collector",
            clean_session=True,
        )
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties) -> None:
        LOG.info("MQTT conectado a %s:%s; assinando %s", self.host, self.port, self.topic)
        set_metadata("mqtt_connected", "1")
        set_metadata("mqtt_topic", self.topic)
        client.subscribe(self.topic, qos=1)

    def on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, reason_code, properties) -> None:
        LOG.warning("MQTT desconectado: %s", reason_code)
        set_metadata("mqtt_connected", "0")

    def on_message(self, client: mqtt.Client, userdata, message: mqtt.MQTTMessage) -> None:
        if self.processor.process(message.payload):
            set_metadata("last_mqtt_event_at", str(int(time.time())))

    def seed_ircddb_cache(self) -> None:
        try:
            result = subprocess.run(
                [
                    "journalctl",
                    "-u", "polar-dstargateway.service",
                    "-n", "2000",
                    "-o", "cat",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            loaded = 0
            for line in result.stdout.splitlines():
                if remember_ircddb_user_from_line(line):
                    loaded += 1
            if loaded:
                LOG.info("Cache ircDDB inicializado com %s registros USER recentes", loaded)
        except Exception as exc:
            LOG.debug("Não foi possível pré-carregar cache ircDDB: %s", exc)

    def journal_loop(self) -> None:
        command = [
            "journalctl",
            "-u", "pp5ci-hotspot-host.service",
            "-u", "polar-dstargateway.service",
            "-f",
            "-n", "0",
            "-o", "cat",
            "--no-pager",
        ]
        try:
            self.journal_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            LOG.info("Enriquecimento journald ativo para URCALL/slow text e Callsign Routing G2")
            assert self.journal_process.stdout is not None
            for line in self.journal_process.stdout:
                if self.stop_event.is_set():
                    break
                self.processor.process_journal_line(line.rstrip("\n"))
        except Exception as exc:
            LOG.warning("Enriquecimento journald indisponível: %s", exc)
        finally:
            process = self.journal_process
            self.journal_process = None
            if process and process.poll() is None:
                process.terminate()

    def network_loop(self) -> None:
        LOG.info("Monitor de rede ativo: reflector ou gateway direto via TCP (sem ICMP) + baseline Internet")
        self.network_monitor.run(self.stop_event)

    def stop(self, *_args) -> None:
        self.stop_event.set()
        process = self.journal_process
        if process and process.poll() is None:
            process.terminate()
        try:
            self.client.disconnect()
        except Exception:
            pass

    def run(self) -> int:
        self.processor.reset_runtime()
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        self.seed_ircddb_cache()

        journal_thread = threading.Thread(target=self.journal_loop, name="polar-journal", daemon=True)
        journal_thread.start()

        network_thread = threading.Thread(target=self.network_loop, name="polar-network", daemon=True)
        network_thread.start()

        while not self.stop_event.is_set():
            try:
                LOG.info("Conectando ao MQTT %s:%s", self.host, self.port)
                self.client.connect(self.host, self.port, keepalive=60)
                self.client.loop_forever(retry_first_connection=True)
            except Exception as exc:
                LOG.error("Falha MQTT: %s", exc)
                set_metadata("mqtt_connected", "0")
                if self.stop_event.wait(3):
                    break
        return 0


def main() -> int:
    return Collector().run()


if __name__ == "__main__":
    sys.exit(main())
