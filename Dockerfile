FROM python:3.8

# the context should be the parent directory of the Dockerfile(..)
ENV PYTHONUNBUFFERED=1
# to make the uv environment across all folders
ENV UV_PROJECT_ENVIRONMENT="/usr/local/"

# use uv
COPY --from=ghcr.io/astral-sh/uv:0.7.6 /uv /uvx /bin/
# System deps:
RUN apt update && apt install ffmpeg libsm6 libxext6  -y

# Updated WORKDIR
WORKDIR /usr/src/app

# Install dependencies
COPY ./fluxghost /usr/src/app/build/fluxghost
RUN cd /usr/src/app/build/fluxghost && uv sync --locked --no-dev -n

COPY ./fluxclient-dev /usr/src/app/build/fluxclient-dev
COPY ./fluxsvg /usr/src/app/build/fluxsvg
COPY ./beamify /usr/src/app/build/beamify

RUN cd /usr/src/app/build/beamify/python && uv run setup.py install
RUN cd /usr/src/app/build/fluxsvg && uv run setup.py install
# use python3 to run due to fluxclient-dev has no project
RUN cd /usr/src/app/build/fluxclient-dev && python3 setup.py install

# RUN command to remove the build directory, path updated
RUN rm -rf /usr/src/app/build

EXPOSE 8000
