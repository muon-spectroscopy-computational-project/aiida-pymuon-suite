# Runtime image: AiiDA + pymuon-suite + this plugin, ready to run the UEP pipeline.

ARG AIIDA_BASE_IMAGE=ghcr.io/aiidateam/aiida-core-base:edge
FROM ${AIIDA_BASE_IMAGE}

LABEL org.opencontainers.image.title="aiida-pymuon-suite" \
      org.opencontainers.image.description="AiiDA plugin wrapping the pymuon-suite UEP muon site calculation tools" \
      org.opencontainers.image.source="https://github.com/muon-spectroscopy-computational-project/aiida-pymuon-suite" \
      org.opencontainers.image.licenses="MIT"

USER root
COPY --chown=${SYSTEM_UID}:${SYSTEM_GID} . /opt/aiida-pymuon-suite

RUN PYTHONUSERBASE=/home/aiida/.local pip install --no-cache-dir --user /opt/aiida-pymuon-suite

USER ${SYSTEM_USER}

# Verify as the runtime user: the CalcJob submit scripts invoke these by name,
# so they must resolve on PATH, and the AiiDA entry points must register.
RUN pm-muairss --help > /dev/null \
    && pm-uep-opt --help > /dev/null \
    && verdi plugin list aiida.calculations | grep pymuon
