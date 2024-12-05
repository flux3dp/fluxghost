# This script is used to update the dependencies of the docker image
# It need the dependencies to be located in the same directory as fluxghost
cd $(dirname $0)
cd ../..
docker run -v ./beamify:/code/build/beamify \
    -v ./fluxsvg:/code/build/fluxsvg \
    -v ./fluxclient-dev:/code/build/fluxclient-dev \
    fluxghost bash -c "
    cd /code/build/beamify/python && python3 setup.py install && \
    cd /code/build/fluxsvg && python3 setup.py install && \
    cd /code/build/fluxclient-dev && python3 setup.py install"

