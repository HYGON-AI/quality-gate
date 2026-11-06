FROM 42.228.13.241:5000/dcu/admin/base/pytorch@sha256:07c285c51837d76fbcc73b771b1a95ecf2d8b71203e5feadb3cb9cb12b5d3f4d
USER 0:0
RUN groupadd --gid 1001 ci-runner && useradd --uid 1001 --gid 1001 --create-home --home-dir /home/ci-runner --shell /bin/bash --password "!" ci-runner
ENV HOME=/home/ci-runner
WORKDIR /home/ci-runner
USER 1001:1001
