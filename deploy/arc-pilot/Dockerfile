FROM ghcr.io/actions/actions-runner@sha256:e275409999c37162649aa050ca573f03eab2eabcb3a1e7fcc47548de6b4f9690
USER root
COPY kubectl /usr/local/bin/kubectl
COPY arc-volcano-pilot.py /opt/hygon/arc-volcano-pilot.py
RUN chmod 0555 /usr/local/bin/kubectl /opt/hygon/arc-volcano-pilot.py
USER runner
