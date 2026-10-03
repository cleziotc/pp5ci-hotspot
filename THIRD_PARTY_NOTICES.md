# Third-party notices and credits

PP5CI Hotspot is an integration project. It does not claim authorship or ownership of the upstream projects listed here.

## MMDVMHost

- Project: `g4klx/MMDVM-Host`
- Primary author/maintainer: **Jonathan Naylor, G4KLX**
- Upstream license: **GNU GPL v2**
- Role in PP5CI Hotspot: host process that communicates with the MMDVM modem and the D-STAR gateway.
- The installer checks out commit `590c531391dfd3146073afbc3956f70d42c62a46`.
- `patches/MMDVMHost-live-rssi.patch` modifies upstream MMDVMHost behavior for live D-STAR RSSI. The patch follows the license obligations of the GPL-covered upstream code.

## DStarGateway

- Project: `F4FXL/DStarGateway`
- Maintainer/author: **Geoffrey Merck, F4FXL / KC3FRA**
- Upstream license: **GNU GPL v2**
- DStarGateway itself credits:
  - **Jonathan Naylor, G4KLX**, original author of ircDDBGateway;
  - **Thomas A. Early, N7TAE**, for code reused from smart-group-server;
  - **Geoffrey Merck, F4FXL / KC3FRA**.
- Role in PP5CI Hotspot: D-STAR gateway, reflector protocols and callsign routing.
- The installer checks out commit `0c1dbb5` from the v0.7 line.

## MMDVM_HS firmware

- Project: `juribeparada/MMDVM_HS`
- Firmware lineage: based on Jonathan Naylor G4KLX's MMDVM.
- Important upstream copyright contributors include **Jonathan Naylor, G4KLX** and **Andy Uribe, CA6JAU**.
- Upstream README states GNU GPL v2 and amateur/educational use.
- Role in PP5CI Hotspot: firmware commonly used by MMDVM_HS personal hotspot boards.

PP5CI Hotspot does not redistribute a firmware binary; the operator's MMDVM board is expected to contain compatible firmware.

## Pi-Star host lists

The project can download DPlus, DExtra, DCS and XLX host lists from `www.pistar.uk`. Those lists and the Pi-Star project remain the work of their respective maintainers.

## ircDDB / QuadNet

The default D-STAR callsign-routing configuration uses the QuadNet ircDDB endpoint `ircv4.openquad.net`. PP5CI Hotspot is not affiliated with, and does not claim ownership of, the ircDDB or QuadNet infrastructure.

## Mosquitto

Eclipse Mosquitto is used as the local MQTT broker. It is installed from the operating system package repository and is not vendored into this repository.

## Nginx

Nginx is used as the local HTTP server and reverse proxy. It is installed from the operating system package repository and is not vendored into this repository.

## Python dependencies

Runtime Python dependencies are declared in `backend/requirements.txt`, including FastAPI, Uvicorn, paho-mqtt and python-multipart. Each dependency keeps its own copyright and license.

## JavaScript dependencies

Frontend dependencies are declared in `frontend/package.json` and locked in `frontend/package-lock.json`, including React, Vite, ECharts, Lucide and React Router. Each dependency keeps its own copyright and license.

## Linux, Debian, Ubuntu and Raspberry Pi

Linux and the distributions/platforms supported by the installers are independent projects and trademarks of their respective owners.

## D-STAR

D-STAR is a digital voice/data protocol. Product and project names used in this repository are for technical identification; no affiliation or endorsement is implied.

## PP5CI Hotspot original code

The integration code, dashboard, API, installer orchestration and project-specific documentation are maintained in this repository. See `LICENSE` for the licensing status of original PP5CI Hotspot code.
