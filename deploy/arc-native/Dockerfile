FROM ghcr.io/actions/actions-runner:2.338.1 AS runner
FROM quality-gate-hcu-test:nonroot-20261106-v1
LABEL ci.hygon.cn.native-accept="20261107"
USER 0:0
COPY --from=runner --chown=1001:1001 /home/runner /home/runner
ENV HOME=/home/runner
WORKDIR /home/runner
USER 1001:1001
RUN /home/runner/bin/Runner.Listener --version
ENTRYPOINT []
CMD ["/home/runner/run.sh"]
