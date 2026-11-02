# Tesserae + paperlesspaper: the official Tesserae image with this repository's
# plugins and device kind added. Home Assistant builds it with only this folder
# as the build context, so the rest of the repository is fetched as a tarball
# of the commit in build.yaml.
ARG BUILD_FROM=ghcr.io/dmellok/tesserae:0.480.0
FROM ${BUILD_FROM}

ARG WIDGETS_REF=8832e6bc2fd6973c8724bc10f80d2cff69d98a79
ARG WIDGETS_REPO=Emacee/Tesserae-Paperlesspaper

USER root
COPY add_widgets.py /tmp/add_widgets.py
RUN python3 /tmp/add_widgets.py "${WIDGETS_REPO}" "${WIDGETS_REF}" && rm /tmp/add_widgets.py

# Tesserae 0.480's paintings page says a widget's settings are under
# "Settings › Plugins", a tab it calls "Widgets". Name it as the menu does;
# a later template without that text is left as it is.
RUN f=/app/templates/artwork.html; \
    if [ -f "$f" ]; then sed -i 's/Settings › Plugins › /Settings › Widgets › /' "$f"; fi

LABEL io.hass.type="addon" io.hass.arch="aarch64|amd64"
