# Tesserae + paperlesspaper: the official Tesserae image with this repository's
# plugins and device kind added. Home Assistant builds it with only this folder
# as the build context, so the rest of the repository is fetched as a tarball
# of the commit in build.yaml.
ARG BUILD_FROM=ghcr.io/dmellok/tesserae:0.480.0
FROM ${BUILD_FROM}

ARG WIDGETS_REF=ad7e2ba26e101fa9fbb8248146d5efc8d31c096e
ARG WIDGETS_REPO=Emacee/Tesserae-Paperlesspaper

USER root
COPY add_widgets.py /tmp/add_widgets.py
RUN python3 /tmp/add_widgets.py "${WIDGETS_REPO}" "${WIDGETS_REF}" && rm /tmp/add_widgets.py

LABEL io.hass.type="addon" io.hass.arch="aarch64|amd64"
