# Tesserae + paperlesspaper: the official Tesserae image with this repository's
# plugins and device kind added. Home Assistant builds it with only this folder
# as the build context, so the rest of the repository is fetched as a tarball
# of the tag in build.yaml.
ARG BUILD_FROM=ghcr.io/dmellok/tesserae:0.480.0
FROM ${BUILD_FROM}

ARG WIDGETS_REF=v0.1.0
ARG WIDGETS_REPO=Emacee/Tesserae-Paperlesspaper

USER root
COPY add_widgets.py /tmp/add_widgets.py
RUN python3 /tmp/add_widgets.py "${WIDGETS_REPO}" "${WIDGETS_REF}" && rm /tmp/add_widgets.py

LABEL io.hass.type="addon" io.hass.arch="aarch64|amd64"
