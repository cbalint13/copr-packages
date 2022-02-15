FROM fedora:latest

RUN dnf install -y git rpmdevtools rpm-build

RUN dnf install -y copr-cli python3-copr

COPY update-copr-pkgs.py /update-copr-pkgs.py

ARG copr_login copr_token

RUN mkdir /root/.config; \
    echo "[copr-cli]" > /root/.config/copr; \
    echo "username = rezso" >> /root/.config/copr; \
    echo "login = ${copr_login}" >> /root/.config/copr; \
    echo "token = ${copr_token}" >> /root/.config/copr; \
    echo "copr_url = https://copr.fedorainfracloud.org" >> /root/.config/copr;

RUN python3 -u update-copr-pkgs.py HDL --min-days 7 --fork fedora-rawhide fedora-36

RUN python3 -u update-copr-pkgs.py VLSI --min-days 7 --fork fedora-rawhide fedora-36

RUN python3 -u update-copr-pkgs.py SDR --min-days 7 --fork fedora-rawhide fedora-36

RUN python3 -u update-copr-pkgs.py ML --min-days 7 --cuda-ver-maj 11 --cuda-ver-min 6 --cuda-builds 1 --fork fedora-rawhide fedora-36
